from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List

from scripts.llm_generator import SubagentOutput
from .react_common import run_standard_react_subgraph


MAX_REACT_STEPS = 5


async def run_integration_design_node(
    state: Dict[str, Any],
    *,
    base_dir: Path,
    generate_with_llm_fn: Callable[[str, str, List[str]], SubagentOutput],
    execute_tool_fn: Callable[[str, Dict[str, Any] | None], Dict[str, Any]],
    update_task_status_fn: Callable[[List[Dict[str, Any]], str, str], List[Dict[str, Any]]],
) -> Dict[str, Any]:
    return await run_standard_react_subgraph(
        capability="integration-design",
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
        ),
        fallback_artifacts_fn=lambda payload, observations, expected_files: _fallback_integration_artifacts(payload, observations, expected_files[0]),
        tool_history_entries_fn=_tool_history_entries,
        build_evidence_fn=lambda payload, artifacts, observations, react_trace, tool_results, expected_files: {
            "integration_mapping": _build_integration_mapping(artifacts, observations)
        },
        expected_files_fn=lambda payload: [f"integration-{payload.get('provider', 'provider').replace(' ', '').lower()}.md", "asyncapi.yaml"],
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
You are the integration-design ReAct controller running inside the main FastAPI process.
Choose one next action at a time to ground downstream calls, asynchronous events, idempotency, retries, and compensation.

Available tools:
- list_files
- extract_structure
- grep_search
- read_file_chunk

Rules:
1. Start by understanding which files describe integration behavior and event contracts.
2. Use extract_structure to find headings and JSON keys before reading long chunks.
3. Use grep_search to find terms like idempotency, retry, outbox, callback, event, queue, Kafka, request-id, compensation.
4. Use read_file_chunk only for focused verification.
5. Stop only when you can generate grounded integration markdown and AsyncAPI artifacts.
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
                "integration_md": templates["integration.md"][:400],
                "asyncapi_yaml": templates["asyncapi.yaml"][:400],
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
    integration_file: str,
) -> SubagentOutput:
    system_prompt = f"""
You are a senior integration architect.
Generate {integration_file} and asyncapi.yaml only from grounded observations gathered during the ReAct loop.

Requirements:
1. The integration markdown must describe idempotency, retries, circuit breaking, and compensation grounded in the evidence.
2. asyncapi.yaml must define concrete domain events and operations grounded in the evidence.
3. Use the templates as style references, not as mandatory content.
4. Keep asyncapi.yaml syntactically plausible and aligned to the scenario.

[integration.md]
{templates["integration.md"]}

[asyncapi.yaml]
{templates["asyncapi.yaml"]}
""".strip()
    user_prompt = json.dumps(
        {
            "requirements_payload": payload,
            "grounded_observations": observations,
        },
        ensure_ascii=False,
        indent=2,
    )
    return generate_with_llm_fn(system_prompt, user_prompt, [integration_file, "asyncapi.yaml"])


def _tool_history_entries(tool_name: str, tool_result: Dict[str, Any]) -> List[str]:
    output = tool_result.get("output") or {}
    if tool_name == "list_files":
        return [f"[integration-design] Listed files: {len(output.get('files', []))}"]
    if tool_name == "extract_structure":
        return [f"[integration-design] Extracted structure from {len(output.get('files', []))} files"]
    if tool_name == "grep_search":
        return [f"[integration-design] Search keyword: {output.get('pattern', '')}"]
    if tool_name == "read_file_chunk":
        return [f"[integration-design] Read file chunk: {output.get('path', '')}:{output.get('start_line', 1)}-{output.get('end_line', 1)}"]
    return [f"[integration-design] Tool call: {tool_name}"]


