from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List

from scripts.llm_generator import SubagentOutput
from .react_common import run_standard_react_subgraph


MAX_REACT_STEPS = int(os.getenv("AGENT_MAX_REACT_STEPS", "12"))


async def run_architecture_mapping_node(
    state: Dict[str, Any],
    *,
    base_dir: Path,
    generate_with_llm_fn: Callable[[str, str, List[str]], SubagentOutput],
    execute_tool_fn: Callable[[str, Dict[str, Any] | None], Dict[str, Any]],
    update_task_status_fn: Callable[[List[Dict[str, Any]], str, str], List[Dict[str, Any]]],
) -> Dict[str, Any]:
    def next_decision(payload: Dict[str, Any], observations: List[Dict[str, Any]], templates: Dict[str, str], step: int) -> Dict[str, Any]:
        candidate_files = payload.get("uploaded_files", []) or ["original-requirements.md"]
        structure_candidates = [file_name for file_name in candidate_files if file_name.endswith((".md", ".txt", ".json"))] or ["original-requirements.md"]
        return _next_react_decision(generate_with_llm_fn, payload, candidate_files, structure_candidates, observations, templates, step)

    def final_artifacts(payload: Dict[str, Any], observations: List[Dict[str, Any]], templates: Dict[str, str], expected_files: List[str]) -> SubagentOutput:
        return _generate_final_artifacts(generate_with_llm_fn, payload, observations, templates)

    def fallback_artifacts(payload: Dict[str, Any], observations: List[Dict[str, Any]], expected_files: List[str]) -> SubagentOutput:
        return _fallback_architecture_artifacts(payload, observations)

    return await run_standard_react_subgraph(
        capability="architecture-mapping",
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
            "module_mapping": _build_module_mapping(artifacts.get("module-map.json", ""), observations)
        },
        expected_files_fn=lambda payload: ["architecture.md", "module-map.json"],
        candidate_files_fn=lambda payload: payload.get("uploaded_files", []) or ["original-requirements.md"],
        structure_candidates_fn=lambda candidate_files: [file_name for file_name in candidate_files if file_name.endswith((".md", ".txt", ".json"))] or ["original-requirements.md"],
    )


def _next_react_decision(
    generate_with_llm_fn: Callable[[str, str, List[str]], SubagentOutput],
    payload: Dict[str, Any],
    candidate_files: List[str],
    structure_candidates: List[str],
    observations: List[Dict[str, Any]],
    templates: Dict[str, str],
    step: int,
) -> Dict[str, Any]:
    system_prompt = f"""
You are the architecture-mapping ReAct controller running inside the main FastAPI process.
Choose one next action at a time to ground system boundaries, containers, and module constraints.

Available tools:
- list_files / read_file_chunk / grep_search / extract_structure / extract_lookup_values (Read operations from baseline)
- write_file (Write design artifacts to the artifacts directory)
- patch_file (Make partial corrections to already written files)

Strategy:
1. Research: Use read tools to collect evidence from requirement files and structure candidates.
2. Write: Use write_file to produce draft artifacts (e.g., architecture.md).
3. Verify: Use read_file_chunk to read back and verify the written content if needed.
4. Patch: Use patch_file for minor adjustments based on verification or new insights.
5. Finalize: Set done=true only when all expected artifacts are correctly written and verified.

Rules:
1. Only output one next action.
2. Stop only when you have enough evidence and have written all expected files (architecture.md and module-map.json).
3. Keep tool_input concise and machine-readable JSON.
4. Candidate files are: {candidate_files}
5. Structure candidates are: {structure_candidates}

Return JSON in artifacts.decision:
{{
  "done": false,
  "thought": "why this step is needed",
  "tool_name": "list_files" | "extract_structure" | "grep_search" | "read_file_chunk" | "write_file" | "patch_file" | "none",
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
                "architecture_md": templates["architecture.md"][:400],
                "module_map_json": templates["module-map.json"][:400],
            },
        },
        ensure_ascii=False,
        indent=2,
    )
    llm_output = generate_with_llm_fn(system_prompt, user_prompt, ["decision"])
    raw_decision = llm_output.artifacts.get("decision", "")
    try:
        decision = json.loads(raw_decision) if raw_decision else _fallback_react_decision(candidate_files, structure_candidates, observations)
    except json.JSONDecodeError:
        decision = _fallback_react_decision(candidate_files, structure_candidates, observations)
    if not isinstance(decision, dict):
        decision = _fallback_react_decision(candidate_files, structure_candidates, observations)
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
) -> SubagentOutput:
    system_prompt = f"""
