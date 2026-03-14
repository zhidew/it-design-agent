# IT 详细设计 Agent 工作框架 v3（参考业界实践）

## 1. 设计基线（Industry Baseline）
本框架以以下主流标准/实践为基线：

1. 架构描述：ISO/IEC/IEEE 42010:2022（视角/视图与干系人关注点）。
2. 架构表达：C4 模型（Context/Container/Component/Code）+ arc42 章节组织。
3. 架构决策：ADR（Architecture Decision Records）。
4. 契约标准：OpenAPI（同步 HTTP API，内部与外部都适用，按受众区分 internal/public）+ AsyncAPI（异步事件）+ RFC 9457（错误语义）。
5. 结构化校验：JSON Schema 2020-12。
6. 可观测：OpenTelemetry 规范。
7. 安全与供应链：NIST SSDF、OWASP ASVS、SLSA。

## 2. 用户与场景（Frontend/Backend/QA/SRE）

### 2.1 核心用户诉求
- 前端开发：稳定接口契约、错误语义、流程状态。
- 后端开发：模块边界、DDD 结构、数据与集成设计。
- 测试人员：需求到测试可追踪、可覆盖主/异常/边界路径。
- SRE：可发布、可监控、可回滚、可审计。

### 2.2 用户旅程（项目级）
1. 设计启动：读取项目基线（需求、约束、已有资产）。
2. 方案生成：输出主产物（技术设计）与角色消费产物。
3. 评审验收：按角色门禁校验（前端/后端/测试/SRE）。
4. 交付执行：支撑开发、测试、发布与运行。
5. 运行反馈：将故障/告警/容量数据反哺下一版设计。

## 3. 能力边界与优先级

### 3.1 In Scope
- 需求到技术设计映射（项目级）。
- 资产驱动设计（代码/文档/数据库/运行数据）。
- 结构化产物生成、校验、追踪、汇编。

### 3.2 Out of Scope
- 修改业务目标与优先级。
- 直接执行生产变更（部署、DB 变更执行）。

### 3.3 能力优先级（MUST/SHOULD/Optional）

| 能力 | 优先级 | 触发条件 | 边界说明 |
|---|---|---|---|
| 架构映射 | MUST | 所有需求 | 输出模块边界与依赖关系 |
| API 设计 | MUST | 有服务接口 | 输出兼容策略与错误语义 |

| 数据与迁移设计 | MUST | 有数据变更 | 输出表结构、索引、迁移方案 |
| 流程/状态设计 | MUST | 有流程变更 | 输出主链路与异常链路 |
| 类图 + DDD 结构 | MUST | 领域建模或重构 | 输出边界与依赖规则 |
| 集成设计 | MUST | 跨服务/外部系统 | 输出协议、幂等、补偿策略 |
| 配置设计 | MUST | 多环境/开关/密钥 | 输出配置分层与治理方案 |
| 测试可设计性 | MUST | 所有需求 | 输出测试输入、覆盖映射、可测性约束 |
| 可观测与运行就绪 | MUST | 进入交付评审 | 输出 SLO、告警、回滚、运行手册 |
| 安全与供应链设计 | SHOULD | 涉及敏感数据/合规/外部依赖 | 输出威胁模型、控制项、SBOM/溯源 |
| 批处理设计 | SHOULD | 定时/离线任务存在 | 输出批任务调度与重跑策略 |
| 成本优化 | Optional | 成本受约束 | 输出容量与成本建议 |

### 3.4 执行模型（Orchestrator + Subagent + Skill）
1. `Orchestrator`：负责流程编排、任务路由、门禁控制、结果汇编。
2. `Subagent`：负责能力执行边界（输入输出产物、工具白名单、权限、失败策略），配置说明优先用中文描述。
3. `Skill`：负责能力表达（方法步骤、模板、校验规则、参考资料、脚本调用）。

