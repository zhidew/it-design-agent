from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List

from scripts.llm_generator import SubagentOutput
from .react_common import run_standard_react_subgraph


MAX_REACT_STEPS = 5


async def run_test_design_node(
    state: Dict[str, Any],
    *,
    base_dir: Path,
    generate_with_llm_fn: Callable[[str, str, List[str]], SubagentOutput],
    execute_tool_fn: Callable[[str, Dict[str, Any] | None], Dict[str, Any]],
    update_task_status_fn: Callable[[List[Dict[str, Any]], str, str], List[Dict[str, Any]]],
) -> Dict[str, Any]:
    return await run_standard_react_subgraph(
        capability="test-design",
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
        ),
        fallback_artifacts_fn=lambda payload, observations, expected_files: _fallback_test_artifacts(payload, observations),
        tool_history_entries_fn=_tool_history_entries,
        build_evidence_fn=lambda payload, artifacts, observations, react_trace, tool_results, expected_files: {
            "test_mapping": _build_test_mapping(artifacts, observations)
        },
        expected_files_fn=lambda payload: ["test-inputs.md", "coverage-map.json"],
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
You are the test-design ReAct controller running inside the main FastAPI process.
Choose one next action at a time to ground boundary tests, invalid cases, chaos tests, concurrency tests, and coverage mapping.

Available tools:
- list_files
- extract_structure
- grep_search
- read_file_chunk

Rules:
1. Start by understanding which files describe testing or behavioral constraints.
2. Use extract_structure to find headings and keys before reading long chunks.
3. Use grep_search to find words like invalid, boundary, idempotent, timeout, retry, concurrency, duplicate, status, callback.
4. Use read_file_chunk only for focused verification.
5. Stop only when you can generate grounded test-inputs.md and coverage-map.json.
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
                "test_inputs_md": templates["test-inputs.md"][:400],
                "coverage_map_json": templates["coverage-map.json"][:400],
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
You are a senior QA architect.
Generate test-inputs.md and coverage-map.json only from grounded observations gathered during the ReAct loop.

Requirements:
1. test-inputs.md must include boundary, invalid, integration failure, and concurrency test ideas grounded in the evidence.
2. coverage-map.json must map key design concerns to concrete automated test expectations grounded in the evidence.
3. Use the templates as style references, not as mandatory content.
4. Keep coverage-map.json valid JSON.

[test-inputs.md]
{templates["test-inputs.md"]}

[coverage-map.json]
{templates["coverage-map.json"]}
""".strip()
    user_prompt = json.dumps(
        {
            "requirements_payload": payload,
            "grounded_observations": observations,
        },
        ensure_ascii=False,
        indent=2,
    )
    return generate_with_llm_fn(system_prompt, user_prompt, ["test-inputs.md", "coverage-map.json"])


def _tool_history_entries(tool_name: str, tool_result: Dict[str, Any]) -> List[str]:
    output = tool_result.get("output") or {}
    if tool_name == "list_files":
        return [f"[test-design] Listed files: {len(output.get('files', []))}"]
    if tool_name == "extract_structure":
        return [f"[test-design] Extracted structure from {len(output.get('files', []))} files"]
    if tool_name == "grep_search":
        return [f"[test-design] Search keyword: {output.get('pattern', '')}"]
    if tool_name == "read_file_chunk":
        return [f"[test-design] Read file chunk: {output.get('path', '')}:{output.get('start_line', 1)}-{output.get('end_line', 1)}"]
    return [f"[test-design] Tool call: {tool_name}"]


def _load_templates(base_dir: Path) -> Dict[str, str]:
    template_dir = base_dir / "skills" / "test-design" / "assets" / "templates"
    if not template_dir.exists():
        template_dir = Path(__file__).resolve().parents[2] / "skills" / "test-design" / "assets" / "templates"
    return {
        "test-inputs.md": (template_dir / "test-inputs.md").read_text(encoding="utf-8-sig"),
        "coverage-map.json": (template_dir / "coverage-map.json").read_text(encoding="utf-8-sig"),
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
            "thought": "Mock decision fallback: list files before grounding test evidence.",
            "tool_name": "list_files",
            "tool_input": {},
            "evidence_note": "Identify requirement and test note files.",
        }

    seen_structure = any(obs.get("tool_name") == "extract_structure" for obs in observations)
    if not seen_structure:
        return {
            "done": False,
            "thought": "Mock decision fallback: extract structure from test-related files.",
            "tool_name": "extract_structure",
            "tool_input": {"files": structure_candidates},
            "evidence_note": "Find sections related to boundaries and coverage.",
        }

    seen_search = any(obs.get("tool_name") == "grep_search" for obs in observations)
    if not seen_search:
        return {
            "done": False,
            "thought": "Mock decision fallback: search for idempotent requirements.",
            "tool_name": "grep_search",
            "tool_input": {"pattern": "idempotent"},
            "evidence_note": "Locate deduplication and concurrency expectations.",
        }

    seen_chunk = any(obs.get("tool_name") == "read_file_chunk" for obs in observations)
    if not seen_chunk:
        return {
            "done": False,
            "thought": "Mock decision fallback: read the main testing requirement chunk.",
            "tool_name": "read_file_chunk",
            "tool_input": {"path": primary_file, "start_line": 1, "end_line": 12},
            "evidence_note": "Verify field boundaries, chaos tests, and concurrency requirements.",
        }

    return {
        "done": True,
        "thought": "Mock decision fallback: enough testing evidence collected.",
        "tool_name": "none",
        "tool_input": {},
        "evidence_note": "Generate test design artifacts.",
    }


def _fallback_test_artifacts(payload: Dict[str, Any], observations: List[Dict[str, Any]]) -> SubagentOutput:
    entity_name = payload.get("entity_name", "Entity")
    scenario_name = payload.get("scenario_name", "Scenario")
    provider = payload.get("provider", "Provider")
    evidence_text = json.dumps(observations, ensure_ascii=False).lower()

    test_inputs_md = (
        "# Test Inputs\n\n"
        f"- {entity_name} amount boundary: positive valid, zero invalid, negative invalid\n"
        "- callback idempotency: repeat notification should not duplicate state changes\n"
        f"- chaos: {provider} timeout and retry validation\n"
        "- concurrency: duplicate submission under load\n"
    )
    coverage_map = {
        "coverage_rules": [
            {
                "design_module": f"{scenario_name} API",
                "coverage_requirement": "critical API paths need automated integration tests",
            },
            {
                "design_module": "State transition",
                "coverage_requirement": "important status transitions must be covered",
            },
        ],
        "mapped_test_cases": [
            {
                "scenario": "callback idempotency",
                "design_ref": "notify flow",
                "test_type": "Integration",
            }
        ],
    }
    if "kafka" in evidence_text:
        coverage_map["coverage_rules"].append(
            {
                "design_module": "Async publish",
                "coverage_requirement": "Kafka publish failures require chaos validation",
            }
        )
    return SubagentOutput(
        reasoning="Fallback test design artifacts generated from grounded observations.",
        artifacts={
            "test-inputs.md": test_inputs_md,
            "coverage-map.json": json.dumps(coverage_map, ensure_ascii=False, indent=2),
        },
    )


def _build_test_mapping(artifacts: Dict[str, str], observations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    combined_text = "\n".join(artifacts.values())
    tokens: List[str] = []
    patterns = [
        r"\b(callback idempotency|duplicate submission|Kafka publish failure|timeout)\b",
        r"\b(amount|ALIPAY|WECHAT|UNIONPAY|BANK_CARD)\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, combined_text, flags=re.IGNORECASE):
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
