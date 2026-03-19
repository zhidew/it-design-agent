import asyncio
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List

from scripts.llm_generator import SubagentOutput, generate_with_llm

from .state import DesignState, Task
from .tools import execute_tool
from subgraphs.dynamic_subagent import run_dynamic_subagent

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Agent aliases for normalization (kept for backward compatibility)
AGENT_ALIASES = {
    "architect-map": "architecture-mapping",
    "architecture-map": "architecture-mapping",
    "readiness": "ops-readiness",
    "ops": "ops-readiness",
    "tests": "test-design",
    "test": "test-design",
}


def _get_supported_agent_ids() -> set:
    """Get supported agent IDs from AgentRegistry (dynamic).
    
    Includes both registry-based agents and built-in agents (validator).
    """
    # Built-in agents that are not in the registry
    builtin_agents = {"validator"}
    
    try:
        from registry.agent_registry import AgentRegistry
        registry = AgentRegistry.get_instance()
        return set(registry.get_capabilities()) | builtin_agents
    except RuntimeError:
        # Fallback to hardcoded list if registry not initialized
        return {
            "architecture-mapping",
            "integration-design",
            "data-design",
            "ddd-structure",
            "flow-design",
            "api-design",
            "config-design",
            "test-design",
            "ops-readiness",
            "design-assembler",
            "validator",
        }


# Legacy constant for compatibility
SUPPORTED_AGENT_IDS = _get_supported_agent_ids()


# Enable dynamic subagent execution (can be controlled via environment variable)
USE_DYNAMIC_SUBAGENT = os.getenv("USE_DYNAMIC_SUBAGENT", "true").lower() in ("true", "1", "yes")

# Agents that have explicit hardcoded implementations (prefer those for now)
# Set to empty to use dynamic subagent for all agents
_HARDCODED_AGENTS: set = set()


def _should_use_dynamic_subagent(agent_type: str) -> bool:
    """
    Determine whether to use dynamic subagent execution.
    
    Returns True if:
    1. USE_DYNAMIC_SUBAGENT is enabled
    2. Agent is NOT in the hardcoded list
    
    Now defaults to True for all agents (configuration-driven approach).
    """
    if not USE_DYNAMIC_SUBAGENT:
        return False
    return agent_type not in _HARDCODED_AGENTS


def supervisor(state: DesignState) -> Dict[str, Any]:
    queue = state.get("task_queue", [])
    phase = state.get("workflow_phase", "INIT")

    if state.get("human_intervention_required"):
        return {"next": "END"}

    # Check for actually running tasks based on state
    running_tasks = [task for task in queue if task["status"] == "running"]
    if running_tasks:
        # If tasks are already running (e.g. in parallel branch), we wait for them to re-enter supervisor
        return {"next": "END"}

    todo_tasks = [task for task in queue if task["status"] == "todo"]
    if todo_tasks:
        ready_tasks = [task for task in sorted(todo_tasks, key=lambda item: item["priority"], reverse=True) if _dependencies_met(task, queue)]
        if ready_tasks:
            limit = _resolve_parallel_limit(state)
            selected_tasks = ready_tasks[:limit]
            
            # CRITICAL FIX: Do NOT update task_queue to 'running' here.
            # Let the specific worker node do it when it actually starts.
            
            dispatched_tasks = [{"id": task["id"], "agent_type": task["agent_type"]} for task in selected_tasks]
            if len(selected_tasks) == 1:
                task = selected_tasks[0]
                return {
                    "next": task["agent_type"],
                    "current_task_id": task["id"],
                    "current_node": task["agent_type"],
                    "dispatched_tasks": dispatched_tasks,
                }
            return {
                "next": [task["agent_type"] for task in selected_tasks],
                "current_task_ids": [task["id"] for task in selected_tasks],
                "current_node": selected_tasks[0]["agent_type"],
                "dispatched_tasks": dispatched_tasks,
            }

    # Phase transition logic (only if no tasks are todo or running)
    phases = ["INIT", "ANALYSIS", "ARCHITECTURE", "MODELING", "INTERFACE", "READINESS", "DELIVERY", "DONE"]
    try:
        current_idx = phases.index(phase)
        if current_idx < len(phases) - 1:
            next_phase = phases[current_idx + 1]
            # Advance phase
            return {"next": "supervisor_advance", "workflow_phase": next_phase}
        
        # If we are in DONE phase or no more phases
        return {"next": "END"}
    except ValueError:
        return {"next": "END"}


