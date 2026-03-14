# IT 详细设计 Agent 工作框架 v2（参考业界实践）

## 1. 设计原则（对齐业界实践）
本框架按“架构描述标准 + 文档结构标准 + 契约标准 + 可观测标准”设计：

1. 架构描述：采用“视角/视图”思想，避免单图覆盖一切。
2. 分层表达：采用 C4 的层次化表达（Context/Container/Component/Code）。
3. 文档编排：采用 arc42 的章节化组织思想，提升评审可读性。
4. 决策可追踪：采用 ADR 记录架构关键决策与取舍。
5. 接口契约：同步 API 用 OpenAPI；异步事件用 AsyncAPI；错误语义对齐 RFC 9457。
6. 结构化校验：所有 JSON/YAML 产物优先提供 JSON Schema（2020-12）校验。
7. 可观测落地：观测语义与采集路径优先对齐 OpenTelemetry 规范。

## 2. 能力边界定义（Capability Boundary）

### 2.1 Agent 负责（In Scope）
- 将需求基线映射为可实现的技术设计。
- 基于已有资产（代码/文档/数据库/运行数据）形成证据化设计。
- 输出结构化产物并通过机器校验。
- 汇编项目级详细设计文档并保留来源追踪。

### 2.2 Agent 不负责（Out of Scope）
- 修改业务目标、业务范围、需求优先级。
- 直接落地生产变更（代码上线、DB 变更执行）。
- 跳过资产读取直接“凭经验”产出最终方案。

### 2.3 能力优先级与触发条件

| 能力 | 优先级 | 触发条件 | 边界说明 |
|---|---|---|---|
| 架构映射 | MUST | 所有需求 | 负责模块边界与依赖，不负责业务优先级变更 |
| API 设计 | MUST | 有对外/内部接口 | 负责契约与兼容策略，不负责接口上线发布 |
| 数据设计 | MUST | 有数据落库/查询变更 | 负责模型与迁移方案，不负责执行迁移 |
| 流程/状态设计 | MUST | 有业务流程变更 | 负责主异常链路，不负责运行态调度 |
| 类图 + DDD 结构设计 | MUST | 涉及领域模型或重构 | 负责边界与依赖规则，不负责代码重写 |
| 配置设计 | MUST | 有环境差异/开关/密钥 | 负责配置分层，不负责密钥发放操作 |
| 集成设计 | MUST | 有外部系统或跨服务协同 | 负责协议/补偿/幂等，不负责联调执行 |
| 批处理设计 | SHOULD | 存在定时/离线任务 | 若无批任务可降级为 N/A |
| 韧性与性能设计 | SHOULD | 存在 SLO 或高可用要求 | 负责策略与指标，不负责压测实施 |
| 安全与可观测设计 | SHOULD | 有合规或运维要求 | 负责控制项与观测规范，不负责 SOC 执行 |
| 成本优化 | Optional | 成本为约束目标 | 作为设计建议，不作为阻塞项 |

## 3. 工具定义（Tooling Definition）
工具不是能力。工具仅用于“读取资产、生成产物、校验质量、沉淀证据”。

### 3.1 工具分层
1. 资产读取工具：代码/文档/数据库/运行信息读取。
2. 建模生成工具：OpenAPI、AsyncAPI、Mermaid、SQL、JSON/YAML 模板生成。
3. 校验工具：语法、Schema、一致性、依赖规则、兼容性检查。
4. 证据工具：将工具输出沉淀为 `evidence/*.json`，支撑评审追踪。

### 3.2 每个工具的最小定义字段
- `tool_name`：工具名
- `purpose`：用途（读取/生成/校验/证据）
- `input`：输入资产类型
- `output`：结构化输出
- `failure_mode`：失败时的处理策略
- `evidence_fields`：需要回填的证据字段

## 4. 能力 -> 用户角色 -> 资产 -> 工具 -> 反馈 -> 产出物 映射

