# 详细设计说明书: {{project_name}}

> **版本**: {{version}}
> **生成时间**: {{generated_at}}

## 1. 业务需求概述
本文档基于需求基线生成。核心目标是交付 {{project_name}} 相关的业务价值。

## 2. 系统架构映射 (Architecture Mapping)
本章节描述了系统的物理与逻辑边界。
- **架构图与决策**: 详见 `artifacts/architecture.md`
- **模块依赖分析**: 详见 `artifacts/module-map.json`

## 3. 核心领域与类图设计 (Domain Design)
本章节描述了系统的核心业务语言与对象结构。
- **领域结构说明**: 详见 `artifacts/ddd-structure.md`
- **聚合根与实体**: 详见 `artifacts/class-*.md`

## 4. 流程与状态设计 (Flow & State)
描述关键业务链路的交互过程与生命周期。
- **业务时序图**: 详见 `artifacts/sequence-*.md`
- **实体状态机**: 详见 `artifacts/state-*.md`

## 5. 接口与集成契约 (Contracts & Integrations)
定义微服务对外提供以及依赖的外部系统契约。
- **内部 API 设计**: `artifacts/api-internal.yaml`
- **外部 API 设计**: `artifacts/api-public.yaml`
- **异常结构定义**: `artifacts/errors-rfc9457.json`
- **外部系统集成**: `artifacts/integration-*.md` 和 `artifacts/asyncapi.yaml`

## 6. 数据模型设计 (Data Design)
核心数据的存储与结构定义。
- **数据库字典(DDL)**: `artifacts/schema.sql`
- **实体关系图(ER)**: `artifacts/er.md`
- **数据迁移方案**: `artifacts/migration-plan.md`

## 7. 质量保证与运维属性
为下游的测试与运维提供基准指南。
- **测试覆盖与边界**: `artifacts/test-inputs.md`
- **SLO 与可观测基线**: `artifacts/slo.yaml` 及 `artifacts/observability-spec.yaml`
- **环境配置矩阵**: `artifacts/config-matrix.md`
- **发布与回滚手册**: `artifacts/deployment-runbook.md`