def create_worker_node(agent_type: str):
    async def worker_node(state: DesignState) -> Dict[str, Any]:
        # Update our own status to 'running' in the queue as the very first step
        queue = state.get("task_queue", [])
        current_task_id = state.get("current_task_id")

        # If we are in a parallel branch, find our specific task by agent_type
        if not current_task_id:
            task = next((t for t in queue if t["agent_type"] == agent_type and t["status"] == "todo"), None)
            if task:
                current_task_id = task["id"]

        updated_queue = queue
        if current_task_id:
            updated_queue = _update_tasks_by_id(queue, [current_task_id], "running")

        state["task_queue"] = updated_queue
        # Inject current task id into state if missing (important for ID mapping)
        if current_task_id and not state.get("current_task_id"):
            state["current_task_id"] = current_task_id

        # =================================================================
        # Dynamic subagent execution (configuration-driven)
        # =================================================================
        result = await run_dynamic_subagent(
            capability=agent_type,
            state=state,
            base_dir=BASE_DIR,
            generate_with_llm_fn=generate_with_llm,
            execute_tool_fn=execute_tool,
            update_task_status_fn=_update_task_status,
        )
        return result

        # NOTE: The following fallback code is kept for reference only.
        # All agents now use dynamic subagent execution.
        # If you need to add a special agent, add it to _HARDCODED_AGENTS set.

        project_id = state["project_id"]
        version = state["version"]
        project_path = BASE_DIR / "projects" / project_id / version
        baseline_path = project_path / "baseline" / "requirements.json"
        logs_dir = project_path / "logs"

        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

        script_name_map = {
            "api-design": "render_contract_stub.py",
            "architecture-mapping": "render_architecture_mapping_stub.py",
            "config-design": "render_config_design_stub.py",
            "data-design": "render_data_stub.py",
            "ddd-structure": "render_ddd_structure_stub.py",
            "flow-design": "render_flow_design_stub.py",
            "integration-design": "render_integration_design_stub.py",
            "ops-readiness": "render_ops_readiness_stub.py",
            "test-design": "render_test_design_stub.py",
            "design-assembler": "render_design_assembler_stub.py",
            "validator": "validate_artifacts.py",
        }

        script_name = script_name_map.get(agent_type)
        if not script_name:
            return {"history": [f"[ERROR] Unknown agent {agent_type}"]}

        script_path = (
            BASE_DIR / "scripts" / script_name
            if agent_type == "validator"
            else BASE_DIR / "skills" / agent_type / "scripts" / script_name
        )
        if not script_path.exists():
            return {"history": [f"[ERROR] Script not found: {script_path}"]}

        def run_sync_process():
            if agent_type == "validator":
                cmd = [sys.executable, str(script_path), "--project", str(project_path)]
            else:
                cmd = [sys.executable, str(script_path), str(baseline_path), str(project_path)]
            return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")

        start_msg = f"[SYSTEM] Agent '{agent_type}' is now running..."
        result = await asyncio.to_thread(run_sync_process)

        stdout_clean = result.stdout.strip() if result.stdout else ""
        stderr_clean = result.stderr.strip() if result.stderr else ""

        if agent_type == "validator":
            (logs_dir / "validator.log").write_text(f"{stdout_clean}\n{stderr_clean}", encoding="utf-8")

        status = "success" if result.returncode == 0 else "failed"

        history_updates = [start_msg, f"[{agent_type}] Completed with status: {status}"]
        if stderr_clean:
            history_updates.append(f"[{agent_type}] [ERROR] {stderr_clean}")
        if status == "failed" and stdout_clean:
            history_updates.append(f"[{agent_type}] [STDOUT] {stdout_clean}")

        return {
            "history": history_updates,
            "task_queue": _update_task_status(state["task_queue"], agent_type, status),
            "human_intervention_required": False,
            "last_worker": agent_type,
        }

    return worker_node


def _update_task_status(queue: List[Task], agent_type: str, status: str) -> List[Task]:
    return [{**task, "status": status} if task["agent_type"] == agent_type else task for task in queue]


def _update_tasks_by_id(queue: List[Task], task_ids: List[str], status: str) -> List[Task]:
    task_id_set = set(task_ids)
    return [{**task, "status": status} if task["id"] in task_id_set else task for task in queue]


