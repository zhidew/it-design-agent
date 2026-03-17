import asyncio
from contextlib import asynccontextmanager, contextmanager
import datetime
import json
import os
import shutil
import sqlite3
import uuid
from pathlib import Path

import yaml

from graphs.builder import CHECKPOINT_DB_PATH, CHECKPOINTS_DIR, create_design_graph
from graphs.state import merge_artifacts
from models.events import dump_event, validate_event_payload
from services.log_service import get_run_log, save_run_log

BASE_DIR = Path(__file__).resolve().parent.parent.parent
PROJECTS_DIR = BASE_DIR / "projects"
AGENTS_DIR = BASE_DIR / "agents"
SKILLS_DIR = BASE_DIR / "skills"

RUN_STATUS_QUEUED = "queued"
RUN_STATUS_RUNNING = "running"
RUN_STATUS_WAITING_HUMAN = "waiting_human"
RUN_STATUS_SUCCESS = "success"
RUN_STATUS_FAILED = "failed"
STALE_RUNNING_TIMEOUT_SECONDS = int(os.getenv("ORCHESTRATOR_STALE_TIMEOUT_SECONDS", "180"))

jobs = {}
runtime_registry = {}
runtime_tasks = {}


@contextmanager
def _graph_for_state():
    CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver

        with SqliteSaver.from_conn_string(str(CHECKPOINT_DB_PATH)) as checkpointer:
            yield create_design_graph(checkpointer=checkpointer)
            return
    except Exception:
        from langgraph.checkpoint.memory import MemorySaver

        yield create_design_graph(checkpointer=MemorySaver())


@asynccontextmanager
async def _graph_for_run():
    CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        async with AsyncSqliteSaver.from_conn_string(str(CHECKPOINT_DB_PATH)) as checkpointer:
            yield create_design_graph(checkpointer=checkpointer)
            return
    except Exception:
        from langgraph.checkpoint.memory import MemorySaver

        yield create_design_graph(checkpointer=MemorySaver())


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _thread_id(project_id: str, version: str) -> str:
    return f"{project_id}_{version}"


def _graph_config(project_id: str, version: str, run_id: str | None = None) -> dict:
    config = {"configurable": {"thread_id": _thread_id(project_id, version), "version": version}}
    if run_id:
        config["configurable"]["run_id"] = run_id
    return config


def _new_event_id() -> str:
    return str(uuid.uuid4())


def _ensure_job(job_id: str) -> dict:
    existing = jobs.get(job_id)
    if existing:
        existing.setdefault("logs", [])
        existing.setdefault("events", [])
        existing.setdefault("subscribers", set())
        existing.setdefault("status", RUN_STATUS_QUEUED)
        return existing

    jobs[job_id] = {"status": RUN_STATUS_QUEUED, "logs": [], "events": [], "subscribers": set()}
    return jobs[job_id]


def _set_runtime_state(
    project_id: str,
    version: str,
    *,
    run_status: str,
    current_node: str | None = None,
    waiting_reason: str | None = None,
    can_resume: bool | None = None,
    job_id: str | None = None,
):
    thread_id = _thread_id(project_id, version)
    previous = runtime_registry.get(thread_id, {})
    runtime_registry[thread_id] = {
        **previous,
        "project_id": project_id,
        "version": version,
        "job_id": job_id or previous.get("job_id"),
        "run_status": run_status,
        "current_node": current_node,
        "waiting_reason": waiting_reason,
        "can_resume": (
            can_resume
            if can_resume is not None
            else run_status in {RUN_STATUS_WAITING_HUMAN, RUN_STATUS_FAILED}
        ),
        "updated_at": _now_iso(),
    }


def _has_active_runtime_task(thread_id: str) -> bool:
    task = runtime_tasks.get(thread_id)
    return bool(task and not task.done())


def _launch_runtime_task(thread_id: str, coro):
    # SMARTER CONCURRENCY: If there's an active task, check its status.
    # If it's already running, don't kill it unless we absolutely must (e.g. state was reset).
    # This avoids "generator didn't stop after athrow()" by not interrupting LangGraph's internal parallel nodes.
    existing_task = runtime_tasks.get(thread_id)
    if existing_task and not existing_task.done():
        print(f"[DEBUG] An active task already exists for thread {thread_id}. Reusing existing execution flow.")
        # We wrap the new coroutine to ensure it's closed/disposed if not used
        coro.close() 
        return existing_task

    task = asyncio.create_task(coro)
    runtime_tasks[thread_id] = task

    def _cleanup(completed_task):
        if runtime_tasks.get(thread_id) is completed_task:
            runtime_tasks.pop(thread_id, None)

    task.add_done_callback(_cleanup)
    return task


def _latest_project_timestamp(project_id: str, version: str) -> str:
    project_root = PROJECTS_DIR / project_id / version
    if not project_root.exists():
        return _now_iso()

    latest_mtime = None
    for path in project_root.rglob("*"):
        try:
            if path.is_file():
                path_mtime = path.stat().st_mtime
                latest_mtime = path_mtime if latest_mtime is None else max(latest_mtime, path_mtime)
        except OSError:
            continue

    if latest_mtime is None:
        return _now_iso()
    return datetime.datetime.fromtimestamp(latest_mtime, tz=datetime.timezone.utc).isoformat()


def _load_artifacts_from_disk(project_id: str, version: str) -> dict:
    artifacts = {}
    project_root = PROJECTS_DIR / project_id / version
    for dirname in ("baseline", "artifacts", "logs", "evidence", "release"):
        dir_path = project_root / dirname
        if not dir_path.exists():
            continue
        for item in dir_path.iterdir():
            if not item.is_file():
                continue
            try:
                artifacts[item.name] = item.read_text(encoding="utf-8")
            except Exception:
                artifacts[item.name] = "[Binary]"
    return artifacts


