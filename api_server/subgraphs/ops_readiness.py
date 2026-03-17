from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List

from scripts.llm_generator import SubagentOutput
from .react_common import run_standard_react_subgraph


MAX_REACT_STEPS = 5


async def run_ops_readiness_node(
    state: Dict[str, Any],
    *,
    base_dir: Path,
    generate_with_llm_fn: Callable[[str, str, List[str]], SubagentOutput],
    execute_tool_fn: Callable[[str, Dict[str, Any] | None], Dict[str, Any]],
    update_task_status_fn: Callable[[List[Dict[str, Any]], str, str], List[Dict[str, Any]]],
) -> Dict[str, Any]:
    return await run_standard_react_subgraph(
        capability="ops-readiness",
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
        fallback_artifacts_fn=lambda payload, observations, expected_files: _fallback_ops_artifacts(payload, observations),
        tool_history_entries_fn=_tool_history_entries,
        build_evidence_fn=lambda payload, artifacts, observations, react_trace, tool_results, expected_files: {
            "ops_mapping": _build_ops_mapping(artifacts, observations)
        },
        expected_files_fn=lambda payload: ["slo.yaml", "observability-spec.yaml", "deployment-runbook.md"],
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
You are the ops-readiness ReAct controller running inside the main FastAPI process.
Choose one next action at a time to ground SLOs, observability requirements, alerts, deployment checks, and rollback triggers.

Available tools:
- list_files
- extract_structure
- grep_search
- read_file_chunk

Rules:
1. Start by understanding which files describe operational and non-functional requirements.
2. Use extract_structure to find headings and keys before reading long chunks.
3. Use grep_search to find terms like availability, latency, rollback, alert, Kafka, tracing, error rate, p99, dependency.
4. Use read_file_chunk only for focused verification.
5. Stop only when you can generate grounded SLO, observability, and runbook artifacts.
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
                "slo_yaml": templates["slo.yaml"][:400],
                "observability_yaml": templates["observability-spec.yaml"][:400],
                "runbook_md": templates["deployment-runbook.md"][:400],
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
You are a senior SRE and production readiness reviewer.
Generate slo.yaml, observability-spec.yaml, and deployment-runbook.md only from grounded observations gathered during the ReAct loop.

Requirements:
1. slo.yaml must define concrete SLI/SLO targets grounded in the evidence.
2. observability-spec.yaml must define metrics, spans, and alerts grounded in the evidence.
3. deployment-runbook.md must define rollout checks and rollback triggers grounded in the evidence.
4. Use the templates as style references, not as mandatory content.

[slo.yaml]
{templates["slo.yaml"]}

[observability-spec.yaml]
{templates["observability-spec.yaml"]}

[deployment-runbook.md]
{templates["deployment-runbook.md"]}
""".strip()
    user_prompt = json.dumps(
        {
            "requirements_payload": payload,
            "grounded_observations": observations,
        },
        ensure_ascii=False,
        indent=2,
    )
    return generate_with_llm_fn(system_prompt, user_prompt, ["slo.yaml", "observability-spec.yaml", "deployment-runbook.md"])


def _tool_history_entries(tool_name: str, tool_result: Dict[str, Any]) -> List[str]:
    output = tool_result.get("output") or {}
    if tool_name == "list_files":
        return [f"[ops-readiness] Listed files: {len(output.get('files', []))}"]
    if tool_name == "extract_structure":
        return [f"[ops-readiness] Extracted structure from {len(output.get('files', []))} files"]
    if tool_name == "grep_search":
        return [f"[ops-readiness] Search keyword: {output.get('pattern', '')}"]
    if tool_name == "read_file_chunk":
        return [f"[ops-readiness] Read file chunk: {output.get('path', '')}:{output.get('start_line', 1)}-{output.get('end_line', 1)}"]
    return [f"[ops-readiness] Tool call: {tool_name}"]


def _load_templates(base_dir: Path) -> Dict[str, str]:
    template_dir = base_dir / "skills" / "ops-readiness" / "assets" / "templates"
    if not template_dir.exists():
        template_dir = Path(__file__).resolve().parents[2] / "skills" / "ops-readiness" / "assets" / "templates"
    return {
        "slo.yaml": (template_dir / "slo.yaml").read_text(encoding="utf-8-sig"),
        "observability-spec.yaml": (template_dir / "observability-spec.yaml").read_text(encoding="utf-8-sig"),
        "deployment-runbook.md": (template_dir / "deployment-runbook.md").read_text(encoding="utf-8-sig"),
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
            "thought": "Mock decision fallback: list files before grounding operational evidence.",
            "tool_name": "list_files",
            "tool_input": {},
            "evidence_note": "Identify requirement and ops note files.",
        }

    seen_structure = any(obs.get("tool_name") == "extract_structure" for obs in observations)
    if not seen_structure:
        return {
            "done": False,
            "thought": "Mock decision fallback: extract structure from ops files.",
            "tool_name": "extract_structure",
            "tool_input": {"files": structure_candidates},
            "evidence_note": "Find sections related to SLOs, alerts, and rollback.",
        }

    seen_search = any(obs.get("tool_name") == "grep_search" for obs in observations)
    if not seen_search:
        return {
            "done": False,
            "thought": "Mock decision fallback: search for latency references.",
            "tool_name": "grep_search",
            "tool_input": {"pattern": "latency"},
            "evidence_note": "Locate thresholds for alerting and rollback.",
        }

    seen_chunk = any(obs.get("tool_name") == "read_file_chunk" for obs in observations)
    if not seen_chunk:
        return {
            "done": False,
            "thought": "Mock decision fallback: read the main ops requirement chunk.",
            "tool_name": "read_file_chunk",
            "tool_input": {"path": primary_file, "start_line": 1, "end_line": 12},
            "evidence_note": "Verify SLOs, observability scope, and rollback triggers.",
        }

    return {
        "done": True,
        "thought": "Mock decision fallback: enough operational evidence collected.",
        "tool_name": "none",
        "tool_input": {},
        "evidence_note": "Generate ops readiness artifacts.",
    }


def _fallback_ops_artifacts(payload: Dict[str, Any], observations: List[Dict[str, Any]]) -> SubagentOutput:
    project_name = payload.get("project_name", payload.get("project_id", "service"))
    provider = payload.get("provider", "provider")
    scenario_name = payload.get("scenario_name", "scenario")
    evidence_text = json.dumps(observations, ensure_ascii=False).lower()
    latency_target = "< 200ms" if "200ms" in evidence_text else "< 500ms"
    rollback_threshold = "2000ms" if "2000ms" in evidence_text else "5000ms"

    slo_yaml = (
        f"service: {project_name}\n"
        "slos:\n"
        "  - sli_name: api_success_rate\n"
        "    target: 99.99\n"
        "  - sli_name: api_latency_p99\n"
        f"    target: \"{latency_target}\"\n"
    )
    observability_yaml = (
        f"service: {project_name}\n"
        "tracing:\n"
        "  critical_spans:\n"
        "    - name: external_api_call\n"
        f"alerts:\n  - name: {provider}LatencySpike\n    condition: {provider.lower()}_p99_latency > {rollback_threshold}\n"
    )
    runbook_md = (
        f"# Deployment Runbook: {project_name}\n\n"
        f"- Verify Kafka and {provider} health before rollout\n"
        "- Roll back when error rate exceeds 5% for 3 minutes\n"
        f"- Roll back when downstream latency exceeds {rollback_threshold}\n"
        f"- Protect core scenario `{scenario_name}` during canary rollout\n"
    )
    return SubagentOutput(
        reasoning="Fallback ops readiness artifacts generated from grounded observations.",
        artifacts={
            "slo.yaml": slo_yaml,
            "observability-spec.yaml": observability_yaml,
            "deployment-runbook.md": runbook_md,
        },
    )


def _build_ops_mapping(artifacts: Dict[str, str], observations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    combined_text = "\n".join(artifacts.values())
    tokens = []
    patterns = [
        r"\b(99\.99|200ms|2000ms|5%)\b",
        r"\b(external_api_call|Kafka|rollback|latency|availability)\b",
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
