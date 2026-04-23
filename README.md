# IT Design Agent

IT Design Agent 是一个面向企业软件项目的详细设计智能体平台。当前实现采用
`FastAPI + LangGraph + React + YAML Expert Registry`：用户输入需求、上传基线材料并配置项目资产后，Planner 会从项目启用的专家中推荐执行管线，经过人工确认后按阶段、依赖和优先级调度多个专家生成设计产物。

## 当前能力

- 项目/版本管理：每次设计运行绑定到一个项目版本，支持上传基线文件、查看产物、日志和执行状态。
- 项目资产配置：支持配置代码仓库、数据库、知识库、项目模型、默认 LLM、调试日志和启用专家。
- Expert Center：以 `experts/*.expert.yaml` 和 `skills/<expert-id>/SKILL.md` 为专家定义源，支持查看、编辑、创建、删除、热加载专家。
- 阶段编排：`config/phases.yaml` 定义业务阶段、顺序和专家归属，前端可在 Expert Center 的阶段编排面板中维护。
- Planner 人工确认：Planner 只会从当前项目启用的专家中推荐参与专家，执行前会暂停等待用户确认、增删专家或补充说明。
- 动态专家执行：专家运行时读取 YAML、SKILL、项目资产和上游产物，按 ReAct + 输出规划生成结构化设计文件。
- 实时状态：后端通过 SSE 推送运行事件，前端展示任务看板、等待人工、失败重试、继续执行、取消执行等状态。
- 本地持久化：项目、配置、工作流状态、任务事件、计划运行和 LangGraph checkpoint 都保存在本地 `projects/.orchestrator/`。

## 技术栈

- 后端：FastAPI、Pydantic、LangGraph、SQLite、PyYAML、OpenAI-compatible SDK
- 前端：React 19、Vite、TypeScript、Tailwind CSS、i18next、Mermaid、Axios
- 编排：LangGraph `bootstrap -> planner -> supervisor -> dynamic experts`
- 专家注册：`experts/*.expert.yaml`
- 专家技能：`skills/<expert-id>/SKILL.md`、模板、参考文档和脚本
- 元数据存储：`projects/.orchestrator/metadata.sqlite`
- Checkpoint：`projects/.orchestrator/langgraph-checkpoints.sqlite`

## 目录结构