| 能力 | 主要使用角色 | 支撑后续活动 | 设计前资产（必须） | 工具定义（示例） | 工具反馈（用于支撑设计） | 产出物（项目级） |
|---|---|---|---|---|---|---|
| 架构映射 | 后端、SRE | 模块拆分、部署边界确认 | 现有架构图、核心代码入口、历史 ADR、模块依赖 | `filesystem/git/依赖分析脚本` | 边界冲突、循环依赖、可复用模块清单 | `architecture.md`、`module-map.json`、`adr/ADR-*.md` |
| API 设计 | 前端、后端、测试 | 联调、契约测试、异常处理 | 现有 API 文档、网关路由、调用日志、错误码规范 | `OpenAPI lint`、兼容性 diff、示例回放 | 兼容性风险、参数缺失、错误码冲突 | `openapi.yaml`、`errors-rfc9457.json` |
| 数据设计 | 后端、测试、SRE | 开发落库、数据校验、容量评估 | DDL、索引、数据字典、迁移脚本、慢查询 | `SQL lint`、schema diff、索引建议 | 迁移风险、索引收益、字段约束冲突 | `schema.sql`、`er.md`、`migration-plan.md` |
| 流程/状态设计 | 前端、后端、测试 | 流程实现、状态测试、异常覆盖 | 业务流程文档、调用链、历史异常案例 | `Mermaid`、流程一致性检查脚本 | 主链路/异常链路覆盖度、状态缺口 | `sequence-*.md`、`state-*.md` |
| 类图 + DDD 结构 | 后端 | 代码结构落地、依赖治理 | 领域模型代码、上下文边界文档、目录结构 | 类关系抽取、静态依赖规则检查 | 聚合边界漂移、跨上下文违规依赖 | `class-*.md`、`context-map.md`、`ddd-structure.md` |
| 集成设计 | 后端、测试、SRE | 联调、故障演练、消息一致性验证 | 外部系统接口文档、消息契约、重试策略 | 契约校验、幂等检查、重试策略检查 | 协议不一致、补偿缺口、幂等冲突点 | `integration-*.md`、`asyncapi.yaml` |
| 批处理设计 | 后端、SRE、测试 | 定时任务开发、运行监控、回归验证 | 调度配置、批任务日志、失败重跑记录 | 调度/分片检查、吞吐评估脚本 | 瓶颈步骤、重复消费风险、RPO/RTO 风险 | `batch-*.md`、`batch-jobs.json` |
| 配置设计 | 后端、SRE | 环境准备、灰度开关、安全检查 | 多环境配置、开关策略、密钥规范、变更记录 | config schema 校验、secret scan、配置 diff | 环境漂移、敏感配置暴露风险 | `config-catalog.yaml`、`config-matrix.md` |
| 韧性与性能 | 后端、SRE、测试 | 降级策略、容量规划、性能测试输入 | SLO/SLA、容量数据、历史故障复盘 | 容量估算、限流/熔断策略检查 | 单点风险、容量水位、恢复时间估算 | `resilience-policy.md`、`capacity-plan.md`、`slo.yaml` |
| 安全与可观测 | SRE、后端、测试 | 监控告警、审计、上线值守 | 安全基线、审计要求、监控指标与日志规范 | policy check、OpenTelemetry 约束检查 | 控制项缺口、告警盲区、追踪断点 | `security-controls.yaml`、`observability-spec.yaml` |
| 文档汇编 | 全角色 | 开发评审、测试评审、上线评审 | 全部结构化产物、模板、评审意见 | 汇编脚本、追踪矩阵检查、文档渲染 | 缺失章节、来源断链、未闭环风险 | `detailed-design.md`、`traceability.json`、`review-checklist.md` |

## 5. 产出物标准（Output Artifacts）

### 5.1 结构化优先
- 每个产出物必须是可解析文本（`yaml/json/sql/md`）。
- 图统一用 Mermaid（`flowchart/sequence/state/class/er`）。
- 关键 JSON/YAML 必须有 Schema 校验本地。

### 5.2 证据化要求
每个能力至少一条证据记录（建议多条），保存在 `evidence/`：

```json
{
  "capability": "api-design",
  "asset_type": "doc",
  "source": "docs/api/v1.md",
  "tool": "spectral",

  "result_summary": "发现2个兼容性风险",
  "design_impact": "新增v2路径并保留v1",
  "confidence": 0.9
}
```

### 5.3 角色消费契约（必须）

| 角色 | 最小必需交付物 | 交付物用途 |
|---|---|---|
| 前端开发人员 | `openapi.yaml`、`errors-rfc9457.json`、`sequence-*.md` | 页面联调、异常处理、状态流转实现 |
| 后端开发人员 | `module-map.json`、`ddd-structure.md`、`schema.sql`、`integration-*.md` | 代码实现、依赖治理、集成与数据落地 |
| 测试人员 | `traceability.json`、`state-*.md`、`errors-rfc9457.json`、`test-inputs.md` | 用例设计、覆盖率检查、回归输入准备 |
| SRE | `slo.yaml`、`observability-spec.yaml`、`resilience-policy.md`、`deployment-runbook.md` | 发布评审、监控告警、回滚和值守执行 |

## 6. 质量门禁（可执行）
1. 资产门禁：MUST 能力未完成资产读取，禁止进入评审。
2. 语法门禁：OpenAPI/AsyncAPI/SQL/Mermaid/Schema 校验必须通过。
3. 一致性门禁：`REQ -> Design -> Test` 追踪链完整。
4. 风险门禁：高风险项必须有 Owner、缓解措施、计划日期。
5. 汇编门禁：最终文档仅由结构化产物汇编，不允许手工补写关键章节。
6. 角色门禁：四类角色最小必需交付物任一缺失，不得进入“可开发/可测试/可发布”状态。

## 7. 项目级产出物范围与目录（Project Scope）

### 7.1 范围规则
- 产出物归属“项目级基线”，不以个人文档作为交付基准。
- 交付对象是“项目设计包”，不是单一章节或单图。
- 跨项目依赖通过引用方式记录，不内嵌对方项目详细设计。

### 7.2 建议目录结构
```text
/projects/<project-id>/design
  /baseline
    requirements-baseline.json
    constraints.json
  /artifacts
    openapi.yaml
    asyncapi.yaml
    schema.sql
    architecture.md
    class-domain.md
    sequence-order.md
    state-order.md
    config-catalog.yaml
    ddd-structure.md
  /evidence
    architecture-mapping.json
    api-contract-design.json
  /adr
    ADR-0001-*.md
  /release
    detailed-design.md
    traceability.json
```

## 8. 与需求分析 Agent 的契约
- 输入只接受“需求基线 + 变更记录 + 影响矩阵”。
- 若输入缺失关键字段，返回“设计阻塞清单”，不输出最终稿。
- 下游输出必须可回溯到 `REQ-*`，并可映射到测试项。

## 9. 用户旅程视角下的执行检查点
1. 设计启动：四类角色关注点是否被转换为对应能力与产出物。
2. 设计生成：是否同时形成“主产物 + 角色最小交付物”。
3. 评审阶段：是否按角色完成门禁（前端/后端/测试/SRE）。
4. 交付阶段：项目级设计包是否可直接支撑开发、测试、发布活动。

## 10. 落地建议（2周最小化）
1. 第1周：固化 MUST 能力产物模板 + 角色最小交付物模板 + 校验脚本。
2. 第2周：接入文档汇编和角色门禁流水线，在一个项目试点。
