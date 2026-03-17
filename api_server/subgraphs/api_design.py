from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List

from scripts.llm_generator import SubagentOutput
from .react_common import run_standard_react_subgraph


MAX_REACT_STEPS = int(os.getenv("AGENT_MAX_REACT_STEPS", "12"))


async def run_api_design_node(
    state: Dict[str, Any],
    *,
    base_dir: Path,
    generate_with_llm_fn: Callable[[str, str, List[str]], SubagentOutput],
    execute_tool_fn: Callable[[str, Dict[str, Any] | None], Dict[str, Any]],
    update_task_status_fn: Callable[[List[Dict[str, Any]], str, str], List[Dict[str, Any]]],
) -> Dict[str, Any]:
    def next_decision(payload: Dict[str, Any], observations: List[Dict[str, Any]], templates: Dict[str, str], step: int) -> Dict[str, Any]:
        candidate_files = payload.get("uploaded_files", []) or ["original-requirements.md"]
        return _next_react_decision(generate_with_llm_fn, payload, candidate_files, observations, templates, step)

    def final_artifacts(payload: Dict[str, Any], observations: List[Dict[str, Any]], templates: Dict[str, str], expected_files: List[str]) -> SubagentOutput:
        return _generate_final_artifacts(generate_with_llm_fn, payload, observations, templates, expected_files)

    def fallback_artifacts(payload: Dict[str, Any], observations: List[Dict[str, Any]], expected_files: List[str]) -> SubagentOutput:
        return _fallback_api_artifacts(payload, _lookup_entries_from_observations(observations), expected_files)

    return await run_standard_react_subgraph(
        capability="api-design",
        state=state,
        base_dir=base_dir,
        max_react_steps=MAX_REACT_STEPS,
        generate_with_llm_fn=generate_with_llm_fn,
        execute_tool_fn=execute_tool_fn,
        update_task_status_fn=update_task_status_fn,
        load_templates_fn=_load_templates,
        next_decision_fn=next_decision,
        generate_final_artifacts_fn=final_artifacts,
        fallback_artifacts_fn=fallback_artifacts,
        tool_history_entries_fn=_tool_history_entries,
        build_evidence_fn=lambda payload, artifacts, observations, react_trace, tool_results, expected_files: {
            "lookup_entries": _lookup_entries_from_observations(observations),
            "enum_mapping": _build_enum_mapping(artifacts, _lookup_entries_from_observations(observations)),
        },
        expected_files_fn=_expected_files,
        candidate_files_fn=lambda payload: payload.get("uploaded_files", []) or ["original-requirements.md"],
    )


def _expected_files(payload: Dict[str, Any]) -> List[str]:
    audience = payload.get("audience", "both")
    expected_files = ["api-design.md", "errors-rfc9457.json"]
    if audience in {"internal", "both"}:
        expected_files.append("api-internal.yaml")
    if audience in {"external", "both"}:
        expected_files.append("api-public.yaml")
    return expected_files


