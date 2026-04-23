"""Delivery contract helpers for dynamic subagents."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from registry.expert_runtime_profile import ExpertRuntimeProfile


_LEGACY_DELIVERY_CHECKLIST_MAP = {
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
    "modular-design": {
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
        "evidence_expectations": ["契约要清晰到前后端可以直接讨论联调。"],
    },
    "flow-design": {
        "must_answer": [
            "批次主流程、补发回溯、员工/segment 重算、差异解释流程是否闭环。",
            "异常分支、回滚点、审计节点是否明确。",
        ],
        "evidence_expectations": ["流程图或步骤必须区分主干和异常路径。"],
    },
    "config-design": {
        "must_answer": [
            "灰度矩阵、开关、权限、规则版本绑定和回滚策略。",
            "配置项如何作用于不同法人、薪资组、月份。",
        ],
        "evidence_expectations": ["配置设计不能只有字段清单，要说明生效范围和优先级。"],
    },
    "ops-design": {
        "must_answer": [
            "指标、日志、审计、告警和故障恢复方案。",
            "批次、segment、税差异常、局部重算的可观测性。",
        ],
        "evidence_expectations": ["监控项要能转成实际运维检查项。"],
    },
    "test-design": {
        "must_answer": [
            "当前 IR 的颗粒度是否适中，是否需要拆分、并入或保持当前边界。",
            "当前 IR 是否需要新增测试策略设计；若不需要，复用哪份既有策略以及它的适用边界是什么。",
            "测试策略设计是否明确测试目标、范围边界、风险优先级、测试层级和进入/退出准则。",
            "测试方案设计是否基于策略设计结果展开，并说明验证主题簇、回归影响面、非功能关注点，以及数据/环境/观测方案。",
        ],
        "evidence_expectations": [
            "若只输出 test-solution-design.md，必须引用既有测试策略来源并解释继承关系。",
            "测试方案设计必须回指 IR 验收项与上游设计事实，禁止直接展开为测试用例步骤、等价类明细或边界值枚举。",
        ],
    },
    "ddd-structure": {
        "must_answer": [
            "聚合根、实体、值对象、命令模型与边界上下文。",
            "segment 的建模方式是否合理并解释取舍。",
        ],
        "evidence_expectations": ["命名和职责边界要与领域语言一致。"],
    },
    "validator": {
        "must_answer": ["方案内部的一致性、约束满足情况、遗漏风险。"],
        "evidence_expectations": ["指出冲突项、模糊项和残余风险。"],
    },
    "design-assembler": {
        "must_answer": [
            "多专家输出是否整合成一套一致方案。",
            "跨文档术语、边界、命名和结论是否统一。",
        ],
        "evidence_expectations": ["合并时要标出仍待确认的风险或空白。"],
    },
}


def _normalize_relative_path(raw_path: str) -> str:
    return str(raw_path or "").strip().replace("\\", "/").lstrip("./")


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            ordered.append(text)
    return ordered


def _match_review_target_path(configured_path: str, existing_paths: list[str]) -> str:
    normalized = _normalize_relative_path(configured_path)
    if normalized in existing_paths:
        return normalized

    basename = Path(normalized).name
    basename_matches = [path for path in existing_paths if Path(path).name == basename]
    if len(basename_matches) == 1:
        return basename_matches[0]
    return normalized


def build_generic_artifact_review(
    expected_files: list[str],
) -> dict[str, list[str]]:
    artifact_review_checklist: dict[str, list[str]] = {}
    for file_name in expected_files:
        normalized = _normalize_relative_path(file_name)
        suffix = Path(normalized).suffix.lower()
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
        artifact_review_checklist[normalized] = review_items
    return artifact_review_checklist


def merge_artifact_review(
    generic_review: dict[str, list[str]],
    configured_review: dict[str, Any],
) -> dict[str, list[str]]:
    merged = {path: list(items) for path, items in (generic_review or {}).items()}
    for raw_path, items in (configured_review or {}).items():
        target_path = _match_review_target_path(str(raw_path or ""), list(merged.keys()))
        configured_items = [str(item).strip() for item in (items or []) if str(item).strip()]
        merged[target_path] = _dedupe_preserve_order(list(merged.get(target_path, [])) + configured_items)
    return merged


def build_delivery_checklist(
    profile: ExpertRuntimeProfile,
    capability: str,
    expected_files: list[str],
) -> dict[str, Any]:
    configured = profile.delivery_contract or {}
    legacy = _LEGACY_DELIVERY_CHECKLIST_MAP.get(
        capability,
        {
            "must_answer": ["该专家负责的核心设计问题是否被完整回答。"],
            "evidence_expectations": ["输出必须结构化、可交付，并与证据一致。"],
        },
    )
    generic_review = build_generic_artifact_review(expected_files)
    configured_review = configured.get("artifact_review_checklist") or {}
    return {
        "must_answer": list(configured.get("must_answer") or legacy["must_answer"]),
        "evidence_expectations": list(configured.get("evidence_expectations") or legacy["evidence_expectations"]),
        "artifact_review_checklist": merge_artifact_review(generic_review, configured_review),
    }
