"""
Dynamic Subagent Execution Module.

This module provides a unified interface for executing subagents based on their
configuration from AgentRegistry. It replaces hardcoded subgraph files with
a configuration-driven approach.

Usage:
    from subgraphs.dynamic_subagent import run_dynamic_subagent
    
    result = await run_dynamic_subagent(
        capability="data-design",
        state=state,
        base_dir=base_dir,
        ...
    )
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from services.llm_service import SubagentOutput, resolve_runtime_llm_settings

if TYPE_CHECKING:
    from registry.agent_registry import AgentFullConfig


MAX_REACT_STEPS = int(os.getenv("AGENT_MAX_REACT_STEPS", "99"))
MAX_ACTIONS_PER_STEP = int(os.getenv("AGENT_MAX_ACTIONS_PER_STEP", "2"))
MAX_FINALIZATION_STEPS = int(os.getenv("AGENT_MAX_FINALIZATION_STEPS", "16"))
REACT_PLATEAU_WINDOW = int(os.getenv("AGENT_REACT_PLATEAU_WINDOW", "4"))
REACT_MIN_STEPS_BEFORE_PLATEAU = int(os.getenv("AGENT_REACT_MIN_STEPS_BEFORE_PLATEAU", "8"))
PATH_NOT_FOUND_REPEAT_LIMIT = int(os.getenv("AGENT_PATH_NOT_FOUND_REPEAT_LIMIT", "2"))
MARKDOWN_BUDGET_TRUNCATION_NOTE = "\n\n> [内容已按控制器字符预算截断；如需更多细节，请重试当前节点并补充范围。]\n"

OUTPUT_CHAR_BUDGET_BY_SUFFIX = {
    ".md": 18000,
    ".json": 12000,
    ".yaml": 14000,
    ".yml": 14000,
    ".sql": 18000,
    ".mmd": 8000,
}

OUTPUT_CHAR_BUDGET_BY_FILE = {
    ("architecture-mapping", "architecture.md"): 24000,
    ("architecture-mapping", "module-map.json"): 12000,
    ("integration-design", "integration.md"): 18000,
    ("integration-design", "asyncapi.yaml"): 14000,
}

OUTPUT_MUST_COVER_LIMIT_BY_SUFFIX = {
    ".md": 5,
    ".json": 4,
    ".yaml": 4,
    ".yml": 4,
    ".sql": 5,
}

OUTPUT_MUST_COVER_LIMIT_BY_FILE = {
    ("architecture-mapping", "architecture.md"): 4,
    ("architecture-mapping", "module-map.json"): 4,
    ("integration-design", "integration.md"): 4,
    ("integration-design", "asyncapi.yaml"): 4,
}

CAPABILITY_SCOPE_NOTES = {
    "architecture-mapping": (
        "Focus on system boundary, container decomposition, module ownership, and allowed dependencies only. "
        "Do not absorb downstream experts' detailed integration protocols, event payloads, schema/index design, "
        "configuration matrices, deployment/ops plans, or test cases."
    ),
    "data-design": (
        "Own schema, ER relationships, indexes, and migration/rollback design. "
        "Do not re-derive the full architecture narrative, REST/Async contracts, config matrices, ops runbooks, or test cases."
    ),
    "ddd-structure": (
        "Own aggregates, bounded contexts, invariants, domain services, and context mapping. "
        "Do not expand into full DDL, full API/interface payloads, deployment/runbook content, or test plans."
    ),
    "api-design": (
        "Own request/response contracts, endpoint semantics, and error models for synchronous APIs. "
        "Reference async integration behavior only briefly when necessary; do not duplicate AsyncAPI/event payload design, DDL, config matrices, or test plans."
    ),
    "integration-design": (
        "Focus on cross-service and external integration contracts, async/sync interaction choices, idempotency, "
        "retry, timeout, and compensation. Do not expand into full REST schema catalogs, full DDL, deployment/runbook details, or exhaustive test cases."
    ),
    "flow-design": (
        "Own sequence and state/lifecycle views. "
        "Do not restate full API schemas, AsyncAPI payload details, DDL/index design, config matrices, ops runbooks, or test inventories."
    ),
    "config-design": (
        "Own configuration keys, environment differences, feature flags, and secret handling rules. "
        "Do not redesign APIs, event contracts, schema structures, observability specs, or test plans."
    ),
    "ops-design": (
        "Own SLOs, metrics, alerts, deployment checks, rollback triggers, and runbooks. "
        "Reference config keys, APIs, and events only as operational dependencies; do not redefine their detailed designs."
    ),
    "test-design": (
        "Own test inputs, coverage mapping, and verification scenarios. "
        "Do not redesign architecture, domain models, API/event contracts, schema DDL, config matrices, or ops policies."
    ),
    "design-assembler": (
        "Own synthesis, cross-artifact alignment, and traceability only. "
        "Do not invent new detailed designs that were not produced by upstream experts except for minimal consistency stitching."
    ),
    "validator": (
        "Own validation findings only. "
        "Do not create replacement designs; report gaps, conflicts, and missing evidence instead."
    ),
}

ARCHITECTURE_SCOPE_EXCLUSION_RE = re.compile(
    r"(asyncapi|event\s+contract|event\s+payload|message\s+payload|topic|idempoten|retry\s+policy|"
    r"compensation|sql|ddl|schema|table|index|migration|字段|索引|表结构|迁移|"
    r"config\s+matrix|env\s+var|feature\s+flag|配置矩阵|环境变量|"
    r"deployment|runbook|monitor|alert|sla|部署|运维|监控|告警|"
    r"test\s+case|coverage|chaos|压测|测试用例|覆盖率|混沌)",
    re.IGNORECASE,
)

# Default tools available to all subagents
DEFAULT_READ_TOOLS = {"list_files", "extract_structure", "grep_search", "read_file_chunk", "extract_lookup_values"}
DEFAULT_WRITE_TOOLS = {"write_file", "patch_file"}


def _tool_is_available(tool_name: str, tools_allowed: List[str]) -> bool:
    return tool_name in tools_allowed or "*" in tools_allowed


def _is_read_tool(tool_name: str) -> bool:
    return tool_name in DEFAULT_READ_TOOLS


def _coerce_positive_int(value: Any) -> Optional[int]:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _normalize_relative_path(raw_path: str) -> str:
    return raw_path.strip().replace("\\", "/").lstrip("./")


def _normalize_signature_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"`[^`]+`", "<ref>", text)
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _decision_focus_signature(decision: Dict[str, Any]) -> str:
    thought = _normalize_signature_text(decision.get("thought"))
    note = _normalize_signature_text(decision.get("evidence_note"))
    return " | ".join(part for part in [thought, note] if part)


def _compact_tool_signature_value(value: Any) -> Any:
    if isinstance(value, dict):
        compact: Dict[str, Any] = {}
        for key in sorted(value.keys()):
            if key in {"root_dir", "content"}:
                continue
            compact[key] = _compact_tool_signature_value(value[key])
        return compact
    if isinstance(value, list):
        return [_compact_tool_signature_value(item) for item in value[:4]]
    if isinstance(value, str):
        return value[:160]
    return value


def _tool_execution_signature(
    tool_name: str,
    tool_input: Dict[str, Any],
    tool_result: Dict[str, Any],
) -> str:
    output = dict(tool_result.get("output") or {})
    compact_output = {
        "status": tool_result.get("status"),
        "error_code": tool_result.get("error_code"),
        "path": output.get("path"),
        "project_relative_path": output.get("project_relative_path"),
        "search_hint": output.get("search_hint"),
        "match_count": len(output.get("matches") or []) if isinstance(output.get("matches"), list) else None,
        "files_count": len(output.get("files") or []) if isinstance(output.get("files"), list) else None,
        "error": _compact_tool_signature_value(output.get("error") or {}),
    }
    payload = {
        "tool_name": tool_name,
        "tool_input": _compact_tool_signature_value(tool_input),
        "tool_result": _compact_tool_signature_value(compact_output),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _dedupe_preserve_order(items: List[str]) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _normalize_expected_output_paths(expected_files: List[str]) -> set[str]:
    normalized: set[str] = set()
    for item in expected_files:
        if isinstance(item, str) and item.strip():
            normalized.add(_normalize_relative_path(item))
    return normalized


def _normalize_output_candidate_list(items: List[str]) -> List[str]:
    normalized: List[str] = []
    for item in items:
        if isinstance(item, str) and item.strip():
            normalized.append(_normalize_relative_path(item))
    return _dedupe_preserve_order(normalized)


def _match_output_candidate(raw_value: Any, candidate_outputs: List[str]) -> Optional[str]:
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None

    normalized = _normalize_relative_path(raw_value)
    candidate_set = set(candidate_outputs)
    if normalized in candidate_set:
        return normalized

    basename = Path(normalized).name
    for candidate in candidate_outputs:
        if Path(candidate).name == basename:
            return candidate
    return None


def _default_output_plan(
    capability: str,
    candidate_outputs: List[str],
    *,
    selected_outputs: Optional[List[str]] = None,
) -> Dict[str, Any]:
    selected = _normalize_output_candidate_list(selected_outputs or candidate_outputs)
    if not selected and candidate_outputs:
        selected = [candidate_outputs[0]]

    skipped = [
        {
            "path": candidate,
            "reason": "Not selected for the current requirement scope.",
        }
        for candidate in candidate_outputs
        if candidate not in set(selected)
    ]
    return {
        "capability": capability,
        "candidate_outputs": list(candidate_outputs),
        "selected_outputs": selected,
        "skipped_outputs": skipped,
        "file_order": list(selected),
        "must_cover_by_file": {path: [] for path in selected},
        "evidence_focus": [],
        "planning_notes": "",
    }


def _resolve_output_char_budget(
    state: Dict[str, Any],
    capability: str,
    target_file: str,
) -> int:
    orchestrator_config = ((state.get("design_context") or {}).get("orchestrator") or {})
    overrides = orchestrator_config.get("output_char_budgets") or {}
    normalized_target = _normalize_relative_path(target_file)
    basename = Path(normalized_target).name
    if isinstance(overrides, dict):
        for key in (normalized_target, basename):
            explicit = _coerce_positive_int(overrides.get(key))
            if explicit is not None:
                return explicit

    explicit = OUTPUT_CHAR_BUDGET_BY_FILE.get((capability, basename))
    if explicit is not None:
        return explicit
    return OUTPUT_CHAR_BUDGET_BY_SUFFIX.get(Path(normalized_target).suffix.lower(), 12000)


def _resolve_must_cover_limit(capability: str, target_file: str) -> int:
    normalized_target = _normalize_relative_path(target_file)
    basename = Path(normalized_target).name
    explicit = OUTPUT_MUST_COVER_LIMIT_BY_FILE.get((capability, basename))
    if explicit is not None:
        return explicit
    return OUTPUT_MUST_COVER_LIMIT_BY_SUFFIX.get(Path(normalized_target).suffix.lower(), 4)


def _scope_boundary_note(capability: str) -> str:
    return CAPABILITY_SCOPE_NOTES.get(
        capability,
        "Keep each artifact concise and limited to this expert's primary responsibility.",
    )


def _filter_scope_items_for_capability(capability: str, items: List[str]) -> List[str]:
    normalized_items = [str(item).strip() for item in items if str(item).strip()]
    if capability != "architecture-mapping":
        return normalized_items

    filtered = [item for item in normalized_items if not ARCHITECTURE_SCOPE_EXCLUSION_RE.search(item)]
    return filtered if filtered else normalized_items


def _constrain_output_plan(capability: str, output_plan: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(output_plan)
    selected_outputs = _normalize_output_candidate_list(normalized.get("selected_outputs") or [])
    must_cover_by_file = dict(normalized.get("must_cover_by_file") or {})
    constrained_must_cover: Dict[str, List[str]] = {}
    for target_file in selected_outputs:
        items = _filter_scope_items_for_capability(capability, must_cover_by_file.get(target_file) or [])
        constrained_must_cover[target_file] = items[: _resolve_must_cover_limit(capability, target_file)]

    evidence_focus = _filter_scope_items_for_capability(
        capability,
        list(normalized.get("evidence_focus") or []),
    )[:6]

    planning_notes = str(normalized.get("planning_notes") or "").strip()
    boundary_note = _scope_boundary_note(capability)
    if boundary_note not in planning_notes:
        planning_notes = f"{planning_notes} {boundary_note}".strip()

    normalized["selected_outputs"] = selected_outputs
    normalized["file_order"] = [item for item in (normalized.get("file_order") or []) if item in set(selected_outputs)] or list(selected_outputs)
    normalized["must_cover_by_file"] = constrained_must_cover
    normalized["evidence_focus"] = evidence_focus
    normalized["planning_notes"] = planning_notes
    return normalized


def _enforce_markdown_budget(content: str, total_budget: int) -> tuple[str, bool]:
    if total_budget <= 0 or len(content) <= total_budget:
        return content, False

    note = MARKDOWN_BUDGET_TRUNCATION_NOTE
    base_content = content
    if base_content.endswith(note):
        base_content = base_content[: -len(note)].rstrip()

    allowed = max(200, total_budget - len(note))
    trimmed = base_content[:allowed].rstrip()
    return f"{trimmed}{note}", True


def _normalize_output_plan(
    raw_plan: Any,
    *,
    capability: str,
    candidate_outputs: List[str],
) -> Dict[str, Any]:
    default_plan = _default_output_plan(capability, candidate_outputs)
    if not isinstance(raw_plan, dict):
        return default_plan

    selected_outputs: List[str] = []
    raw_selected = raw_plan.get("selected_outputs") or []
    if isinstance(raw_selected, list):
        for item in raw_selected:
            if isinstance(item, dict):
                item = item.get("path")
            matched = _match_output_candidate(item, candidate_outputs)
            if matched:
                selected_outputs.append(matched)
    selected_outputs = _normalize_output_candidate_list(selected_outputs)
    if not selected_outputs and candidate_outputs:
        selected_outputs = list(candidate_outputs)

    selected_set = set(selected_outputs)
    skipped_by_path: Dict[str, str] = {}
    raw_skipped = raw_plan.get("skipped_outputs") or []
    if isinstance(raw_skipped, list):
        for item in raw_skipped:
            reason = ""
            path_value: Any = item
            if isinstance(item, dict):
                path_value = item.get("path")
                reason = str(item.get("reason") or "").strip()
            matched = _match_output_candidate(path_value, candidate_outputs)
            if matched and matched not in selected_set:
                skipped_by_path[matched] = reason or "Not selected for the current requirement scope."

    for candidate in candidate_outputs:
        if candidate not in selected_set and candidate not in skipped_by_path:
            skipped_by_path[candidate] = "Not selected for the current requirement scope."

    file_order: List[str] = []
    raw_file_order = raw_plan.get("file_order") or []
    if isinstance(raw_file_order, list):
        for item in raw_file_order:
            matched = _match_output_candidate(item, selected_outputs)
            if matched and matched not in file_order:
                file_order.append(matched)
    for selected in selected_outputs:
        if selected not in file_order:
            file_order.append(selected)

    must_cover_by_file: Dict[str, List[str]] = {}
    raw_must_cover = raw_plan.get("must_cover_by_file") or {}
    if isinstance(raw_must_cover, dict):
        for raw_path, items in raw_must_cover.items():
            matched = _match_output_candidate(raw_path, selected_outputs)
            if not matched:
                continue
            if isinstance(items, list):
                must_cover_by_file[matched] = [
                    str(item).strip()
                    for item in items
                    if str(item).strip()
                ][:12]
    for selected in selected_outputs:
        must_cover_by_file.setdefault(selected, [])

    evidence_focus: List[str] = []
    raw_focus = raw_plan.get("evidence_focus") or []
    if isinstance(raw_focus, list):
        evidence_focus = [str(item).strip() for item in raw_focus if str(item).strip()][:16]

    normalized = {
        "capability": capability,
        "candidate_outputs": list(candidate_outputs),
        "selected_outputs": selected_outputs,
        "skipped_outputs": [
            {"path": path, "reason": reason}
            for path, reason in skipped_by_path.items()
        ],
        "file_order": file_order,
        "must_cover_by_file": must_cover_by_file,
        "evidence_focus": evidence_focus,
        "planning_notes": str(raw_plan.get("planning_notes") or "").strip(),
    }
    return _constrain_output_plan(capability, normalized)


def _normalize_react_action(action: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(action, dict):
        return None

    tool_name = str(action.get("tool_name") or "none").strip() or "none"
    tool_input = action.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}

    return {
        "tool_name": tool_name,
        "tool_input": dict(tool_input),
    }


def _normalize_react_decision(decision: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(decision)
    normalized_actions: List[Dict[str, Any]] = []
    raw_actions = normalized.get("actions")

    if isinstance(raw_actions, list):
        for raw_action in raw_actions[:MAX_ACTIONS_PER_STEP]:
            action = _normalize_react_action(raw_action)
            if action is not None:
                normalized_actions.append(action)

    if not normalized_actions:
        single_action = _normalize_react_action(
            {
                "tool_name": normalized.get("tool_name"),
                "tool_input": normalized.get("tool_input"),
            }
        )
        if single_action is not None and single_action["tool_name"] != "none":
            normalized_actions.append(single_action)

    normalized["actions"] = normalized_actions
    if normalized_actions:
        normalized["tool_name"] = normalized_actions[0]["tool_name"]
        normalized["tool_input"] = dict(normalized_actions[0]["tool_input"])
    else:
        normalized["tool_name"] = "none"
        normalized["tool_input"] = {}

    if isinstance(raw_actions, list) and len(raw_actions) > MAX_ACTIONS_PER_STEP:
        normalized["actions_truncated"] = len(raw_actions) - MAX_ACTIONS_PER_STEP

    if len(normalized_actions) > 1 and any(not _is_read_tool(action["tool_name"]) for action in normalized_actions):
        normalized["actions_restricted_to_single"] = True
        normalized_actions = normalized_actions[:1]
        normalized["actions"] = normalized_actions
        normalized["tool_name"] = normalized_actions[0]["tool_name"]
        normalized["tool_input"] = dict(normalized_actions[0]["tool_input"])

    return normalized


def _action_targets_final_artifact(
    action: Dict[str, Any],
    expected_files: List[str],
) -> Optional[str]:
    return _decision_targets_final_artifact(action, expected_files)


def _decision_targets_final_artifact(
    decision: Dict[str, Any],
    expected_files: List[str],
) -> Optional[str]:
    tool_name = str(decision.get("tool_name") or "").strip()
    if tool_name not in DEFAULT_WRITE_TOOLS:
        return None

    tool_input = dict(decision.get("tool_input") or {})
    raw_path = tool_input.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None

    normalized_path = _normalize_relative_path(raw_path)
    expected_paths = _normalize_expected_output_paths(expected_files)
    expected_basenames = {Path(path).name for path in expected_paths}
    if normalized_path in expected_paths or Path(normalized_path).name in expected_basenames:
        return normalized_path
    return None


def _resolve_candidate_files(payload: Dict[str, Any]) -> List[str]:
    candidates: List[str] = []
    project_layout = payload.get("project_layout") or {}
    baseline_dir = str(project_layout.get("baseline_dir") or "baseline").strip("/\\") or "baseline"

    explicit_candidates = payload.get("candidate_files") or []
    for raw_path in explicit_candidates:
        if isinstance(raw_path, str) and raw_path.strip():
            candidates.append(_normalize_relative_path(raw_path))

    tool_context = payload.get("tool_context") or {}
    list_files_output = tool_context.get("list_files") or {}
    list_files_root = str(list_files_output.get("root_dir") or "")
    use_baseline_prefix = (
        list_files_root == baseline_dir
        or list_files_root.replace("\\", "/").endswith(f"/{baseline_dir}")
    )
    for file_info in list_files_output.get("files") or []:
        raw_path = file_info.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        normalized = _normalize_relative_path(raw_path)
        if use_baseline_prefix and not normalized.startswith(f"{baseline_dir}/"):
            normalized = f"{baseline_dir}/{normalized}"
        candidates.append(normalized)

    for raw_path in payload.get("uploaded_files") or []:
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        normalized = _normalize_relative_path(raw_path)
        if "/" not in normalized and not normalized.startswith(f"{baseline_dir}/"):
            normalized = f"{baseline_dir}/{normalized}"
        candidates.append(normalized)

    filtered = [
        path for path in _dedupe_preserve_order(candidates)
        if path.endswith((".md", ".txt", ".json", ".yaml", ".yml"))
    ]
    if filtered:
        return filtered
    return [f"{baseline_dir}/original-requirements.md"]


def _get_runtime_project_root(payload: Dict[str, Any]) -> Optional[Path]:
    raw_value = payload.get("_runtime_project_root")
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None
    return Path(raw_value)


def _resolve_explicit_max_react_steps(state: Dict[str, Any]) -> Optional[int]:
    orchestrator_config = ((state.get("design_context") or {}).get("orchestrator") or {})
    return _coerce_positive_int(orchestrator_config.get("max_react_steps"))


def _resolve_explicit_max_finalization_steps(state: Dict[str, Any]) -> Optional[int]:
    orchestrator_config = ((state.get("design_context") or {}).get("orchestrator") or {})
    return _coerce_positive_int(orchestrator_config.get("max_finalization_steps"))


def _estimate_react_budget(
    *,
    state: Dict[str, Any],
    payload: Dict[str, Any],
    expected_files: List[str],
    agent_config: Optional["AgentFullConfig"],
    upstream_artifacts: Dict[str, List[str]],
    default_value: int,
) -> int:
    if default_value != MAX_REACT_STEPS:
        return max(1, int(default_value))

    explicit_override = _resolve_explicit_max_react_steps(state)
    if explicit_override is not None:
        return explicit_override

    # ReAct budget is now a single global cap instead of per-expert tuning.
    return MAX_REACT_STEPS


def _estimate_finalization_budget(
    *,
    state: Dict[str, Any],
    expected_files: List[str],
    default_value: int = MAX_FINALIZATION_STEPS,
) -> int:
    explicit_override = _resolve_explicit_max_finalization_steps(state)
    if explicit_override is not None:
        return explicit_override

    return max(1, max(default_value, len(expected_files) * 3))


def _relativize_path_for_prompt(raw_value: str, project_root: Optional[Path]) -> str:
    normalized = raw_value.strip()
    if not normalized:
        return normalized
    if project_root is None:
        return normalized
    try:
        candidate = Path(normalized).expanduser()
        if candidate.is_absolute():
            try:
                return candidate.resolve().relative_to(project_root.resolve()).as_posix() or "."
            except ValueError:
                return normalized
    except (OSError, RuntimeError, ValueError):
        return normalized
    return normalized


def _sanitize_prompt_payload(value: Any, project_root: Optional[Path], *, key: str | None = None) -> Any:
    if isinstance(value, dict):
        return {
            str(item_key): _sanitize_prompt_payload(item_value, project_root, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_prompt_payload(item, project_root) for item in value]
    if isinstance(value, str):
        if key == "root_dir":
            return "."
        return _relativize_path_for_prompt(value, project_root)
    return value


def _workspace_relative_dir(capability: str) -> str:
    return f"_work/{capability}"


def _extract_markdown_sections(requirement_text: str) -> List[Dict[str, Any]]:
    sections: List[Dict[str, Any]] = []
    current_heading = "Overview"
    current_level = 1
    current_lines: List[str] = []

    for raw_line in requirement_text.splitlines():
        line = raw_line.rstrip()
        heading_match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line.strip())
        if heading_match:
            body = "\n".join(current_lines).strip()
            if body:
                sections.append(
                    {
                        "heading": current_heading,
                        "level": current_level,
                        "body": body,
                    }
                )
            current_heading = heading_match.group(2).strip()
            current_level = len(heading_match.group(1))
            current_lines = []
            continue
        current_lines.append(line)

    body = "\n".join(current_lines).strip()
    if body:
        sections.append(
            {
                "heading": current_heading,
                "level": current_level,
                "body": body,
            }
        )
    return sections


def _extract_bullet_items(section_body: str, max_items: int = 8) -> List[str]:
    bullet_items: List[str] = []
    for raw_line in section_body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if re.match(r"^[-*]\s+", line) or re.match(r"^\d+[.)、]\s*", line):
            bullet_items.append(line)
        if len(bullet_items) >= max_items:
            break
    return bullet_items


def _capability_keywords(capability: str) -> List[str]:
    base_keywords = capability.replace("-", " ").split()
    capability_map = {
        "architecture-mapping": ["架构", "模块", "边界", "交互", "容器", "上下文", "复用点"],
        "data-design": ["数据", "表", "字段", "索引", "迁移", "兼容", "约束", "审计"],
        "integration-design": ["集成", "协议", "异步", "消息", "回调", "审批", "考勤", "通知", "组织"],
        "ddd-structure": ["聚合", "实体", "值对象", "领域", "命令", "DDD"],
        "flow-design": ["流程", "批次", "重算", "回溯", "差异解释"],
        "api-design": ["API", "接口", "查询", "重算", "明细", "权限"],
        "config-design": ["配置", "灰度", "开关", "权限", "回滚", "规则"],
        "ops-design": ["运维", "可观测", "监控", "告警", "指标", "审计"],
        "test-design": ["测试", "场景", "校验", "验收", "回归"],
        "validator": ["约束", "一致性", "风险", "校验"],
        "design-assembler": ["汇总", "方案", "整合", "结论"],
    }
    return _dedupe_preserve_order(base_keywords + capability_map.get(capability, []))


def _score_section_for_capability(
    section: Dict[str, Any],
    capability: str,
    expected_files: List[str],
) -> int:
    heading = str(section.get("heading") or "")
    body = str(section.get("body") or "")
    combined = f"{heading}\n{body}"
    score = 0

    priority_headings = ["强制设计约束", "非功能要求", "风险关注点", "期望设计结论", "指定设计输出要求"]
    for marker in priority_headings:
        if marker in heading:
            score += 4

    for keyword in _capability_keywords(capability):
        if keyword and keyword.lower() in combined.lower():
            score += 2

    for file_name in expected_files:
        stem = Path(file_name).stem
        if stem and stem.lower() in combined.lower():
            score += 1

    return score


def _select_focus_sections(
    requirement_text: str,
    capability: str,
    expected_files: List[str],
    *,
    max_sections: int = 6,
) -> List[Dict[str, Any]]:
    sections = _extract_markdown_sections(requirement_text)
    if not sections:
        return []

    scored_sections = sorted(
        (
            {
                **section,
                "score": _score_section_for_capability(section, capability, expected_files),
            }
            for section in sections
        ),
        key=lambda item: item["score"],
        reverse=True,
    )

    selected = [section for section in scored_sections if section["score"] > 0][:max_sections]
    if not selected:
        selected = sections[:max_sections]
    return selected


def _build_expected_file_guidance(capability: str, expected_files: List[str]) -> List[Dict[str, str]]:
    guidance_map = {
        ".sql": "落到可执行 DDL，明确新增/改造表、关键字段、索引、约束与兼容策略。",
        ".md": "覆盖设计动机、关键结构、约束、边界与引用证据。",
        ".json": "保持结构化、可被下游稳定消费，字段命名一致。",
        ".yaml": "输出可落地的契约/配置，不只给概念性描述。",
        ".yml": "输出可落地的契约/配置，不只给概念性描述。",
    }
    capability_hint = {
        "data-design": "重点回答表结构、字段、唯一键、索引、迁移/回滚。",
        "architecture-mapping": "重点回答模块边界、复用点、上下文/容器职责。",
        "integration-design": "重点回答外部系统交互、消息契约、异常补偿与幂等。",
        "api-design": "重点回答接口路径、入参出参、幂等与权限边界。",
    }.get(capability, "重点回答该专家负责的核心设计问题，并确保内容可落地。")

    guidance_rows: List[Dict[str, str]] = []
    for file_name in expected_files:
        suffix = Path(file_name).suffix.lower()
        guidance_rows.append(
            {
                "path": _normalize_relative_path(file_name),
                "guidance": f"{guidance_map.get(suffix, '输出需完整、结构化、可直接交付。')} {capability_hint}",
            }
        )
    return guidance_rows


def _build_capability_delivery_checklist(capability: str, expected_files: List[str]) -> Dict[str, Any]:
    checklist_map = {
        "data-design": {
            "must_answer": [
                "哪些存量表直接复用，哪些表需要新增字段或新增表。",
                "唯一键、索引、审计字段、历史兼容和迁移/回滚策略是否闭环。",
                "最终 SQL 是否能支撑批次、员工、segment、税差等关键查询路径。",
            ],
            "evidence_expectations": [
                "尽量落到真实表名/字段名/索引名，而不是抽象描述。",
                "迁移方案要说明增量上线顺序、历史数据兼容、失败回滚。",
            ],
        },
        "architecture-mapping": {
            "must_answer": [
                "新老模块边界如何划分，哪些容器/模块复用，哪些需要新增。",
                "前后端交互链路与上下文边界是否清晰。",
                "是否明确标注现有代码复用点和缺口。",
            ],
            "evidence_expectations": [
                "尽量引用真实模块名、类名、入口、容器职责。",
                "设计图和模块映射要能解释为什么这么拆。",
            ],
        },
        "integration-design": {
            "must_answer": [
                "外部系统之间的同步/异步边界、消息契约、补偿与幂等策略。",
                "失败重试、回调/Webhook、超时和降级策略。",
                "审批、考勤、组织、通知等系统如何参与主流程和异常流程。",
            ],
            "evidence_expectations": [
                "能落到具体接口、事件名、关键字段更好。",
                "必须解释错误处理和补偿，而不只是 happy path。",
            ],
        },
        "api-design": {
            "must_answer": [
                "接口路径、核心入参/出参、分页/筛选、幂等与权限边界。",
                "员工重算、segment 重算、差异解释、明细查询等能力是否覆盖。",
            ],
            "evidence_expectations": [
                "契约要清晰到前后端可以直接讨论联调。",
            ],
        },
        "flow-design": {
            "must_answer": [
                "批次主流程、补发回溯、员工/segment 重算、差异解释流程是否闭环。",
                "异常分支、回滚点、审计节点是否明确。",
            ],
            "evidence_expectations": [
                "流程图或步骤必须区分主干和异常路径。",
            ],
        },
        "config-design": {
            "must_answer": [
                "灰度矩阵、开关、权限、规则版本绑定和回滚策略。",
                "配置项如何作用于不同法人、薪资组、月份。",
            ],
            "evidence_expectations": [
                "配置设计不能只有字段清单，要说明生效范围和优先级。",
            ],
        },
        "ops-design": {
            "must_answer": [
                "指标、日志、审计、告警和故障恢复方案。",
                "批次、segment、税差异常、局部重算的可观测性。",
            ],
            "evidence_expectations": [
                "监控项要能转成实际运维检查项。",
            ],
        },
        "test-design": {
            "must_answer": [
                "核心场景、边界场景、回归场景和验收标准。",
                "跨月补发、segment 重算、税差校验、灰度回滚场景。",
            ],
            "evidence_expectations": [
                "测试矩阵要覆盖成功/失败/回滚/并发等关键分支。",
            ],
        },
        "ddd-structure": {
            "must_answer": [
                "聚合根、实体、值对象、命令模型与边界上下文。",
                "segment 的建模方式是否合理并解释取舍。",
            ],
            "evidence_expectations": [
                "命名和职责边界要与领域语言一致。",
            ],
        },
        "validator": {
            "must_answer": [
                "方案内部的一致性、约束满足情况、遗漏风险。",
            ],
            "evidence_expectations": [
                "指出冲突项、模糊项和残余风险。",
            ],
        },
        "design-assembler": {
            "must_answer": [
                "多专家输出是否整合成一套一致方案。",
                "跨文档术语、边界、命名和结论是否统一。",
            ],
            "evidence_expectations": [
                "合并时要标出仍待确认的风险或空白。",
            ],
        },
    }
    base = checklist_map.get(
        capability,
        {
            "must_answer": ["该专家负责的核心设计问题是否被完整回答。"],
            "evidence_expectations": ["输出必须结构化、可交付，并与证据一致。"],
        },
    )

    artifact_review_checklist: Dict[str, List[str]] = {}
    for file_name in expected_files:
        suffix = Path(file_name).suffix.lower()
        review_items = [
            "内容不能为空，且结构完整。",
            "命名与其他产物保持一致。",
            "能回指需求约束或已收集证据，而不是纯推测。",
        ]
        if suffix == ".sql":
            review_items.extend(
                [
                    "DDL 可执行，包含必要字段、约束、索引和注释。",
                    "变更对历史兼容、迁移和回滚有交代。",
                ]
            )
        elif suffix in {".yaml", ".yml", ".json"}:
            review_items.extend(
                [
                    "结构化字段完整，便于程序消费或联调。",
                    "示例值和字段语义不冲突。",
                ]
            )
        else:
            review_items.extend(
                [
                    "文档章节覆盖目标问题、设计决策、约束、风险和结论。",
                    "不是只有概念说明，而是包含可落地细节。",
                ]
            )
        artifact_review_checklist[_normalize_relative_path(file_name)] = review_items

    return {
        "must_answer": base["must_answer"],
        "evidence_expectations": base["evidence_expectations"],
        "artifact_review_checklist": artifact_review_checklist,
    }


def _build_coverage_brief(
    payload: Dict[str, Any],
    capability: str,
    candidate_files: List[str],
    expected_files: List[str],
    *,
    candidate_output_files: Optional[List[str]] = None,
    output_plan: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    requirement_text = str(payload.get("requirement") or "").strip()
    focus_sections = _select_focus_sections(requirement_text, capability, expected_files)
    candidate_output_files = _normalize_output_candidate_list(candidate_output_files or expected_files)
    output_plan = output_plan or _default_output_plan(
        capability,
        candidate_output_files,
        selected_outputs=expected_files,
    )

    def _find_section_items(marker: str, max_items: int = 6) -> List[str]:
        for section in _extract_markdown_sections(requirement_text):
            if marker in str(section.get("heading") or ""):
                items = _extract_bullet_items(str(section.get("body") or ""), max_items=max_items)
                if items:
                    return items
        return []

    return {
        "capability": capability,
        "candidate_files": candidate_files,
        "candidate_output_files": candidate_output_files,
        "expected_files": expected_files,
        "selected_outputs": list(output_plan.get("selected_outputs") or expected_files),
        "skipped_outputs": list(output_plan.get("skipped_outputs") or []),
        "file_order": list(output_plan.get("file_order") or expected_files),
        "must_cover_by_file": dict(output_plan.get("must_cover_by_file") or {}),
        "evidence_focus": list(output_plan.get("evidence_focus") or []),
        "planning_notes": str(output_plan.get("planning_notes") or ""),
        "expected_file_guidance": _build_expected_file_guidance(capability, expected_files),
        "delivery_checklist": _build_capability_delivery_checklist(capability, expected_files),
        "focus_sections": [
            {
                "heading": section.get("heading"),
                "score": section.get("score"),
                "must_cover_points": _extract_bullet_items(str(section.get("body") or ""), max_items=6),
                "excerpt": _summarize_value_for_prompt(str(section.get("body") or ""), max_string=600),
            }
            for section in focus_sections
        ],
        "hard_constraints": _find_section_items("强制设计约束", max_items=8),
        "non_functional_requirements": _find_section_items("非功能要求", max_items=8),
        "risks": _find_section_items("风险关注点", max_items=8),
        "target_outcomes": _find_section_items("期望设计结论", max_items=8),
    }


def _build_requirement_digest(
    payload: Dict[str, Any],
    candidate_files: List[str],
    capability: str,
    expected_files: List[str],
    *,
    candidate_output_files: Optional[List[str]] = None,
    output_plan: Optional[Dict[str, Any]] = None,
) -> str:
    requirement_text = str(payload.get("requirement") or "").strip()
    coverage_brief = _build_coverage_brief(
        payload,
        capability,
        candidate_files,
        expected_files,
        candidate_output_files=candidate_output_files,
        output_plan=output_plan,
    )
    structure_entries = ((payload.get("tool_context") or {}).get("extract_structure") or {}).get("files") or []
    headings: List[str] = []
    for entry in structure_entries:
        if not isinstance(entry, dict):
            continue
        for heading in entry.get("headings") or []:
            if isinstance(heading, str) and heading.strip():
                headings.append(heading.strip())

    lines = [
        "# Requirement Digest",
        "",
        f"- Project: {payload.get('project_id') or payload.get('project_name') or 'unknown'}",
        f"- Version: {payload.get('version') or 'unknown'}",
    ]

    active_agents = [agent for agent in payload.get("active_agents") or [] if isinstance(agent, str) and agent.strip()]
    if active_agents:
        lines.append(f"- Active agents: {', '.join(active_agents)}")
    if candidate_files:
        lines.append(f"- Baseline files: {', '.join(candidate_files[:10])}")
    candidate_output_files = coverage_brief.get("candidate_output_files") or []
    if candidate_output_files:
        lines.append(f"- Candidate outputs: {', '.join(candidate_output_files)}")
    if expected_files:
        lines.append(f"- Selected outputs: {', '.join(expected_files)}")

    skipped_outputs = coverage_brief.get("skipped_outputs") or []
    if skipped_outputs:
        lines.extend(["", "## Skipped Candidate Outputs"])
        for row in skipped_outputs:
            if isinstance(row, dict) and row.get("path"):
                lines.append(f"- {row['path']}: {row.get('reason') or 'Not selected for this run.'}")

    file_guidance = coverage_brief.get("expected_file_guidance") or []
    if file_guidance:
        lines.extend(
            [
                "",
                "## Output Targets",
                *[
                    f"- {row['path']}: {row['guidance']}"
                    for row in file_guidance
                    if isinstance(row, dict) and row.get("path") and row.get("guidance")
                ],
            ]
        )

    file_order = coverage_brief.get("file_order") or []
    must_cover_by_file = coverage_brief.get("must_cover_by_file") or {}
    evidence_focus = coverage_brief.get("evidence_focus") or []
    planning_notes = str(coverage_brief.get("planning_notes") or "").strip()
    if file_order or must_cover_by_file or evidence_focus or planning_notes:
        lines.append("")
        lines.append("## Output Plan")
        if file_order:
            lines.append(f"- File order: {', '.join(file_order)}")
        if evidence_focus:
            lines.extend(f"- Evidence focus: {item}" for item in evidence_focus)
        if planning_notes:
            lines.append(f"- Planning notes: {planning_notes}")
        for file_name in file_order:
            items = must_cover_by_file.get(file_name) or []
            if not items:
                continue
            lines.append(f"### {file_name}")
            lines.extend(f"- {item}" for item in items[:10])

    delivery_checklist = coverage_brief.get("delivery_checklist") or {}
    if delivery_checklist:
        must_answer = delivery_checklist.get("must_answer") or []
        evidence_expectations = delivery_checklist.get("evidence_expectations") or []
        artifact_review_checklist = delivery_checklist.get("artifact_review_checklist") or {}
        if must_answer:
            lines.extend(["", "## Expert Must Answer", *[f"- {item}" for item in must_answer]])
        if evidence_expectations:
            lines.extend(["", "## Evidence Expectations", *[f"- {item}" for item in evidence_expectations]])
        if artifact_review_checklist:
            lines.append("")
            lines.append("## Artifact Review Checklist")
            for file_name, items in artifact_review_checklist.items():
                lines.append(f"### {file_name}")
                lines.extend(f"- {item}" for item in items[:8])

    if headings:
        lines.extend(
            [
                "",
                "## Outline",
                *[f"- {heading}" for heading in headings[:25]],
            ]
        )
        if len(headings) > 25:
            lines.append(f"- ... ({len(headings) - 25} more headings omitted)")

    focus_sections = coverage_brief.get("focus_sections") or []
    if focus_sections:
        lines.extend(["", "## Must-Cover Sections"])
        for section in focus_sections:
            heading = section.get("heading") or "Unknown Section"
            lines.append(f"### {heading}")
            points = section.get("must_cover_points") or []
            if points:
                lines.extend(f"- {point}" for point in points)
            excerpt = str(section.get("excerpt") or "").strip()
            if excerpt:
                lines.append(excerpt)

    for title, key in (
        ("Hard Constraints", "hard_constraints"),
        ("Non-Functional Requirements", "non_functional_requirements"),
        ("Risks", "risks"),
        ("Target Outcomes", "target_outcomes"),
    ):
        items = coverage_brief.get(key) or []
        if items:
            lines.extend(["", f"## {title}", *[f"- {item}" for item in items]])

    if requirement_text:
        excerpt_limit = 2400
        excerpt = requirement_text[:excerpt_limit]
        if len(requirement_text) > excerpt_limit:
            excerpt = f"{excerpt}\n...[truncated {len(requirement_text) - excerpt_limit} chars]"
        lines.extend(
            [
                "",
                "## Requirement Excerpt",
                excerpt,
            ]
        )
    else:
        lines.extend(
            [
                "",
                "## Requirement Excerpt",
                "(No inline requirement text found. Read the baseline files if more detail is needed.)",
            ]
        )

    return "\n".join(lines).strip() + "\n"


def _collect_artifact_status(
    artifacts_dir: Path,
    expected_files: List[str],
) -> List[Dict[str, Any]]:
    status_rows: List[Dict[str, Any]] = []
    for file_name in expected_files:
        artifact_path = artifacts_dir / file_name
        exists = artifact_path.exists() and artifact_path.is_file()
        size_bytes = artifact_path.stat().st_size if exists else 0
        status_rows.append(
            {
                "path": _normalize_relative_path(file_name),
                "exists": exists,
                "size_bytes": size_bytes,
            }
        )
    return status_rows


def _ordered_selected_outputs(output_plan: Dict[str, Any], expected_files: List[str]) -> List[str]:
    ordered: List[str] = []
    for item in output_plan.get("file_order") or []:
        matched = _match_output_candidate(item, expected_files)
        if matched and matched not in ordered:
            ordered.append(matched)
    for item in expected_files:
        if item not in ordered:
            ordered.append(item)
    return ordered


def _all_expected_artifacts_complete(
    artifacts_dir: Path,
    expected_files: List[str],
) -> bool:
    for file_name in expected_files:
        artifact_path = artifacts_dir / file_name
        if not artifact_path.exists() or not artifact_path.is_file():
            return False
        if not artifact_path.read_text(encoding="utf-8").strip():
            return False
    return True


def _persist_workspace_snapshot(
    *,
    project_path: Path,
    payload: Dict[str, Any],
    capability: str,
    candidate_files: List[str],
    candidate_output_files: List[str],
    expected_files: List[str],
    output_plan: Dict[str, Any],
    observations: List[Dict[str, Any]],
    react_trace: List[Dict[str, Any]],
    upstream_artifacts: Dict[str, List[str]],
    artifacts_dir: Path,
    work_dir: Path,
    final_trace: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, str]:
    final_trace = final_trace or []
    project_root = project_path
    work_dir.mkdir(parents=True, exist_ok=True)

    requirement_digest_path = work_dir / "requirement-digest.md"
    coverage_brief_path = work_dir / "coverage-brief.json"
    output_plan_path = work_dir / "output-plan.json"
    observations_path = work_dir / "grounded-observations.jsonl"
    observations_summary_path = work_dir / "grounded-observations-summary.json"
    react_trace_path = work_dir / "react-trace.json"
    final_trace_path = work_dir / "finalization-trace.json"
    workspace_index_path = work_dir / "workspace-index.json"

    requirement_digest_path.write_text(
        _build_requirement_digest(
            payload,
            candidate_files,
            capability,
            expected_files,
            candidate_output_files=candidate_output_files,
            output_plan=output_plan,
        ),
        encoding="utf-8",
    )
    coverage_brief_path.write_text(
        json.dumps(
            _build_coverage_brief(
                payload,
                capability,
                candidate_files,
                expected_files,
                candidate_output_files=candidate_output_files,
                output_plan=output_plan,
            ),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    output_plan_path.write_text(
        json.dumps(_sanitize_prompt_payload(output_plan, project_root), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with observations_path.open("w", encoding="utf-8") as handle:
        for observation in observations:
            sanitized = _sanitize_prompt_payload(observation, project_root)
            handle.write(json.dumps(sanitized, ensure_ascii=False) + "\n")

    observations_summary = _compact_observations_for_prompt(
        observations,
        capability,
        "final",
        project_root=project_root,
    )
    observations_summary_path.write_text(
        json.dumps(observations_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    react_trace_path.write_text(
        json.dumps(_sanitize_prompt_payload(react_trace, project_root), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    final_trace_path.write_text(
        json.dumps(_sanitize_prompt_payload(final_trace, project_root), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    workspace_index = {
        "capability": capability,
        "candidate_files": candidate_files,
        "candidate_output_files": candidate_output_files,
        "expected_files": expected_files,
        "selected_outputs": list(output_plan.get("selected_outputs") or expected_files),
        "skipped_outputs": list(output_plan.get("skipped_outputs") or []),
        "requirement_digest_path": _normalize_relative_path(str(requirement_digest_path.relative_to(artifacts_dir))),
        "coverage_brief_path": _normalize_relative_path(str(coverage_brief_path.relative_to(artifacts_dir))),
        "output_plan_path": _normalize_relative_path(str(output_plan_path.relative_to(artifacts_dir))),
        "grounded_observations_path": _normalize_relative_path(str(observations_path.relative_to(artifacts_dir))),
        "grounded_observations_summary_path": _normalize_relative_path(str(observations_summary_path.relative_to(artifacts_dir))),
        "react_trace_path": _normalize_relative_path(str(react_trace_path.relative_to(artifacts_dir))),
        "finalization_trace_path": _normalize_relative_path(str(final_trace_path.relative_to(artifacts_dir))),
        "upstream_artifacts": upstream_artifacts,
        "current_expected_artifacts": _collect_artifact_status(artifacts_dir, expected_files),
        "observation_count": len(observations),
        "react_step_count": len(react_trace),
        "finalization_step_count": len(final_trace),
    }
    workspace_index_path.write_text(
        json.dumps(_sanitize_prompt_payload(workspace_index, project_root), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "requirement_digest": _normalize_relative_path(str(requirement_digest_path.relative_to(artifacts_dir))),
        "coverage_brief": _normalize_relative_path(str(coverage_brief_path.relative_to(artifacts_dir))),
        "output_plan": _normalize_relative_path(str(output_plan_path.relative_to(artifacts_dir))),
        "grounded_observations": _normalize_relative_path(str(observations_path.relative_to(artifacts_dir))),
        "grounded_observations_summary": _normalize_relative_path(str(observations_summary_path.relative_to(artifacts_dir))),
        "workspace_index": _normalize_relative_path(str(workspace_index_path.relative_to(artifacts_dir))),
        "react_trace": _normalize_relative_path(str(react_trace_path.relative_to(artifacts_dir))),
        "finalization_trace": _normalize_relative_path(str(final_trace_path.relative_to(artifacts_dir))),
    }


def _write_finalization_step_log(
    *,
    logs_dir: Path,
    capability: str,
    step: int,
    decision: Dict[str, Any],
    artifact_status: List[Dict[str, Any]],
    workspace_paths: Dict[str, str],
    project_root: Path,
    tool_results: Optional[List[Dict[str, Any]]] = None,
) -> Path:
    finalization_dir = logs_dir / "finalization" / capability
    finalization_dir.mkdir(parents=True, exist_ok=True)
    log_path = finalization_dir / f"step-{step:02d}.json"
    payload = {
        "step": step,
        "decision": _sanitize_prompt_payload(decision, project_root),
        "artifact_status": _sanitize_prompt_payload(artifact_status, project_root),
        "workspace_paths": _sanitize_prompt_payload(workspace_paths, project_root),
        "tool_results": _sanitize_prompt_payload(tool_results or [], project_root),
    }
    log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return log_path


def _build_asset_tool_section(tools_allowed: List[str], configured_assets: Dict[str, Any] | None) -> str:
    configured_assets = configured_assets or {}
    asset_lines: List[str] = []

    if configured_assets.get("repositories") and _tool_is_available("clone_repository", tools_allowed):
        asset_lines.append("- clone_repository (Clone or update a project-shared repository cache for grounded code inspection; reuse the returned `project_relative_path`/`search_hint` in later `repos_dir` lookups)")
    if configured_assets.get("databases") and _tool_is_available("query_database", tools_allowed):
        asset_lines.append("- query_database (Inspect configured database schemas or run read-only SQL)")
    if configured_assets.get("knowledge_bases") and _tool_is_available("query_knowledge_base", tools_allowed):
        asset_lines.append("- query_knowledge_base (Search configured knowledge bases for terms, feature trees, and design docs)")

    if not asset_lines:
        return ""

    return f"""
