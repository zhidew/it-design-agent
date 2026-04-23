"""Prompt guidance helpers for dynamic subagents."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from registry.expert_runtime_profile import ExpertRuntimeProfile, GENERIC_BOUNDARY_NOTE


_GENERIC_GUIDANCE_BY_SUFFIX = {
    ".sql": "落到可执行 DDL，明确新增/改造表、关键字段、索引、约束与兼容策略。",
    ".md": "覆盖设计动机、关键结构、约束、边界与引用证据。",
    ".json": "保持结构化、可被下游稳定消费，字段命名一致。",
    ".yaml": "输出可落地的契约/配置，不只给概念性描述。",
    ".yml": "输出可落地的契约/配置，不只给概念性描述。",
}

_CAPABILITY_HINTS = {
    "data-design": "重点回答表结构、字段、唯一键、索引、迁移/回滚。",
    "modular-design": "重点回答模块边界、复用点、上下文/容器职责。",
    "integration-design": "重点回答外部系统交互、消息契约、异常补偿与幂等。",
    "api-design": "重点回答接口路径、入参出参、幂等与权限边界。",
}


def _normalize_relative_path(raw_path: str) -> str:
    return str(raw_path or "").strip().replace("\\", "/").lstrip("./")


def render_boundary_note(profile: ExpertRuntimeProfile, capability: str) -> str:
    if profile.boundary_note:
        return profile.boundary_note
    return GENERIC_BOUNDARY_NOTE if not capability else profile.boundary_note or GENERIC_BOUNDARY_NOTE


def resolve_guidance_for_target(
    profile: ExpertRuntimeProfile,
    target_file: str,
) -> str:
    normalized_target = _normalize_relative_path(target_file)
    basename = Path(normalized_target).name
    prompt_hints = profile.prompt_hints or {}
    file_guidance = dict(prompt_hints.get("file_guidance") or {})

    if normalized_target in file_guidance:
        return str(file_guidance[normalized_target]).strip()

    for configured_path, guidance in file_guidance.items():
        if Path(configured_path).name == basename:
            return str(guidance).strip()

    default_guidance = str(prompt_hints.get("default_file_guidance") or "").strip()
    if default_guidance:
        return default_guidance

    capability_hint = _CAPABILITY_HINTS.get(
        profile.capability,
        "重点回答该专家负责的核心设计问题，并确保内容可落地。",
    )
    return f"{_GENERIC_GUIDANCE_BY_SUFFIX.get(Path(normalized_target).suffix.lower(), '输出需完整、结构化、可直接交付。')} {capability_hint}"


def resolve_file_guidance(
    profile: ExpertRuntimeProfile,
    expected_files: list[str],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for file_name in expected_files:
        normalized = _normalize_relative_path(file_name)
        rows.append(
            {
                "path": normalized,
                "guidance": resolve_guidance_for_target(profile, normalized),
            }
        )
    return rows