def _load_templates(base_dir: Path) -> Dict[str, str]:
    template_dir = base_dir / "skills" / "integration-design" / "assets" / "templates"
    if not template_dir.exists():
        template_dir = Path(__file__).resolve().parents[2] / "skills" / "integration-design" / "assets" / "templates"
    return {
        "integration.md": (template_dir / "integration.md").read_text(encoding="utf-8-sig"),
        "asyncapi.yaml": (template_dir / "asyncapi.yaml").read_text(encoding="utf-8-sig"),
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
            "thought": "Mock decision fallback: list files before grounding integration evidence.",
            "tool_name": "list_files",
            "tool_input": {},
            "evidence_note": "Identify requirement and event contract files.",
        }

    seen_structure = any(obs.get("tool_name") == "extract_structure" for obs in observations)
    if not seen_structure:
        return {
            "done": False,
            "thought": "Mock decision fallback: extract structure from integration files.",
            "tool_name": "extract_structure",
            "tool_input": {"files": structure_candidates},
            "evidence_note": "Find sections related to events and downstream calls.",
        }

    seen_search = any(obs.get("tool_name") == "grep_search" for obs in observations)
    if not seen_search:
        return {
            "done": False,
            "thought": "Mock decision fallback: search for idempotency references.",
            "tool_name": "grep_search",
            "tool_input": {"pattern": "idempotency"},
            "evidence_note": "Locate deduplication and retry hints.",
        }

    seen_chunk = any(obs.get("tool_name") == "read_file_chunk" for obs in observations)
    if not seen_chunk:
        return {
            "done": False,
            "thought": "Mock decision fallback: read the main integration chunk.",
            "tool_name": "read_file_chunk",
            "tool_input": {"path": primary_file, "start_line": 1, "end_line": 12},
            "evidence_note": "Verify downstream flow, eventing, and compensation.",
        }

    return {
        "done": True,
        "thought": "Mock decision fallback: enough integration evidence collected.",
        "tool_name": "none",
        "tool_input": {},
        "evidence_note": "Generate integration artifacts.",
    }


def _fallback_integration_artifacts(
    payload: Dict[str, Any],
    observations: List[Dict[str, Any]],
    integration_file: str,
) -> SubagentOutput:
    consumer = payload.get("consumer", "Consumer")
    provider = payload.get("provider", "Provider")
    project_name = payload.get("project_name", payload.get("project_id", "system"))
    evidence_text = json.dumps(observations, ensure_ascii=False).lower()
    event_name = "payment.succeeded" if "payment" in evidence_text else f"{project_name}.event"
    request_id_label = "x-request-id" if "request-id" in evidence_text or "idempotency" in evidence_text else "requestId"

    integration_md = (
        f"# Integration Design: {provider}\n\n"
        f"- Consumer: {consumer}\n"
        f"- Provider: {provider}\n"
        f"- Idempotency key: {request_id_label}\n"
        "- Retry: exponential backoff with bounded retries\n"
        "- Circuit breaker: degrade when downstream error rate spikes\n"
        "- Compensation: outbox relay and replay job\n"
    )
    asyncapi_yaml = (
        "asyncapi: 3.0.0\n"
        "channels:\n"
        f"  {event_name.replace('.', '_')}:\n"
        f"    address: {event_name}\n"
        "operations:\n"
        f"  publish_{event_name.replace('.', '_')}:\n"
        "    action: send\n"
    )
    return SubagentOutput(
        reasoning="Fallback integration artifacts generated from grounded observations.",
        artifacts={integration_file: integration_md, "asyncapi.yaml": asyncapi_yaml},
    )


def _build_integration_mapping(artifacts: Dict[str, str], observations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    combined_text = "\n".join(artifacts.values())
    patterns = [
        r"([a-z]+(?:\.[a-z_]+)+)",
        r"\b(x-request-id|requestId|outbox|Kafka|retry|idempotency)\b",
    ]
    tokens: List[str] = []
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
                    json_keys = file_summary.get("top_level_keys", [])
                    if any(token.lower() in heading.lower() for heading in headings) or any(
                        token.lower() in item.lower() for item in json_keys
                    ):
                        source_evidence.append({"path": file_summary.get("path"), "type": "structure_match"})
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