Asset-aware tools:
{chr(10).join(asset_lines)}
"""


def _get_configured_asset_items(configured_assets: Dict[str, Any] | None, asset_kind: str) -> List[Dict[str, Any]]:
    configured_assets = configured_assets or {}
    bucket = configured_assets.get(asset_kind) or {}
    items = bucket.get("items") or []
    return [item for item in items if isinstance(item, dict)]


def _format_asset_examples(configured_assets: Dict[str, Any] | None) -> str:
    configured_assets = configured_assets or {}
    sections: List[str] = []

    repositories = _get_configured_asset_items(configured_assets, "repositories")
    if repositories:
        repo_lines = [
            f'  - `{item.get("id")}`: {item.get("name") or item.get("description") or "repository"}'
            for item in repositories
        ]
        repo_example = repositories[0].get("id")
        sections.append(
            "\n".join(
                [
                    "Configured repositories:",
                    *repo_lines,
                    f'  Example: `{{"tool_name":"clone_repository","tool_input":{{"repo_id":"{repo_example}"}}}}`',
                ]
            )
        )

    databases = _get_configured_asset_items(configured_assets, "databases")
    if databases:
        db_lines = [
            f'  - `{item.get("id")}`: {item.get("name") or item.get("description") or "database"}'
            for item in databases
        ]
        db_example = databases[0].get("id")
        sections.append(
            "\n".join(
                [
                    "Configured databases:",
                    *db_lines,
                    f'  Example: `{{"tool_name":"query_database","tool_input":{{"db_id":"{db_example}","query_type":"list_tables"}}}}`',
                ]
            )
        )

    knowledge_bases = _get_configured_asset_items(configured_assets, "knowledge_bases")
    if knowledge_bases:
        kb_lines = [
            f'  - `{item.get("id")}` ({item.get("type") or "local"}): {item.get("name") or item.get("description") or "knowledge base"}'
            for item in knowledge_bases
        ]
        kb_example = knowledge_bases[0].get("id")
        sections.append(
            "\n".join(
                [
                    "Configured knowledge bases:",
                    *kb_lines,
                    f'  Example: `{{"tool_name":"query_knowledge_base","tool_input":{{"kb_id":"{kb_example}","query_type":"search_design_docs","keyword":"补发"}}}}`',
                ]
            )
        )

    if not sections:
        return ""
    return "\n\nKnown configured asset IDs:\n" + "\n\n".join(sections)


def _resolve_single_asset_id(
    configured_assets: Dict[str, Any] | None,
    asset_kind: str,
    requested_id: Any,
) -> tuple[Optional[str], Optional[str]]:
    items = _get_configured_asset_items(configured_assets, asset_kind)
    asset_ids = [str(item.get("id")) for item in items if item.get("id")]
    bucket = (configured_assets or {}).get(asset_kind) or {}
    is_complete_catalog = len(asset_ids) == int(bucket.get("count") or len(asset_ids))

    if isinstance(requested_id, str) and requested_id.strip():
        requested_id = requested_id.strip()
        if is_complete_catalog and requested_id not in asset_ids:
            return None, (
                f"Unknown {asset_kind[:-1]} id '{requested_id}'. "
                f"Available ids: {', '.join(asset_ids) if asset_ids else '(none)'}."
            )
        return requested_id, None

    if len(asset_ids) == 1:
        return asset_ids[0], f"Auto-selected the only configured {asset_kind[:-1]} id '{asset_ids[0]}'."

    if len(asset_ids) > 1:
        return None, f"Missing {asset_kind[:-1]} id. Choose one of: {', '.join(asset_ids)}."

    return None, f"No configured {asset_kind} are available for this project."


def _preflight_asset_tool_action(
    action: Dict[str, Any],
    configured_assets: Dict[str, Any] | None,
) -> tuple[Dict[str, Any], Optional[str], Optional[str]]:
    tool_name = str(action.get("tool_name") or "").strip()
    tool_input = dict(action.get("tool_input") or {})

    if tool_name == "clone_repository":
        resolved_id, note = _resolve_single_asset_id(configured_assets, "repositories", tool_input.get("repo_id"))
        if resolved_id is None:
            return tool_input, None, note
        tool_input["repo_id"] = resolved_id
        return tool_input, note, None

    if tool_name == "query_database":
        resolved_id, note = _resolve_single_asset_id(configured_assets, "databases", tool_input.get("db_id"))
        if resolved_id is None:
            return tool_input, None, note
        tool_input["db_id"] = resolved_id
        return tool_input, note, None

    if tool_name == "query_knowledge_base":
        kb_id = tool_input.get("kb_id")
        if kb_id is None or (isinstance(kb_id, str) and not kb_id.strip()):
            resolved_id, note = _resolve_single_asset_id(configured_assets, "knowledge_bases", kb_id)
            if resolved_id is not None:
                tool_input["kb_id"] = resolved_id
                return tool_input, note, None
            if "Missing knowledge_base id" in str(note):
                return tool_input, None, note
        else:
            resolved_id, note = _resolve_single_asset_id(configured_assets, "knowledge_bases", kb_id)
            if resolved_id is None:
                return tool_input, None, note
            tool_input["kb_id"] = resolved_id
        return tool_input, None, None

    return tool_input, None, None


def _build_tool_name_options(tools_allowed: List[str], configured_assets: Dict[str, Any] | None) -> str:
    tool_names = ["list_files", "read_file_chunk", "grep_search", "extract_structure", "extract_lookup_values"]
    configured_assets = configured_assets or {}

    if _tool_is_available("write_file", tools_allowed):
        tool_names.append("write_file")
    if _tool_is_available("patch_file", tools_allowed):
        tool_names.append("patch_file")
    if _tool_is_available("run_command", tools_allowed):
        tool_names.append("run_command")
    if configured_assets.get("repositories") and _tool_is_available("clone_repository", tools_allowed):
        tool_names.append("clone_repository")
    if configured_assets.get("databases") and _tool_is_available("query_database", tools_allowed):
        tool_names.append("query_database")
    if configured_assets.get("knowledge_bases") and _tool_is_available("query_knowledge_base", tools_allowed):
        tool_names.append("query_knowledge_base")

    tool_names.append("none")
    return " | ".join(f'"{name}"' for name in tool_names)


def _build_tool_contract_section(tools_allowed: List[str], candidate_files: List[str]) -> str:
    read_example = candidate_files[0] if candidate_files else "baseline/original-requirements.md"
    write_examples: List[str] = []
    if _tool_is_available("write_file", tools_allowed):
        write_examples.append(
            '- `write_file`: `{"path":"architecture.md","content":"..."}`. `path` is relative to `artifacts/`.'
        )
    if _tool_is_available("patch_file", tools_allowed):
        write_examples.append(
            '- `patch_file`: `{"path":"architecture.md","old_content":"...","new_content":"..."}`. `path` is relative to `artifacts/`.'
        )
    if _tool_is_available("run_command", tools_allowed):
        write_examples.append(
            '- `run_command`: `{"command":"python -m unittest","timeout":30}`. Runs from project root `.`.'
        )

    write_block = "\n".join(write_examples)
    if write_block:
        write_block = f"\n{write_block}"

    return f"""
