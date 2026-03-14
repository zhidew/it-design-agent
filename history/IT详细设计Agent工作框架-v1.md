# IT 详细设计 Agent 工作框架

## 1. 目标与适用范围
本框架用于将需求基线包转化为可开发、可测试、可发布的详细设计包，并形成可追踪、可评审的交付标准。

适用范围：
- 架构映射与模块设计
- 接口、数据、流程、类图与配置设计
- 集成、批处理、DDD 代码结构设计
- 设计评审、发布与回滚准备

## 2. 职责边界

### 2.1 IT 详细设计 Agent 负责
- 架构与模块分解
- API、数据模型、状态与时序设计
- 类图、集成、批处理、配置、DDD 代码结构设计
- 异常路径与韧性策略
- 测试设计、发布与回滚方案

### 2.2 IT 详细设计 Agent 不负责
- 变更业务目标本身（仅反馈影响与风险）
- 跳过基线需求直接生成方案

## 3. 工作流（设计侧）
1. 接收并校验需求基线包。
2. 读取现有资产（代码/设计文档/数据库/运行信息）。
3. 进行架构映射与模块边界划分。
4. 生成结构化设计产物（OpenAPI/SQL/Mermaid/JSON）。
5. 执行语法与语义校验。
6. 输出评审包并关闭风险项。
7. 汇编最终《详细设计说明书》。

## 4. 输入输出产物（I/O Artifacts）

### 4.1 输入
- PRD 基线
- 需求追踪矩阵
- 影响分析矩阵
- 现有系统架构约束

### 4.2 输出（结构化过程产物）
- `openapi.yaml`
- `schema.sql`
- `architecture.md`（Mermaid）
- `sequence-*.md`、`state-*.md`（Mermaid）
- `class-*.md`（Mermaid）
- `integration-*.md`、`batch-*.md`
- `config-catalog.yaml`
- `ddd-structure.md`
- `traceability.json`

### 4.3 输出（最终交付）
- `detailed-design.md`（由模板汇编，不手工拼接）

## 5. 能力层优先级（MUST / SHOULD / Optional）

| 能力层 | 优先级 | 说明 |
|---|---|---|
| 架构映射（Architecture Mapping） | MUST | 需求拆解、边界划分、模块职责 |
| 接口设计（API Design） | MUST | OpenAPI、错误码、幂等、版本 |
| 数据设计（Data Design） | MUST | 实体、索引、迁移、一致性 |
| 流程设计（Sequence/State） | MUST | 主异常链路与状态流转 |
| 类图设计（Class Diagram） | MUST | 领域对象与依赖关系 |
| 集成与批处理（Integration + Batch） | SHOULD | 系统协同与批任务可靠性 |
| 配置设计（Config Design） | SHOULD | 多环境配置与安全治理 |
| DDD 代码结构设计（DDD Structure） | MUST | 分层目录、边界与依赖约束 |
| 异常韧性（Resilience） | SHOULD | 降级、熔断、重试、补偿 |
| 性能容量（Performance） | SHOULD | SLO、压测目标、容量规划 |
| 安全合规（Security） | SHOULD | 鉴权、审计、脱敏、合规控制 |
| 可观测性（Observability） | SHOULD | 指标、日志、链路、告警 |
| 发布回滚（Release & Rollback） | SHOULD | 灰度、回滚条件、演练 |
| 多租户/国际化专项（Tenant/I18n） | Optional | 按场景启用 |

## 6. 设计前资产基线（Asset Baseline）
为避免“凭空设计”，每次设计任务开始前必须完成资产读取，并产出证据。

### 6.1 必读资产范围
1. 代码资产：现有仓库代码、模块目录、关键配置、已有测试。
2. 文档资产：历史 HLD/LLD、ADR、接口文档、发布/回滚记录。
3. 数据资产：现有 DDL、ER 图、数据字典、迁移脚本、慢查询信息。
4. 运行资产：日志样例、监控指标、链路追踪、批任务执行记录。

### 6.2 证据回填要求
每次工具调用后，回填证据到 `evidence/*.json`（或同等结构化记录），至少包含：
- `asset_type`：code/doc/db/runtime
- `source`：文件路径、仓库链接或数据来源
- `tool`：使用的工具或脚本
- `result_summary`：关键发现摘要
- `design_impact`：对当前设计的影响
- `confidence`：置信度（0-1）