def _dependencies_met(task: Task, queue: List[Task]) -> bool:
    """Check if all dependencies of a task are satisfied.
    
    Implements weak dependency semantics:
    - Dependencies are only added for agents that were selected by planner
    - If a dependency task doesn't exist in queue, it means that agent was skipped
    - Only check status for dependencies that actually exist in the queue
    """
    for dep_id in task.get("dependencies", []):
        dep_task = next((queued_task for queued_task in queue if queued_task["id"] == dep_id), None)
        # Weak dependency: if task not in queue, it was skipped by planner - ignore
        if dep_task is None:
            continue
        # Strong dependency: task exists but not yet completed
        if dep_task["status"] != "success":
            return False
    return True


def _resolve_parallel_limit(state: DesignState) -> int:
    orchestrator_config = (state.get("design_context") or {}).get("orchestrator") or {}
    raw_limit = orchestrator_config.get("max_parallel_tasks", os.getenv("ORCHESTRATOR_MAX_PARALLEL", "2"))
    try:
        return max(1, int(raw_limit))
    except (TypeError, ValueError):
        return 2


def _build_task_queue(active_agents: set[str]) -> List[Task]:
    """Build task queue with cross-agent memory dependencies.
    
    Dependency graph (cross-agent memory):
    - api-design reads: data-design.schema.sql, ddd-structure.ddd-structure.md
    - integration-design reads: api-design.api-*.yaml
    - ops-readiness reads: config-design.config-catalog.yaml
    - test-design reads: flow-design.sequence/state-*.md (existing)
    - ddd-structure reads: data-design.schema.sql (existing)
    """
    tasks: List[Task] = [
        {"id": "0", "agent_type": "planner", "status": "success", "dependencies": [], "priority": 100}
    ]

    def add_task_if_active(task_id: str, agent: str, priority: int, deps: List[str]):
        if agent in active_agents:
            tasks.append({"id": task_id, "agent_type": agent, "status": "todo", "dependencies": deps, "priority": priority})
            return True
        return False

    # Phase 1: Architecture foundation
    add_task_if_active("1", "architecture-mapping", 90, ["0"])
    
    # Phase 2: Parallel design work (all depend on architecture)
    has_data = add_task_if_active("3", "data-design", 80, ["1"])
    add_task_if_active("6", "config-design", 65, ["1"])
    add_task_if_active("7", "flow-design", 60, ["1"])
    
    # Phase 3: Domain modeling (depends on data design for schema context)
    has_ddd = add_task_if_active("4", "ddd-structure", 75, ["3" if has_data else "1"])
    
    # Phase 4: API design (cross-agent memory: reads data schema + domain model)
    api_deps = ["1"]
    if has_data:
        api_deps.append("3")  # Read schema.sql for DTO alignment
    if has_ddd:
        api_deps.append("4")  # Read ddd-structure.md for entity mapping
    has_api = add_task_if_active("5", "api-design", 70, api_deps)
    
    # Phase 5: Integration design (cross-agent memory: reads API contracts)
    integ_deps = ["1"]
    if has_api:
        integ_deps.append("5")  # Read api-*.yaml for contract consistency
    add_task_if_active("2", "integration-design", 85, integ_deps)
    
    # Phase 6: Test design (cross-agent memory: reads flow diagrams)
    test_deps = ["1"]
    if "flow-design" in active_agents:
        test_deps.append("7")  # Read sequence/state diagrams
    add_task_if_active("8", "test-design", 50, test_deps)
    
    # Phase 7: Ops readiness (cross-agent memory: reads config catalog)
    ops_deps = ["1"]
    if "config-design" in active_agents:
        ops_deps.append("6")  # Read config-catalog.yaml for monitoring context
    add_task_if_active("9", "ops-readiness", 45, ops_deps)

    # Phase 8: Assembly and validation
    current_ids = [task["id"] for task in tasks if task["id"] != "0"]
    tasks.append({"id": "10", "agent_type": "design-assembler", "status": "todo", "dependencies": current_ids, "priority": 20})
    tasks.append({"id": "11", "agent_type": "validator", "status": "todo", "dependencies": ["10"], "priority": 10})
    return tasks


def _normalize_active_agents(active_agents: set[str]) -> set[str]:
    """Normalize agent IDs using aliases and validate against registry."""
    supported_ids = _get_supported_agent_ids()  # Get fresh list from registry
    normalized = set()
    for agent in active_agents:
        canonical_agent = AGENT_ALIASES.get(agent, agent)
        if canonical_agent in supported_ids:
            normalized.add(canonical_agent)
    return normalized