Current location:
- Project root: `.`
- Baseline directory: `baseline/`
- Artifacts directory: `artifacts/`
- Evidence directory: `evidence/`
- Candidate requirement files: {candidate_files}

Tool input contract:
- Do NOT include `root_dir`. The runtime injects it automatically.
- For read tools, all `path` values are relative to project root `.`.
- For write tools, all `path` values are relative to `artifacts/`.
- `list_files`: use `{{}}` to inspect project root, or `{{"repos_dir":"baseline"}}` to inspect a subdirectory.
- `read_file_chunk`: use `{{"path":"{read_example}","start_line":1,"end_line":120}}`. Optional: `search_root`, `repos_dir`.
- `extract_structure`: use `{{"files":["{read_example}"]}}`. Do not send `path`.
- `grep_search`: use `{{"pattern":"Kafka|Redis|callback"}}`. Optional: `repos_dir`. Do not send `file_glob`, `include`, or ad-hoc filters.{write_block}
""".strip()


def _get_prompt_budget_profile(capability: str, stage: str) -> Dict[str, int]:
    profile = {
        "max_depth": 3,
        "max_string": 500,
        "max_list_items": 6,
        "max_dict_items": 12,
        "max_observations": 6,
    }

    if stage == "react":
        profile.update(
            {
                "max_string": 300,
                "max_list_items": 5,
                "max_dict_items": 10,
                "max_observations": 5,
            }
        )

    if capability in {"design-assembler", "validator"} and stage == "final":
        profile.update(
            {
                "max_depth": 2,
                "max_string": 180,
                "max_list_items": 3,
                "max_dict_items": 8,
                "max_observations": 4,
            }
        )

    return profile


def _summarize_value_for_prompt(
    value: Any,
    *,
    max_depth: int = 3,
    max_string: int = 500,
    max_list_items: int = 6,
    max_dict_items: int = 12,
) -> Any:
    if max_depth < 0:
        return "[Truncated]"

    if isinstance(value, str):
        if len(value) <= max_string:
            return value
        return f"{value[:max_string]}...[truncated {len(value) - max_string} chars]"

    if isinstance(value, list):
        items = [
            _summarize_value_for_prompt(
                item,
                max_depth=max_depth - 1,
                max_string=max_string,
                max_list_items=max_list_items,
                max_dict_items=max_dict_items,
            )
            for item in value[:max_list_items]
        ]
        if len(value) > max_list_items:
            items.append(f"[{len(value) - max_list_items} more items omitted]")
        return items

    if isinstance(value, dict):
        summary: Dict[str, Any] = {}
        keys = list(value.keys())[:max_dict_items]
        for key in keys:
            summary[str(key)] = _summarize_value_for_prompt(
                value[key],
                max_depth=max_depth - 1,
                max_string=max_string,
                max_list_items=max_list_items,
                max_dict_items=max_dict_items,
            )
        if len(value) > max_dict_items:
            summary["_omitted_keys"] = len(value) - max_dict_items
        return summary

    return value


def _compact_payload_for_prompt(payload: Dict[str, Any], capability: str, stage: str) -> Dict[str, Any]:
    profile = _get_prompt_budget_profile(capability, stage)
    project_root = _get_runtime_project_root(payload)
    compact: Dict[str, Any] = {}

    for key in (
        "project_name",
        "project_id",
        "version",
        "requirement",
        "active_agents",
        "project_layout",
        "candidate_output_files",
        "selected_outputs",
    ):
        if key in payload:
            compact[key] = payload[key]

    uploaded_files = payload.get("uploaded_files") or []
    if uploaded_files:
        compact["uploaded_files"] = uploaded_files[:10]
        if len(uploaded_files) > 10:
            compact["uploaded_files_omitted"] = len(uploaded_files) - 10

    candidate_files = payload.get("candidate_files") or []
    if candidate_files:
        compact["candidate_files"] = candidate_files[:10]
        if len(candidate_files) > 10:
            compact["candidate_files_omitted"] = len(candidate_files) - 10

    if "configured_assets" in payload:
        compact["configured_assets"] = _summarize_value_for_prompt(
            payload["configured_assets"],
            max_depth=min(profile["max_depth"], 3),
            max_string=min(profile["max_string"], 200),
            max_list_items=min(profile["max_list_items"], 5),
            max_dict_items=min(profile["max_dict_items"], 8),
        )

    tool_context = payload.get("tool_context") or {}
    if tool_context:
        sanitized_tool_context = _sanitize_prompt_payload(tool_context, project_root)
        compact["tool_context"] = {
            "list_files": _summarize_value_for_prompt(
                sanitized_tool_context.get("list_files") or {},
                max_depth=min(profile["max_depth"], 3),
                max_string=min(profile["max_string"], 200),
                max_list_items=min(profile["max_list_items"], 6),
                max_dict_items=min(profile["max_dict_items"], 8),
            ),
            "extract_structure": _summarize_value_for_prompt(
                (sanitized_tool_context.get("extract_structure") or {}).get("files") or [],
                max_depth=min(profile["max_depth"], 3),
                max_string=min(profile["max_string"], 200),
                max_list_items=min(profile["max_list_items"], 6),
                max_dict_items=min(profile["max_dict_items"], 8),
            ),
        }

    if payload.get("human_inputs"):
        compact["human_inputs"] = _summarize_value_for_prompt(
            payload["human_inputs"],
            max_depth=min(profile["max_depth"], 3),
            max_string=min(profile["max_string"], 300),
            max_list_items=min(profile["max_list_items"], 4),
            max_dict_items=min(profile["max_dict_items"], 8),
        )

    if payload.get("output_plan"):
        compact["output_plan"] = _summarize_value_for_prompt(
            payload["output_plan"],
            max_depth=min(profile["max_depth"], 4),
            max_string=min(profile["max_string"], 240),
            max_list_items=min(profile["max_list_items"], 6),
            max_dict_items=min(profile["max_dict_items"], 10),
        )

    return compact


def _compact_observations_for_prompt(
    observations: List[Dict[str, Any]],
    capability: str,
    stage: str,
    *,
    project_root: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    profile = _get_prompt_budget_profile(capability, stage)
    compact_observations: List[Dict[str, Any]] = []

    selected_observations = observations[-profile["max_observations"] :]
    for observation in selected_observations:
        sanitized_tool_input = _sanitize_prompt_payload(observation.get("tool_input") or {}, project_root)
        sanitized_tool_output = _sanitize_prompt_payload(observation.get("tool_output") or {}, project_root)
        compact_observations.append(
            {
                "step": observation.get("step"),
                "action_index": observation.get("action_index"),
                "tool_name": observation.get("tool_name"),
                "evidence_note": observation.get("evidence_note", ""),
                "tool_input": _summarize_value_for_prompt(
                    sanitized_tool_input,
                    max_depth=max(1, profile["max_depth"] - 1),
                    max_string=min(profile["max_string"], 200),
                    max_list_items=min(profile["max_list_items"], 4),
                    max_dict_items=min(profile["max_dict_items"], 8),
                ),
                "tool_output": _summarize_value_for_prompt(
                    sanitized_tool_output,
                    max_depth=max(1, profile["max_depth"] - 1),
                    max_string=profile["max_string"],
                    max_list_items=min(profile["max_list_items"], 4),
                    max_dict_items=min(profile["max_dict_items"], 10),
                ),
            }
        )

    if len(observations) > len(selected_observations):
        compact_observations.append(
            {
                "omitted_observations": len(observations) - len(selected_observations)
            }
        )

    return compact_observations


def _compact_finalization_observations_for_prompt(
    observations: List[Dict[str, Any]],
    *,
    max_observations: int = 4,
) -> List[Dict[str, Any]]:
    compact_rows: List[Dict[str, Any]] = []
    selected = observations[-max_observations:]

    for observation in selected:
        tool_name = str(observation.get("tool_name") or "")
        tool_input = dict(observation.get("tool_input") or {})
        tool_output = dict(observation.get("tool_output") or {})
        compact_input: Dict[str, Any] = {}
        compact_output: Dict[str, Any] = {}

        if "path" in tool_input:
            compact_input["path"] = tool_input.get("path")
        if "start_line" in tool_input:
            compact_input["start_line"] = tool_input.get("start_line")
        if "end_line" in tool_input:
            compact_input["end_line"] = tool_input.get("end_line")
        if "files" in tool_input and isinstance(tool_input.get("files"), list):
            compact_input["files"] = tool_input.get("files")[:3]
        if "pattern" in tool_input:
            compact_input["pattern"] = _summarize_value_for_prompt(str(tool_input.get("pattern") or ""), max_string=120)
        if "content" in tool_input and isinstance(tool_input.get("content"), str):
            compact_input["content_summary"] = f"<omitted {len(tool_input['content'])} chars>"
        if "old_content" in tool_input and isinstance(tool_input.get("old_content"), str):
            compact_input["old_content_summary"] = f"<omitted {len(tool_input['old_content'])} chars>"
        if "new_content" in tool_input and isinstance(tool_input.get("new_content"), str):
            compact_input["new_content_summary"] = f"<omitted {len(tool_input['new_content'])} chars>"

        if "path" in tool_output:
            compact_output["path"] = tool_output.get("path")
        if "size_bytes" in tool_output:
            compact_output["size_bytes"] = tool_output.get("size_bytes")
        if "message" in tool_output:
            compact_output["message"] = _summarize_value_for_prompt(str(tool_output.get("message") or ""), max_string=120)
        if "content" in tool_output and isinstance(tool_output.get("content"), str):
            compact_output["content_summary"] = f"<omitted {len(tool_output['content'])} chars>"
        if "matches" in tool_output and isinstance(tool_output.get("matches"), list):
            compact_output["match_count"] = len(tool_output["matches"])

        compact_rows.append(
            {
                "step": observation.get("step"),
                "action_index": observation.get("action_index"),
                "tool_name": tool_name,
                "evidence_note": _summarize_value_for_prompt(str(observation.get("evidence_note") or ""), max_string=160),
                "tool_input": compact_input,
                "tool_output": compact_output,
                "stage": observation.get("stage"),
            }
        )

    if len(observations) > len(selected):
        compact_rows.append({"omitted_observations": len(observations) - len(selected)})

    return compact_rows


def _compact_payload_for_finalization_prompt(
    payload: Dict[str, Any],
    expected_files: List[str],
) -> Dict[str, Any]:
    compact = {
        "project_name": payload.get("project_name") or payload.get("project_id"),
        "project_id": payload.get("project_id"),
        "version": payload.get("version"),
        "candidate_files": (payload.get("candidate_files") or [])[:5],
        "candidate_output_files": (payload.get("candidate_output_files") or [])[:8],
        "selected_outputs": (payload.get("selected_outputs") or expected_files)[:8],
        "expected_files": expected_files,
    }

    configured_assets = payload.get("configured_assets") or {}
    if isinstance(configured_assets, dict):
        compact["configured_asset_counts"] = {
            "repositories": ((configured_assets.get("repositories") or {}).get("count") or 0),
            "databases": ((configured_assets.get("databases") or {}).get("count") or 0),
            "knowledge_bases": ((configured_assets.get("knowledge_bases") or {}).get("count") or 0),
        }

    return compact


def _compact_payload_for_output_planning_prompt(payload: Dict[str, Any]) -> Dict[str, Any]:
    compact: Dict[str, Any] = {
        "project_name": payload.get("project_name") or payload.get("project_id"),
        "project_id": payload.get("project_id"),
        "version": payload.get("version"),
        "active_agents": (payload.get("active_agents") or [])[:12],
        "candidate_files": (payload.get("candidate_files") or [])[:8],
    }
    configured_assets = payload.get("configured_assets") or {}
    if isinstance(configured_assets, dict):
        compact["configured_asset_counts"] = {
            "repositories": ((configured_assets.get("repositories") or {}).get("count") or 0),
            "databases": ((configured_assets.get("databases") or {}).get("count") or 0),
            "knowledge_bases": ((configured_assets.get("knowledge_bases") or {}).get("count") or 0),
        }
    return compact


def build_output_planning_prompt(
    capability: str,
    prompt_instructions: str,
    candidate_outputs: List[str],
) -> str:
    candidate_block = "\n".join(
        f"- {path} (target <= {_resolve_output_char_budget({}, capability, path)} chars)"
        for path in candidate_outputs
    ) or "- (none)"
    custom_section = ""
    if prompt_instructions:
        custom_section = f"""