You are a senior software architect.
Generate architecture.md and module-map.json only from grounded observations gathered during the ReAct loop.

Requirements:
1. architecture.md must include a C4 context view and a C4 container view grounded in the evidence.
2. module-map.json must define realistic module boundaries and allowed dependencies.
3. Use the templates as style references, not as mandatory content.
4. Keep module-map.json valid JSON.

[architecture.md]
{templates["architecture.md"]}

[module-map.json]
{templates["module-map.json"]}
""".strip()
    user_prompt = json.dumps(
        {
            "requirements_payload": payload,
            "grounded_observations": observations,
        },
        ensure_ascii=False,
        indent=2,
    )
    return generate_with_llm_fn(system_prompt, user_prompt, ["architecture.md", "module-map.json"])


def _tool_history_entries(tool_name: str, tool_result: Dict[str, Any]) -> List[str]:
    output = tool_result.get("output") or {}
    if tool_name == "list_files":
        return [f"[architecture-mapping] Listed files: {len(output.get('files', []))}"]
    if tool_name == "extract_structure":
        return [f"[architecture-mapping] Extracted structure from {len(output.get('files', []))} files"]
    if tool_name == "grep_search":
        return [f"[architecture-mapping] Search keyword: {output.get('pattern', '')}"]
    if tool_name == "read_file_chunk":
        return [
            f"[architecture-mapping] Read file chunk: {output.get('path', '')}:{output.get('start_line', 1)}-{output.get('end_line', 1)}"
        ]
    return [f"[architecture-mapping] Tool call: {tool_name}"]


def _load_templates(base_dir: Path) -> Dict[str, str]:
    template_dir = base_dir / "skills" / "architecture-mapping" / "assets" / "templates"
    if not template_dir.exists():
        template_dir = Path(__file__).resolve().parents[2] / "skills" / "architecture-mapping" / "assets" / "templates"
    return {
        "architecture.md": (template_dir / "architecture.md").read_text(encoding="utf-8-sig"),
        "module-map.json": (template_dir / "module-map.json").read_text(encoding="utf-8-sig"),
    }


def _fallback_react_decision(
    candidate_files: List[str],
    structure_candidates: List[str],
    observations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    primary_file = candidate_files[0] if candidate_files else "original-requirements.md"

    if not observations:
        return {
            "done": False,
            "thought": "Mock decision fallback: list files before extracting architecture evidence.",
            "tool_name": "list_files",
            "tool_input": {},
            "evidence_note": "Identify available requirement and context files.",
        }

    seen_structure = any(obs.get("tool_name") == "extract_structure" for obs in observations)
    if not seen_structure:
        return {
            "done": False,
            "thought": "Mock decision fallback: extract structure from requirement files.",
            "tool_name": "extract_structure",
            "tool_input": {"files": structure_candidates},
            "evidence_note": "Find sections and keys related to architecture.",
        }

    seen_search = any(obs.get("tool_name") == "grep_search" for obs in observations)
    if not seen_search:
        return {
            "done": False,
            "thought": "Mock decision fallback: search for gateway mentions.",
            "tool_name": "grep_search",
            "tool_input": {"pattern": "gateway"},
            "evidence_note": "Locate boundary and entry-point language.",
        }

    seen_chunk = any(obs.get("tool_name") == "read_file_chunk" for obs in observations)
    if not seen_chunk:
        return {
            "done": False,
            "thought": "Mock decision fallback: read the core architecture chunk.",
            "tool_name": "read_file_chunk",
            "tool_input": {"path": primary_file, "start_line": 1, "end_line": 12},
            "evidence_note": "Verify containers and dependencies in the source text.",
        }

    return {
        "done": True,
        "thought": "Mock decision fallback: enough architecture evidence collected.",
        "tool_name": "none",
        "tool_input": {},
        "evidence_note": "Generate architecture artifacts.",
    }


def _fallback_architecture_artifacts(payload: Dict[str, Any], observations: List[Dict[str, Any]]) -> SubagentOutput:
    project_name = payload.get("project_name", payload.get("project_id", "System"))
    provider = payload.get("provider", "ExternalSystem")
    consumer = payload.get("consumer", "ConsumerSystem")
    aggregate_root = payload.get("aggregate_root", "Entity")

    evidence_text = json.dumps(observations, ensure_ascii=False)
    has_queue = any(token in evidence_text.lower() for token in ("mq", "queue", "kafka"))
    queue_line = '    Container(queue, "MQ", "Kafka", "Publishes domain events")\n' if has_queue else ""
    queue_rel = '    Rel(app, queue, "Publishes events", "MQ")\n' if has_queue else ""

    architecture_md = (
        f"# Architecture for {project_name}\n\n"
        "```mermaid\n"
        "C4Context\n"
        f'    System(core, "{project_name}", "Core system")\n'
        f'    System_Ext(provider, "{provider}", "Upstream provider")\n'
        f'    System_Ext(consumer, "{consumer}", "Downstream consumer")\n'
        "```\n\n"
        "```mermaid\n"
        "C4Container\n"
        f'    Container(api, "API Gateway", "Gateway", "Receives client traffic for {aggregate_root}")\n'
        '    Container(app, "Application Service", "Service", "Runs business orchestration")\n'
        '    ContainerDb(db, "MySQL", "Database", "Stores transactional data")\n'
        '    ContainerDb(cache, "Redis", "Cache", "Caches hot reads and locks")\n'
        f"{queue_line}"
        '    Rel(api, app, "Routes requests", "HTTP")\n'
        '    Rel(app, db, "Reads and writes", "SQL")\n'
        '    Rel(app, cache, "Caches data", "RESP")\n'
        f"{queue_rel}"
        "```\n"
    )
    module_map = {
        "project_name": project_name,
        "modules": [
            {"name": "interfaces", "allowed_dependencies": ["application", "domain"]},
            {"name": "application", "allowed_dependencies": ["domain"]},
            {"name": "domain", "allowed_dependencies": []},
            {"name": "infrastructure", "allowed_dependencies": ["application", "domain"]},
        ],
    }
    return SubagentOutput(
        reasoning="Fallback architecture artifacts generated from grounded observations.",
        artifacts={
            "architecture.md": architecture_md,
            "module-map.json": json.dumps(module_map, ensure_ascii=False, indent=2),
        },
    )


def _build_module_mapping(module_map_text: str, observations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    try:
        parsed = json.loads(module_map_text) if module_map_text.strip() else {}
    except json.JSONDecodeError:
        return []

    modules = parsed.get("modules", [])
    mappings = []
    for module in modules:
        name = module.get("name")
        if not isinstance(name, str):
            continue
        source_evidence = []
        for observation in observations:
            tool_name = observation.get("tool_name")
            output = observation.get("tool_output") or {}
            if tool_name == "extract_structure":
                for file_summary in output.get("files", []):
                    headings = file_summary.get("headings", [])
                    if any(name.lower() in heading.lower() for heading in headings):
                        source_evidence.append({"path": file_summary.get("path"), "type": "heading_match"})
            elif tool_name == "grep_search":
                for match in output.get("matches", []):
                    line_text = match.get("line", "")
                    if name.lower() in line_text.lower():
                        source_evidence.append(
                            {
                                "path": match.get("path"),
                                "line_number": match.get("line_number"),
                                "excerpt": line_text,
                            }
                        )
            elif tool_name == "read_file_chunk":
                content = output.get("content", "")
                if name.lower() in content.lower():
                    source_evidence.append(
                        {
                            "path": output.get("path"),
                            "line_range": [output.get("start_line"), output.get("end_line")],
                        }
                    )
        mappings.append(
            {
                "module": name,
                "allowed_dependencies": module.get("allowed_dependencies", []),
                "source_evidence": source_evidence[:6],
            }
        )
    return mappings