### 3.5 设计约束（必须遵守）
1. 一个能力域对应一个主 `subagent`（可有扩展子能力）。
2. 一个 `subagent` 可挂多个 `skill`（基础版/行业版/高级版）。
3. 输出 Schema 固定在 `subagent` 层，`skill` 不得突破输出产物。
4. 工具权限与调用白名单在 `subagent` 层治理，不能仅靠 `skill` 约束。
5. `Orchestrator` 只接收结构化输出，不接收自由文本作为最终交付依据。
6. `subagent` 配置文件统一采用 `xxx-design.agent.yaml` 命名。
7. `subagent` 的 `name` 与 `description` 字段默认使用中文。
8. 同步 HTTP API 默认按受众拆分为 `openapi-internal.yaml` 和 `openapi-public.yaml`（按需）。


### 3.6 能力到 Subagent/Skill 映射（最小）
| 能力域 | Subagent（执行体） | Skill（能力规范） |
|---|---|---|
| API 设计 | `api-design-agent` | `api-design` |

| 数据与迁移设计 | `data-design-agent` | `data-model-design` |
| 流程/状态设计 | `flow-design-agent` | `flow-design` |
| 类图 + DDD 结构 | `ddd-structure-agent` | `ddd-code-structure-design` |
| 可观测与运行就绪 | `ops-readiness-agent` | `observability-design` |
| 文档汇编 | `design-assembler-agent` | `design-doc-assembler` |

## 4. 工具定义（Tooling）

### 4.1 工具分层
1. 资产读取工具：读取代码、历史设计文档、DDL、运行日志与指标。
2. 建模生成工具：OpenAPI/AsyncAPI/SQL/Mermaid/模板引擎。
3. 校验工具：语法、Schema、一致性、兼容性、依赖规则检查。
4. 证据工具：回填 `evidence/*.json`。
5. 安全工具：威胁建模检查、ASVS 清单检查、SBOM 与供应链溯源检查。

### 4.2 每个工具最小定义字段
- `tool_name`
- `purpose`（read/generate/validate/evidence/security）
- `input`
- `output`
- `failure_mode`
- `evidence_fields`

## 5. 能力 -> 角色 -> 资产 -> 工具 -> 反馈 -> 产出物

| 能力 | 主要角色 | 设计前资产 | 工具 | 工具反馈 | 产出物（项目级） |
|---|---|---|---|---|---|
| 架构映射 | 后端/SRE | 架构图、代码入口、历史 ADR | 文件检索、依赖分析 | 边界冲突、循环依赖 | `architecture.md`、`module-map.json`、`adr/ADR-*.md` |
| API 设计 | 前端/后端/测试 | 现有 API 文档、路由、错误码规范 | OpenAPI lint、diff 检查 | 兼容性风险、字段缺失、受众边界不清 | `openapi-internal.yaml`、`errors-rfc9457.json`、`openapi-public.yaml`（按需） |

| 数据与迁移设计 | 后端/测试/SRE | DDL、索引、迁移脚本、慢查询 | SQL lint、Schema diff | 迁移风险、索引收益 | `schema.sql`、`er.md`、`migration-plan.md` |
| 流程/状态设计 | 前端/后端/测试 | 业务流程文档、调用链、异常案例 | Mermaid、流程一致性检查 | 漏链路、状态缺口 | `sequence-*.md`、`state-*.md` |
| 类图 + DDD 结构 | 后端 | 领域代码、边界文档、目录结构 | 类关系抽取、依赖规则检查 | 跨上下文违规依赖 | `class-*.md`、`ddd-structure.md`、`context-map.md` |
| 集成设计 | 后端/测试/SRE | 外部接口、消息契约、重试策略 | 契约校验、幂等检查 | 协议不一致、补偿缺口 | `integration-*.md`、`asyncapi.yaml` |
| 配置设计 | 后端/SRE | 多环境配置、开关策略、密钥规范 | 配置 schema 校验、secret 扫描 | 环境漂移、配置风险 | `config-catalog.yaml`、`config-matrix.md` |
| 测试可设计性 | 测试/后端/前端 | 需求基线、流程图、错误语义 | 覆盖缺口检查、追踪矩阵检查 | 主/异常/边界覆盖缺口 | `test-inputs.md`、`coverage-map.json` |
| 可观测与运行就绪 | SRE/后端 | SLO/SLA、监控规范、故障复盘 | OTel 约束检查、告警规则检查 | 告警盲区、运行断点 | `slo.yaml`、`observability-spec.yaml`、`deployment-runbook.md` |
| 安全与供应链设计 | SRE/后端/测试 | 安全基线、合规要求、依赖清单 | 威胁建模、ASVS 清单、SBOM 检查 | 控制项缺口、依赖风险 | `threat-model.md`、`security-controls.yaml`、`sbom.spdx.json`、`provenance.intoto.jsonl` |
| 文档汇编 | 全角色 | 全部结构化产物、评审意见 | 汇编脚本、追踪校验 | 缺失章节、断链风险 | `detailed-design.md`、`traceability.json`、`review-checklist.md` |