def _build_pending_interrupt(
    *,
    node_id: str,
    node_type: str,
    question: str,
    context: Dict[str, Any] | None = None,
    resume_target: str,
    interrupt_kind: str,
) -> Dict[str, Any]:
    return {
        "node_id": node_id,
        "node_type": node_type,
        "interrupt_id": str(uuid.uuid4()),
        "question": question,
        "context": context or {},
        "resume_target": resume_target,
        "interrupt_kind": interrupt_kind,
    }


def _normalize_interrupt_context(raw_context: Any) -> Dict[str, Any]:
    if not isinstance(raw_context, dict):
        return {}

    normalized_context = dict(raw_context)
    raw_options = normalized_context.get("options")
    if isinstance(raw_options, list):
        normalized_options = []
        for index, option in enumerate(raw_options):
            if isinstance(option, dict):
                value = str(option.get("value") or option.get("label") or f"option_{index + 1}").strip()
                label = str(option.get("label") or value).strip()
                description = str(option.get("description") or "").strip()
            else:
                value = str(option).strip()
                label = value
                description = ""
            if not value:
                continue
            normalized_options.append(
                {
                    "value": value,
                    "label": label or value,
                    "description": description,
                }
            )
        if normalized_options:
            normalized_context["options"] = normalized_options
        else:
            normalized_context.pop("options", None)
    else:
        normalized_context.pop("options", None)

    if "allow_free_text" not in normalized_context:
        normalized_context["allow_free_text"] = True
    return normalized_context


def _summarize_human_inputs(answer_entries: List[Dict[str, Any]], human_feedback: str = "") -> Dict[str, Any] | None:
    normalized_answers = [dict(entry) for entry in answer_entries if isinstance(entry, dict)]
    if human_feedback.strip():
        normalized_answers.append(
            {
                "interrupt_id": "manual-feedback",
                "answer": human_feedback.strip(),
                "summary": human_feedback.strip(),
            }
        )

    if not normalized_answers:
        return None

    summary_parts = []
    for entry in normalized_answers:
        summary = (entry.get("summary") or "").strip()
        answer = (entry.get("answer") or "").strip()
        selected_option = (entry.get("selected_option") or "").strip()
        if selected_option:
            selected_option_text = f"Selected option: {selected_option}"
            if summary:
                summary = f"{selected_option_text}. {summary}"
            elif answer:
                summary = f"{selected_option_text}. {answer}"
            else:
                summary = selected_option_text
        if summary and answer and summary != answer:
            summary_parts.append(f"{summary} 原文: {answer}")
        else:
            summary_parts.append(summary or answer)
    summary = "\n".join(f"- {part}" for part in summary_parts if part)
    return {
        "summary": summary,
        "analysis": "Human clarifications have been merged into the planning context and should be treated as authoritative supplements to the input materials.",
        "answers": normalized_answers,
    }


def _planner_success_task() -> List[Task]:
    return [{"id": "0", "agent_type": "planner", "status": "success", "dependencies": [], "priority": 100}]


