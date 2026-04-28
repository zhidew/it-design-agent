"""Deterministic runtime hooks for the design-assembler skill.

The generic dynamic subagent runner loads this file as an optional skill-owned
extension. Keep assembler-specific aggregation rules here instead of hardcoding
them in the global orchestration layer.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


OWN_OUTPUTS = {
    "detailed-design.md",
    "implementation-plan.json",
    "traceability.json",
    "review-checklist.md",
}

DETAILED_DESIGN_REQUIRED_MUST_COVER_GROUPS = [
    {
        "label": "synthesis / 综合结论",
        "keywords": [
            "synthesis",
            "synthesized",
            "final design",
            "design conclusion",
            "core conclusion",
            "综合",
            "汇总",
            "聚合",
            "整合",
            "最终设计",
            "设计结论",
            "核心设计结论",
        ],
    },
    {
        "label": "cross-artifact alignment / 跨产物一致性",
        "keywords": [
            "cross-artifact",
            "alignment",
            "consistency",
            "conflict",
            "gap",
            "upstream artifact",
            "跨产物",
            "跨专家",
            "一致性",
            "对齐",
            "冲突",
            "缺口",
            "上游产物",
        ],
    },
    {
        "label": "traceability / 追踪关系",
        "keywords": [
            "traceability",
            "trace",
            "source",
            "requirement mapping",
            "decision source",
            "evidence",
            "追踪",
            "追溯",
            "映射",
            "来源",
            "需求",
            "关键决策",
            "证据",
        ],
    },
    {
        "label": "residual risks and open questions / 残余风险和待确认项",
        "keywords": [
            "residual risk",
            "risk",
            "assumption",
            "open question",
            "unresolved",
            "low confidence",
            "待确认",
            "待澄清",
            "残余风险",
            "风险",
            "假设",
            "未决",
            "低置信",
        ],
    },
]


def _normalize_relative_path(raw_path: str) -> str:
    return raw_path.strip().replace("\\", "/").lstrip("./")


def _clip_text(value: Any, limit: int = 500) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _string_items(values: Any, limit: int) -> List[str]:
    if not isinstance(values, list):
        return []
    return [str(item).strip() for item in values if str(item).strip()][:limit]


def discover_upstream_artifacts(*, artifacts_dir: Path) -> Dict[str, List[str]]:
    if not artifacts_dir.exists():
        return {}
    actual_files = sorted(
        _normalize_relative_path(item.name)
        for item in artifacts_dir.iterdir()
        if item.is_file()
        and item.name not in OWN_OUTPUTS
        and not item.name.startswith(".")
    )
    return {"actual_workspace": actual_files} if actual_files else {}


def default_must_cover_items(*, target_file: str) -> List[str]:
    basename = Path(_normalize_relative_path(target_file)).name
    if basename != "detailed-design.md":
        return []
    return [
        "聚合上游设计结论，覆盖跨产物一致性/冲突/缺口、需求与关键决策追踪，以及残余风险和待确认项。",
    ]


def required_must_cover_groups(*, target_file: str) -> List[Dict[str, Any]]:
    basename = Path(_normalize_relative_path(target_file)).name
    if basename != "detailed-design.md":
        return []
    return DETAILED_DESIGN_REQUIRED_MUST_COVER_GROUPS


def output_planning_rule(*, candidate_outputs: List[str]) -> str:
    candidate_names = {Path(_normalize_relative_path(item)).name for item in candidate_outputs}
    if "detailed-design.md" not in candidate_names:
        return ""
    return (
        "If `detailed-design.md` is selected, must-cover items must stay inside the assembler boundary: "
        "synthesis / 综合结论, cross-artifact alignment / 跨产物一致性（含冲突和缺口）, "
        "traceability / 追踪关系, and residual risks or open questions / 残余风险和待确认项. "
        "Do not require domain-specific implementation details such as critical path, fallback, schema, API, test, "
        "or ops details unless they are already grounded in upstream artifacts. Use Simplified Chinese wording when the project language is Chinese."
    )


def targeted_artifact_rule(*, target_file: str) -> str:
    basename = Path(_normalize_relative_path(target_file)).name
    if basename != "detailed-design.md":
        return ""
    return (
        "For `detailed-design.md`, derive headings from `assembly-plan.json` and the actual upstream artifacts "
        "summarized in the user prompt; do not create empty sections for artifact types that are absent from this workspace."
    )


def finalization_rule(*, workspace_paths: Dict[str, str]) -> str:
    if not workspace_paths.get("assembly_plan"):
        return ""
    return (
        "For design-assembler outputs, follow `assembly-plan.json`: create `detailed-design.md` sections from its dynamic outline, "
        "fill `traceability.json` from its traceability seeds, and derive `review-checklist.md` from its alignment checks, gaps, risks, and open questions."
    )


def _artifact_summary_text(row: Dict[str, Any]) -> str:
    section_summaries = row.get("section_summaries") or []
    if isinstance(section_summaries, list):
        parts = []
        for section in section_summaries[:4]:
            if not isinstance(section, dict):
                continue
            heading = str(section.get("heading") or "").strip()
            body = str(section.get("body_summary") or "").strip()
            if heading or body:
                parts.append(f"{heading}: {body}".strip(": "))
        if parts:
            return "；".join(parts)

    headings = _string_items(row.get("headings"), 8)
    if headings:
        return "包含章节：" + "、".join(headings)

    keys = _string_items(row.get("top_level_keys"), 12)
    if keys:
        return "包含字段：" + "、".join(keys)

    excerpt = str(row.get("excerpt") or "").strip()
    return excerpt or "当前产物缺少可摘要文本，需要人工复核。"


def build_workspace_plan(
    *,
    actual_workspace_artifacts: List[Dict[str, Any]],
    output_plan: Dict[str, Any],
    coverage_brief: Dict[str, Any],
) -> Dict[str, Any]:
    selected_outputs = list(output_plan.get("selected_outputs") or [])
    source_artifacts: List[Dict[str, Any]] = []
    expert_conclusions: List[Dict[str, Any]] = []
    traceability_seeds: List[Dict[str, Any]] = []
    outline_sections: List[Dict[str, Any]] = [
        {
            "heading": "设计聚合总览",
            "purpose": "说明本次聚合覆盖的实际上游产物、未覆盖范围和总装结论边界。",
            "sources": [],
        }
    ]

    for row in actual_workspace_artifacts:
        if not isinstance(row, dict):
            continue
        path = str(row.get("path") or "").strip()
        if not path:
            continue
        owner = str(row.get("source_owner") or "actual_workspace").strip()
        headings = _string_items(row.get("headings"), 8)
        top_level_keys = _string_items(row.get("top_level_keys"), 12)
        source_artifacts.append(
            {
                "path": path,
                "source_owner": owner,
                "kind": row.get("kind"),
                "size_bytes": row.get("size_bytes"),
                "headings": headings,
                "top_level_keys": top_level_keys,
            }
        )
        expert_conclusions.append(
            {
                "source_artifact": path,
                "source_owner": owner,
                "summary": _clip_text(_artifact_summary_text(row)),
                "confidence": "medium",
            }
        )
        traceability_seeds.append(
            {
                "source_artifact": path,
                "anchors": headings[:6] or top_level_keys[:6],
                "expected_use": "用于支撑 detailed-design.md 的综合结论、traceability.json 的来源映射和 review-checklist.md 的评审项。",
            }
        )
        display_name = headings[0] if headings else path
        outline_sections.append(
            {
                "heading": f"来自 {display_name} 的设计结论",
                "purpose": "提炼该上游产物中可被设计总装引用的结论、约束和待确认项。",
                "sources": [path],
            }
        )

    source_paths = [row["path"] for row in source_artifacts]
    if source_paths:
        open_questions = [
            "请确认各上游产物之间是否存在未被显式记录的业务优先级或取舍。",
            "请确认低置信度或缺失来源的设计结论是否需要人工补证。",
        ]
        gaps: List[str] = []
    else:
        open_questions = [
            "未发现可聚合的上游专家产物，design-assembler 只能基于需求摘要输出待确认项。",
        ]
        gaps = [
            "缺少流程内专家产物，无法完成跨产物一致性检查和来源追踪。",
        ]

    outline_sections.extend(
        [
            {
                "heading": "跨产物一致性与缺口",
                "purpose": "比较实际上游产物之间的命名、依赖、约束、风险和待确认内容。",
                "sources": source_paths,
            },
            {
                "heading": "追踪关系与来源映射",
                "purpose": "将需求、关键设计决策、上游产物和验证项建立可追踪关系。",
                "sources": source_paths,
            },
            {
                "heading": "残余风险和待确认项",
                "purpose": "保留缺失、冲突、低置信和需要人工确认的事项。",
                "sources": source_paths,
            },
        ]
    )

    delivery_checklist = coverage_brief.get("delivery_checklist") or {}
    return {
        "capability": "design-assembler",
        "status": "ready" if source_artifacts else "missing_upstream_artifacts",
        "selected_outputs": selected_outputs,
        "source_artifacts": source_artifacts,
        "expert_conclusions": expert_conclusions,
        "cross_artifact_alignment": {
            "source_count": len(source_artifacts),
            "sources_considered": source_paths,
            "consistency_checks": [
                "检查上游产物之间的术语、模块、接口、数据、约束和风险表述是否一致。",
                "只聚合上游已有结论；缺少支撑的领域细节进入缺口或待确认项。",
            ],
            "known_gaps": gaps,
        },
        "traceability_seeds": traceability_seeds,
        "open_questions": open_questions,
        "detailed_design_outline": outline_sections,
        "review_contract": {
            "must_answer": list(delivery_checklist.get("must_answer") or [])[:6],
            "evidence_expectations": list(delivery_checklist.get("evidence_expectations") or [])[:6],
        },
    }


def resolve_template_hint(*, target_file: str, template_hint: str) -> str:
    basename = Path(_normalize_relative_path(target_file)).name
    if basename != "detailed-design.md":
        return template_hint
    return (
        "Do not follow a fixed detailed-design table of contents. Build the section structure dynamically "
        "from `assembly-plan.json`, `actual_workspace_artifacts`, `workspace_index.upstream_artifacts`, and the output plan. "
        "Only include sections for upstream artifact files that actually exist in this run; missing domains "
        "must appear as gaps or open questions instead of empty template sections."
    )