def _next_react_decision(
    generate_with_llm_fn: Callable[[str, str, List[str]], SubagentOutput],
    payload: Dict[str, Any],
    candidate_files: List[str],
    observations: List[Dict[str, Any]],
    templates: Dict[str, str],
    step: int,
) -> Dict[str, Any]:
    system_prompt = f"""
You are the api-design ReAct controller running inside the main FastAPI process.
Choose one next action at a time to ground API enums and request fields.

Available tools:
- list_files / read_file_chunk / grep_search / extract_structure / extract_lookup_values (Read operations from baseline)
- write_file (Write design artifacts to the artifacts directory)
- patch_file (Make partial corrections to already written files)

Strategy:
1. Research: Use read tools to collect evidence from requirement files and lookups.
2. Write: Use write_file to produce draft artifacts (e.g., api-internal.yaml).
3. Verify: Use read_file_chunk to read back and verify the written content if needed.
4. Patch: Use patch_file for minor adjustments based on verification or new insights.
5. Finalize: Set done=true only when all expected artifacts are correctly written and verified.

Rules:
1. Only output one next action.
2. Stop only when you have enough evidence and have written all expected files.
3. Keep tool_input concise and machine-readable JSON.
4. Candidate files are: {candidate_files}

Return JSON in artifacts.decision:
{{
  "done": false,
  "thought": "why this step is needed",
  "tool_name": "list_files" | "extract_lookup_values" | "grep_search" | "read_file_chunk" | "write_file" | "patch_file" | "none",
  "tool_input": {{}},
  "evidence_note": "what this step should confirm or produce"
}}
""".strip()
    user_prompt = json.dumps(
        {
            "requirements_payload": payload,
            "step": step,
            "observations": observations,
            "template_hints": {
                "api_internal": templates["api-internal.yaml"][:300],
                "api_public": templates["api-public.yaml"][:300],
            },
        },
        ensure_ascii=False,
        indent=2,
    )
    llm_output = generate_with_llm_fn(system_prompt, user_prompt, ["decision"])
    raw_decision = llm_output.artifacts.get("decision", "")
    try:
        decision = json.loads(raw_decision) if raw_decision else _fallback_react_decision(payload, candidate_files, observations, step)
    except json.JSONDecodeError:
        decision = _fallback_react_decision(payload, candidate_files, observations, step)
    if not isinstance(decision, dict):
        decision = _fallback_react_decision(payload, candidate_files, observations, step)
    decision.setdefault("done", False)
    decision.setdefault("tool_name", "none")
    decision.setdefault("tool_input", {})
    decision.setdefault("thought", "")
    decision.setdefault("evidence_note", "")
    decision["reasoning"] = llm_output.reasoning
    return decision


def _generate_final_artifacts(
    generate_with_llm_fn: Callable[[str, str, List[str]], SubagentOutput],
    payload: Dict[str, Any],
    observations: List[Dict[str, Any]],
    templates: Dict[str, str],
    expected_files: List[str],
) -> SubagentOutput:
    system_prompt = f"""
You are a senior API designer.
Generate API artifacts only from grounded observations gathered during the ReAct loop.
If lookup entries exist, the enum values in OpenAPI must match them exactly.

[api-internal.yaml]
{templates["api-internal.yaml"]}

[api-public.yaml]
{templates["api-public.yaml"]}

[errors-rfc9457.json]
{templates["errors-rfc9457.json"]}
""".strip()
    user_prompt = json.dumps(
        {
            "requirements_payload": payload,
            "grounded_observations": observations,
            "lookup_entries": _lookup_entries_from_observations(observations),
        },
        ensure_ascii=False,
        indent=2,
    )
    return generate_with_llm_fn(system_prompt, user_prompt, expected_files)


def _tool_history_entries(tool_name: str, tool_result: Dict[str, Any]) -> List[str]:
    output = tool_result.get("output") or {}
    if tool_name == "list_files":
        return [f"[api-design] Listed files: {len(output.get('files', []))}"]
    if tool_name == "extract_lookup_values":
        entries = output.get("entries", [])
        if entries:
            return [f"[api-design] Lookup enums detected: {', '.join(entry['name'] for entry in entries[:3])}"]
        return ["[api-design] Lookup file not provided; proceeding with degraded enum guidance."]
    if tool_name == "read_file_chunk":
        return [f"[api-design] Read file chunk: {output.get('path', '')}:{output.get('start_line', 1)}-{output.get('end_line', 1)}"]
    if tool_name == "grep_search":
        return [f"[api-design] Search keyword: {output.get('pattern', '')}"]
    return [f"[api-design] Tool call: {tool_name}"]


