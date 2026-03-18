from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable, Dict, List

from scripts.llm_generator import SubagentOutput


DecisionFn = Callable[[Dict[str, Any], List[Dict[str, Any]], Dict[str, str], int], Dict[str, Any]]
FinalArtifactsFn = Callable[[Dict[str, Any], List[Dict[str, Any]], Dict[str, str], List[str]], SubagentOutput]
FallbackArtifactsFn = Callable[[Dict[str, Any], List[Dict[str, Any]], List[str]], SubagentOutput]
ToolHistoryFn = Callable[[str, Dict[str, Any]], List[str]]
EvidenceFn = Callable[[Dict[str, Any], Dict[str, str], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[str]], Dict[str, Any]]


def default_structure_candidates(candidate_files: List[str]) -> List[str]:
    structure_candidates = [file_name for file_name in candidate_files if file_name.endswith((".md", ".txt", ".json", ".yaml", ".yml"))]
    return structure_candidates or ["original-requirements.md"]


async def run_standard_react_subgraph(
    *,
    capability: str,
    state: Dict[str, Any],
    base_dir: Path,
    max_react_steps: int,
    generate_with_llm_fn: Callable[[str, str, List[str]], SubagentOutput],
    execute_tool_fn: Callable[[str, Dict[str, Any] | None], Dict[str, Any]],
    update_task_status_fn: Callable[[List[Dict[str, Any]], str, str], List[Dict[str, Any]]],
    load_templates_fn: Callable[[Path], Dict[str, str]],
    next_decision_fn: DecisionFn,
    generate_final_artifacts_fn: FinalArtifactsFn,
    fallback_artifacts_fn: FallbackArtifactsFn,
    tool_history_entries_fn: ToolHistoryFn,
    build_evidence_fn: EvidenceFn,
    expected_files_fn: Callable[[Dict[str, Any]], List[str]],
    candidate_files_fn: Callable[[Dict[str, Any]], List[str]] | None = None,
    structure_candidates_fn: Callable[[List[str]], List[str]] | None = None,
    enable_permission_check: bool = True,
) -> Dict[str, Any]:
    project_id = state["project_id"]
    version = state["version"]
    project_path = base_dir / "projects" / project_id / version
    baseline_path = project_path / "baseline" / "requirements.json"
    baseline_dir = baseline_path.parent
    artifacts_dir = project_path / "artifacts"
    logs_dir = project_path / "logs"
    evidence_dir = project_path / "evidence"

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    payload = json.loads(baseline_path.read_text(encoding="utf-8-sig"))
    candidate_files = candidate_files_fn(payload) if candidate_files_fn else (payload.get("uploaded_files", []) or ["original-requirements.md"])
    structure_candidates = (
        structure_candidates_fn(candidate_files)
        if structure_candidates_fn
        else default_structure_candidates(candidate_files)
    )
    expected_files = expected_files_fn(payload)
    templates = await asyncio.to_thread(load_templates_fn, base_dir)

    history_updates = [f"[SYSTEM] Agent '{capability}' is now running in-process."]
    tool_results: List[Dict[str, Any]] = []
    react_trace: List[Dict[str, Any]] = []
    observations: List[Dict[str, Any]] = []

    READ_TOOLS = {"list_files", "extract_structure", "grep_search", "read_file_chunk", "extract_lookup_values"}
    WRITE_TOOLS = {"write_file", "patch_file", "run_command"}

    # Create permission-aware tool executor
    def _execute_tool_with_permission(tool_name: str, tool_input: Dict[str, Any] | None) -> Dict[str, Any]:
        """Execute tool with optional permission check."""
        if enable_permission_check:
            from api_server.graphs.tools.protocol import execute_tool_with_permission
            return execute_tool_with_permission(
                tool_name, tool_input, agent_capability=capability
            )
        return execute_tool_fn(tool_name, tool_input)

    try:
        for step in range(1, max_react_steps + 1):
            decision = await asyncio.to_thread(
                next_decision_fn,
                payload,
                observations,
                templates,
                step,
            )
            react_trace.append({"step": step, **decision})
            thought = decision.get("thought", "")
            if thought:
                history_updates.append(f"[{capability}] ReAct step {step}: {thought}")

            if decision.get("done"):
                history_updates.append(f"[{capability}] ReAct step {step}: evidence collection complete.")
                break

            tool_name = decision.get("tool_name") or "none"
            tool_input = dict(decision.get("tool_input") or {})
            
            # Determine which root_dir to use
            if tool_name in WRITE_TOOLS:
                tool_input["root_dir"] = str(artifacts_dir)
            else:
                # Default to baseline_dir for read tools or unrecognized tools
                tool_input["root_dir"] = str(baseline_dir)

            tool_result = await asyncio.to_thread(_execute_tool_with_permission, tool_name, tool_input)
            tool_results.append(tool_result)
            react_trace[-1]["tool_result"] = {
                "status": tool_result.get("status"),
                "error_code": tool_result.get("error_code"),
                "duration_ms": tool_result.get("duration_ms"),
            }
            history_updates.extend(tool_history_entries_fn(tool_name, tool_result))
            observations.append(
                {
                    "step": step,
                    "tool_name": tool_name,
                    "tool_input": tool_result.get("input") or {},
                    "tool_output": tool_result.get("output") or {},
                    "evidence_note": decision.get("evidence_note", ""),
                }
            )
        else:
            history_updates.append(
                f"[{capability}] ReAct step {max_react_steps}: reached max steps, generating with available evidence."
            )

        llm_output = await asyncio.to_thread(
            generate_final_artifacts_fn,
            payload,
            observations,
            templates,
            expected_files,
        )

        if any(not (llm_output.artifacts.get(name) or "").strip() for name in expected_files):
            llm_output = fallback_artifacts_fn(payload, observations, expected_files)

        reasoning_sections = [entry.get("reasoning", "") for entry in react_trace if entry.get("reasoning")]
        reasoning_sections.append(llm_output.reasoning)
        (logs_dir / f"{capability}-reasoning.md").write_text(
            "\n\n".join(section for section in reasoning_sections if section),
            encoding="utf-8",
        )

        for artifact_name in expected_files:
            (artifacts_dir / artifact_name).write_text(llm_output.artifacts.get(artifact_name, ""), encoding="utf-8")

        evidence = build_evidence_fn(payload, llm_output.artifacts, observations, react_trace, tool_results, expected_files)
        evidence.setdefault("capability", capability)
        evidence.setdefault("mode", "in_process_react")
        evidence.setdefault("source_files", candidate_files)
        evidence.setdefault(
            "tool_trace",
            [
                {
                    "tool_name": result["tool_name"],
                    "status": result["status"],
                    "error_code": result["error_code"],
                    "duration_ms": result["duration_ms"],
                }
                for result in tool_results
            ],
        )
        evidence.setdefault("react_trace", react_trace)
        (evidence_dir / f"{capability}.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")

        history_updates.append(f"[{capability}] Completed with status: success")
        return {
            "history": history_updates,
            "task_queue": update_task_status_fn(state["task_queue"], capability, "success"),
            "human_intervention_required": False,
            "last_worker": capability,
            "tool_results": tool_results,
        }
    except Exception as exc:
        history_updates.append(f"[{capability}] [ERROR] {exc}")
        return {
            "history": history_updates,
            "task_queue": update_task_status_fn(state["task_queue"], capability, "failed"),
            "human_intervention_required": False,
            "last_worker": capability,
            "tool_results": tool_results,
        }
