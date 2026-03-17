from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List

from scripts.llm_generator import SubagentOutput
from .react_common import run_standard_react_subgraph


MAX_REACT_STEPS = int(os.getenv("AGENT_MAX_REACT_STEPS", "12"))


async def run_data_design_node(
    state: Dict[str, Any],
    *,
    base_dir: Path,
    generate_with_llm_fn: Callable[[str, str, List[str]], SubagentOutput],
    execute_tool_fn: Callable[[str, Dict[str, Any] | None], Dict[str, Any]],
    update_task_status_fn: Callable[[List[Dict[str, Any]], str, str], List[Dict[str, Any]]],
) -> Dict[str, Any]:
    project_id = state["project_id"]
    version = state["version"]

    def next_decision(payload: Dict[str, Any], observations: List[Dict[str, Any]], templates: Dict[str, str], step: int) -> Dict[str, Any]:
        candidate_files = _candidate_files(payload)
        return _next_react_decision(generate_with_llm_fn, project_id, version, payload, candidate_files, observations, templates, step)

    def final_artifacts(payload: Dict[str, Any], observations: List[Dict[str, Any]], templates: Dict[str, str], expected_files: List[str]) -> SubagentOutput:
        return _generate_final_artifacts(generate_with_llm_fn, project_id, version, payload, observations, templates)

    def fallback_artifacts(payload: Dict[str, Any], observations: List[Dict[str, Any]], expected_files: List[str]) -> SubagentOutput:
        return _fallback_data_artifacts(payload, observations)

    return await run_standard_react_subgraph(
        capability="data-design",
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
            "mapping": _build_mapping(artifacts.get("schema.sql", ""), observations)
        },
        expected_files_fn=lambda payload: ["schema.sql", "er.md", "migration-plan.md"],
        candidate_files_fn=_candidate_files,
        structure_candidates_fn=lambda candidate_files: candidate_files or ["original-requirements.md"],
    )


def _candidate_files(payload: Dict[str, Any]) -> List[str]:
    uploaded_files = payload.get("uploaded_files", [])
    candidate_files = [file_name for file_name in uploaded_files if file_name.endswith((".md", ".txt", ".json"))]
    return candidate_files or ["original-requirements.md"]


def _next_react_decision(
    generate_with_llm_fn: Callable[[str, str, List[str]], SubagentOutput],
    project_id: str,
    version: str,
    payload: Dict[str, Any],
    candidate_files: List[str],
    observations: List[Dict[str, Any]],
    templates: Dict[str, str],
    step: int,
) -> Dict[str, Any]:
    system_prompt = f"""
You are the data-design ReAct controller running inside the main FastAPI process.
Choose one next action at a time to ground database design artifacts.

Available tools:
- list_files / read_file_chunk / grep_search / extract_structure / extract_lookup_values (Read operations from baseline)
- write_file (Write design artifacts to the artifacts directory)
- patch_file (Make partial corrections to already written files)

Strategy:
1. Research: Use read tools to collect evidence from requirement files.
2. Write: Use write_file to produce draft artifacts (e.g., schema.sql).
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
  "tool_name": "grep_search" | "read_file_chunk" | "write_file" | "patch_file" | "none",
  "tool_input": {{}},
  "evidence_note": "what this step should confirm or produce"
}}
""".strip()

    user_prompt = json.dumps(
        {
            "project": project_id,
            "version": version,
            "step": step,
            "requirements_payload": payload,
            "observations": observations,
            "template_hints": {
                "schema_sql": templates["schema.sql"][:400],
                "er_md": templates["er.md"][:300],
                "migration_plan": templates["migration-plan.md"][:300],
            },
        },
        ensure_ascii=False,
        indent=2,
    )
    llm_output = generate_with_llm_fn(system_prompt, user_prompt, ["decision"])
    raw_decision = llm_output.artifacts.get("decision", "")
    try:
        decision = json.loads(raw_decision) if raw_decision else _fallback_react_decision(candidate_files, observations)
    except json.JSONDecodeError:
        decision = _fallback_react_decision(candidate_files, observations)
    if not isinstance(decision, dict):
        decision = _fallback_react_decision(candidate_files, observations)
    decision.setdefault("done", False)
    decision.setdefault("tool_name", "none")
    decision.setdefault("tool_input", {})
    decision.setdefault("thought", "")
    decision.setdefault("evidence_note", "")
    decision["reasoning"] = llm_output.reasoning
    return decision


def _generate_final_artifacts(
    generate_with_llm_fn: Callable[[str, str, List[str]], SubagentOutput],
    project_id: str,
    version: str,
    payload: Dict[str, Any],
    observations: List[Dict[str, Any]],
    templates: Dict[str, str],
) -> SubagentOutput:
    system_prompt = f"""
You are a senior database designer.
Generate schema.sql, er.md, and migration-plan.md only from grounded evidence collected during the ReAct loop.

Requirements:
1. Reflect only tables, fields, and relationships supported by the observations.
2. Keep names in snake_case.
3. Include enough structure for assembler and validator to consume.
4. Use the templates as style references, not as mandatory content.

[schema.sql template]
{templates["schema.sql"]}

[er.md template]
{templates["er.md"]}

[migration-plan.md template]
{templates["migration-plan.md"]}
""".strip()
    user_prompt = json.dumps(
        {
            "project": project_id,
            "version": version,
            "requirements_payload": payload,
            "grounded_observations": observations,
        },
        ensure_ascii=False,
        indent=2,
    )
    return generate_with_llm_fn(system_prompt, user_prompt, ["schema.sql", "er.md", "migration-plan.md"])