## 6. 角色消费契约（必须）

| 角色 | 最小必需交付物 | 支撑后续活动 |
|---|---|---|
| 前端开发人员 | `openapi-internal.yaml`、`errors-rfc9457.json`、`sequence-*.md` | 联调、错误处理、状态实现 |
| 后端开发人员 | `module-map.json`、`ddd-structure.md`、`schema.sql`、`integration-*.md` | 开发拆解、依赖治理、数据与集成实现 |
| 测试人员 | `traceability.json`、`state-*.md`、`test-inputs.md`、`coverage-map.json` | 用例设计、覆盖验证、回归测试 |
| SRE | `slo.yaml`、`observability-spec.yaml`、`deployment-runbook.md`、`resilience-policy.md` | 发布评审、监控告警、回滚与值守 |

## 7. 质量门禁（项目级）
1. 资产门禁：MUST 能力未完成资产读取，不得进入评审。
2. 契约门禁：OpenAPI/AsyncAPI/错误语义/Schema 校验必须通过。
3. 数据门禁：迁移脚本与回滚策略必须成对提供。
4. 测试门禁：`REQ -> Design -> Test` 追踪链完整，覆盖缺口已标注与处理。
5. 运维门禁：SLO、告警、运行手册、回滚策略齐备。
6. 角色门禁：四类角色最小必需交付物缺任一项，不得进入交付状态。
7. 安全门禁（适用时）：威胁模型、关键控制项、SBOM/溯源产物齐备。

## 8. 项目级产出物范围与目录

### 8.1 范围规则
- 交付对象是“项目设计包”，而非单文档。
- 所有产物归属项目基线，不以个人临时文档为准。
- 跨项目依赖采用引用方式，不复制对方详细设计正文。

### 8.2 建议目录
```text
/projects/<project-id>/design
  /baseline
    requirements-baseline.json
    constraints.json
  /artifacts
    openapi.yaml
    asyncapi.yaml
    errors-rfc9457.json
    schema.sql
    architecture.md
    class-*.md
    sequence-*.md
    state-*.md
    ddd-structure.md
    config-catalog.yaml
    test-inputs.md
    coverage-map.json
    slo.yaml
    observability-spec.yaml
    deployment-runbook.md
    threat-model.md
    security-controls.yaml
    sbom.spdx.json
  /evidence
    *.json
  /adr
    ADR-*.md
  /release
    detailed-design.md
    traceability.json
    review-checklist.md
```

## 9. 与需求分析 Agent 的契约
- 输入只接受“需求基线 + 变更记录 + 影响矩阵”。
- 输入缺失关键字段时输出“设计阻塞清单”，不输出最终稿。
- 下游输出必须可追溯到 `REQ-*`，并映射至测试与运行产物。

## 10. 落地建议（2周最小化）
1. 第1周：固化 MUST 能力模板、角色最小交付物模板、证据 schema。
2. 第2周：接入校验流水线与角色门禁，在一个项目试点。