Custom Instructions from SKILL.md:
{prompt_instructions[:1200]}
"""

    return f"""
You are the {capability} output planner.
Treat the listed outputs as candidate deliverables, not mandatory files.
Choose only the files that are actually needed for this requirement scope.

Candidate outputs:
{candidate_block}

{custom_section}
Rules:
1. Select the minimum useful artifact set that still lets this expert deliver grounded, actionable output.
2. If some information can be referenced inside another selected document, prefer that over producing an extra file.
3. Every selected file must have a clear purpose and must-cover points.
4. Skipped files need a short reason.
5. The downstream ReAct loop will gather evidence around the selected outputs, so make the plan concrete.
6. Keep each file concise and scoped to this expert's responsibility; avoid absorbing downstream experts' detailed design work.
7. Respect the approximate per-file char budgets shown above when choosing scope and must-cover items.

Return JSON in artifacts.output_plan:
{{
  "selected_outputs": ["output.md"],
  "skipped_outputs": [
    {{"path": "extra.json", "reason": "Covered sufficiently inside output.md"}}
  ],
  "file_order": ["output.md"],
  "must_cover_by_file": {{
    "output.md": ["what this file must answer"]
  }},
  "evidence_focus": ["what evidence the expert should gather next"],
  "planning_notes": "optional short planning rationale"
}}
""".strip()


def default_plan_outputs(
    generate_with_llm_fn: Callable[[str, str, List[str], int, Dict[str, Any] | None, str | None, str | None, str | None], SubagentOutput],
    capability: str,
    project_id: str,
    version: str,
    payload: Dict[str, Any],
    candidate_files: List[str],
    candidate_outputs: List[str],
    agent_config: Optional["AgentFullConfig"] = None,
) -> Dict[str, Any]:
    candidate_outputs = _normalize_output_candidate_list(candidate_outputs)
    if len(candidate_outputs) <= 1:
        return _default_output_plan(capability, candidate_outputs)

    prompt_instructions = ""
    if agent_config:
        prompt_instructions = agent_config.prompt_instructions or ""

    preview = _build_coverage_brief(
        payload,
        capability,
        candidate_files,
        candidate_outputs,
        candidate_output_files=candidate_outputs,
        output_plan=_default_output_plan(capability, candidate_outputs),
    )
    user_prompt = json.dumps(
        {
            "project": project_id,
            "version": version,
            "payload_summary": _compact_payload_for_output_planning_prompt(payload),
            "candidate_outputs": candidate_outputs,
            "coverage_preview": {
                "focus_sections": preview.get("focus_sections") or [],
                "hard_constraints": preview.get("hard_constraints") or [],
                "non_functional_requirements": preview.get("non_functional_requirements") or [],
                "risks": preview.get("risks") or [],
                "target_outcomes": preview.get("target_outcomes") or [],
                "delivery_checklist": preview.get("delivery_checklist") or {},
            },
        },
        ensure_ascii=False,
        indent=2,
    )
    llm_output = generate_with_llm_fn(
        build_output_planning_prompt(capability, prompt_instructions, candidate_outputs),
        user_prompt,
        ["output_plan"],
        project_id=project_id,
        version=version,
        node_id=f"{capability}-output-plan",
    )
    raw_plan = llm_output.artifacts.get("output_plan", "")
    try:
        parsed = json.loads(raw_plan) if raw_plan else {}
    except json.JSONDecodeError:
        parsed = {}
    normalized = _normalize_output_plan(
        parsed,
        capability=capability,
        candidate_outputs=candidate_outputs,
    )
    if llm_output.reasoning:
        normalized["planning_notes"] = str(normalized.get("planning_notes") or llm_output.reasoning).strip()
    return normalized


def _read_workspace_json(path: Path) -> Any:
    if not path.exists() or not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _read_workspace_text(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _compact_requirement_digest_for_final_prompt(requirement_digest: str) -> str:
    if not requirement_digest.strip():
        return ""

    compact_lines: List[str] = []
    include_section = False
    allowed_sections = {
        "## Expert Must Answer",
        "## Evidence Expectations",
        "## Hard Constraints",
        "## Non-Functional Requirements",
        "## Risks",
        "## Target Outcomes",
        "## Outline",
    }
    for raw_line in requirement_digest.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("# ") or stripped.startswith("- Project:") or stripped.startswith("- Version:") or stripped.startswith("- Active agents:") or stripped.startswith("- Baseline files:") or stripped.startswith("- Candidate outputs:") or stripped.startswith("- Selected outputs:"):
            compact_lines.append(line)
            continue

        if stripped.startswith("## "):
            include_section = stripped in allowed_sections
            if include_section:
                compact_lines.append(line)
            continue

        if include_section and (stripped.startswith("- ") or stripped.startswith("### ")):
            compact_lines.append(line)

    return "\n".join(compact_lines).strip()


def _compact_output_plan_for_target_file(output_plan: Dict[str, Any], target_file: str) -> Dict[str, Any]:
    must_cover = output_plan.get("must_cover_by_file") or {}
    compact: Dict[str, Any] = {
        "selected_outputs": list(output_plan.get("selected_outputs") or []),
        "file_order": list(output_plan.get("file_order") or []),
        "target_file": target_file,
        "target_must_cover": [
            _summarize_value_for_prompt(str(item), max_string=240)
            for item in (must_cover.get(target_file) or [])[:8]
        ],
        "evidence_focus": [
            _summarize_value_for_prompt(str(item), max_string=220)
            for item in (output_plan.get("evidence_focus") or [])[:6]
        ],
        "planning_notes": _summarize_value_for_prompt(
            str(output_plan.get("planning_notes") or ""),
            max_string=260,
        ),
    }
    skipped = output_plan.get("skipped_outputs") or []
    if skipped:
        compact["skipped_outputs"] = [
            {
                "path": row.get("path"),
                "reason": _summarize_value_for_prompt(str(row.get("reason") or ""), max_string=140),
            }
            for row in skipped[:6]
            if isinstance(row, dict) and row.get("path")
        ]
    return compact


def _compact_coverage_brief_for_target_file(coverage_brief: Dict[str, Any], target_file: str) -> Dict[str, Any]:
    delivery = coverage_brief.get("delivery_checklist") or {}
    target_review_items = ((delivery.get("artifact_review_checklist") or {}).get(target_file) or [])[:6]
    return {
        "hard_constraints": (coverage_brief.get("hard_constraints") or [])[:6],
        "non_functional_requirements": (coverage_brief.get("non_functional_requirements") or [])[:6],
        "risks": (coverage_brief.get("risks") or [])[:6],
        "target_outcomes": (coverage_brief.get("target_outcomes") or [])[:6],
        "must_answer": (delivery.get("must_answer") or [])[:6],
        "evidence_expectations": (delivery.get("evidence_expectations") or [])[:6],
        "target_artifact_review": target_review_items,
        "focus_sections": [
            {
                "heading": row.get("heading"),
                "must_cover_points": (row.get("must_cover_points") or [])[:4],
            }
            for row in (coverage_brief.get("focus_sections") or [])[:4]
            if isinstance(row, dict)
        ],
    }


def _compact_grounded_observations_summary_for_final_prompt(observations_summary: Any) -> Any:
    if not isinstance(observations_summary, list):
        return observations_summary

    compact_rows: List[Dict[str, Any]] = []
    for row in observations_summary[-5:]:
        if not isinstance(row, dict):
            continue
        compact_rows.append(
            {
                "step": row.get("step"),
                "action_index": row.get("action_index"),
                "tool_name": row.get("tool_name"),
                "evidence_note": _summarize_value_for_prompt(str(row.get("evidence_note") or ""), max_string=180),
                "tool_input": _summarize_value_for_prompt(row.get("tool_input") or {}, max_depth=2, max_string=120, max_list_items=4, max_dict_items=6),
                "tool_output": _summarize_value_for_prompt(row.get("tool_output") or {}, max_depth=2, max_string=120, max_list_items=4, max_dict_items=6),
            }
        )
    if len(observations_summary) > len(compact_rows):
        compact_rows.append({"omitted_observations": len(observations_summary) - len(compact_rows)})
    return compact_rows


def _build_generation_batches(target_file: str, output_plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    must_cover = [str(item).strip() for item in ((output_plan.get("must_cover_by_file") or {}).get(target_file) or []) if str(item).strip()]
    suffix = Path(target_file).suffix.lower()
    batch_size = 1 if suffix == ".md" else max(1, len(must_cover) or 1)
    batches: List[Dict[str, Any]] = []

    if must_cover:
        for index in range(0, len(must_cover), batch_size):
            batch_items = must_cover[index:index + batch_size]
            batches.append(
                {
                    "batch_index": len(batches) + 1,
                    "batch_total": max(1, (len(must_cover) + batch_size - 1) // batch_size),
                    "section_focus": batch_items,
                }
            )
    else:
        batches.append(
            {
                "batch_index": 1,
                "batch_total": 1,
                "section_focus": [],
            }
        )
    return batches


def _compact_template_hint_for_prompt(template_hint: str) -> str:
    if not template_hint.strip():
        return ""
    lines: List[str] = []
    for raw_line in template_hint.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("```") or line.startswith("%%"):
            continue
        if line.startswith("#") or line.startswith("##") or line.startswith("###"):
            lines.append(line)
        if len(lines) >= 8:
            break
    if not lines:
        compact = _summarize_value_for_prompt(template_hint, max_string=280)
        return str(compact)
    return "\n".join(lines)


def _is_timeout_exception(exc: Exception) -> bool:
    text = str(exc).lower()
    return "timeout" in text or "504" in text or "524" in text


def _build_timeout_fallback_fragment(
    *,
    target_file: str,
    section_focus: List[str],
    batch_index: int,
    batch_total: int,
    output_plan: Dict[str, Any],
    coverage_brief: Dict[str, Any],
) -> str:
    suffix = Path(target_file).suffix.lower()
    if suffix == ".json":
        return json.dumps(
            {
                "file": target_file,
                "batch_index": batch_index,
                "batch_total": batch_total,
                "selected_outputs": output_plan.get("selected_outputs") or [],
                "module_notes": section_focus or ["Timeout fallback fragment generated by controller."],
                "must_answer": (coverage_brief.get("must_answer") or [])[:4],
            },
            ensure_ascii=False,
            indent=2,
        )

    lines = [
        f"## Batch {batch_index}/{batch_total}",
        "",
        "本段为超时保护下生成的控制器回退片段，后续可继续补充细化。",
        "",
    ]
    for item in section_focus or ["围绕当前产物目标补充结构化设计说明。"]:
        title = str(item).split("：", 1)[0].strip() or "设计点"
        lines.extend(
            [
                f"### {title}",
                f"- 目标：{item}",
                "- 依据：结合已收集的代码仓、数据库、知识库与需求约束证据进行落地。",
                "- 待补强：如需更细的类名、表名、接口名，可在后续 patch 阶段继续细化。",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def build_targeted_artifact_prompt(
    capability: str,
    prompt_instructions: str,
    target_file: str,
    output_plan: Dict[str, Any],
    template_hint: str,
    *,
    section_focus: Optional[List[str]] = None,
    batch_index: int = 1,
    batch_total: int = 1,
    total_char_budget: int = 12000,
) -> str:
    must_cover = section_focus or (output_plan.get("must_cover_by_file", {}).get(target_file) or [])
    evidence_focus = output_plan.get("evidence_focus") or []
    skipped_outputs = output_plan.get("skipped_outputs") or []
    batch_char_budget = total_char_budget if batch_total <= 1 else max(800, total_char_budget // max(1, batch_total))
    custom_section = ""
    if prompt_instructions:
        custom_section = f"""