def _tool_history_entries(tool_name: str, tool_result: Dict[str, Any]) -> List[str]:
    output = tool_result.get("output") or {}
    if tool_name == "grep_search":
        return [f"[data-design] Search keyword: {output.get('pattern', '')}"]
    if tool_name == "read_file_chunk":
        return [
            f"[data-design] Read file chunk: {output.get('path', '')}:{output.get('start_line', 1)}-{output.get('end_line', 1)}"
        ]
    return [f"[data-design] Tool call: {tool_name}"]


def _load_templates(base_dir: Path) -> Dict[str, str]:
    template_dir = base_dir / "skills" / "data-design" / "assets" / "templates"
    if not template_dir.exists():
        template_dir = Path(__file__).resolve().parents[2] / "skills" / "data-design" / "assets" / "templates"
    return {
        "schema.sql": (template_dir / "schema.sql").read_text(encoding="utf-8-sig"),
        "er.md": (template_dir / "er.md").read_text(encoding="utf-8-sig"),
        "migration-plan.md": (template_dir / "migration-plan.md").read_text(encoding="utf-8-sig"),
    }


def _fallback_react_decision(candidate_files: List[str], observations: List[Dict[str, Any]]) -> Dict[str, Any]:
    primary_file = candidate_files[0] if candidate_files else "original-requirements.md"

    if not observations:
        return {
            "done": False,
            "thought": "Mock decision fallback: search for core order entities first.",
            "tool_name": "grep_search",
            "tool_input": {"pattern": "order"},
            "evidence_note": "Locate candidate tables and fields in the requirements.",
        }

    seen_chunk = any(obs.get("tool_name") == "read_file_chunk" for obs in observations)
    if not seen_chunk:
        return {
            "done": False,
            "thought": "Mock decision fallback: read the most relevant requirement chunk.",
            "tool_name": "read_file_chunk",
            "tool_input": {"path": primary_file, "start_line": 1, "end_line": 16},
            "evidence_note": "Verify table fields and relationships from source text.",
        }

    return {
        "done": True,
        "thought": "Mock decision fallback: enough evidence collected for schema drafting.",
        "tool_name": "none",
        "tool_input": {},
        "evidence_note": "Generate data design artifacts.",
    }


def _fallback_data_artifacts(payload: Dict[str, Any], observations: List[Dict[str, Any]]) -> SubagentOutput:
    requirement_text = payload.get("requirement", "")
    content_fragments = [requirement_text]
    for observation in observations:
        output = observation.get("tool_output") or {}
        if observation.get("tool_name") == "grep_search":
            content_fragments.extend(match.get("line", "") for match in output.get("matches", []))
        elif observation.get("tool_name") == "read_file_chunk":
            content_fragments.append(output.get("content", ""))

    joined_text = "\n".join(fragment for fragment in content_fragments if fragment)
    has_refund = "refund" in joined_text.lower()

    schema_sql = (
        "CREATE TABLE payment_order (\n"
        "  id BIGINT PRIMARY KEY,\n"
        "  merchant_id VARCHAR(64) NOT NULL,\n"
        "  out_trade_no VARCHAR(64) NOT NULL,\n"
        "  amount BIGINT NOT NULL,\n"
        "  status VARCHAR(32) NOT NULL,\n"
        "  created_at DATETIME NOT NULL,\n"
        "  updated_at DATETIME NOT NULL\n"
        ");\n"
    )
    er_md = "# ER Diagram\n\n- payment_order\n"
    migration_plan = "# Migration Plan\n\n1. Create core transactional tables.\n2. Backfill required indexes and constraints.\n"

    if has_refund:
        schema_sql += (
            "\nCREATE TABLE refund_order (\n"
            "  id BIGINT PRIMARY KEY,\n"
            "  payment_order_id BIGINT NOT NULL,\n"
            "  refund_amount BIGINT NOT NULL,\n"
            "  status VARCHAR(32) NOT NULL,\n"
            "  created_at DATETIME NOT NULL,\n"
            "  updated_at DATETIME NOT NULL\n"
            ");\n"
        )
        er_md += "- refund_order -> payment_order\n"
        migration_plan += "3. Create refund tables and foreign-key relationships.\n"

    return SubagentOutput(
        reasoning="Fallback data artifacts generated from grounded observations.",
        artifacts={
            "schema.sql": schema_sql,
            "er.md": er_md,
            "migration-plan.md": migration_plan,
        },
    )


def _build_mapping(schema_sql: str, observations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    table_names = re.findall(r"CREATE TABLE\s+(?:IF NOT EXISTS\s+)?([a-zA-Z_][a-zA-Z0-9_]*)", schema_sql, flags=re.IGNORECASE)
    mapping = []
    for table_name in table_names:
        source_evidence = []
        for observation in observations:
            output = observation.get("tool_output") or {}
            if observation.get("tool_name") == "grep_search":
                for match in output.get("matches", []):
                    line_text = match.get("line", "")
                    if any(token in line_text.lower() for token in table_name.lower().split("_")):
                        source_evidence.append(
                            {
                                "path": match.get("path"),
                                "line_number": match.get("line_number"),
                                "excerpt": line_text,
                            }
                        )
            elif observation.get("tool_name") == "read_file_chunk":
                content = output.get("content", "")
                excerpt_lines = [line.strip() for line in content.splitlines() if line.strip()]
                if any(any(token in line.lower() for token in table_name.lower().split("_")) for line in excerpt_lines):
                    source_evidence.append(
                        {
                            "path": output.get("path"),
                            "line_range": [output.get("start_line"), output.get("end_line")],
                            "excerpt": "\n".join(excerpt_lines[:4]),
                        }
                    )
        mapping.append({"table": table_name, "source_evidence": source_evidence[:6]})
    return mapping