### 6.3 进入设计门槛
- 关键能力（MUST）未完成资产读取，不得生成最终设计稿。
- 关键设计结论必须可追溯到资产证据。

## 7. 能力层到 Skill 映射（资产驱动执行清单）

| 能力层 | Skill 名称（建议） | 设计前必须读取的资产 | 工具调用（MCP/脚本） | 工具反馈如何支撑设计 | 产出物模板 |
|---|---|---|---|---|---|
| 架构映射 | `architecture-mapping` | 现有架构图、模块目录、历史 ADR、核心代码入口 | `filesystem`、`git`、依赖分析脚本、JSON Schema 校验 | 输出模块边界、依赖冲突、可复用组件清单，支撑 `module-map` 与架构分层 | `architecture.md`、`module-map.json` |
| 接口设计 | `api-design` | 现有 API 文档、网关路由、调用日志、错误码规范 | OpenAPI lint（Spectral）、接口差异脚本、示例回放脚本 | 输出接口兼容性差异、参数缺失、错误码冲突，支撑接口版本与幂等策略 | `openapi.yaml`、`errors.json` |
| 数据设计 | `data-model-design` | 当前表结构、索引、数据字典、迁移历史、慢查询 | SQLFluff、Schema Diff、索引建议脚本 | 输出字段映射、索引影响、迁移风险，支撑 ER 与 DDL 调整 | `schema.sql`、`er.md` |
| 流程设计 | `flow-design` | 现有时序图、调用链日志、业务流程文档 | Mermaid CLI、流程校验脚本、调用链分析脚本 | 输出主链路/异常链路证据，支撑时序图与状态机设计 | `sequence-*.md`、`state-*.md` |
| 类图设计 | `class-diagram-design` | 领域模型代码、接口定义、聚合相关文档 | Mermaid CLI、类关系抽取脚本、静态分析工具 | 输出实体关系、继承/组合/依赖关系，支撑类图与职责划分 | `class-*.md` |
| 集成与批处理设计 | `integration-batch-design` | 外部系统接口文档、消息契约、调度配置、历史失败任务 | 契约校验脚本、重试策略检查、批任务日志分析 | 输出重试/补偿建议、幂等冲突点、批任务瓶颈，支撑集成与批处理方案 | `integration-*.md`、`batch-*.md`、`event-contracts.json` |
| 配置设计 | `config-design` | 各环境配置、密钥管理规则、灰度开关、配置变更记录 | 配置 Schema 校验、secret-scan、配置差异脚本 | 输出环境差异、敏感配置风险、开关治理建议，支撑配置分层设计 | `config-catalog.yaml`、`config-matrix.md` |
| DDD 代码结构设计 | `ddd-code-structure-design` | 当前目录结构、领域边界文档、依赖关系图、代码规范 | 依赖规则检查脚本、静态依赖分析工具 | 输出跨上下文违规依赖与分层违例，支撑上下文与目录重构 | `ddd-structure.md`、`context-map.md` |
| 文档汇编发布 | `design-doc-assembler` | 全部结构化产物、模板文件、评审意见记录 | Pandoc、汇编脚本、追踪矩阵校验脚本 | 输出章节映射与缺失项报告，确保最终详设来自可追踪资产 | `detailed-design.md`、`detailed-design.pdf` |

## 8. 设计门禁与发布门禁
1. 无结构化产物，不允许汇编最终文档。
2. 无校验结果，不允许进入评审。
3. 无 `REQ -> Design -> Test` 追踪链，不允许发布。
4. 关键风险必须有 Owner、缓解方案与计划日期。
5. 无资产证据回填（第6节），不允许关闭设计评审。

## 9. 最小落地清单
1. 统一编号：`REQ-*`、`DES-*`、`API-*`、`DB-*`、`TC-*`。
2. 每条需求至少映射一个设计项与测试项。
3. 每个设计项必须对应结构化文件与校验记录。
4. 最终文档必须由模板汇编并保留来源与版本信息。
5. 每个 MUST 能力至少提供一条资产证据链。