Custom Instructions from SKILL.md:
{prompt_instructions[:1200]}
"""

    template_section = ""
    if template_hint:
        template_section = f"""
Template/style hint for `{target_file}`:
{_compact_template_hint_for_prompt(template_hint)}
"""

    skipped_block = "\n".join(
        f"- {row.get('path')}: {row.get('reason') or 'Not selected'}"
        for row in skipped_outputs
        if isinstance(row, dict) and row.get("path")
    )
    if not skipped_block:
        skipped_block = "- (none)"

    must_cover_block = "\n".join(f"- {item}" for item in must_cover) or "- (use the grounded evidence to determine the exact structure)"
    evidence_focus_block = "\n".join(f"- {item}" for item in evidence_focus) or "- Ground the file in the requirement digest and gathered observations."

    return f"""
You are the {capability} artifact writer.
You are writing batch {batch_index} of {batch_total} for `{target_file}`.
Return only the fragment needed for this batch, not the whole file.
The controller will append or patch fragments into the final artifact.

Selected outputs for this run:
{chr(10).join(f"- {item}" for item in (output_plan.get("selected_outputs") or [target_file]))}

Skipped candidate outputs:
{skipped_block}

This file must cover:
{must_cover_block}

Evidence focus for the expert:
{evidence_focus_block}

{template_section}
{custom_section}
Rules:
1. Use only the grounded context provided in the user prompt.
2. If information is already covered by code/KB/DB evidence, reference it inside this file instead of inventing extra artifacts.
3. Produce deliverable-ready content, not meta commentary.
4. Keep this batch within about {batch_char_budget} characters, and keep the full `{target_file}` within about {total_char_budget} characters.
5. {_scope_boundary_note(capability)}
6. Return only the fragment content for `{target_file}` in the artifact payload.
7. Do not attempt to cover sections outside the current batch focus.
8. If this is not the first batch, continue the same file naturally and avoid repeating sections already covered in the current artifact.
""".strip()


def default_generate_artifact_for_output(
    generate_with_llm_fn: Callable[[str, str, List[str], int, Dict[str, Any] | None, str | None, str | None, str | None], SubagentOutput],
    capability: str,
    project_id: str,
    version: str,
    payload: Dict[str, Any],
    workspace_paths: Dict[str, str],
    artifacts_dir: Path,
    target_file: str,
    output_plan: Dict[str, Any],
    templates: Dict[str, str],
    agent_config: Optional["AgentFullConfig"] = None,
    step: int = 1,
    section_focus: Optional[List[str]] = None,
    batch_index: int = 1,
    batch_total: int = 1,
) -> SubagentOutput:
    prompt_instructions = ""
    if agent_config:
        prompt_instructions = agent_config.prompt_instructions or ""
    total_char_budget = _resolve_output_char_budget(
        {"design_context": payload.get("design_context") or {}},
        capability,
        target_file,
    )

    requirement_digest = _read_workspace_text(artifacts_dir / workspace_paths["requirement_digest"])
    coverage_brief = _read_workspace_json(artifacts_dir / workspace_paths["coverage_brief"])
    observations_summary = _read_workspace_json(artifacts_dir / workspace_paths["grounded_observations_summary"])
    current_artifact_path = artifacts_dir / target_file
    current_artifact = current_artifact_path.read_text(encoding="utf-8") if current_artifact_path.exists() else ""
    compact_output_plan = _compact_output_plan_for_target_file(output_plan, target_file)
    compact_coverage_brief = _compact_coverage_brief_for_target_file(coverage_brief, target_file)

    user_prompt = json.dumps(
        {
            "project": project_id,
            "version": version,
            "step": step,
            "batch_index": batch_index,
            "batch_total": batch_total,
            "payload_summary": _compact_payload_for_finalization_prompt(
                payload,
                list(output_plan.get("selected_outputs") or []),
            ),
            "target_file": target_file,
            "target_context": compact_output_plan,
            "section_focus": section_focus or [],
            "requirement_digest": _summarize_value_for_prompt(
                _compact_requirement_digest_for_final_prompt(requirement_digest),
                max_string=1800,
            ),
            "coverage_brief": compact_coverage_brief,
            "grounded_observations_summary": _compact_grounded_observations_summary_for_final_prompt(observations_summary),
            "current_artifact": _summarize_value_for_prompt(current_artifact, max_string=1600) if current_artifact else "",
        },
        ensure_ascii=False,
        indent=2,
    )
    return generate_with_llm_fn(
        build_targeted_artifact_prompt(
            capability,
            prompt_instructions,
            target_file,
            output_plan,
            templates.get(target_file, ""),
            section_focus=section_focus,
            batch_index=batch_index,
            batch_total=batch_total,
            total_char_budget=total_char_budget,
        ),
        user_prompt,
        [target_file],
        max_retries=0,
        project_id=project_id,
        version=version,
        node_id=f"{capability}-final-{Path(target_file).stem}-step-{step}",
    )


def build_react_system_prompt(
    capability: str,
    prompt_instructions: str,
    tools_allowed: List[str],
    candidate_files: List[str],
    workflow_steps: Optional[List[str]] = None,
    upstream_artifacts: Optional[Dict[str, List[str]]] = None,
    configured_assets: Optional[Dict[str, Any]] = None,
    selected_outputs: Optional[List[str]] = None,
    output_plan: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build the ReAct system prompt from agent configuration.
    
    Args:
        capability: Agent capability identifier
        prompt_instructions: Instructions extracted from SKILL.md
        tools_allowed: List of allowed tools
        candidate_files: Files available for reading
        workflow_steps: Optional workflow steps from SKILL.md
        upstream_artifacts: Dict mapping upstream agent -> list of artifact files
        (enables cross-agent memory)
        
    Returns:
        Formatted system prompt for ReAct loop
    """
    selected_outputs = _normalize_output_candidate_list(selected_outputs or [])
    output_plan = output_plan or {}
    tool_contract_section = _build_tool_contract_section(tools_allowed, candidate_files)
    tools_section = f"""
Available tools:
- list_files / read_file_chunk / grep_search / extract_structure / extract_lookup_values (Read operations)
- write_file (Write scratch drafts only when they materially help evidence collection)
- patch_file (Make partial corrections to scratch drafts under `artifacts/`)
- run_command (Execute shell commands from project root when explicitly allowed)

{tool_contract_section}
"""
    asset_tool_section = _build_asset_tool_section(tools_allowed, configured_assets)
    asset_examples_section = _format_asset_examples(configured_assets)
    tool_name_options = _build_tool_name_options(tools_allowed, configured_assets)
    
    # Build workflow section if available
    workflow_section = ""
    if workflow_steps:
        workflow_section = f"""
Workflow Steps:
{chr(10).join(f'{i+1}. {step}' for i, step in enumerate(workflow_steps))}
"""
    
    # Build custom instructions section
    custom_section = ""
    if prompt_instructions:
        custom_section = f"""
Custom Instructions from SKILL.md:
{prompt_instructions}
"""

    output_plan_section = ""
    if selected_outputs:
        selected_block = "\n".join(f"- {item}" for item in selected_outputs)
        must_cover_by_file = output_plan.get("must_cover_by_file") or {}
        evidence_focus = output_plan.get("evidence_focus") or []
        plan_lines = [
            "Selected outputs for this run:",
            selected_block,
        ]
        for file_name in selected_outputs:
            items = must_cover_by_file.get(file_name) or []
            if items:
                plan_lines.append(f"- {file_name} must cover: {'; '.join(str(item) for item in items[:6])}")
        if evidence_focus:
            plan_lines.append("Evidence focus:")
            plan_lines.extend(f"- {item}" for item in evidence_focus[:10])
        output_plan_section = "\n".join(plan_lines) + "\n"
    
    # Build cross-agent memory section
    memory_section = ""
    if upstream_artifacts:
        memory_lines = []
        for upstream_agent, artifacts in upstream_artifacts.items():
            if artifacts:
                artifact_paths = [f"artifacts/{a}" for a in artifacts]
                memory_lines.append(f"- {upstream_agent}: {', '.join(artifact_paths)}")
        if memory_lines:
            memory_section = f"""
Cross-Agent Memory (upstream artifacts available for reading):
{chr(10).join(memory_lines)}

You can read these files using read_file_chunk with file_path like "artifacts/schema.sql".
"""
    
    system_prompt = f"""
You are the {capability} ReAct controller.
Choose one next action at a time to ground design artifacts.
{custom_section}
{tools_section}
{asset_tool_section}
{asset_examples_section}
{output_plan_section}
Scope boundary:
- {_scope_boundary_note(capability)}

{workflow_section}{memory_section}
Strategy:
1. Ground quickly: Anchor on the candidate baseline file immediately instead of searching for it by filename.
2. Research: Use read tools to collect the minimum evidence needed from baseline/ and upstream artifacts/, always in service of the selected outputs above.
3. Draft optionally: Use write_file only when an intermediate draft materially helps, and write it under `scratch/` with a `.draft` style filename.
4. Verify: Use read_file_chunk to inspect generated drafts only when needed.
5. Finalize: Set done=true as soon as the collected evidence is sufficient for final generation to produce all expected artifacts.

Rules:
1. You may output one action or a short sequential batch in `actions`, but keep it to at most {MAX_ACTIONS_PER_STEP} actions.
2. Stop when evidence is sufficient for final generation, even if ReAct has not written any artifact files yet.
3. Keep tool_input concise and machine-readable JSON.
4. Candidate files in baseline/: {candidate_files}
4a. Do not try to gather evidence for skipped candidate outputs; focus only on the selected outputs.
5. Only use asset-aware tools when the corresponding configured assets are present in the requirements payload.
5a. For `clone_repository`, `query_database`, and most `query_knowledge_base` calls, prefer passing the concrete configured asset id shown above.
5b. After `clone_repository`, prefer the returned `project_relative_path` or `search_hint` for later `repos_dir` parameters instead of guessing the cache directory name.
6. By step 2, you should already have grounded yourself on the correct baseline requirement content.
7. Do NOT write or patch the final expected artifact paths during ReAct. If you are ready to produce the final expected artifacts, return `done=true` instead.
8. Only use `actions` for short read-only batches such as `read_file_chunk`, `extract_structure`, `grep_search`, or `extract_lookup_values`.
9. Never batch `write_file`, `patch_file`, `run_command`, `clone_repository`, `query_database`, or `query_knowledge_base`; those must be emitted as a single action step.
10. Later actions in the same batch cannot see outputs from earlier actions in that batch, so only batch independent or low-risk steps.

Return JSON in artifacts.decision:
{{
  "done": false,
  "thought": "why this step is needed",
  "tool_name": {tool_name_options},
  "tool_input": {{}},
  "actions": [
    {{"tool_name": "read_file_chunk", "tool_input": {{"path": "{candidate_files[0] if candidate_files else 'baseline/original-requirements.md'}", "start_line": 1, "end_line": 120}}}},
    {{"tool_name": "extract_structure", "tool_input": {{"files": ["{candidate_files[0] if candidate_files else 'baseline/original-requirements.md'}"]}}}}
  ],
  "evidence_note": "what this step should confirm or produce"
}}
""".strip()
    
    return system_prompt