async def bootstrap_node(state: DesignState) -> Dict[str, Any]:
    project_id = state["project_id"]
    version = state["version"]
    requirement_text = state.get("requirement", "")
    project_path = BASE_DIR / "projects" / project_id / version
    baseline_dir = project_path / "baseline"
    logs_dir = project_path / "logs"

    baseline_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    if requirement_text:
        (baseline_dir / "original-requirements.md").write_text(requirement_text, encoding="utf-8")

    resume_action = state.get("resume_action")
    resume_target_node = state.get("resume_target_node")
    existing_queue = state.get("task_queue") or []
    existing_planner = next((task for task in existing_queue if task.get("agent_type") == "planner"), None)
    if resume_target_node:
        return {
            "workflow_phase": state.get("workflow_phase", "ANALYSIS"),
            "history": [f"[SYSTEM] Bootstrap: resuming targeted node {resume_target_node} for {project_id}."],
            "last_worker": "bootstrap",
            "human_intervention_required": False,
            "waiting_reason": None,
            "resume_action": resume_action,
            "resume_target_node": resume_target_node,
            "current_node": resume_target_node,
        }
    if resume_action == "approve":
        return {
            "workflow_phase": state.get("workflow_phase", "ARCHITECTURE"),
            "history": [f"[SYSTEM] Bootstrap: resuming approved plan for {project_id}."],
            "last_worker": "bootstrap",
            "human_intervention_required": False,
            "waiting_reason": None,
            "resume_action": resume_action,
        }

    if resume_action == "revise":
        return {
            "workflow_phase": "ANALYSIS",
            "task_queue": [
                {"id": "0", "agent_type": "planner", "status": "running", "dependencies": [], "priority": 100}
            ],
            "history": [f"[SYSTEM] Bootstrap: restarting planner with human feedback for {project_id}."],
            "last_worker": "bootstrap",
            "human_intervention_required": False,
            "waiting_reason": None,
            "resume_action": resume_action,
        }

    if existing_planner and existing_planner.get("status") in {"running", "success", "failed"}:
        return {
            "workflow_phase": state.get("workflow_phase", "ANALYSIS"),
            "history": [f"[SYSTEM] Bootstrap: restored existing workflow state for {project_id}."],
            "last_worker": "bootstrap",
        }

    return {
        "workflow_phase": "ANALYSIS",
        "task_queue": [
            {"id": "0", "agent_type": "planner", "status": "running", "dependencies": [], "priority": 100}
        ],
        "history": [
            f"[SYSTEM] Bootstrap: initialized workflow context for {project_id}.",
            "[SYSTEM] Planner started.",
        ],
        "last_worker": "bootstrap",
        "current_node": "planner",
    }