def _check_success(project_root: Path, file_patterns: list[str]) -> bool:
    for dirname in ("artifacts", "release"):
        target_dir = project_root / dirname
        if not target_dir.exists():
            continue
        for pattern in file_patterns:
            if any(target_dir.glob(pattern)):
                return True
    return False


def _build_legacy_task_queue(project_id: str, version: str) -> list[dict]:
    project_root = PROJECTS_DIR / project_id / version
    logs_dir = project_root / "logs"
    baseline_file = project_root / "baseline" / "requirements.json"

    active_agents = set()
    if baseline_file.exists():
        try:
            base_data = json.loads(baseline_file.read_text(encoding="utf-8"))
            active_agents = set(base_data.get("active_agents", []))
        except Exception:
            active_agents = set()

    if not active_agents:
        active_agents = {"planner", "architecture-mapping", "design-assembler", "validator"}

    validator_status = "todo"
    val_log_path = logs_dir / "validator.log"
    if val_log_path.exists():
        content = val_log_path.read_text(encoding="utf-8")
        validator_status = "success" if "[SUCCESS]" in content else "failed"

    full_map = [
        {"id": "0", "agent_type": "planner", "status": "success"},
        {"id": "1", "agent_type": "architecture-mapping", "status": "success" if _check_success(project_root, ["architecture.md"]) else "todo"},
        {"id": "2", "agent_type": "integration-design", "status": "success" if _check_success(project_root, ["integration-*", "asyncapi.yaml"]) else "todo"},
        {"id": "3", "agent_type": "data-design", "status": "success" if _check_success(project_root, ["schema.sql", "er.md"]) else "todo"},
        {"id": "4", "agent_type": "ddd-structure", "status": "success" if _check_success(project_root, ["ddd-structure.md"]) else "todo"},
        {"id": "5", "agent_type": "api-design", "status": "success" if _check_success(project_root, ["api-internal.yaml", "api-public.yaml"]) else "todo"},
        {"id": "6", "agent_type": "config-design", "status": "success" if _check_success(project_root, ["config-catalog.yaml"]) else "todo"},
        {"id": "7", "agent_type": "flow-design", "status": "success" if _check_success(project_root, ["sequence-*", "state-*"]) else "todo"},
        {"id": "8", "agent_type": "test-design", "status": "success" if _check_success(project_root, ["test-inputs.md", "coverage-map.json"]) else "todo"},
        {"id": "9", "agent_type": "ops-readiness", "status": "success" if _check_success(project_root, ["slo.yaml", "observability-spec.yaml"]) else "todo"},
        {"id": "10", "agent_type": "design-assembler", "status": "success" if _check_success(project_root, ["detailed-design.md"]) else "todo"},
        {"id": "11", "agent_type": "validator", "status": validator_status},
    ]
    return [task for task in full_map if task["agent_type"] in active_agents or task["agent_type"] == "planner"]


def _derive_run_status(task_queue: list[dict], human_intervention_required: bool) -> str:
    statuses = {task.get("status", "todo") for task in task_queue}
    if human_intervention_required or "waiting_human" in statuses:
        return RUN_STATUS_WAITING_HUMAN
    if "running" in statuses:
        return RUN_STATUS_RUNNING
    if "failed" in statuses:
        return RUN_STATUS_FAILED
    if task_queue and statuses.issubset({"success", "skipped"}):
        return RUN_STATUS_SUCCESS
    if task_queue and "todo" in statuses:
        return RUN_STATUS_QUEUED
    return RUN_STATUS_QUEUED


def _derive_current_node(task_queue: list[dict], raw_state: dict | None) -> str | None:
    if raw_state and raw_state.get("human_intervention_required") and raw_state.get("last_worker"):
        return raw_state.get("last_worker")
    if raw_state and raw_state.get("current_node"):
        return raw_state.get("current_node")
    running_task = next((task for task in task_queue if task.get("status") == "running"), None)
    if running_task:
        return running_task.get("agent_type")
    return raw_state.get("last_worker") if raw_state else None