def build_final_artifacts_prompt(
    capability: str,
    prompt_instructions: str,
    expected_files: List[str],
    templates: Dict[str, str],
) -> str:
    """
    Build the final artifacts generation prompt.
    
    Args:
        capability: Agent capability identifier
        prompt_instructions: Instructions from SKILL.md
        expected_files: Files to generate
        templates: Template content for each file
        
    Returns:
        Formatted system prompt for final generation
    """
    template_sections = []
    for file_name in expected_files:
        template_content = templates.get(file_name, "")
        if template_content:
            # Truncate long templates
            preview = template_content[:800] if len(template_content) > 800 else template_content
            template_sections.append(f"[{file_name}]\n{preview}")
    
    templates_block = "\n\n".join(template_sections)
    
    custom_section = ""
    if prompt_instructions:
        custom_section = f"""
Additional Guidelines:
{prompt_instructions[:1000]}
"""
    
    system_prompt = f"""
You are a senior designer for {capability}.
Generate {', '.join(expected_files)} only from grounded evidence collected during the ReAct loop.

Requirements:
1. Reflect only content supported by the observations.
2. Use consistent naming conventions.
3. Include enough structure for downstream consumers.
4. Use the templates as style references.

{templates_block}
{custom_section}
""".strip()
    
    return system_prompt


def build_finalization_system_prompt(
    capability: str,
    prompt_instructions: str,
    expected_files: List[str],
    candidate_files: List[str],
    workspace_paths: Dict[str, str],
) -> str:
    tool_contract_section = _build_tool_contract_section(["write_file", "patch_file"], candidate_files)
    expected_block = "\n".join(f"- {file_name}" for file_name in expected_files)
    workspace_block = "\n".join(
        [
            f"- workspace index: artifacts/{workspace_paths['workspace_index']}",
            f"- requirement digest: artifacts/{workspace_paths['requirement_digest']}",
            f"- coverage brief: artifacts/{workspace_paths['coverage_brief']}",
            f"- output plan: artifacts/{workspace_paths['output_plan']}",
            f"- grounded observations: artifacts/{workspace_paths['grounded_observations']}",
            f"- observations summary: artifacts/{workspace_paths['grounded_observations_summary']}",
            f"- react trace: artifacts/{workspace_paths['react_trace']}",
            f"- finalization trace: artifacts/{workspace_paths['finalization_trace']}",
        ]
    )
    custom_section = ""
    if prompt_instructions:
        custom_section = f"""
Custom Instructions from SKILL.md:
{prompt_instructions[:1200]}
"""

    return f"""
You are the {capability} finalization controller.
Your job is to turn grounded evidence already stored on disk into the final expected artifact files.

Expected artifacts:
{expected_block}

Workspace files you should use first:
{workspace_block}

{custom_section}
Available tools:
- list_files / read_file_chunk / grep_search / extract_structure (read project files and workspace files)
- write_file / patch_file (write or refine files under `artifacts/`)

{tool_contract_section}

Rules:
1. The full requirement text is intentionally NOT embedded here. Start from the requirement digest and coverage brief, and only read the baseline file again if needed.
2. Prefer reading `artifacts/{workspace_paths['workspace_index']}`, `artifacts/{workspace_paths['output_plan']}`, `artifacts/{workspace_paths['coverage_brief']}`, and `artifacts/{workspace_paths['requirement_digest']}` before writing.
3. Write final artifacts incrementally. One file at a time is preferred.
4. You may patch an existing final artifact when refining it.
5. Use `write_file` for new files and `patch_file` for targeted corrections.
6. Batch only read-only actions. Never batch `write_file` or `patch_file`.
7. Set `done=true` only when every expected artifact exists under `artifacts/` and is materially complete.

Return JSON in artifacts.decision:
{{
  "done": false,
  "thought": "why this step is needed",
  "tool_name": "list_files" | "read_file_chunk" | "grep_search" | "extract_structure" | "write_file" | "patch_file" | "none",
  "tool_input": {{}},
  "actions": [
    {{"tool_name":"read_file_chunk","tool_input":{{"path":"artifacts/{workspace_paths['workspace_index']}","start_line":1,"end_line":200}}}},
    {{"tool_name":"read_file_chunk","tool_input":{{"path":"artifacts/{workspace_paths['requirement_digest']}","start_line":1,"end_line":200}}}}
  ],
  "evidence_note": "what this step should confirm or produce"
}}
""".strip()


def default_next_finalization_decision(
    generate_with_llm_fn: Callable[[str, str, List[str], int, Dict[str, Any] | None, str | None, str | None, str | None], SubagentOutput],
    capability: str,
    project_id: str,
    version: str,
    payload: Dict[str, Any],
    candidate_files: List[str],
    expected_files: List[str],
    workspace_paths: Dict[str, str],
    artifact_status: List[Dict[str, Any]],
    observations: List[Dict[str, Any]],
    step: int,
    agent_config: Optional["AgentFullConfig"] = None,
) -> Dict[str, Any]:
    prompt_instructions = ""
    if agent_config:
        prompt_instructions = agent_config.prompt_instructions or ""

    system_prompt = build_finalization_system_prompt(
        capability=capability,
        prompt_instructions=prompt_instructions,
        expected_files=expected_files,
        candidate_files=candidate_files,
        workspace_paths=workspace_paths,
    )

    payload_summary = _compact_payload_for_finalization_prompt(payload, expected_files)
    user_prompt = json.dumps(
        {
            "project": project_id,
            "version": version,
            "step": step,
            "payload_summary": payload_summary,
            "expected_files": expected_files,
            "workspace_paths": workspace_paths,
            "artifact_status": artifact_status,
            "recent_finalization_observations": _compact_finalization_observations_for_prompt(observations),
        },
        ensure_ascii=False,
        indent=2,
    )

    llm_output = generate_with_llm_fn(
        system_prompt,
        user_prompt,
        ["decision"],
        project_id=project_id,
        version=version,
        node_id=f"{capability}-final-step-{step}",
    )
    raw_decision = llm_output.artifacts.get("decision", "")

    try:
        decision = json.loads(raw_decision) if raw_decision else {"done": False, "tool_name": "none", "tool_input": {}}
    except json.JSONDecodeError:
        decision = {"done": False, "tool_name": "none", "tool_input": {}}

    if not isinstance(decision, dict):
        decision = {"done": False, "tool_name": "none", "tool_input": {}}

    decision.setdefault("done", False)
    decision.setdefault("tool_name", "none")
    decision.setdefault("tool_input", {})
    decision.setdefault("thought", "")
    decision.setdefault("evidence_note", "")
    decision = _normalize_react_decision(decision)
    decision["reasoning"] = llm_output.reasoning
    return decision