async def planner_node(state: DesignState) -> Dict[str, Any]:
    project_id = state["project_id"]
    version = state["version"]
    requirement_text = state.get("requirement", "")
    project_path = BASE_DIR / "projects" / project_id / version
    baseline_dir = project_path / "baseline"

    list_files_result = execute_tool("list_files", {"root_dir": str(baseline_dir)})
    uploaded_files = [file_info["name"] for file_info in list_files_result["output"].get("files", [])]
    extract_structure_result = execute_tool(
        "extract_structure",
        {
            "root_dir": str(baseline_dir),
            "files": [file_info["path"] for file_info in list_files_result["output"].get("files", [])],
        },
    )
    tool_results = [list_files_result, extract_structure_result]
    structure_summary = extract_structure_result["output"].get("files", [])
    planner_answers = ((state.get("human_answers") or {}).get("planner") or [])
    human_feedback = state.get("human_feedback", "")
    human_inputs = _summarize_human_inputs(planner_answers, human_feedback)

    # Get dynamic agent descriptions from AgentRegistry
    try:
        from registry.agent_registry import AgentRegistry
        registry = AgentRegistry.get_instance()
        agent_descriptions = registry.get_planner_agent_descriptions()
    except RuntimeError:
        # Fallback if registry not initialized
        agent_descriptions = """- architecture-mapping: Core system structure.
- integration-design: External service calls, MQ, Kafka.
- data-design: DB schemas, SQL tables.
- ddd-structure: Domain entities, aggregates.
- flow-design: Sequence diagrams, flows.
- api-design: REST/RPC interface contracts.
- config-design: App parameters, lookup lists.
- test-design: Test cases, coverage.
- ops-readiness: Monitoring, deployment specs.
- design-assembler: Assemble all design artifacts.
- validator: Validate design outputs."""

    system_prompt = f"""You are an Expert IT Design Orchestrator.
Your task is to analyze the user's requirements and provide a tailored design pipeline.

We have the following Subagents available:
{agent_descriptions}

ALWAYS INCLUDE: architecture-mapping, design-assembler, validator.
ONLY INCLUDE others if the requirement clearly involves those domains.
You must first evaluate the current input materials, uploaded file structure, and any prior human clarifications.
Treat this as a material sufficiency assessment:
- If the existing materials are already sufficient to choose a grounded pipeline, do NOT ask the human anything.
- Only set needs_human=true when a real information gap would block accurate subagent selection or materially weaken downstream design quality.
- Do not ask for optional nice-to-have details.
- When you do ask, ask only one focused clarification question at a time.
- Prefer multiple-choice style options grounded in the current materials, but still allow free-text fallback when none fit.
- In reasoning, explicitly explain which parts of the provided materials were sufficient and which specific gap remains unresolved.

Output JSON format:
{{
  "reasoning": "Your step-by-step thinking about which agents to select based on text and files.",
  "artifacts": {{
    "active_agents": ["agent-id-1", "agent-id-2"],
    "needs_human": false,
    "question": "",
    "context": {{
      "missing_information": ["field_name"],
      "why_needed": "Explain why the clarification matters.",
      "options": [
        {{"value": "option_value", "label": "Option Label", "description": "When this applies."}}
      ],
      "allow_free_text": true
    }}
  }}
}}"""

    user_prompt = (
        f"Requirement Text: {requirement_text}\n"
        f"Uploaded Files: {', '.join(uploaded_files)}\n"
        f"Uploaded File Structures: {json.dumps(structure_summary, ensure_ascii=False)}\n"
        "Evaluate whether the existing materials already provide enough information to select the design subagents."
    )
    if human_feedback:
        user_prompt += f"\nHuman Revision Feedback: {human_feedback}"
    if human_inputs:
        user_prompt += f"\nHuman Clarifications: {json.dumps(human_inputs, ensure_ascii=False)}"
    llm_decision = SubagentOutput(reasoning="", artifacts={"active_agents": "[]"})
    decision_data: Any = []
    needs_human = False
    ask_human_question = ""
    ask_human_context: Dict[str, Any] = {}

    try:
        print("[DEBUG] Planner: Calling LLM for intent analysis...")
        llm_decision = await asyncio.to_thread(generate_with_llm, system_prompt, user_prompt, ["active_agents"])

        decision_data = json.loads(llm_decision.artifacts.get("active_agents", "[]"))
        if isinstance(decision_data, dict):
            active_agents = set(decision_data.get("active_agents", []))
            needs_human = bool(decision_data.get("needs_human"))
            ask_human_question = (decision_data.get("question") or "").strip()
            ask_human_context = _normalize_interrupt_context(decision_data.get("context"))
        elif isinstance(decision_data, list):
            active_agents = set(decision_data)
        else:
            active_agents = {"architecture-mapping"}
    except Exception as exc:
        print(f"[ERROR] Planner LLM failed: {exc}. Falling back to default.")
        active_agents = {"architecture-mapping", "data-design", "api-design", "flow-design"}

    active_agents = _normalize_active_agents(active_agents)
    active_agents.update({"architecture-mapping", "design-assembler", "validator"})
    tasks = _build_task_queue(active_agents)

    reasoning_content = (
        f"### LLM Orchestration Reasoning\n\n{llm_decision.reasoning}\n\n"
        f"**Selected Pipeline:** {', '.join(sorted(list(active_agents)))}"
    )
    (project_path / "logs" / "planner-reasoning.md").write_text(reasoning_content, encoding="utf-8")

    baseline_payload = {
        "project_name": project_id,
        "project_id": project_id,
        "version": version,
        "requirement": requirement_text,
        "uploaded_files": uploaded_files,
        "tool_context": {
            "list_files": list_files_result["output"],
            "extract_structure": extract_structure_result["output"],
        },
        "active_agents": list(active_agents),
        "domain_name": "Domain",
        "aggregate_root": "Entity",
        "provider": "ExternalSystem",
        "consumer": "ConsumerSystem",
    }
    if human_inputs:
        baseline_payload["human_inputs"] = human_inputs
    (baseline_dir / "requirements.json").write_text(
        json.dumps(baseline_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if needs_human:
        pending_interrupt = _build_pending_interrupt(
            node_id="planner",
            node_type="planner",
            question=ask_human_question or "Please clarify the missing planning information before the workflow continues.",
            context=ask_human_context,
            resume_target="planner",
            interrupt_kind="ask_human",
        )
        return {
            "workflow_phase": "ANALYSIS",
            "task_queue": _planner_success_task(),
            "history": [
                "[SYSTEM] Planner: insufficient information detected, requesting human clarification.",
            ],
            "human_intervention_required": True,
            "waiting_reason": pending_interrupt["question"],
            "pending_interrupt": pending_interrupt,
            "run_status": "waiting_human",
            "last_worker": "planner",
            "current_node": "planner",
            "tool_results": tool_results,
        }

    return {
        "workflow_phase": "ARCHITECTURE",
        "task_queue": tasks,
        "history": [
            "[SYSTEM] Planner: LLM-driven intent analysis completed and baseline initialized.",
            "[SYSTEM] Planner finished.",
        ],
        "human_intervention_required": False,
        "waiting_reason": None,
        "pending_interrupt": None,
        "run_status": "running",
        "last_worker": "planner",
        "current_node": "planner",
        "tool_results": tool_results,
    }
