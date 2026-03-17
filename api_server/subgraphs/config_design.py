from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List

from scripts.llm_generator import SubagentOutput
from .react_common import run_standard_react_subgraph


MAX_REACT_STEPS = 5


async def run_config_design_node(
    state: Dict[str, Any],
    *,
    base_dir: Path,
    generate_with_llm_fn: Callable[[str, str, List[str]], SubagentOutput],
    execute_tool_fn: Callable[[str, Dict[str, Any] | None], Dict[str, Any]],
    update_task_status_fn: Callable[[List[Dict[str, Any]], str, str], List[Dict[str, Any]]],
) -> Dict[str, Any]:
    return await run_standard_react_subgraph(
        capability="config-design",
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
        fallback_artifacts_fn=lambda payload, observations, expected_files: _fallback_config_artifacts(payload, observations),
        tool_history_entries_fn=_tool_history_entries,
        build_evidence_fn=lambda payload, artifacts, observations, react_trace, tool_results, expected_files: {
            "config_mapping": _build_config_mapping(artifacts, observations)
        },
        expected_files_fn=lambda payload: ["config-catalog.yaml", "config-matrix.md"],
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
You are the config-design ReAct controller running inside the main FastAPI process.
Choose one next action at a time to ground configuration keys, environment differences, and feature toggles.

Available tools:
- list_files
- extract_structure
- grep_search
- read_file_chunk

Rules:
1. Start by understanding available config-related files.
2. Use extract_structure to inspect headings and JSON keys before reading large chunks.
3. Use grep_search to find configuration language such as timeout, feature flag, Redis, MySQL, Kafka, URL, password, secret, env, prod.
4. Use read_file_chunk only for focused verification.
5. Stop only when you can generate grounded config-catalog.yaml and config-matrix.md.
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
                "config_catalog": templates["config-catalog.yaml"][:400],
                "config_matrix": templates["config-matrix.md"][:400],
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
You are a senior platform configuration designer.
Generate config-catalog.yaml and config-matrix.md only from grounded observations gathered during the ReAct loop.

Requirements:
1. config-catalog.yaml must enumerate externalized config keys, types, and secret handling.
2. config-matrix.md must compare DEV, TEST, and PROD strategies without exposing production secrets in plaintext.
3. Use the templates as style references, not as mandatory content.
4. Keep config-catalog.yaml valid YAML-like text and config-matrix.md readable markdown.

[config-catalog.yaml]
{templates["config-catalog.yaml"]}

[config-matrix.md]
{templates["config-matrix.md"]}
""".strip()
    user_prompt = json.dumps(
        {
            "requirements_payload": payload,
            "grounded_observations": observations,
        },
        ensure_ascii=False,
        indent=2,
    )
    return generate_with_llm_fn(system_prompt, user_prompt, ["config-catalog.yaml", "config-matrix.md"])


def _tool_history_entries(tool_name: str, tool_result: Dict[str, Any]) -> List[str]:
    output = tool_result.get("output") or {}
    if tool_name == "list_files":
        return [f"[config-design] Listed files: {len(output.get('files', []))}"]
    if tool_name == "extract_structure":
        return [f"[config-design] Extracted structure from {len(output.get('files', []))} files"]
    if tool_name == "grep_search":
        return [f"[config-design] Search keyword: {output.get('pattern', '')}"]
    if tool_name == "read_file_chunk":
        return [f"[config-design] Read file chunk: {output.get('path', '')}:{output.get('start_line', 1)}-{output.get('end_line', 1)}"]
    return [f"[config-design] Tool call: {tool_name}"]


def _load_templates(base_dir: Path) -> Dict[str, str]:
    template_dir = base_dir / "skills" / "config-design" / "assets" / "templates"
    if not template_dir.exists():
        template_dir = Path(__file__).resolve().parents[2] / "skills" / "config-design" / "assets" / "templates"
    return {
        "config-catalog.yaml": (template_dir / "config-catalog.yaml").read_text(encoding="utf-8-sig"),
        "config-matrix.md": (template_dir / "config-matrix.md").read_text(encoding="utf-8-sig"),
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
            "thought": "Mock decision fallback: list files before identifying config evidence.",
            "tool_name": "list_files",
            "tool_input": {},
            "evidence_note": "Identify requirement and config-related input files.",
        }

    seen_structure = any(obs.get("tool_name") == "extract_structure" for obs in observations)
    if not seen_structure:
        return {
            "done": False,
            "thought": "Mock decision fallback: extract structure from config files.",
            "tool_name": "extract_structure",
            "tool_input": {"files": structure_candidates},
            "evidence_note": "Find headings and JSON keys related to configuration.",
        }

    seen_search = any(obs.get("tool_name") == "grep_search" for obs in observations)
    if not seen_search:
        return {
            "done": False,
            "thought": "Mock decision fallback: search for feature flag references.",
            "tool_name": "grep_search",
            "tool_input": {"pattern": "feature"},
            "evidence_note": "Locate business toggle requirements.",
        }

    seen_chunk = any(obs.get("tool_name") == "read_file_chunk" for obs in observations)
    if not seen_chunk:
        return {
            "done": False,
            "thought": "Mock decision fallback: read the core configuration requirement chunk.",
            "tool_name": "read_file_chunk",
            "tool_input": {"path": primary_file, "start_line": 1, "end_line": 12},
            "evidence_note": "Verify config keys and environment concerns from the source text.",
        }

    return {
        "done": True,
        "thought": "Mock decision fallback: enough config evidence collected.",
        "tool_name": "none",
        "tool_input": {},
        "evidence_note": "Generate config artifacts.",
    }


def _fallback_config_artifacts(payload: Dict[str, Any], observations: List[Dict[str, Any]]) -> SubagentOutput:
    project_name = payload.get("project_name", payload.get("project_id", "service"))
    provider = payload.get("provider", "provider")
    scenario_name = payload.get("scenario_name", "feature")
    requirement_text = json.dumps(observations, ensure_ascii=False).lower()

    props = [
        "spring.datasource.url",
        "spring.redis.host",
        f"integration.{provider}.timeout_ms",
        f"features.{scenario_name}.enabled",
    ]
    if "kafka" in requirement_text:
        props.append("messaging.kafka.bootstrap_servers")

    catalog_lines = [f"service: {project_name}", 'version: "1.0"', "properties:"]
    for key in props:
        inferred_type = "boolean" if key.endswith(".enabled") else "integer" if key.endswith("timeout_ms") else "string"
        catalog_lines.extend(
            [
                f"  - key: {key}",
                f"    type: {inferred_type}",
            ]
        )

    matrix_lines = [
        f"# Config Matrix: {project_name}",
        "",
        "| Config Key | DEV | TEST | PROD |",
        "| :--- | :--- | :--- | :--- |",
        "| `spring.datasource.url` | `jdbc:mysql://dev` | `jdbc:mysql://test` | `jdbc:mysql://prod` |",
        f"| `integration.{provider}.timeout_ms` | `5000` | `3000` | `2000` |",
        f"| `features.{scenario_name}.enabled` | `true` | `true` | `false` |",
    ]
    return SubagentOutput(
        reasoning="Fallback config artifacts generated from grounded observations.",
        artifacts={
            "config-catalog.yaml": "\n".join(catalog_lines) + "\n",
            "config-matrix.md": "\n".join(matrix_lines) + "\n",
        },
    )


def _build_config_mapping(artifacts: Dict[str, str], observations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    combined_text = "\n".join(artifacts.values())
    keys = []
    for match in re.finditer(r"([a-zA-Z0-9_]+\.[a-zA-Z0-9_.-]+)", combined_text):
        key = match.group(1)
        if key not in keys:
            keys.append(key)

    mappings = []
    for key in keys:
        source_evidence = []
        for observation in observations:
            tool_name = observation.get("tool_name")
            output = observation.get("tool_output") or {}
            if tool_name == "extract_structure":
                for file_summary in output.get("files", []):
                    json_keys = file_summary.get("top_level_keys", [])
                    if any(key.lower() in item.lower() or item.lower() in key.lower() for item in json_keys):
                        source_evidence.append({"path": file_summary.get("path"), "type": "json_key_match"})
            elif tool_name == "grep_search":
                for match_item in output.get("matches", []):
                    line_text = match_item.get("line", "")
                    if any(token in line_text.lower() for token in key.lower().split(".")):
                        source_evidence.append(
                            {
                                "path": match_item.get("path"),
                                "line_number": match_item.get("line_number"),
                                "excerpt": line_text,
                            }
                        )
            elif tool_name == "read_file_chunk":
                content = output.get("content", "")
                if any(token in content.lower() for token in key.lower().split(".")):
                    source_evidence.append(
                        {
                            "path": output.get("path"),
                            "line_range": [output.get("start_line"), output.get("end_line")],
                        }
                    )
        mappings.append({"config_key": key, "source_evidence": source_evidence[:6]})
    return mappings