def _parse_iso_timestamp(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    try:
        normalized_value = value.replace("Z", "+00:00")
        parsed = datetime.datetime.fromisoformat(normalized_value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.timezone.utc)
        return parsed.astimezone(datetime.timezone.utc)
    except ValueError:
        return None


def _normalize_state(project_id: str, version: str, raw_state: dict | None, runtime: dict | None = None) -> dict | None:
    runtime = runtime if runtime is not None else runtime_registry.get(_thread_id(project_id, version), {})
    if not raw_state and not runtime:
        return None

    state = dict(raw_state or {})
    task_queue = state.get("task_queue") or []
    if not task_queue:
        task_queue = _build_legacy_task_queue(project_id, version)
    history = state.get("history") or []
    messages = state.get("messages") or []
    artifacts = merge_artifacts(_load_artifacts_from_disk(project_id, version), state.get("artifacts") or {})
    human_intervention_required = bool(state.get("human_intervention_required", False))

    derived_run_status = _derive_run_status(task_queue, human_intervention_required)
    run_status = runtime.get("run_status") or derived_run_status
    current_node = runtime.get("current_node")
    if current_node is None:
        current_node = _derive_current_node(task_queue, state)

    waiting_reason = runtime.get("waiting_reason")
    if waiting_reason is None:
        waiting_reason = state.get("waiting_reason")
    if waiting_reason is None and run_status == RUN_STATUS_WAITING_HUMAN:
        waiting_reason = "human_intervention_required"

    normalized_updated_at = runtime.get("updated_at") or state.get("updated_at") or _latest_project_timestamp(project_id, version)
    stale_running_detected = False
    runtime_thread_id = _thread_id(project_id, version)
    runtime_missing_or_inactive = not runtime or not _has_active_runtime_task(runtime_thread_id)
    if runtime_missing_or_inactive and run_status == RUN_STATUS_RUNNING:
        updated_at_dt = _parse_iso_timestamp(normalized_updated_at)
        if updated_at_dt is not None:
            age_seconds = (datetime.datetime.now(datetime.timezone.utc) - updated_at_dt).total_seconds()
            if age_seconds >= STALE_RUNNING_TIMEOUT_SECONDS:
                stale_running_detected = True

    normalized_task_queue = list(task_queue)
    if stale_running_detected:
        failed_queue = []
        for task in normalized_task_queue:
            if task.get("status") == "running":
                failed_queue.append({**task, "status": "failed"})
            else:
                failed_queue.append(task)
        normalized_task_queue = failed_queue
        run_status = RUN_STATUS_FAILED
        human_intervention_required = False
        current_node = current_node or _derive_current_node(normalized_task_queue, state)
        stale_node = current_node or "current node"
        waiting_reason = (
            f"Execution appears stalled at {stale_node}. "
            "No active orchestrator runtime task was found for this running state. "
            "You can retry the node or review the latest logs and tool output."
        )

    can_resume = runtime.get("can_resume")
    if can_resume is None:
        can_resume = run_status in {RUN_STATUS_WAITING_HUMAN, RUN_STATUS_FAILED}
    
    # FORCE: If status is queued or running, it cannot be 'resumed' via the resume/answer API
    if run_status in {RUN_STATUS_QUEUED, RUN_STATUS_RUNNING}:
        can_resume = False

    return {
        **state,
        "project_id": project_id,
        "version": version,
        "run_id": runtime.get("job_id") or state.get("run_id"),
        "task_queue": normalized_task_queue,
        "history": history,
        "messages": messages,
        "artifacts": artifacts,
        "run_status": run_status,
        "current_node": current_node,
        "can_resume": can_resume,
        "waiting_reason": waiting_reason,
        "pending_interrupt": state.get("pending_interrupt"),
        "human_answers": state.get("human_answers") or {},
        "updated_at": normalized_updated_at,
        "stale_execution_detected": stale_running_detected,
    }


def _coerce_event_output(output) -> dict:
    return output if isinstance(output, dict) else {}


def _append_job_log(job_id: str, message: str):
    _ensure_job(job_id)["logs"].append(message)


def _publish_event(job_id: str, payload: dict) -> dict:
    event = validate_event_payload(payload)
    serialized = dump_event(event)
    job = _ensure_job(job_id)
    job["events"].append(serialized)

    stale_subscribers = []
    for subscriber in job["subscribers"]:
        try:
            subscriber.put_nowait(serialized)
        except Exception:
            stale_subscribers.append(subscriber)

    for subscriber in stale_subscribers:
        job["subscribers"].discard(subscriber)

    return serialized


def _emit_node_started(job_id: str, run_id: str, node_id: str, node_type: str):
    _publish_event(
        job_id,
        {
            "event_id": _new_event_id(),
            "event_type": "node_started",
            "run_id": run_id,
            "node_id": node_id,
            "node_type": node_type,
            "timestamp": _now_iso(),
        },
    )


def _emit_node_completed(job_id: str, run_id: str, node_id: str, node_type: str, status: str):
    if status not in {"success", "failed", "skipped"}:
        return
    _publish_event(
        job_id,
        {
            "event_id": _new_event_id(),
            "event_type": "node_completed",
            "run_id": run_id,
            "node_id": node_id,
            "node_type": node_type,
            "status": status,
            "timestamp": _now_iso(),
        },
    )


def _emit_text_delta(job_id: str, run_id: str, node_id: str, node_type: str, delta: str, stream_name: str = "history"):
    _publish_event(
        job_id,
        {
            "event_id": _new_event_id(),
            "event_type": "text_delta",
            "run_id": run_id,
            "node_id": node_id,
            "node_type": node_type,
            "stream_name": stream_name,
            "delta": delta,
            "timestamp": _now_iso(),
        },
    )


def _emit_artifact_updates(job_id: str, run_id: str, node_id: str, node_type: str, before: dict, after: dict):
    before = before or {}
    after = after or {}
    for artifact_name, content in after.items():
        if artifact_name not in before:
            artifact_status = "created"
        elif before[artifact_name] != content:
            artifact_status = "updated"
        else:
            continue

        _publish_event(
            job_id,
            {
                "event_id": _new_event_id(),
                "event_type": "artifact_updated",
                "run_id": run_id,
                "node_id": node_id,
                "node_type": node_type,
                "artifact_name": artifact_name,
                "artifact_status": artifact_status,
                "timestamp": _now_iso(),
            },
        )


def _emit_tool_events(job_id: str, run_id: str, node_id: str, node_type: str, tool_results: list[dict] | None):
    for tool_result in tool_results or []:
        _publish_event(
            job_id,
            {
                "event_id": _new_event_id(),
                "event_type": "tool_event",
                "run_id": run_id,
                "node_id": node_id,
                "node_type": node_type,
                "tool_name": tool_result.get("tool_name", "unknown"),
                "status": tool_result.get("status", "error"),
                "error_code": tool_result.get("error_code", "UNKNOWN"),
                "duration_ms": int(tool_result.get("duration_ms", 0) or 0),
                "tool_input": tool_result.get("input") or {},
                "tool_output": tool_result.get("output") or {},
                "timestamp": _now_iso(),
            },
        )


def _emit_waiting_human(
    job_id: str,
    run_id: str,
    node_id: str,
    node_type: str,
    question: str,
    resume_target: str,
    *,
    interrupt_id: str | None = None,
    context: dict | None = None,
):
    _publish_event(
        job_id,
        {
            "event_id": _new_event_id(),
            "event_type": "waiting_human",
            "run_id": run_id,
            "node_id": node_id,
            "node_type": node_type,
            "interrupt_id": interrupt_id,
            "question": question,
            "context": context or {},
            "resume_target": resume_target,
            "timestamp": _now_iso(),
        },
    )


def _emit_run_completed(job_id: str, run_id: str):
    _publish_event(
        job_id,
        {
            "event_id": _new_event_id(),
            "event_type": "run_completed",
            "run_id": run_id,
            "status": "success",
            "timestamp": _now_iso(),
        },
    )


def _emit_run_failed(job_id: str, run_id: str, error_message: str):
    _publish_event(
        job_id,
        {
            "event_id": _new_event_id(),
            "event_type": "run_failed",
            "run_id": run_id,
            "status": "failed",
            "error_message": error_message,
            "timestamp": _now_iso(),
        },
    )


def _resolve_node_id(node_name: str, payload: dict) -> str:
    if payload.get("current_task_id"):
        return payload["current_task_id"]

    for task in payload.get("task_queue", []) or []:
        if task.get("agent_type") == node_name:
            return task.get("id", node_name)

    if node_name == "planner":
        return "0"
    return node_name


def _record_graph_event(
    project_id: str,
    version: str,
    node_name: str,
    output,
    *,
    job_id: str | None = None,
):
    payload = _coerce_event_output(output)
    node_run_status = RUN_STATUS_WAITING_HUMAN if payload.get("human_intervention_required") else RUN_STATUS_RUNNING
    current_node = payload.get("current_node") or node_name
    _set_runtime_state(
        project_id,
        version,
        run_status=node_run_status,
        current_node=current_node,
        waiting_reason=payload.get("waiting_reason"),
        job_id=job_id,
    )
    return payload


def _handle_structured_graph_event(
    job_id: str,
    project_id: str,
    version: str,
    node_name: str,
    payload: dict,
    previous_artifacts: dict,
) -> dict:
    run_id = job_id
    node_id = _resolve_node_id(node_name, payload)
    node_type = node_name

    completed_status = "success"
    if node_name not in {"bootstrap", "supervisor"}:
        matched_task = next((task for task in payload.get("task_queue", []) if task.get("agent_type") == node_name), None)
        if matched_task:
            completed_status = matched_task.get("status", "success")
        elif payload.get("human_intervention_required"):
            completed_status = "skipped"

    _emit_node_completed(job_id, run_id, node_id, node_type, completed_status)

    for history_entry in payload.get("history", []):
        _append_job_log(job_id, history_entry)
        _emit_text_delta(job_id, run_id, node_id, node_type, history_entry, "history")

    _emit_tool_events(job_id, run_id, node_id, node_type, payload.get("tool_results"))

    current_artifacts = _load_artifacts_from_disk(project_id, version)
    _emit_artifact_updates(job_id, run_id, node_id, node_type, previous_artifacts, current_artifacts)

    if payload.get("human_intervention_required"):
        pending_interrupt = payload.get("pending_interrupt") or {}
        question = pending_interrupt.get("question") or payload.get("waiting_reason") or "Human input required to continue."
        _emit_waiting_human(
            job_id,
            run_id,
            node_id,
            node_type,
            question,
            resume_target=pending_interrupt.get("resume_target", node_type),
            interrupt_id=pending_interrupt.get("interrupt_id"),
            context=pending_interrupt.get("context") or {},
        )

    if node_name == "bootstrap":
        resume_target_node = payload.get("resume_target_node")
        if resume_target_node:
            resume_task = next(
                (task for task in payload.get("task_queue", []) if task.get("agent_type") == resume_target_node),
                None,
            )
            _emit_node_started(
                job_id,
                run_id,
                (resume_task or {}).get("id", "0" if resume_target_node == "planner" else resume_target_node),
                resume_target_node,
            )
        elif payload.get("resume_action") != "approve":
            _emit_node_started(job_id, run_id, "0", "planner")
    elif node_name == "supervisor":
        next_node = payload.get("next")
        if isinstance(next_node, list):
            dispatched_tasks = payload.get("dispatched_tasks") or []
            task_id_by_agent = {
                task.get("agent_type"): task.get("id")
                for task in dispatched_tasks
                if task.get("agent_type") and task.get("id")
            }
            for index, node_type in enumerate(next_node):
                if node_type in {"END", "human_review", "supervisor_advance"}:
                    continue
                current_task_ids = payload.get("current_task_ids") or []
                next_node_id = task_id_by_agent.get(node_type) or (
                    current_task_ids[index] if index < len(current_task_ids) else node_type
                )
                _emit_node_started(job_id, run_id, next_node_id, node_type)
        elif next_node and next_node not in {"END", "human_review", "supervisor_advance"}:
            next_node_id = payload.get("current_task_id") or next_node
            _emit_node_started(job_id, run_id, next_node_id, next_node)

    return current_artifacts


def _initial_history(project_id: str, history: list[str]) -> list[str]:
    if history:
        return history
    return [f"[SYSTEM] Initializing design session for {project_id}..."]


def _build_resume_task_queue(current_state: dict, resume_action: str, resume_target_node: str | None = None) -> list[dict]:
    if resume_action != "revise":
        if not resume_target_node or resume_target_node == "supervisor":
            return current_state.get("task_queue", [])

        updated_queue = []
        target_found = False
        for task in current_state.get("task_queue", []):
            if task.get("agent_type") == resume_target_node:
                updated_queue.append({**task, "status": "running"})
                target_found = True
            else:
                updated_queue.append(dict(task))
        if target_found:
            return updated_queue
        if resume_target_node == "planner":
            return [{"id": "0", "agent_type": "planner", "status": "running", "dependencies": [], "priority": 100}]
        return current_state.get("task_queue", [])
    return [{"id": "0", "agent_type": "planner", "status": "running", "dependencies": [], "priority": 100}]


def _reset_retry_branch(task_queue: list[dict], target_node_type: str) -> list[dict]:
    tasks_by_id = {task["id"]: dict(task) for task in task_queue}
    target_task = next((task for task in task_queue if task.get("agent_type") == target_node_type), None)
    if not target_task:
        return task_queue

    to_reset = {target_task["id"]}
    changed = True
    while changed:
        changed = False
        for task in task_queue:
            deps = set(task.get("dependencies", []))
            if deps & to_reset and task["id"] not in to_reset:
                to_reset.add(task["id"])
                changed = True

    reset_queue = []
    for task in task_queue:
        if task["id"] in to_reset:
            reset_queue.append({**task, "status": "todo"})
        else:
            reset_queue.append(dict(task))
    return reset_queue


def _build_graph_input_state(
    job_id: str,
    project_id: str,
    version: str,
    requirement_text: str,
    persisted_state: dict | None,
    *,
    resume_action: str | None = None,
    feedback: str = "",
) -> dict:
    messages = list((persisted_state or {}).get("messages", []))
    history = list((persisted_state or {}).get("history", []))
    resume_target_node = (persisted_state or {}).get("resume_target_node")
    if resume_action:
        human_message = {
            "role": "human",
            "action": resume_action,
            "content": feedback,
            "timestamp": _now_iso(),
        }
        messages.append(human_message)
        history.append(
            f"[HUMAN] Action: {resume_action}. Feedback: {feedback or 'None'}"
        )

    state = {
        "project_id": project_id,
        "version": version,
        "run_id": job_id,
        "requirement": requirement_text or (persisted_state or {}).get("requirement", ""),
        "design_context": (persisted_state or {}).get("design_context", {}),
        "task_queue": _build_resume_task_queue(persisted_state or {}, resume_action or "", resume_target_node),
        "workflow_phase": (persisted_state or {}).get("workflow_phase", "INIT"),
        "history": _initial_history(project_id, history),
        "messages": messages,
        "artifacts": (persisted_state or {}).get("artifacts", {}),
        "human_intervention_required": False,
        "waiting_reason": None,
        "pending_interrupt": (persisted_state or {}).get("pending_interrupt"),
        "human_answers": (persisted_state or {}).get("human_answers", {}),
        "last_worker": (persisted_state or {}).get("last_worker"),
        "current_node": "bootstrap",
        "resume_target_node": resume_target_node,
        "run_status": RUN_STATUS_RUNNING,
        "updated_at": _now_iso(),
        "resume_action": resume_action,
        "human_feedback": feedback,
    }
    if resume_action == "revise":
        state["workflow_phase"] = "ANALYSIS"
    return state


async def run_orchestrator_task(
    job_id: str,
    project_id: str,
    version: str,
    requirement_text: str,
    *,
    resume_action: str | None = None,
    feedback: str = "",
    persisted_state_override: dict | None = None,
):
    thread_id = _thread_id(project_id, version)
    print(f"\n[DEBUG] Starting/Resuming Job: {job_id} for Thread: {thread_id}")
    _ensure_job(job_id)["status"] = RUN_STATUS_RUNNING
    _set_runtime_state(
        project_id,
        version,
        run_status=RUN_STATUS_RUNNING,
        current_node="bootstrap",
        can_resume=False,
        job_id=job_id,
    )
    _emit_node_started(job_id, job_id, "bootstrap", "bootstrap")

    try:
        project_path = PROJECTS_DIR / project_id / version
        baseline_path = project_path / "baseline"
        baseline_path.mkdir(parents=True, exist_ok=True)
        (project_path / "logs").mkdir(parents=True, exist_ok=True)

        if requirement_text:
            (baseline_path / "original-requirements.md").write_text(requirement_text, encoding="utf-8")

        persisted_state = persisted_state_override if persisted_state_override is not None else get_workflow_state(project_id, version)
        initial_state = _build_graph_input_state(
            job_id,
            project_id,
            version,
            requirement_text,
            persisted_state,
            resume_action=resume_action,
            feedback=feedback,
        )

        config = _graph_config(project_id, version, job_id)
        known_artifacts = _load_artifacts_from_disk(project_id, version)
        paused_for_human = False
        pause_node = None
        pause_reason = None
        async with _graph_for_run() as design_graph:
            async for event in design_graph.astream(initial_state, config=config, stream_mode="updates"):
                for node_name, output in event.items():
                    print(f"[DEBUG] Node {node_name} yielded an update event.")
                    payload = _record_graph_event(project_id, version, node_name, output, job_id=job_id)
                    if payload.get("human_intervention_required"):
                        paused_for_human = True
                        pause_node = node_name
                        pause_reason = payload.get("waiting_reason")
                    known_artifacts = _handle_structured_graph_event(job_id, project_id, version, node_name, payload, known_artifacts)

        # FINAL STATE GUARD: Check if we exited the loop while tasks are still 'running'
        if not paused_for_human:
            final_state = get_workflow_state(project_id, version, include_runtime=False)
            if final_state:
                queue = final_state.get("task_queue", [])
                stalled_tasks = [t for t in queue if t["status"] == "running"]
                if stalled_tasks:
                    print(f"[ERROR] Graph execution ended but {len(stalled_tasks)} tasks are still 'running'. Marking as failed.")
                    # Force failed status to avoid frontend spinning
                    for task in stalled_tasks:
                        _emit_node_completed(job_id, job_id, task["id"], task["agent_type"], "failed")
                    
                    # Update persisted state to reflect failure
                    _set_runtime_state(
                        project_id,
                        version,
                        run_status=RUN_STATUS_FAILED,
                        current_node=stalled_tasks[0]["agent_type"],
                        waiting_reason="Execution stalled: Background task ended unexpectedly.",
                        can_resume=True, # Allow retry
                        job_id=job_id,
                    )
                    _ensure_job(job_id)["status"] = RUN_STATUS_FAILED
                    return

        if paused_for_human:
            _ensure_job(job_id)["status"] = RUN_STATUS_WAITING_HUMAN
            _set_runtime_state(
                project_id,
                version,
                run_status=RUN_STATUS_WAITING_HUMAN,
                current_node=pause_node,
                waiting_reason=pause_reason,
                can_resume=True,
                job_id=job_id,
            )
            return

        latest_state = get_workflow_state(project_id, version, include_runtime=False)
        latest_status = latest_state.get("run_status") if latest_state else RUN_STATUS_SUCCESS
        if latest_status == RUN_STATUS_SUCCESS:
            _ensure_job(job_id)["status"] = RUN_STATUS_SUCCESS
            _set_runtime_state(
                project_id,
                version,
                run_status=RUN_STATUS_SUCCESS,
                current_node=None,
                waiting_reason=None,
                can_resume=False,
                job_id=job_id,
            )
            _emit_run_completed(job_id, job_id)
        else:
            _ensure_job(job_id)["status"] = latest_status
            _set_runtime_state(
                project_id,
                version,
                run_status=latest_status,
                current_node=latest_state.get("current_node") if latest_state else None,
                waiting_reason=latest_state.get("waiting_reason") if latest_state else None,
                can_resume=latest_state.get("can_resume") if latest_state else False,
                job_id=job_id,
            )
    except Exception as exc:
        import traceback

        error_msg = f"[ERROR] LangGraph execution error: {exc}\n{traceback.format_exc()}"
        print(error_msg)
        _ensure_job(job_id)["status"] = RUN_STATUS_FAILED
        _append_job_log(job_id, error_msg)
        _emit_text_delta(job_id, job_id, runtime_registry.get(thread_id, {}).get("current_node") or "run", runtime_registry.get(thread_id, {}).get("current_node") or "run", error_msg, "stderr")
        _set_runtime_state(
            project_id,
            version,
            run_status=RUN_STATUS_FAILED,
            current_node=None,
            waiting_reason=str(exc),
            can_resume=True,
            job_id=job_id,
        )
        _emit_run_failed(job_id, job_id, str(exc))
    finally:
        latest_state = get_workflow_state(project_id, version)
        if latest_state and "history" in latest_state:
            save_run_log(project_id, version, BASE_DIR, latest_state["history"])


def get_workflow_state(project_id: str, version: str, include_runtime: bool = True):
    config = _graph_config(project_id, version)
    runtime = runtime_registry.get(_thread_id(project_id, version), {}) if include_runtime else {}
    try:
        with _graph_for_state() as design_graph:
            try:
                state = design_graph.get_state(config)
                if state and state.values:
                    return _normalize_state(project_id, version, state.values, runtime=runtime)
            except Exception as e:
                print(f"[Orchestrator] Error getting graph state for {project_id}/{version}: {e}")

        persisted_logs = get_run_log(project_id, version, BASE_DIR)
        legacy_state = {
            "project_id": project_id,
            "version": version,
            "workflow_phase": "ARCHIVED",
            "task_queue": _build_legacy_task_queue(project_id, version),
            "history": persisted_logs if persisted_logs else [],
        }
        return _normalize_state(project_id, version, legacy_state, runtime=runtime)
    except Exception as e:
        print(f"[Orchestrator] Critical error in get_workflow_state for {project_id}/{version}: {e}")
        return _normalize_state(project_id, version, None, runtime=runtime)


async def resume_workflow(project_id: str, version: str, human_input: dict):
    action = (human_input or {}).get("action")
    feedback = (human_input or {}).get("feedback", "")
    answer = (human_input or {}).get("answer", "")
    selected_option = ((human_input or {}).get("selected_option") or "").strip()
    if action not in {"approve", "revise", "answer"}:
        return False

    current_state = get_workflow_state(project_id, version)
    if not current_state or not current_state.get("can_resume"):
        return False

    run_id = current_state.get("run_id")
    if not run_id:
        return False

    pending_interrupt = current_state.get("pending_interrupt") or {}
    requested_node_id = (human_input or {}).get("node_id") or pending_interrupt.get("node_id") or current_state.get("current_node")
    requested_interrupt_id = (human_input or {}).get("interrupt_id") or pending_interrupt.get("interrupt_id")

    if pending_interrupt:
        if requested_node_id != pending_interrupt.get("node_id"):
            return False
        if pending_interrupt.get("interrupt_id") and requested_interrupt_id != pending_interrupt.get("interrupt_id"):
            return False

    normalized_feedback = feedback
    resume_target_node = "supervisor" if action == "approve" else "planner"
    human_answers = dict(current_state.get("human_answers") or {})

    if action == "answer":
        normalized_answer = answer.strip()
        normalized_feedback = normalized_answer
        if not normalized_answer and not selected_option:
            return False
        resume_target_node = pending_interrupt.get("resume_target") or requested_node_id or "planner"
        target_key = requested_node_id or "planner"
        answer_entries = list(human_answers.get(target_key, []))
        summary = normalized_answer
        if selected_option:
            summary = f"Selected option: {selected_option}"
            if normalized_answer:
                summary = f"{summary}. {normalized_answer}"
        answer_entries.append(
            {
                "interrupt_id": requested_interrupt_id,
                "question": pending_interrupt.get("question") or current_state.get("waiting_reason"),
                "answer": normalized_answer,
                "selected_option": selected_option or None,
                "summary": summary,
            }
        )
        human_answers[target_key] = answer_entries

    resumed_state = {
        **current_state,
        "pending_interrupt": None,
        "human_answers": human_answers,
        "resume_target_node": resume_target_node,
        "human_intervention_required": False,
        "waiting_reason": None,
        "run_status": RUN_STATUS_RUNNING,
        "current_node": "bootstrap",
    }

    _delete_checkpoint_state(project_id, version)
    _ensure_job(run_id)
    _set_runtime_state(
        project_id,
        version,
        run_status=RUN_STATUS_RUNNING,
        current_node="bootstrap",
        waiting_reason=None,
        can_resume=False,
        job_id=run_id,
    )
    _launch_runtime_task(
        _thread_id(project_id, version),
        run_orchestrator_task(
            run_id,
            project_id,
            version,
            current_state.get("requirement", ""),
            resume_action=action,
            feedback=normalized_feedback,
            persisted_state_override=resumed_state,
        )
    )
    return True


async def retry_workflow_node(project_id: str, version: str, node_type: str):
    current_state = get_workflow_state(project_id, version)
    if not current_state:
        return False

    target_task = next((task for task in current_state.get("task_queue", []) if task.get("agent_type") == node_type), None)
    if not target_task or target_task.get("status") != "failed":
        return False

    run_id = current_state.get("run_id")
    if not run_id:
        return False

    thread_id = _thread_id(project_id, version)
    # FORCE CANCEL for Retry specifically to clear DB locks
    existing_task = runtime_tasks.get(thread_id)
    if existing_task and not existing_task.done():
        existing_task.cancel()
        try:
            await asyncio.wait_for(existing_task, timeout=1.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    reset_queue = _reset_retry_branch(current_state.get("task_queue", []), node_type)
    retry_state = {
        **current_state,
        "task_queue": _build_resume_task_queue({"task_queue": reset_queue}, "approve", node_type),
        "history": [
            *(current_state.get("history") or []),
            f"[HUMAN] Retry node: {node_type}",
        ],
        "run_status": RUN_STATUS_RUNNING,
        "current_node": "bootstrap",
        "human_intervention_required": False,
        "waiting_reason": None,
        "resume_action": "approve",
        "resume_target_node": node_type,
    }

    _delete_checkpoint_state(project_id, version)
    _ensure_job(run_id)
    _set_runtime_state(
        project_id,
        version,
        run_status=RUN_STATUS_RUNNING,
        current_node="bootstrap",
        waiting_reason=None,
        can_resume=False,
        job_id=run_id,
    )
    # Launch new task cleanly
    _launch_runtime_task(
        thread_id,
        run_orchestrator_task(
            run_id,
            project_id,
            version,
            current_state.get("requirement", ""),
            resume_action="approve",
            feedback="",
            persisted_state_override=retry_state,
        )
    )
    return True


async def continue_workflow(project_id: str, version: str):
    current_state = get_workflow_state(project_id, version)
    if not current_state:
        print(f"[DEBUG] continue_workflow: No state found for {project_id}/{version}")
        return False

    run_status = current_state.get("run_status")
    can_resume = current_state.get("can_resume")
    print(f"[DEBUG] continue_workflow: {project_id}/{version} status={run_status}, can_resume={can_resume}")

    if run_status != RUN_STATUS_QUEUED:
        print(f"[DEBUG] continue_workflow: Status is not queued ({run_status})")
        return False

    # If status is queued, we allow continuation even if can_resume was True (it shouldn't be, but we're robust)
    if can_resume and run_status != RUN_STATUS_QUEUED:
        print(f"[DEBUG] continue_workflow: can_resume is True and status is not queued")
        return False

    has_todo_tasks = any(task.get("status") == "todo" for task in current_state.get("task_queue", []))
    if not has_todo_tasks:
        print(f"[DEBUG] continue_workflow: No todo tasks found")
        return False

    run_id = current_state.get("run_id")
    if not run_id:
        return False

    continue_state = {
        **current_state,
        "run_status": RUN_STATUS_RUNNING,
        "current_node": "bootstrap",
        "human_intervention_required": False,
        "waiting_reason": None,
        "resume_action": "approve",
        "history": [
            *(current_state.get("history") or []),
            "[HUMAN] Continue workflow from queued state",
        ],
    }

    _delete_checkpoint_state(project_id, version)
    _ensure_job(run_id)
    _set_runtime_state(
        project_id,
        version,
        run_status=RUN_STATUS_RUNNING,
        current_node="bootstrap",
        waiting_reason=None,
        can_resume=False,
        job_id=run_id,
    )
    _launch_runtime_task(
        _thread_id(project_id, version),
        run_orchestrator_task(
            run_id,
            project_id,
            version,
            current_state.get("requirement", ""),
            resume_action="approve",
            feedback="",
            persisted_state_override=continue_state,
        )
    )
    return True


def trigger_orchestrator(project_id: str, version: str, requirement_text: str) -> str:
    job_id = str(uuid.uuid4())
    _ensure_job(job_id)
    jobs[job_id]["status"] = RUN_STATUS_QUEUED
    _set_runtime_state(
        project_id,
        version,
        run_status=RUN_STATUS_QUEUED,
        current_node="bootstrap",
        can_resume=False,
        job_id=job_id,
    )
    _launch_runtime_task(
        _thread_id(project_id, version),
        run_orchestrator_task(job_id, project_id, version, requirement_text),
    )
    return job_id


def get_job_status(job_id: str):
    return jobs.get(job_id, {"status": "not_found", "logs": [], "events": []})


def get_job_events(job_id: str) -> list[dict]:
    return list(_ensure_job(job_id)["events"])


def subscribe_job_events(job_id: str) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue()
    _ensure_job(job_id)["subscribers"].add(queue)
    return queue


def unsubscribe_job_events(job_id: str, queue: asyncio.Queue):
    if job_id in jobs:
        jobs[job_id]["subscribers"].discard(queue)


def list_projects():
    if not PROJECTS_DIR.exists():
        return []
    return [{"id": d.name, "name": d.name} for d in PROJECTS_DIR.iterdir() if d.is_dir()]


def create_project(project_id: str):
    (PROJECTS_DIR / project_id).mkdir(parents=True, exist_ok=True)


def list_versions(project_id: str):
    proj_dir = PROJECTS_DIR / project_id
    if not proj_dir.exists():
        return []
    return sorted([d.name for d in proj_dir.iterdir() if d.is_dir()], reverse=True)


def _delete_checkpoint_state(project_id: str, version: str):
    if not CHECKPOINT_DB_PATH.exists():
        return

    thread_id = _thread_id(project_id, version)
    conn = sqlite3.connect(CHECKPOINT_DB_PATH)
    try:
        conn.execute("DELETE FROM writes WHERE thread_id = ?", (thread_id,))
        conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))
        conn.commit()
    finally:
        conn.close()