def default_next_react_decision(
    generate_with_llm_fn: Callable[[str, str, List[str], int, Dict[str, Any] | None, str | None, str | None, str | None], SubagentOutput],
    capability: str,
    project_id: str,
    version: str,
    payload: Dict[str, Any],
    candidate_files: List[str],
    observations: List[Dict[str, Any]],
    templates: Dict[str, str],
    step: int,
    agent_config: Optional["AgentFullConfig"] = None,
    upstream_artifacts: Optional[Dict[str, List[str]]] = None,
    selected_outputs: Optional[List[str]] = None,
    output_plan: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Default implementation for ReAct decision making.
    
    Uses AgentFullConfig for prompt construction if available.
    Supports cross-agent memory via upstream_artifacts parameter.
    """
    # Get configuration
    prompt_instructions = ""
    workflow_steps = None
    tools_allowed = []
    
    if agent_config:
        prompt_instructions = agent_config.prompt_instructions or ""
        workflow_steps = agent_config.workflow_steps or None
        tools_allowed = agent_config.tools_allowed or []
    
    bootstrap_decision = _build_bootstrap_decision(candidate_files, observations, step)
    if bootstrap_decision:
        bootstrap_decision["reasoning"] = "Bootstrap grounding step to anchor the agent on the canonical baseline file before free-form ReAct exploration."
        return bootstrap_decision

    configured_assets = payload.get("configured_assets") if isinstance(payload.get("configured_assets"), dict) else None
    project_root = _get_runtime_project_root(payload)
    system_prompt = build_react_system_prompt(
        capability=capability,
        prompt_instructions=prompt_instructions,
        tools_allowed=tools_allowed,
        candidate_files=candidate_files,
        workflow_steps=workflow_steps,
        upstream_artifacts=upstream_artifacts,
        configured_assets=configured_assets,
        selected_outputs=selected_outputs,
        output_plan=output_plan,
    )
    
    # Build template hints
    template_hints = {}
    for name, content in templates.items():
        if content:
            template_hints[name.replace(".", "_")] = content[:400]
    
    user_prompt = json.dumps(
        {
            "project": project_id,
            "version": version,
            "step": step,
            "requirements_payload": _compact_payload_for_prompt(payload, capability, "react"),
            "observations": _compact_observations_for_prompt(
                observations,
                capability,
                "react",
                project_root=project_root,
            ),
            "template_hints": template_hints,
        },
        ensure_ascii=False,
        indent=2,
    )
    
    llm_output = generate_with_llm_fn(
        system_prompt, 
        user_prompt, 
        ["decision"],
        project_id=project_id,
        version=version,
        node_id=f"{capability}-react-step-{step}"
    )
    raw_decision = llm_output.artifacts.get("decision", "")
    
    try:
        decision = json.loads(raw_decision) if raw_decision else _fallback_decision(candidate_files)
    except json.JSONDecodeError:
        decision = _fallback_decision(candidate_files)
    
    if not isinstance(decision, dict):
        decision = _fallback_decision(candidate_files)

    decision.setdefault("done", False)
    decision.setdefault("tool_name", "none")
    decision.setdefault("tool_input", {})
    decision.setdefault("thought", "")
    decision.setdefault("evidence_note", "")
    decision = _normalize_react_decision(decision)
    decision["reasoning"] = llm_output.reasoning
    
    return decision


def default_generate_final_artifacts(
    generate_with_llm_fn: Callable[[str, str, List[str], int, Dict[str, Any] | None, str | None, str | None, str | None], SubagentOutput],
    capability: str,
    project_id: str,
    version: str,
    payload: Dict[str, Any],
    observations: List[Dict[str, Any]],
    templates: Dict[str, str],
    expected_files: List[str],
    agent_config: Optional["AgentFullConfig"] = None,
) -> SubagentOutput:
    """
    Default implementation for final artifacts generation.
    
    Uses AgentFullConfig for prompt construction if available.
    """
    prompt_instructions = ""
    if agent_config:
        prompt_instructions = agent_config.prompt_instructions or ""
    
    system_prompt = build_final_artifacts_prompt(
        capability=capability,
        prompt_instructions=prompt_instructions,
        expected_files=expected_files,
        templates=templates,
    )
    
    project_root = _get_runtime_project_root(payload)
    user_prompt = json.dumps(
        {
            "project": project_id,
            "version": version,
            "requirements_payload": _compact_payload_for_prompt(payload, capability, "final"),
            "grounded_observations": _compact_observations_for_prompt(
                observations,
                capability,
                "final",
                project_root=project_root,
            ),
            "expected_files": expected_files,
        },
        ensure_ascii=False,
        indent=2,
    )
    
    return generate_with_llm_fn(
        system_prompt, 
        user_prompt, 
        expected_files,
        project_id=project_id,
        version=version,
        node_id=f"{capability}-final"
    )


def _fallback_decision(candidate_files: List[str]) -> Dict[str, Any]:
    """Generate a fallback decision when LLM fails."""
    if candidate_files:
        return {
            "done": False,
            "thought": "Starting evidence collection from available files",
            "tool_name": "read_file_chunk",
            "tool_input": {"path": candidate_files[0], "start_line": 1, "end_line": 100},
            "evidence_note": "Reading initial requirements",
        }
    return {
        "done": True,
        "thought": "No candidate files available, treating evidence as sufficient and moving to final generation",
        "tool_name": "none",
        "tool_input": {},
        "evidence_note": "",
    }


def _build_bootstrap_decision(
    candidate_files: List[str],
    observations: List[Dict[str, Any]],
    step: int,
) -> Optional[Dict[str, Any]]:
    if not candidate_files:
        return None

    primary_candidate = candidate_files[0]
    candidate_read_succeeded = any(
        observation.get("tool_name") == "read_file_chunk"
        and (observation.get("tool_input") or {}).get("path") == primary_candidate
        and bool((observation.get("tool_output") or {}).get("content"))
        for observation in observations
    )
    candidate_structure_succeeded = any(
        observation.get("tool_name") == "extract_structure"
        and primary_candidate in ((observation.get("tool_input") or {}).get("files") or [])
        for observation in observations
    )

    if step == 1 and not candidate_read_succeeded:
        return {
            "done": False,
            "thought": f"Read the canonical baseline candidate `{primary_candidate}` first so the agent is grounded on the correct requirement content immediately.",
            "tool_name": "read_file_chunk",
            "tool_input": {
                "path": primary_candidate,
                "start_line": 1,
                "end_line": 160,
            },
            "evidence_note": "Confirm the actual requirement content from the baseline source file before any search or synthesis.",
        }

    if step == 2 and candidate_read_succeeded and not candidate_structure_succeeded:
        return {
            "done": False,
            "thought": f"Extract the structure of `{primary_candidate}` in step 2 so the agent has both the exact content and a stable outline before deeper analysis.",
            "tool_name": "extract_structure",
            "tool_input": {
                "files": [primary_candidate],
            },
            "evidence_note": "Capture headings, sections, and document structure from the canonical baseline file.",
        }

    return None


def default_fallback_artifacts(
    capability: str,
    payload: Dict[str, Any],
    observations: List[Dict[str, Any]],
    expected_files: List[str],
) -> SubagentOutput:
    """Generate minimal fallback artifacts when LLM generation fails."""
    artifacts = {}
    reasoning = f"Fallback generation for {capability} due to empty LLM output."
    
    for file_name in expected_files:
        # Create empty placeholder
        if file_name.endswith(".sql"):
            artifacts[file_name] = "-- Placeholder generated by fallback\n"
        elif file_name.endswith(".md"):
            artifacts[file_name] = f"# {file_name}\n\nPlaceholder content.\n"
        elif file_name.endswith(".yaml") or file_name.endswith(".yml"):
            artifacts[file_name] = "# Placeholder configuration\n"
        elif file_name.endswith(".json"):
            artifacts[file_name] = "{}\n"
        else:
            artifacts[file_name] = ""
    
    return SubagentOutput(reasoning=reasoning, artifacts=artifacts)


def default_tool_history_entries(tool_name: str, tool_result: Dict[str, Any]) -> List[str]:
    """Generate history entries from tool execution."""
    entries = []
    status = tool_result.get("status", "unknown")
    duration = tool_result.get("duration_ms", 0)
    
    if status == "success":
        entries.append(f"[TOOL] {tool_name} completed in {duration}ms")
    else:
        error_code = tool_result.get("error_code", "UNKNOWN")
        entries.append(f"[TOOL] {tool_name} failed: {error_code}")
    
    return entries


def default_build_evidence(
    capability: str,
    payload: Dict[str, Any],
    artifacts: Dict[str, str],
    observations: List[Dict[str, Any]],
    react_trace: List[Dict[str, Any]],
    tool_results: List[Dict[str, Any]],
    expected_files: List[str],
    candidate_output_files: Optional[List[str]] = None,
    output_plan: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build evidence document from execution trace."""
    return {
        "capability": capability,
        "mode": "dynamic_subagent",
        "candidate_output_files": candidate_output_files or [],
        "expected_files": expected_files,
        "selected_outputs": list((output_plan or {}).get("selected_outputs") or expected_files),
        "output_plan": output_plan or {},
        "artifacts_generated": list(artifacts.keys()),
        "observation_count": len(observations),
        "tool_calls": len(tool_results),
        "success_rate": sum(1 for r in tool_results if r.get("status") == "success") / max(len(tool_results), 1),
    }


async def run_dynamic_subagent(
    *,
    capability: str,
    state: Dict[str, Any],
    base_dir: Path,
    generate_with_llm_fn: Callable[[str, str, List[str], int, Dict[str, Any] | None, str | None, str | None, str | None], SubagentOutput],
    execute_tool_fn: Callable[[str, Dict[str, Any] | None], Dict[str, Any]],
    update_task_status_fn: Callable[[List[Dict[str, Any]], str, str], List[Dict[str, Any]]],
    agent_config: Optional["AgentFullConfig"] = None,
    max_react_steps: int = MAX_REACT_STEPS,
    enable_permission_check: bool = True,
    # Optional overrides for custom behavior
    next_decision_fn: Optional[Callable] = None,
    generate_final_artifacts_fn: Optional[Callable] = None,
    fallback_artifacts_fn: Optional[Callable] = None,
    expected_files_fn: Optional[Callable] = None,
    candidate_files_fn: Optional[Callable] = None,
    plan_outputs_fn: Optional[Callable] = None,
    execution_guard_fn: Optional[Callable[[], Optional[Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """
    Execute a subagent dynamically based on its configuration.
    
    This function loads the agent configuration from AgentRegistry and uses
    it to construct prompts, validate tool permissions, and determine expected
    outputs.
    
    Args:
        capability: Agent capability identifier (e.g., "data-design")
        state: Current workflow state
        base_dir: Project base directory
        generate_with_llm_fn: LLM generation function
        execute_tool_fn: Tool execution function
        update_task_status_fn: Task status update function
        agent_config: Pre-loaded AgentFullConfig (optional, loads from registry if not provided)
        max_react_steps: Maximum ReAct loop iterations
        enable_permission_check: Whether to check tool permissions
        next_decision_fn: Override for ReAct decision function
        generate_final_artifacts_fn: Override for final generation function
        fallback_artifacts_fn: Override for fallback generation function
        expected_files_fn: Override for expected files function
        candidate_files_fn: Override for candidate files function
        plan_outputs_fn: Override for output planning function
        execution_guard_fn: Optional callback that can abort execution when the
            owning workflow run is no longer active or a sibling branch failed
        
    Returns:
        Updated state dictionary with execution results
    """
    import asyncio
    from registry.agent_registry import AgentRegistry
    
    # Load agent config if not provided
    if agent_config is None:
        try:
            registry = AgentRegistry.get_instance()
            agent_config = registry.load_full_config(capability)
        except RuntimeError:
            # Registry not initialized, proceed without config
            pass
    
    project_id = state["project_id"]
    version = state["version"]
    project_path = base_dir / "projects" / project_id / version
    baseline_path = project_path / "baseline" / "requirements.json"
    baseline_dir = baseline_path.parent
    artifacts_dir = project_path / "artifacts"
    logs_dir = project_path / "logs"
    evidence_dir = project_path / "evidence"
    work_dir = artifacts_dir / _workspace_relative_dir(capability)

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    payload = json.loads(baseline_path.read_text(encoding="utf-8-sig"))
    payload["candidate_files"] = _resolve_candidate_files(payload)
    payload.setdefault(
        "project_layout",
        {
            "project_root": ".",
            "baseline_dir": "baseline",
            "artifacts_dir": "artifacts",
            "evidence_dir": "evidence",
        },
    )
    payload["_runtime_project_root"] = str(project_path)
    history_updates = []
    runtime_llm_settings = resolve_runtime_llm_settings(state.get("design_context"))
    configured_assets = payload.get("configured_assets") if isinstance(payload.get("configured_assets"), dict) else None
    execution_signatures_seen: set[str] = set()
    unavailable_read_paths: set[str] = set()
    path_not_found_counts: Dict[str, int] = {}
    repeated_action_steps = 0
    repeated_focus_steps = 0
    previous_focus_signature = ""

    def _generate_with_selected_llm(*args: Any, **kwargs: Any) -> SubagentOutput:
        if runtime_llm_settings and "llm_settings" not in kwargs:
            kwargs["llm_settings"] = runtime_llm_settings
        return generate_with_llm_fn(*args, **kwargs)
    
    # Determine candidate files
    if candidate_files_fn:
        candidate_files = candidate_files_fn(payload)
    else:
        candidate_files = payload.get("candidate_files", []) or _resolve_candidate_files(payload)
    
    # Determine candidate outputs, then plan the selected outputs for this run
    if expected_files_fn:
        candidate_output_files = expected_files_fn(payload)
    elif agent_config and agent_config.metadata.get("expected_outputs"):
        candidate_output_files = agent_config.metadata["expected_outputs"]
    else:
        candidate_output_files = _default_expected_files(capability)
    candidate_output_files = _normalize_output_candidate_list(candidate_output_files)

    if plan_outputs_fn:
        output_plan = plan_outputs_fn(
            payload,
            candidate_files,
            candidate_output_files,
            capability,
            agent_config,
        )
    elif expected_files_fn:
        output_plan = _default_output_plan(capability, candidate_output_files)
    else:
        output_plan = await asyncio.to_thread(
            default_plan_outputs,
            _generate_with_selected_llm,
            capability,
            project_id,
            version,
            payload,
            candidate_files,
            candidate_output_files,
            agent_config,
        )
    output_plan = _normalize_output_plan(
        output_plan,
        capability=capability,
        candidate_outputs=candidate_output_files,
    )
    expected_files = _normalize_output_candidate_list(output_plan.get("selected_outputs") or [])
    payload["candidate_output_files"] = candidate_output_files
    payload["selected_outputs"] = expected_files
    payload["output_plan"] = output_plan
    history_updates.append(
        f"[SYSTEM] Output planning selected {expected_files or ['(none)']} from candidate outputs {candidate_output_files or ['(none)']}."
    )
    skipped_outputs = output_plan.get("skipped_outputs") or []
    if skipped_outputs:
        skipped_summary = ", ".join(
            f"{row.get('path')} ({row.get('reason') or 'skipped'})"
            for row in skipped_outputs
            if isinstance(row, dict) and row.get("path")
        )
        if skipped_summary:
            history_updates.append(f"[SYSTEM] Skipped candidate outputs: {skipped_summary}")
    
    # Discover upstream artifacts for cross-agent memory
    upstream_artifacts = _discover_upstream_artifacts(capability, artifacts_dir)
    if upstream_artifacts:
        upstream_summary = {k: v for k, v in upstream_artifacts.items() if v}
        history_updates.append(
            f"[SYSTEM] Cross-agent memory: found upstream artifacts: {upstream_summary}"
        )
    
    # Load templates
    templates = await asyncio.to_thread(
        _load_templates_for_capability,
        base_dir,
        capability,
        agent_config,
    )

    max_react_steps = _estimate_react_budget(
        state=state,
        payload=payload,
        expected_files=expected_files,
        agent_config=agent_config,
        upstream_artifacts=upstream_artifacts,
        default_value=max_react_steps,
    )

    history_updates.append(f"[SYSTEM] Dynamic subagent '{capability}' is now running.")
    history_updates.append(f"[SYSTEM] ReAct budget resolved to {max_react_steps} step(s).")
    tool_results: List[Dict[str, Any]] = []
    react_trace: List[Dict[str, Any]] = []
    observations: List[Dict[str, Any]] = []
    react_exhausted = False

    def _build_abort_result(abort_info: Dict[str, Any]) -> Dict[str, Any]:
        reason = str(abort_info.get("reason") or "execution aborted").strip()
        status_override = abort_info.get("status")
        failure_reason = str(abort_info.get("failure_reason") or "execution_aborted").strip()
        history_updates.append(f"[{capability}] [SYSTEM] Execution stopped: {reason}")
        reasoning_sections = [entry.get("reasoning", "") for entry in react_trace if entry.get("reasoning")]
        reasoning_sections.append(f"Execution aborted: {reason}.")
        (logs_dir / f"{capability}-reasoning.md").write_text(
            "\n\n".join(section for section in reasoning_sections if section),
            encoding="utf-8",
        )
        evidence = default_build_evidence(
            capability,
            payload,
            {},
            observations,
            react_trace,
            tool_results,
            expected_files,
            candidate_output_files,
            output_plan,
        )
        evidence.setdefault("react_trace", react_trace)
        evidence["failure_reason"] = failure_reason
        evidence["abort_reason"] = reason
        (evidence_dir / f"{capability}.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        next_queue = state["task_queue"]
        if isinstance(status_override, str) and status_override:
            next_queue = update_task_status_fn(state["task_queue"], capability, status_override)
        history_updates.append(f"[{capability}] Completed with status: {status_override or 'aborted'}")
        return {
            "history": history_updates,
            "task_queue": next_queue,
            "human_intervention_required": False,
            "last_worker": capability,
            "tool_results": tool_results,
        }

    # Permission-aware tool executor
    def _execute_tool_with_permission(tool_name: str, tool_input: Dict[str, Any] | None) -> Dict[str, Any]:
        if enable_permission_check:
            from api_server.graphs.tools.protocol import execute_tool_with_permission
            return execute_tool_with_permission(
                tool_name, tool_input, agent_capability=capability
            )
        return execute_tool_fn(tool_name, tool_input)

    try:
        for step in range(1, max_react_steps + 1):
            if execution_guard_fn:
                abort_info = execution_guard_fn()
                if abort_info:
                    return _build_abort_result(abort_info)
            # Use custom or default decision function
            if next_decision_fn:
                decision = await asyncio.to_thread(
                    next_decision_fn,
                    payload,
                    observations,
                    templates,
                    step,
                )
            else:
                decision = await asyncio.to_thread(
                    default_next_react_decision,
                    _generate_with_selected_llm,
                    capability,
                    project_id,
                    version,
                    payload,
                    candidate_files,
                    observations,
                    templates,
                    step,
                    agent_config,
                    upstream_artifacts,
                    expected_files,
                    output_plan,
                )

            decision = _normalize_react_decision(decision)
            final_artifact_target = None
            for action in decision.get("actions") or []:
                final_artifact_target = _action_targets_final_artifact(action, expected_files)
                if final_artifact_target:
                    break
            if final_artifact_target:
                decision = dict(decision)
                decision["done"] = True
                decision["actions"] = []
                decision["tool_name"] = "none"
                decision["tool_input"] = {}
                thought = str(decision.get("thought") or "").strip()
                if thought:
                    thought = f"{thought} Final expected artifacts must be generated in the final generation stage."
                else:
                    thought = "Evidence is sufficient; defer final artifact writing to the final generation stage."
                decision["thought"] = thought
                decision["coerced_done_from_final_artifact_write"] = final_artifact_target
            
            react_trace.append({"step": step, **decision})
            focus_signature = _decision_focus_signature(decision)
            if focus_signature and focus_signature == previous_focus_signature:
                repeated_focus_steps += 1
            else:
                repeated_focus_steps = 0
            previous_focus_signature = focus_signature
            thought = decision.get("thought", "")
            if thought:
                history_updates.append(f"[{capability}] ReAct step {step}: {thought}")

            if decision.get("actions_truncated"):
                history_updates.append(
                    f"[{capability}] ReAct step {step}: truncated actions batch by {decision['actions_truncated']} item(s) to respect the per-step cap."
                )

            if decision.get("actions_restricted_to_single"):
                history_updates.append(
                    f"[{capability}] ReAct step {step}: restricted batched actions to a single action because only read-only tools may be batched."
                )

            if final_artifact_target:
                history_updates.append(
                    f"[{capability}] ReAct step {step}: attempted to write final artifact `{final_artifact_target}` during ReAct; switching to final generation."
                )


            if decision.get("done"):
                history_updates.append(f"[{capability}] ReAct step {step}: evidence is sufficient, moving to final generation.")
                break

            executed_action_summaries: List[Dict[str, Any]] = []
            step_signatures: List[str] = []
            for action_index, action in enumerate(decision.get("actions") or [], start=1):
                if execution_guard_fn:
                    abort_info = execution_guard_fn()
                    if abort_info:
                        return _build_abort_result(abort_info)
                tool_name = action.get("tool_name") or "none"
                tool_input = dict(action.get("tool_input") or {})

                if tool_name == "none":
                    continue

                tool_input, autofill_note, validation_error = _preflight_asset_tool_action(
                    action,
                    configured_assets,
                )
                if autofill_note:
                    history_updates.append(f"[{capability}] ReAct step {step}: {autofill_note}")
                if validation_error:
                    history_updates.append(
                        f"[{capability}] ReAct step {step}: asset tool input rejected before execution. {validation_error}"
                    )
                    executed_action_summaries.append(
                        {
                            "action_index": action_index,
                            "tool_name": tool_name,
                            "status": "error",
                            "error_code": "INVALID_ASSET_SELECTION",
                            "duration_ms": 0,
                        }
                    )
                    observations.append(
                        {
                            "step": step,
                            "action_index": action_index,
                            "tool_name": tool_name,
                            "tool_input": _sanitize_prompt_payload(tool_input, project_path),
                            "tool_output": {
                                "error": {
                                    "code": "INVALID_ASSET_SELECTION",
                                    "message": validation_error,
                                }
                            },
                            "evidence_note": decision.get("evidence_note", ""),
                        }
                    )
                    continue

                # Set root_dir based on tool type for cross-agent memory
                # - Write tools: write to artifacts directory
                # - Read tools: can read from project root (baseline/, artifacts/, evidence/)
                # This enables downstream agents to read upstream artifacts
                if tool_name in DEFAULT_WRITE_TOOLS:
                    tool_input["root_dir"] = str(artifacts_dir)
                else:
                    # Read tools can access project root for cross-agent memory
                    tool_input["root_dir"] = str(project_path)

                normalized_path = ""
                if tool_name == "read_file_chunk":
                    normalized_path = _normalize_relative_path(str(tool_input.get("path") or ""))
                    if normalized_path and normalized_path in unavailable_read_paths:
                        tool_result = {
                            "tool_name": tool_name,
                            "status": "error",
                            "error_code": "KNOWN_PATH_UNAVAILABLE",
                            "duration_ms": 0,
                            "input": dict(tool_input or {}),
                            "output": {
                                "error": {
                                    "code": "KNOWN_PATH_UNAVAILABLE",
                                    "message": f"Previously confirmed missing path: {normalized_path}",
                                }
                            },
                        }
                    else:
                        tool_result = await asyncio.to_thread(_execute_tool_with_permission, tool_name, tool_input)
                else:
                    tool_result = await asyncio.to_thread(_execute_tool_with_permission, tool_name, tool_input)
                tool_results.append(tool_result)
                executed_action_summaries.append(
                    {
                        "action_index": action_index,
                        "tool_name": tool_name,
                        "status": tool_result.get("status"),
                        "error_code": tool_result.get("error_code"),
                        "duration_ms": tool_result.get("duration_ms"),
                    }
                )

                if (
                    tool_name == "read_file_chunk"
                    and tool_result.get("status") != "success"
                    and tool_result.get("error_code") == "PATH_NOT_FOUND"
                    and normalized_path
                ):
                    path_not_found_counts[normalized_path] = path_not_found_counts.get(normalized_path, 0) + 1
                    if path_not_found_counts[normalized_path] >= PATH_NOT_FOUND_REPEAT_LIMIT:
                        unavailable_read_paths.add(normalized_path)

                history_updates.extend(default_tool_history_entries(tool_name, tool_result))
                observations.append(
                    {
                        "step": step,
                        "action_index": action_index,
                        "tool_name": tool_name,
                        "tool_input": _sanitize_prompt_payload(tool_result.get("input") or {}, project_path),
                        "tool_output": _sanitize_prompt_payload(tool_result.get("output") or {}, project_path),
                        "evidence_note": decision.get("evidence_note", ""),
                    }
                )
                step_signatures.append(_tool_execution_signature(tool_name, tool_input, tool_result))

            if executed_action_summaries:
                react_trace[-1]["tool_results"] = executed_action_summaries
                if step_signatures and all(signature in execution_signatures_seen for signature in step_signatures):
                    repeated_action_steps += 1
                else:
                    repeated_action_steps = 0
                execution_signatures_seen.update(step_signatures)
                highest_path_not_found_repeat = max(path_not_found_counts.values(), default=0)
                if (
                    step >= REACT_MIN_STEPS_BEFORE_PLATEAU
                    and (
                        repeated_action_steps >= REACT_PLATEAU_WINDOW
                        or (
                            repeated_focus_steps >= REACT_PLATEAU_WINDOW
                            and highest_path_not_found_repeat >= PATH_NOT_FOUND_REPEAT_LIMIT
                        )
                    )
                ):
                    plateau_reason = (
                        f"repeated_action_steps={repeated_action_steps}, "
                        f"repeated_focus_steps={repeated_focus_steps}, "
                        f"path_not_found_repeat={highest_path_not_found_repeat}"
                    )
                    react_trace[-1]["controller_forced_done"] = plateau_reason
                    history_updates.append(
                        f"[{capability}] ReAct step {step}: controller detected repeated evidence plateau ({plateau_reason}); moving to final generation."
                    )
                    break
        else:
            react_exhausted = True
            history_updates.append(
                f"[{capability}] ReAct step {max_react_steps}: reached max steps."
            )

        if react_exhausted:
            reasoning_sections = [entry.get("reasoning", "") for entry in react_trace if entry.get("reasoning")]
            reasoning_sections.append(
                f"ReAct loop exhausted {max_react_steps} steps without reaching done=true (evidence sufficient). Final artifact generation was skipped."
            )
            (logs_dir / f"{capability}-reasoning.md").write_text(
                "\n\n".join(section for section in reasoning_sections if section),
                encoding="utf-8",
            )

            evidence = default_build_evidence(
                capability,
                payload,
                {},
                observations,
                react_trace,
                tool_results,
                expected_files,
                candidate_output_files,
                output_plan,
            )
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
            evidence["failure_reason"] = "max_steps_exhausted"
            (evidence_dir / f"{capability}.json").write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            history_updates.append(f"[{capability}] Completed with status: failed")
            return {
                "history": history_updates,
                "task_queue": update_task_status_fn(state["task_queue"], capability, "failed"),
                "human_intervention_required": False,
                "last_worker": capability,
                "tool_results": tool_results,
            }

        final_trace: List[Dict[str, Any]] = []
        finalization_observations: List[Dict[str, Any]] = []
        workspace_paths = _persist_workspace_snapshot(
            project_path=project_path,
            payload=payload,
            capability=capability,
            candidate_files=candidate_files,
            candidate_output_files=candidate_output_files,
            expected_files=expected_files,
            output_plan=output_plan,
            observations=observations,
            react_trace=react_trace,
            upstream_artifacts=upstream_artifacts,
            artifacts_dir=artifacts_dir,
            work_dir=work_dir,
            final_trace=final_trace,
        )

        artifacts_output: Dict[str, str] = {}
        final_reasoning_sections: List[str] = []
        timeout_fallback_records: List[Dict[str, Any]] = []

        if execution_guard_fn:
            abort_info = execution_guard_fn()
            if abort_info:
                return _build_abort_result(abort_info)

        if generate_final_artifacts_fn:
            llm_output = await asyncio.to_thread(
                generate_final_artifacts_fn,
                payload,
                observations,
                templates,
                expected_files,
            )

            if any(not (llm_output.artifacts.get(name) or "").strip() for name in expected_files):
                if fallback_artifacts_fn:
                    llm_output = fallback_artifacts_fn(payload, observations, expected_files)
                else:
                    llm_output = default_fallback_artifacts(capability, payload, observations, expected_files)

            artifacts_output = dict(llm_output.artifacts)
            final_reasoning_sections.append(llm_output.reasoning)

            for artifact_name in expected_files:
                artifact_content = artifacts_output.get(artifact_name, "")
                if Path(artifact_name).suffix.lower() == ".md":
                    artifact_content, was_trimmed = _enforce_markdown_budget(
                        artifact_content,
                        _resolve_output_char_budget(state, capability, artifact_name),
                    )
                    if was_trimmed:
                        history_updates.append(
                            f"[{capability}] Final artifact `{artifact_name}` exceeded the markdown size budget and was truncated by the controller."
                        )
                        final_reasoning_sections.append(
                            f"Controller truncated `{artifact_name}` to the configured markdown size budget."
                        )
                artifacts_output[artifact_name] = artifact_content
                (artifacts_dir / artifact_name).write_text(artifact_content, encoding="utf-8")
        else:
            finalization_budget = _estimate_finalization_budget(
                state=state,
                expected_files=expected_files,
            )
            history_updates.append(
                f"[SYSTEM] Finalization budget resolved to {finalization_budget} step(s)."
            )
            finalization_completed = not expected_files
            step = 0

            for target_file in _ordered_selected_outputs(output_plan, expected_files):
                generation_batches = _build_generation_batches(target_file, output_plan)
                for batch in generation_batches:
                    if step >= finalization_budget:
                        break

                    target_path = artifacts_dir / target_file
                    step += 1
                    combined_observations = observations + finalization_observations
                    workspace_paths = _persist_workspace_snapshot(
                        project_path=project_path,
                        payload=payload,
                        capability=capability,
                        candidate_files=candidate_files,
                        candidate_output_files=candidate_output_files,
                        expected_files=expected_files,
                        output_plan=output_plan,
                        observations=combined_observations,
                        react_trace=react_trace,
                        upstream_artifacts=upstream_artifacts,
                        artifacts_dir=artifacts_dir,
                        work_dir=work_dir,
                        final_trace=final_trace,
                    )
                    artifact_status = _collect_artifact_status(artifacts_dir, expected_files)
                    coverage_brief_for_batch = _read_workspace_json(artifacts_dir / workspace_paths["coverage_brief"])
                    artifact_char_budget = _resolve_output_char_budget(state, capability, target_file)
                    generation_exception: Optional[Exception] = None
                    try:
                        llm_output = await asyncio.to_thread(
                            default_generate_artifact_for_output,
                            _generate_with_selected_llm,
                            capability,
                            project_id,
                            version,
                            payload,
                            workspace_paths,
                            artifacts_dir,
                            target_file,
                            output_plan,
                            templates,
                            agent_config,
                            step,
                            batch.get("section_focus") or [],
                            int(batch.get("batch_index") or 1),
                            int(batch.get("batch_total") or 1),
                        )
                        generated_content = str(llm_output.artifacts.get(target_file) or "")
                        if llm_output.reasoning:
                            final_reasoning_sections.append(llm_output.reasoning)
                    except Exception as exc:
                        generation_exception = exc
                        if _is_timeout_exception(exc):
                            generated_content = _build_timeout_fallback_fragment(
                                target_file=target_file,
                                section_focus=list(batch.get("section_focus") or []),
                                batch_index=int(batch.get("batch_index") or 1),
                                batch_total=int(batch.get("batch_total") or 1),
                                output_plan=output_plan,
                                coverage_brief=coverage_brief_for_batch,
                            )
                            final_reasoning_sections.append(
                                f"Timeout fallback used for {target_file} batch {batch.get('batch_index')}/{batch.get('batch_total')}: {exc}"
                            )
                            timeout_fallback_records.append(
                                {
                                    "target_file": target_file,
                                    "batch_index": int(batch.get("batch_index") or 1),
                                    "batch_total": int(batch.get("batch_total") or 1),
                                    "error": str(exc),
                                }
                            )
                            history_updates.append(
                                f"[{capability}] Finalization step {step}: LLM timeout while generating `{target_file}` batch {batch.get('batch_index')}/{batch.get('batch_total')}`; writing controller fallback fragment instead."
                            )
                        else:
                            raise

                    if not generated_content.strip():
                        if fallback_artifacts_fn:
                            fallback_output = fallback_artifacts_fn(payload, combined_observations, [target_file])
                        else:
                            fallback_output = default_fallback_artifacts(capability, payload, combined_observations, [target_file])
                        generated_content = str(fallback_output.artifacts.get(target_file) or "")
                        if fallback_output.reasoning:
                            final_reasoning_sections.append(fallback_output.reasoning)

                    current_content = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
                    is_append_batch = bool(current_content) and int(batch.get("batch_total") or 1) > 1 and int(batch.get("batch_index") or 1) > 1
                    if is_append_batch:
                        new_content = f"{current_content.rstrip()}\n\n{generated_content.lstrip()}"
                        if Path(target_file).suffix.lower() == ".md":
                            new_content, was_trimmed = _enforce_markdown_budget(new_content, artifact_char_budget)
                            if was_trimmed:
                                history_updates.append(
                                    f"[{capability}] Finalization step {step}: controller truncated `{target_file}` to the markdown size budget."
                                )
                        tool_name = "patch_file"
                        tool_input = {
                            "path": target_file,
                            "old_content": current_content,
                            "new_content": new_content,
                            "root_dir": str(artifacts_dir),
                        }
                        decision_tool_input = {
                            "path": target_file,
                            "old_content_summary": f"<omitted {len(current_content)} chars>",
                            "new_content_summary": f"<omitted {len(new_content)} chars>",
                        }
                    elif target_path.exists():
                        if Path(target_file).suffix.lower() == ".md":
                            generated_content, was_trimmed = _enforce_markdown_budget(generated_content, artifact_char_budget)
                            if was_trimmed:
                                history_updates.append(
                                    f"[{capability}] Finalization step {step}: controller truncated `{target_file}` to the markdown size budget."
                                )
                        tool_name = "patch_file"
                        tool_input = {
                            "path": target_file,
                            "old_content": current_content,
                            "new_content": generated_content,
                            "root_dir": str(artifacts_dir),
                        }
                        decision_tool_input = {
                            "path": target_file,
                            "old_content_summary": f"<omitted {len(current_content)} chars>",
                            "new_content_summary": f"<omitted {len(generated_content)} chars>",
                        }
                    else:
                        if Path(target_file).suffix.lower() == ".md":
                            generated_content, was_trimmed = _enforce_markdown_budget(generated_content, artifact_char_budget)
                            if was_trimmed:
                                history_updates.append(
                                    f"[{capability}] Finalization step {step}: controller truncated `{target_file}` to the markdown size budget."
                                )
                        tool_name = "write_file"
                        tool_input = {
                            "path": target_file,
                            "content": generated_content,
                            "root_dir": str(artifacts_dir),
                        }
                        decision_tool_input = {
                            "path": target_file,
                            "content_summary": f"<omitted {len(generated_content)} chars>",
                        }

                    decision = {
                        "done": False,
                        "thought": f"Generate and persist `{target_file}` batch {batch.get('batch_index')}/{batch.get('batch_total')} based on the selected output plan and grounded workspace context.",
                        "tool_name": tool_name,
                        "tool_input": decision_tool_input,
                        "actions": [],
                        "evidence_note": f"Produce the planned final artifact `{target_file}` batch {batch.get('batch_index')}/{batch.get('batch_total')}.",
                        "target_file": target_file,
                        "batch_index": batch.get("batch_index"),
                        "batch_total": batch.get("batch_total"),
                        "section_focus": batch.get("section_focus") or [],
                        "reasoning": (
                            f"Timeout fallback fragment generated by controller: {generation_exception}"
                            if generation_exception and _is_timeout_exception(generation_exception)
                            else (llm_output.reasoning if 'llm_output' in locals() else "")
                        ),
                    }
                    final_trace.append({"step": step, **decision, "artifact_status": artifact_status})
                    final_step_log_path = _write_finalization_step_log(
                        logs_dir=logs_dir,
                        capability=capability,
                        step=step,
                        decision=decision,
                        artifact_status=artifact_status,
                        workspace_paths=workspace_paths,
                        project_root=project_path,
                    )
                    history_updates.append(
                        f"[{capability}] Finalization step {step}: step log written to logs/finalization/{capability}/{final_step_log_path.name}."
                    )
                    history_updates.append(
                        f"[{capability}] Finalization step {step}: writing planned artifact `{target_file}` batch {batch.get('batch_index')}/{batch.get('batch_total')}."
                    )

                    tool_result = await asyncio.to_thread(_execute_tool_with_permission, tool_name, tool_input)
                    tool_results.append(tool_result)
                    history_updates.extend(default_tool_history_entries(tool_name, tool_result))
                    executed_action_summaries = [
                        {
                            "action_index": 1,
                            "tool_name": tool_name,
                            "status": tool_result.get("status"),
                            "error_code": tool_result.get("error_code"),
                            "duration_ms": tool_result.get("duration_ms"),
                        }
                    ]
                    finalization_observations.append(
                        {
                            "step": step,
                            "action_index": 1,
                            "tool_name": tool_name,
                            "tool_input": _sanitize_prompt_payload(tool_result.get("input") or {}, project_path),
                            "tool_output": _sanitize_prompt_payload(tool_result.get("output") or {}, project_path),
                            "evidence_note": decision.get("evidence_note", ""),
                            "stage": "finalization",
                            "target_file": target_file,
                            "batch_index": batch.get("batch_index"),
                            "batch_total": batch.get("batch_total"),
                        }
                    )
                    final_trace[-1]["tool_results"] = executed_action_summaries
                    _write_finalization_step_log(
                        logs_dir=logs_dir,
                        capability=capability,
                        step=step,
                        decision=final_trace[-1],
                        artifact_status=_collect_artifact_status(artifacts_dir, expected_files),
                        workspace_paths=workspace_paths,
                        project_root=project_path,
                        tool_results=executed_action_summaries,
                    )

                if step >= finalization_budget:
                    break

            finalization_completed = _all_expected_artifacts_complete(artifacts_dir, expected_files)
            if not finalization_completed:
                combined_observations = observations + finalization_observations
                workspace_paths = _persist_workspace_snapshot(
                    project_path=project_path,
                    payload=payload,
                    capability=capability,
                    candidate_files=candidate_files,
                    candidate_output_files=candidate_output_files,
                    expected_files=expected_files,
                    output_plan=output_plan,
                    observations=combined_observations,
                    react_trace=react_trace,
                    upstream_artifacts=upstream_artifacts,
                    artifacts_dir=artifacts_dir,
                    work_dir=work_dir,
                    final_trace=final_trace,
                )
                reasoning_sections = [entry.get("reasoning", "") for entry in react_trace if entry.get("reasoning")]
                reasoning_sections.extend(final_reasoning_sections)
                reasoning_sections.append(
                    f"Finalization loop exhausted {finalization_budget} steps without producing all expected artifacts."
                )
                (logs_dir / f"{capability}-reasoning.md").write_text(
                    "\n\n".join(section for section in reasoning_sections if section),
                    encoding="utf-8",
                )

                evidence = default_build_evidence(
                    capability,
                    payload,
                    {},
                    observations + finalization_observations,
                    react_trace + final_trace,
                    tool_results,
                    expected_files,
                    candidate_output_files,
                    output_plan,
                )
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
                evidence["failure_reason"] = "finalization_max_steps_exhausted"
                evidence["react_trace"] = react_trace
                evidence["finalization_trace"] = final_trace
                evidence["workspace_paths"] = workspace_paths
                (evidence_dir / f"{capability}.json").write_text(
                    json.dumps(evidence, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

                history_updates.append(f"[{capability}] Completed with status: failed")
                return {
                    "history": history_updates,
                    "task_queue": update_task_status_fn(state["task_queue"], capability, "failed"),
                    "human_intervention_required": False,
                    "last_worker": capability,
                    "tool_results": tool_results,
                }

            artifacts_output = {
                artifact_name: (artifacts_dir / artifact_name).read_text(encoding="utf-8")
                for artifact_name in expected_files
            }

        combined_observations = observations + finalization_observations
        workspace_paths = _persist_workspace_snapshot(
            project_path=project_path,
            payload=payload,
            capability=capability,
            candidate_files=candidate_files,
            candidate_output_files=candidate_output_files,
            expected_files=expected_files,
            output_plan=output_plan,
            observations=combined_observations,
            react_trace=react_trace,
            upstream_artifacts=upstream_artifacts,
            artifacts_dir=artifacts_dir,
            work_dir=work_dir,
            final_trace=final_trace,
        )

        # Write reasoning
        reasoning_sections = [entry.get("reasoning", "") for entry in react_trace if entry.get("reasoning")]
        reasoning_sections.extend(final_reasoning_sections)
        (logs_dir / f"{capability}-reasoning.md").write_text(
            "\n\n".join(section for section in reasoning_sections if section),
            encoding="utf-8",
        )

        # Build evidence
        evidence = default_build_evidence(
            capability,
            payload,
            artifacts_output,
            combined_observations,
            react_trace + final_trace,
            tool_results,
            expected_files,
            candidate_output_files,
            output_plan,
        )
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
        evidence["react_trace"] = react_trace
        evidence["finalization_trace"] = final_trace
        evidence["workspace_paths"] = workspace_paths
        if timeout_fallback_records:
            evidence["failure_reason"] = "finalization_timeout_fallback"
            evidence["timeout_fallbacks"] = timeout_fallback_records
        (evidence_dir / f"{capability}.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        final_status = "failed" if timeout_fallback_records else "success"
        history_updates.append(f"[{capability}] Completed with status: {final_status}")
        return {
            "history": history_updates,
            "task_queue": update_task_status_fn(state["task_queue"], capability, final_status),
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


def _load_templates_for_capability(
    base_dir: Path,
    capability: str,
    agent_config: Optional["AgentFullConfig"],
) -> Dict[str, str]:
    """Load templates for a specific capability."""
    templates = {}
    
    # First, try to use templates from agent_config
    configured_templates = getattr(agent_config, "templates", None) if agent_config else None
    if configured_templates:
        templates.update(configured_templates)
    
    # Then, load from default template directory
    template_dir = base_dir / "skills" / capability / "assets" / "templates"
    if template_dir.exists():
        for template_file in template_dir.glob("*"):
            if template_file.is_file():
                templates[template_file.name] = template_file.read_text(encoding="utf-8")
    
    # Also check global templates
    global_template_dir = base_dir / "assets" / "templates"
    if global_template_dir.exists():
        for template_file in global_template_dir.glob("*"):
            if template_file.is_file() and template_file.name not in templates:
                templates[template_file.name] = template_file.read_text(encoding="utf-8")
    
    return templates


# Cross-agent memory: upstream artifact mapping
# Defines which upstream artifacts each agent should read for cross-agent memory
# Note: This is a fallback when registry is not available; prefer registry configuration
UPSTREAM_ARTIFACT_MAPPING_FALLBACK: Dict[str, Dict[str, List[str]]] = {
    "config-design": {
        "architecture-mapping": ["architecture.md", "module-map.json"],
    },
    "data-design": {
        "architecture-mapping": ["architecture.md", "module-map.json"],
    },
    "ddd-structure": {
        "data-design": ["schema.sql", "er.md", "migration-plan.md"],
    },
    "api-design": {
        "architecture-mapping": ["architecture.md", "module-map.json"],
        "data-design": ["schema.sql", "er.md", "migration-plan.md"],
        "ddd-structure": ["class-diagram.md", "ddd-structure.md", "context-map.md"],
    },
    "flow-design": {
        "architecture-mapping": ["architecture.md", "module-map.json"],
    },
    "integration-design": {
        "architecture-mapping": ["architecture.md", "module-map.json"],
    },
    "ops-design": {
        "config-design": ["config-catalog.yaml", "config-matrix.md"],
    },
    "test-design": {
        "flow-design": ["sequence.md", "state.md"],
        "api-design": ["api-design.md", "errors-rfc9457.json"],
        "integration-design": ["integration.md", "asyncapi.yaml"],
        "ops-design": ["slo.yaml", "observability-spec.yaml", "deployment-runbook.md"],
    },
    "validator": {
        "design-assembler": ["detailed-design.md", "traceability.json", "review-checklist.md"],
    },
}


def _get_expected_artifacts_by_agent() -> Dict[str, List[str]]:
    """Get expected artifacts mapping from registry. Returns {capability: [expected_outputs]}."""
    try:
        from registry.expert_registry import ExpertRegistry
        registry = ExpertRegistry.get_instance()
        return {
            manifest.capability: manifest.expected_outputs
            for manifest in registry.get_all_manifests()
            if manifest.expected_outputs
        }
    except RuntimeError:
        return {}


def _get_upstream_artifact_mapping() -> Dict[str, Dict[str, List[str]]]:
    """Get upstream artifact mapping from registry config.
    
    Reads from expert.yaml `upstream_artifacts` field if defined.
    Falls back to UPSTREAM_ARTIFACT_MAPPING_FALLBACK.
    """
    try:
        from registry.expert_registry import ExpertRegistry
        registry = ExpertRegistry.get_instance()
        result: Dict[str, Dict[str, List[str]]] = {}
        for manifest in registry.get_all_manifests():
            if manifest.upstream_artifacts:
                result[manifest.capability] = manifest.upstream_artifacts
        return result if result else UPSTREAM_ARTIFACT_MAPPING_FALLBACK
    except RuntimeError:
        return UPSTREAM_ARTIFACT_MAPPING_FALLBACK


def _discover_upstream_artifacts(capability: str, artifacts_dir: Path) -> Dict[str, List[str]]:
    """
    Discover upstream artifacts that exist in the artifacts directory.
    
    This enables cross-agent memory: downstream agents can read artifacts
    produced by upstream agents.
    
    Args:
        capability: Current agent's capability
        artifacts_dir: Path to the artifacts directory
        
    Returns:
        Dict mapping upstream agent -> list of existing artifact files
    """
    upstream_map = _get_upstream_artifact_mapping().get(capability, {})
    if not upstream_map:
        return {}
    
    discovered: Dict[str, List[str]] = {}
    
    if not artifacts_dir.exists():
        return discovered
    
    existing_files = set()
    for f in artifacts_dir.iterdir():
        if f.is_file():
            existing_files.add(f.name)
    
    for upstream_agent, expected_files in upstream_map.items():
        found = [f for f in expected_files if f in existing_files]
        if found:
            discovered[upstream_agent] = found
    
    return discovered


def _default_expected_files(capability: str) -> List[str]:
    """Get default expected files for a capability from registry."""
    artifacts_map = _get_expected_artifacts_by_agent()
    if capability in artifacts_map:
        return artifacts_map[capability]
    return ["output.md"]