def _load_templates(base_dir: Path) -> Dict[str, str]:
    template_dir = base_dir / "skills" / "api-design" / "assets" / "templates"
    if not template_dir.exists():
        template_dir = Path(__file__).resolve().parents[2] / "skills" / "api-design" / "assets" / "templates"
    return {
        "api-internal.yaml": (template_dir / "api-internal.yaml").read_text(encoding="utf-8-sig"),
        "api-public.yaml": (template_dir / "api-public.yaml").read_text(encoding="utf-8-sig"),
        "errors-rfc9457.json": (template_dir / "errors-rfc9457.json").read_text(encoding="utf-8-sig"),
    }


def _fallback_react_decision(
    payload: Dict[str, Any],
    candidate_files: List[str],
    observations: List[Dict[str, Any]],
    step: int,
) -> Dict[str, Any]:
    primary_file = candidate_files[0] if candidate_files else "original-requirements.md"
    requirement_text = (payload.get("requirement") or "").lower()

    if not observations:
        return {
            "done": False,
            "thought": "Mock decision fallback: inspect uploaded files before grounding enums.",
            "tool_name": "list_files",
            "tool_input": {},
            "evidence_note": "Identify lookup and requirement files.",
        }

    seen_lookup = any(obs.get("tool_name") == "extract_lookup_values" for obs in observations)
    if not seen_lookup:
        return {
            "done": False,
            "thought": "Mock decision fallback: extract lookup values from uploaded dictionaries.",
            "tool_name": "extract_lookup_values",
            "tool_input": {},
            "evidence_note": "Capture enum values from lookup files.",
        }

    seen_chunk = any(obs.get("tool_name") == "read_file_chunk" for obs in observations)
    if not seen_chunk:
        return {
            "done": False,
            "thought": "Mock decision fallback: read the requirement chunk mentioning enum usage.",
            "tool_name": "read_file_chunk",
            "tool_input": {"path": primary_file, "start_line": 1, "end_line": 12},
            "evidence_note": "Confirm where payment_channel is used in API payloads.",
        }

    if "lookup" in requirement_text and step < MAX_REACT_STEPS:
        return {
            "done": True,
            "thought": "Mock decision fallback: enough evidence collected from lookup and requirement chunk.",
            "tool_name": "none",
            "tool_input": {},
            "evidence_note": "Generate final API artifacts.",
        }

    return {
        "done": True,
        "thought": "Mock decision fallback: no more relevant enum evidence required.",
        "tool_name": "none",
        "tool_input": {},
        "evidence_note": "Generate final API artifacts.",
    }


def _fallback_api_artifacts(payload: Dict[str, Any], lookup_entries: List[Dict[str, Any]], expected_files: List[str]) -> SubagentOutput:
    enum_values = lookup_entries[0]["values"] if lookup_entries else []
    enum_block = f"enum: [{', '.join(enum_values)}]" if enum_values else "description: Lookup file not provided."
    artifacts = {
        "api-design.md": "API design generated with lookup-aware fallback.",
        "errors-rfc9457.json": json.dumps({"errors": [{"errorCode": "COMMON-400"}]}, ensure_ascii=False),
    }
    if "api-internal.yaml" in expected_files:
        artifacts["api-internal.yaml"] = f"paymentChannel:\n  type: string\n  {enum_block}\n"
    if "api-public.yaml" in expected_files:
        artifacts["api-public.yaml"] = f"paymentChannel:\n  type: string\n  {enum_block}\n"
    return SubagentOutput(reasoning="Fallback API artifacts generated from grounded observations.", artifacts=artifacts)


def _lookup_entries_from_observations(observations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for observation in observations:
        if observation.get("tool_name") == "extract_lookup_values":
            return (observation.get("tool_output") or {}).get("entries", [])
    return []


def _build_enum_mapping(artifacts: Dict[str, str], lookup_entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    mappings = []
    artifact_text = "\n".join(artifacts.values())
    for entry in lookup_entries:
        enum_values = [value for value in entry["values"] if value in artifact_text]
        mappings.append({"name": entry["name"], "enum_values": enum_values, "source_path": entry["source_path"]})
    return mappings
