from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List

from scripts.llm_generator import SubagentOutput
from .react_common import run_standard_react_subgraph


MAX_REACT_STEPS = 5


async def run_flow_design_node(
    state: Dict[str, Any],
    *,
    base_dir: Path,
    generate_with_llm_fn: Callable[[str, str, List[str]], SubagentOutput],
    execute_tool_fn: Callable[[str, Dict[str, Any] | None], Dict[str, Any]],
    update_task_status_fn: Callable[[List[Dict[str, Any]], str, str], List[Dict[str, Any]]],
) -> Dict[str, Any]:
    return await run_standard_react_subgraph(
        capability="flow-design",
        state=state,
        base_dir=base_dir,
        max_react_steps=MAX_REACT_STEPS,
        generate_with_llm_fn=generate_with_llm_fn,
        execute_tool_fn=execute_tool_fn,
        update_task_status_fn=update_task_status_fn,
        load_templates_fn=_load_templates,
        next_decision_fn=lambda payload, observations, templates, step: _next_react_decision(
            generate_with_llm_fn,
            payload,
            payload.get("uploaded_files", []) or ["original-requirements.md"],
            [file_name for file_name in (payload.get("uploaded_files", []) or ["original-requirements.md"]) if file_name.endswith((".md", ".txt", ".json", ".yaml", ".yml"))] or ["original-requirements.md"],
            observations,
            templates,
            step,
        ),
        generate_final_artifacts_fn=lambda payload, observations, templates, expected_files: _generate_final_artifacts(
            generate_with_llm_fn,
            payload,
            observations,
            templates,
            expected_files[0],
            expected_files[1],
        ),
        fallback_artifacts_fn=lambda payload, observations, expected_files: _fallback_flow_artifacts(payload, observations, expected_files[0], expected_files[1]),
        tool_history_entries_fn=_tool_history_entries,
        build_evidence_fn=lambda payload, artifacts, observations, react_trace, tool_results, expected_files: {
            "flow_mapping": _build_flow_mapping(artifacts, observations)
        },
        expected_files_fn=lambda payload: [
            f"sequence-{payload.get('scenario_name', 'scenario').lower()}.md",
            f"state-{payload.get('entity_name', payload.get('aggregate_root', 'entity')).lower()}.md",
        ],
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
You are the flow-design ReAct controller running inside the main FastAPI process.
Choose one next action at a time to ground sequence steps, actors, and state transitions.

Available tools:
- list_files
- extract_structure
- grep_search
- read_file_chunk

Rules:
1. Start by understanding which files describe the business flow.
2. Use extract_structure to find scenario and state sections before reading long chunks.
3. Use grep_search to find words like state, status, transition, callback, reserve, cancel, confirm, event, queue, gateway.
4. Use read_file_chunk only for focused verification of sequence or state transitions.
5. Stop only when you can generate grounded sequence and state artifacts.
6. Candidate files are: {candidate_files}
7. Structure candidates are: {structure_candidates}

Return JSON in artifacts.decision:
{{
  "done": false,
  "thought": "why this step is needed",
  "tool_name": "list_files" | "extract_structure" | "grep_search" | "read_file_chunk" | "none",
  "tool_input": {{}},
  "evidence_note": "what this step should confirm"
}}
""".strip()
    user_prompt = json.dumps(
        {
            "requirements_payload": payload,
            "step": step,
            "observations": observations,
            "template_hints": {
                "sequence_md": templates["sequence.md"][:400],
                "state_md": templates["state.md"][:400],
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
    seq_file_name: str,
    state_file_name: str,
) -> SubagentOutput:
    system_prompt = f"""
You are a senior backend workflow designer.
Generate {seq_file_name} and {state_file_name} only from grounded observations gathered during the ReAct loop.

Requirements:
1. The sequence artifact must describe concrete actors, systems, and ordered interactions.
2. The state artifact must describe valid state transitions and idempotency or concurrency notes.
3. Use the templates as style references, not as mandatory content.
4. Keep Mermaid blocks valid and grounded in the evidence.

[sequence.md]
{templates["sequence.md"]}

[state.md]
{templates["state.md"]}
""".strip()
    user_prompt = json.dumps(
        {
            "requirements_payload": payload,
            "grounded_observations": observations,
        },
        ensure_ascii=False,
        indent=2,
    )
    return generate_with_llm_fn(system_prompt, user_prompt, [seq_file_name, state_file_name])


def _tool_history_entries(tool_name: str, tool_result: Dict[str, Any]) -> List[str]:
    output = tool_result.get("output") or {}
    if tool_name == "list_files":
        return [f"[flow-design] Listed files: {len(output.get('files', []))}"]
    if tool_name == "extract_structure":
        return [f"[flow-design] Extracted structure from {len(output.get('files', []))} files"]
    if tool_name == "grep_search":
        return [f"[flow-design] Search keyword: {output.get('pattern', '')}"]
    if tool_name == "read_file_chunk":
        return [f"[flow-design] Read file chunk: {output.get('path', '')}:{output.get('start_line', 1)}-{output.get('end_line', 1)}"]
    return [f"[flow-design] Tool call: {tool_name}"]


def _load_templates(base_dir: Path) -> Dict[str, str]:
    template_dir = base_dir / "skills" / "flow-design" / "assets" / "templates"
    if not template_dir.exists():
        template_dir = Path(__file__).resolve().parents[2] / "skills" / "flow-design" / "assets" / "templates"
    return {
        "sequence.md": (template_dir / "sequence.md").read_text(encoding="utf-8-sig"),
        "state.md": (template_dir / "state.md").read_text(encoding="utf-8-sig"),
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
            "thought": "Mock decision fallback: list files before grounding flow evidence.",
            "tool_name": "list_files",
            "tool_input": {},
            "evidence_note": "Identify requirement and state files.",
        }

    seen_structure = any(obs.get("tool_name") == "extract_structure" for obs in observations)
    if not seen_structure:
        return {
            "done": False,
            "thought": "Mock decision fallback: extract structure from flow files.",
            "tool_name": "extract_structure",
            "tool_input": {"files": structure_candidates},
            "evidence_note": "Find sections for scenario and state rules.",
        }

    seen_search = any(obs.get("tool_name") == "grep_search" for obs in observations)
    if not seen_search:
        return {
            "done": False,
            "thought": "Mock decision fallback: search for reserved state references.",
            "tool_name": "grep_search",
            "tool_input": {"pattern": "reserved"},
            "evidence_note": "Locate state transitions and reserve actions.",
        }

    seen_chunk = any(obs.get("tool_name") == "read_file_chunk" for obs in observations)
    if not seen_chunk:
        return {
            "done": False,
            "thought": "Mock decision fallback: read the main workflow chunk.",
            "tool_name": "read_file_chunk",
            "tool_input": {"path": primary_file, "start_line": 1, "end_line": 12},
            "evidence_note": "Verify participants, transitions, and side effects.",
        }

    return {
        "done": True,
        "thought": "Mock decision fallback: enough workflow evidence collected.",
        "tool_name": "none",
        "tool_input": {},
        "evidence_note": "Generate flow artifacts.",
    }


def _fallback_flow_artifacts(
    payload: Dict[str, Any],
    observations: List[Dict[str, Any]],
    seq_file_name: str,
    state_file_name: str,
) -> SubagentOutput:
    aggregate_root = payload.get("aggregate_root", payload.get("entity_name", "Entity"))
    scenario_name = payload.get("scenario_name", "Scenario")
    evidence_text = json.dumps(observations, ensure_ascii=False).lower()
    publish_step = "Application->>Queue: Publish event\n" if any(token in evidence_text for token in ("kafka", "queue", "event")) else ""

    sequence_md = (
        f"# Sequence: {scenario_name}\n\n"
        "```mermaid\n"
        "sequenceDiagram\n"
        "Client->>Gateway: Submit request\n"
        "Gateway->>Application: Forward command\n"
        f"Application->>{aggregate_root}: Execute business rule\n"
        f"Application->>Repository: Save {aggregate_root}\n"
        f"{publish_step}"
        "```\n"
    )
    state_md = (
        f"# State: {aggregate_root}\n\n"
        "```mermaid\n"
        "stateDiagram\n"
        "[*] --> CREATED\n"
        "CREATED --> PROCESSING\n"
        "PROCESSING --> COMPLETED\n"
        "PROCESSING --> FAILED\n"
        "```\n"
    )
    return SubagentOutput(
        reasoning="Fallback flow artifacts generated from grounded observations.",
        artifacts={seq_file_name: sequence_md, state_file_name: state_md},
    )


def _build_flow_mapping(artifacts: Dict[str, str], observations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    combined_text = "\n".join(artifacts.values())
    tokens = []
    for match in re.finditer(r"\b([A-Z][A-Z_]{2,}|Client|Gateway|Application|Domain|Repository|Kafka)\b", combined_text):
        token = match.group(1)
        if token not in tokens:
            tokens.append(token)

    mappings = []
    for token in tokens:
        source_evidence = []
        for observation in observations:
            tool_name = observation.get("tool_name")
            output = observation.get("tool_output") or {}
            if tool_name == "extract_structure":
                for file_summary in output.get("files", []):
                    headings = file_summary.get("headings", [])
                    if any(token.lower() in heading.lower() for heading in headings):
                        source_evidence.append({"path": file_summary.get("path"), "type": "heading_match"})
            elif tool_name == "grep_search":
                for match_item in output.get("matches", []):
                    line_text = match_item.get("line", "")
                    if token.lower() in line_text.lower():
                        source_evidence.append(
                            {
                                "path": match_item.get("path"),
                                "line_number": match_item.get("line_number"),
                                "excerpt": line_text,
                            }
                        )
            elif tool_name == "read_file_chunk":
                content = output.get("content", "")
                if token.lower() in content.lower():
                    source_evidence.append(
                        {
                            "path": output.get("path"),
                            "line_range": [output.get("start_line"), output.get("end_line")],
                        }
                    )
        mappings.append({"token": token, "source_evidence": source_evidence[:6]})
    return mappings