def delete_version(project_id: str, version: str) -> bool:
    state = get_workflow_state(project_id, version)
    thread_id = _thread_id(project_id, version)
    has_active_runtime = thread_id in runtime_registry or bool(state and state.get("run_id"))
    if has_active_runtime and state and state.get("run_status") in {RUN_STATUS_QUEUED, RUN_STATUS_RUNNING}:
        return False

    project_version_dir = PROJECTS_DIR / project_id / version
    if not project_version_dir.exists():
        return False

    if state and state.get("run_id"):
        jobs.pop(state["run_id"], None)
    runtime_registry.pop(thread_id, None)
    runtime_tasks.pop(thread_id, None)
    _delete_checkpoint_state(project_id, version)
    shutil.rmtree(project_version_dir, ignore_errors=True)
    return True


def get_artifacts_tree(project_id: str, version: str):
    return _load_artifacts_from_disk(project_id, version)


def get_version_logs(project_id: str, version: str) -> list:
    return get_run_log(project_id, version, BASE_DIR)


def list_agents():
    if not AGENTS_DIR.exists():
        return []
    agents = []
    for item in AGENTS_DIR.glob("*.agent.yaml"):
        try:
            with open(item, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                agents.append(
                    {
                        "id": item.stem.replace(".agent", ""),
                        "name": config.get("name", item.stem),
                        "description": config.get("description", ""),
                        "config_path": str(item.relative_to(BASE_DIR)),
                        "skills": config.get("skills", []),
                        "current_config": item.read_text(encoding="utf-8"),
                    }
                )
        except Exception:
            pass
    return agents


def get_agent(agent_id: str):
    config_file = AGENTS_DIR / f"{agent_id}.agent.yaml"
    if not config_file.exists():
        return None
    content = config_file.read_text(encoding="utf-8")
    config = yaml.safe_load(content)
    versions = []
    versions_dir = AGENTS_DIR / ".versions" / agent_id
    if versions_dir.exists():
        v_files = sorted(list(versions_dir.glob("*.v*")), key=os.path.getmtime, reverse=True)
        for v_file in v_files:
            try:
                name_parts = v_file.name.split(".v")
                versions.append(
                    {
                        "version_id": name_parts[1],
                        "timestamp": name_parts[0],
                        "content": v_file.read_text(encoding="utf-8"),
                    }
                )
            except Exception:
                pass
    return {
        "id": agent_id,
        "name": config.get("name", agent_id),
        "description": config.get("description", ""),
        "config_path": str(config_file.relative_to(BASE_DIR)),
        "current_config": content,
        "versions": versions,
        "skills": config.get("skills", []),
    }


def update_agent(agent_id: str, new_config_yaml: str):
    config_file = AGENTS_DIR / f"{agent_id}.agent.yaml"
    if not config_file.exists():
        return False
    try:
        yaml.safe_load(new_config_yaml)
    except Exception:
        return False
    old_content = config_file.read_text(encoding="utf-8")
    versions_dir = AGENTS_DIR / ".versions" / agent_id
    versions_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    v_count = len(list(versions_dir.glob("*.v*"))) + 1
    (versions_dir / f"{timestamp}.v{v_count}").write_text(old_content, encoding="utf-8")
    config_file.write_text(new_config_yaml, encoding="utf-8")
    return True


def list_skills():
    if not SKILLS_DIR.exists():
        return []
    skills = []
    for item in SKILLS_DIR.iterdir():
        if item.is_dir() and (item / "SKILL.md").exists():
            name = item.name
            try:
                content = (item / "SKILL.md").read_text(encoding="utf-8")
                if content.startswith("---"):
                    fm = yaml.safe_load(content.split("---")[1])
                    name = fm.get("name", name)
            except Exception:
                pass
            skills.append(
                {
                    "id": item.name,
                    "name": name,
                    "path": str(item.relative_to(BASE_DIR)),
                    "templates": [t.name for t in (item / "assets" / "templates").iterdir() if t.is_file()]
                    if (item / "assets" / "templates").exists()
                    else [],
                }
            )
    return skills


def get_template(skill_id: str, template_name: str):
    tpl_path = SKILLS_DIR / skill_id / "assets" / "templates" / template_name
    if not tpl_path.exists():
        return None
    content = tpl_path.read_text(encoding="utf-8")
    versions = []
    versions_dir = tpl_path.parent / ".versions" / template_name
    if versions_dir.exists():
        v_files = sorted(list(versions_dir.glob("*.v*")), key=os.path.getmtime, reverse=True)
        for v_file in v_files:
            try:
                name_parts = v_file.name.split(".v")
                versions.append(
                    {
                        "version_id": name_parts[1],
                        "timestamp": name_parts[0],
                        "content": v_file.read_text(encoding="utf-8"),
                    }
                )
            except Exception:
                pass
    return {"id": template_name, "name": template_name, "skill_id": skill_id, "current_content": content, "versions": versions}


def update_template(skill_id: str, template_name: str, new_content: str):
    tpl_path = SKILLS_DIR / skill_id / "assets" / "templates" / template_name
    if not tpl_path.exists():
        tpl_path.parent.mkdir(parents=True, exist_ok=True)
        old_content = ""
    else:
        old_content = tpl_path.read_text(encoding="utf-8")
    if old_content:
        versions_dir = tpl_path.parent / ".versions" / template_name
        versions_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        v_count = len(list(versions_dir.glob("*.v*"))) + 1
        (versions_dir / f"{timestamp}.v{v_count}").write_text(old_content, encoding="utf-8")
    tpl_path.write_text(new_content, encoding="utf-8")
    return True