```text
it-design-agent/
|-- api_server/              # FastAPI 后端、LangGraph 节点、工具和服务
|-- admin-ui/                # React/Vite 管理前端
|-- config/phases.yaml       # 阶段定义和专家到阶段的绑定关系
|-- experts/                 # 专家 YAML profile，Expert Registry 的主要来源
|-- skills/                  # 专家 SKILL、模板、参考资料和脚本
|-- projects/                # 项目版本、上传材料、产物、日志和本地元数据
|-- .expert-center-versions/ # Expert Center 编辑产生的历史版本
|-- .env.example             # 后端/系统级环境变量示例
|-- start-all.bat            # Windows 一键启动
|-- start-backend.bat        # Windows 后端启动
|-- start-frontend.bat       # Windows 前端启动
`-- README.md
```

## 快速启动

前置要求：

- Python 3.11+
- Node.js 18+

后端：

```bash
cd it-design-agent
python -m venv venv
venv\Scripts\activate
pip install -r api_server\requirements.txt
copy .env.example .env
cd api_server
python main.py
```

前端：

```bash
cd it-design-agent\admin-ui
npm install
npm run dev
```

Windows 也可以直接运行：

```bash
start-all.bat
```

默认地址：

- 前端：[http://localhost:5173](http://localhost:5173)
- 后端：[http://localhost:8000](http://localhost:8000)
- Swagger：[http://localhost:8000/docs](http://localhost:8000/docs)

## 运行逻辑

1. 后端启动时初始化 `ExpertRegistry`，扫描 `experts/*.expert.yaml` 和对应 `skills/<expert-id>/SKILL.md`。
2. 用户在项目中配置仓库、数据库、知识库、模型和启用专家。启用专家时，如果专家没有绑定到任何可执行阶段，后端会拒绝启用。
3. 发起设计运行后，`bootstrap` 准备项目版本、上传文件、baseline、artifact、log、evidence 等目录。
4. `planner` 读取上传材料结构、项目资产摘要，并尝试查询仓库/数据库/知识库形成上下文洞察。
5. Planner 只从项目启用专家中选择专家，并额外应用 YAML 中的 `policies.planner_auto_select` 规则。
6. Planner 推荐结果会进入 `waiting_human`，前端允许用户确认、添加或移除参与专家。
7. 确认后，系统根据 `scheduling.dependencies`、`scheduling.priority` 和 `config/phases.yaml` 构建任务队列。
8. `supervisor` 按阶段推进任务；同阶段内没有依赖冲突的任务可并行执行。
9. 每个专家运行时读取 YAML metadata、SKILL prompt、可用工具、上游产物和输出规划，生成 `artifacts/` 与 `evidence/` 下的交付物。
10. `design-assembler` 在启用或被 `validator` 依赖时汇总上游专家产物，`validator` 基于汇总结果做交付校验。

## 内置专家

| Expert ID | 中文名 | 默认阶段 | 主要输出 |
|---|---|---|---|
| `modular-design` | 模块化设计专家 | `ARCHITECTURE` | `architecture.md`, `module-map.json` |
| `integration-design` | 集成设计专家 | `ARCHITECTURE` | `integration.md`, `asyncapi.yaml` |
| `data-design` | 数据设计专家 | `MODELING` | `schema.sql`, `er.md`, `migration-plan.md` |
| `ddd-structure` | 领域结构专家 | `MODELING` | `class-diagram.md`, `ddd-structure.md`, `context-map.md` |
| `api-design` | API设计专家 | `INTERFACE` | `api-design.md`, `errors-rfc9457.json` |
| `config-design` | 配置设计专家 | `INTERFACE` | `config-catalog.yaml`, `config-matrix.md` |
| `flow-design` | 流程设计专家 | `INTERFACE` | `sequence.md`, `state.md` |
| `performance-design` | 性能设计专家 | `DFX` | `performance-design.md`, `performance-budget.yaml`, `capacity-assessment.json` |
| `ops-design` | 运维设计专家 | `DFX` | `slo.yaml`, `observability-spec.yaml`, `deployment-runbook.md` |
| `test-design` | 测试设计专家 | `QUALITY` | `test-strategy-design.md`, `test-solution-design.md` |
| `design-assembler` | 设计聚合专家 | `DELIVERY` | `detailed-design.md`, `implementation-plan.json`, `traceability.json`, `review-checklist.md` |
| `validator` | 验证专家 | `DELIVERY` | `validation-report.md` |
| `expert-creator` | 专家构建器 | 系统专家 | 创建 expert profile、SKILL、模板和脚本，不参与普通项目编排 |

阶段归属以 `config/phases.yaml` 为准；`scheduling.phase` 只作为旧配置或缺少阶段绑定时的兜底。

## Expert YAML

专家 profile 位于 `experts/<expert-id>.expert.yaml`。核心字段包括身份信息、输入输出、调度依赖、上游产物、工具权限、运行边界、主题归属、路由关键词、提示约束、交付契约和策略。

详细字段说明见 [docs/expert-yaml-reference.md](docs/expert-yaml-reference.md)。

最小结构示例：

```yaml
name: API Design Expert
name_en: API Design Expert
name_zh: API设计专家
capability: api-design
description: 负责同步 API 契约、请求响应结构、错误模型与枚举规范设计。
version: 0.1.0
skills:
  - api-design
keywords:
  - API
  - OpenAPI
inputs:
  required:
    - requirements
    - existing_assets
    - output_root
scheduling:
  priority: 70
  dependencies:
    - modular-design
upstream_artifacts:
  modular-design:
    - architecture.md
tools:
  allowed:
    - write_file
    - patch_file
outputs:
  expected:
    - api-design.md
metadata:
  boundary_contract:
    owns:
      - synchronous API contracts
    excludes:
      - database schema redesign
    upstream_inputs:
      - modular-design
policies:
  evidence_required: true
```

## 项目配置

项目配置接口位于 `/api/v1/projects/{project_id}/config/*`，主要内容如下：

| 类型 | 路径 | 说明 |
|---|---|---|
| 仓库 | `/repositories` | Git 仓库地址、分支、凭据、本地路径和描述 |
| 数据库 | `/databases` | MySQL、PostgreSQL、openGauss、DWS、Oracle、SQLite 等连接信息 |
| 知识库 | `/knowledge-bases` | 本地路径或远程索引地址 |
| 专家 | `/experts` | 项目级启用/停用专家配置 |
| LLM | `/llm` | 项目级兼容 OpenAI 的模型配置 |
| 模型列表 | `/models` | 多模型配置、默认模型和自定义 headers |
| 调试 | `/debug` | LLM 交互日志和完整 payload 日志开关 |

敏感字段会写入 `metadata.sqlite`，在安装 `cryptography` 时使用 Fernet 加密；否则使用本地可逆编码兜底。密钥来自 `IT_DESIGN_AGENT_METADATA_KEY`，未配置时自动生成 `projects/.orchestrator/metadata.key`。

## 环境变量

后端读取仓库根目录 `.env`：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `LLM_PROVIDER` | `openai` | 当前实现归一化为 OpenAI-compatible provider |
| `OPENAI_API_KEY` | 空 | 系统级 LLM API key |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible base URL |
| `OPENAI_MODEL_NAME` | `gpt-4o` | 系统级默认模型 |
| `IT_DESIGN_AGENT_METADATA_KEY` | 自动生成 | 元数据敏感字段加密密钥 |
| `LLM_MIN_CALL_INTERVAL_SECONDS` | `0` | LLM 请求开始间隔 |
| `LLM_REQUEST_TIMEOUT_SECONDS` | `600` | 单次同步 LLM 调用超时；`0` 表示不限制 |
| `USE_DYNAMIC_SUBAGENT` | `true` | 启用动态专家执行路径 |
| `USE_MARKDOWN_UPSERT_TOOL` | `true` | 启用 Markdown 增量章节写入工具 |
| `ORCHESTRATOR_MAX_PARALLEL` | `2` | 最大并行调度任务数 |
| `ORCHESTRATOR_STALE_TIMEOUT_SECONDS` | `180` | 运行态卡住检测阈值 |
| `AGENT_MAX_REACT_STEPS` | `99` | 单个专家 ReAct 最大轮数 |
| `AGENT_MAX_ACTIONS_PER_STEP` | `2` | 单轮允许的只读批量动作数 |
| `AGENT_MAX_FINALIZATION_STEPS` | `16` | 产物最终修订最大轮数 |
| `AGENT_REACT_PLATEAU_WINDOW` | `4` | 无进展检测窗口 |
| `AGENT_REACT_MIN_STEPS_BEFORE_PLATEAU` | `8` | 启用无进展检测前的最小轮数 |
| `AGENT_PATH_NOT_FOUND_REPEAT_LIMIT` | `2` | 相同缺失路径错误重复容忍次数 |

前端读取 `admin-ui/.env.development`：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000/api/v1` | 前端调用后端 API 的基础地址 |

## 常用维护动作

热加载专家：

```bash
curl -X POST http://localhost:8000/api/v1/expert-center/reload
```

校验专家依赖图：

```bash
curl http://localhost:8000/api/v1/expert-center/experts/validate-dependencies
```

后端测试：

```bash
cd it-design-agent
python -m pytest api_server\tests -q
```

前端构建：

```bash
cd it-design-agent\admin-ui
npm run build
```

## 新增或调整专家建议

1. 新增 `experts/<expert-id>.expert.yaml`，保证 `capability` 与文件名和 skill 目录一致。
2. 新增 `skills/<expert-id>/SKILL.md`，必要时添加 `assets/templates`、`references`、`scripts`。
3. 在 YAML 中声明 `outputs.expected`、`scheduling.dependencies`、`upstream_artifacts` 和 `metadata.boundary_contract`。
4. 在 Expert Center 的阶段编排中把专家加入一个可执行阶段，或直接维护 `config/phases.yaml`。
5. 调用 `/api/v1/expert-center/reload`，然后运行依赖校验。
6. 在项目配置中启用该专家，再发起设计运行验证 Planner 推荐、人工确认和产物生成是否符合预期。

## 注意事项

- Expert Center 编辑 YAML 和文件时会保存历史版本到 `.expert-center-versions/`。
- `expert-creator` 是系统专家，不能删除，也不会作为普通设计专家参与项目编排。
- `design-assembler` 和 `validator` 有特殊调度逻辑：`design-assembler` 会依赖所有当前参与专家，`validator` 依赖 `design-assembler`。
- 依赖图校验会检查缺失依赖、自依赖、循环依赖、阶段倒挂、重复输出、上游产物映射不一致等问题。
- `outputs.evidence` 和 `outputs.conditional` 当前主要是配置约定和提示语义；强运行约束主要来自 `outputs.expected`、`upstream_artifacts`、`metadata.*` 和 SKILL。
