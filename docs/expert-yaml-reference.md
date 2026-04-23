# Expert YAML 配置说明

本文档说明 `experts/*.expert.yaml` 的字段含义、当前代码消费位置和维护建议。运行时主要由 `api_server/registry/expert_registry.py`、`api_server/registry/expert_runtime_profile.py`、`api_server/subgraphs/dynamic_subagent.py`、`api_server/subgraphs/topic_ownership.py`、`api_server/subgraphs/delivery_contract.py` 和 `api_server/graphs/nodes.py` 消费这些配置。

## 文件发现和加载

- 推荐文件名：`experts/<expert-id>.expert.yaml`。
- 兼容旧文件名：`*.agent.yaml` 仍会被扫描。
- 专家 ID 来源：优先读取 YAML 的 `capability`；缺失时使用文件名去掉 `.expert` 或 `.agent` 后缀。
- Skill 路径：默认匹配 `skills/<capability>/SKILL.md`。
- 热加载：修改后可调用 `POST /api/v1/expert-center/reload`，或重启后端。

## 顶层字段

| 字段 | 类型 | 是否建议必填 | 当前作用 |
|---|---|---|---|
| `name` | string | 是 | 专家显示名；也作为缺省英文名来源。 |
| `name_en` | string | 建议 | 英文显示名；Expert Center 和阶段编排会展示。 |
| `name_zh` | string | 建议 | 中文显示名；前端中文界面优先展示。 |
| `capability` | string | 是 | 专家能力 ID，必须与文件名和 `skills/<id>` 保持一致，Planner、调度、依赖和项目启用都使用它。 |
| `description` | string | 是 | Planner 选择专家时展示给 LLM 的能力说明。 |
| `version` | string | 建议 | 专家 profile 版本；当前主要用于人工维护和审计，不参与调度。 |
| `is_system` | boolean | 可选 | 系统专家标记；当前 `expert-creator` 属于系统专家，普通编排会排除。 |
| `skills` | list[string] | 建议 | 关联 skill 包；当前运行约定为 `skills/<capability>/SKILL.md`，该字段更多用于说明和兼容。 |
| `keywords` | list[string] | 建议 | 专家搜索、展示和 runtime routing fallback；Planner 主要看 `description`，runtime profile 会把它作为路由关键词兜底。 |
| `inputs` | mapping | 建议 | 声明专家需要的输入材料；registry 会读取 `inputs.required`。 |
| `scheduling` | mapping | 是 | 调度优先级、依赖和阶段兜底配置。 |
| `upstream_artifacts` | mapping | 强烈建议 | 声明每个上游专家产物中，本专家会消费哪些文件。参与依赖校验和动态子代理上下文。 |
| `tools` | mapping | 建议 | 声明专家显式允许的写入/执行/校验工具。运行时会自动补默认只读工具。 |
| `outputs` | mapping | 是 | 声明专家预期输出、证据输出和条件输出。强约束主要来自 `outputs.expected`。 |
| `metadata` | mapping | 强烈建议 | 专家边界、主题归属、路由、提示和交付契约。动态专家执行会重点使用。 |
| `policies` | mapping | 建议 | 通用策略和 Planner 自动选择策略。 |
| `error_handling` | mapping | 建议 | 错误处理约定；当前主要作为配置语义和专家提示，不是所有键都有硬编码执行分支。 |

## `inputs`

```yaml
inputs:
  required:
    - requirements
    - existing_assets
    - output_root
  optional:
    - constraints
    - context
```

| 字段 | 类型 | 当前作用 |
|---|---|---|
| `inputs.required` | list[string] | Registry 会归一化到 `ExpertProfile.required_inputs`；用于展示、兼容和配置完整性表达。 |
| `inputs.optional` | list[string] | 当前不进入 `ExpertProfile`，主要作为 profile 文档语义。 |

建议保留 `requirements`、`existing_assets`、`output_root`，这样与现有 Planner baseline 和动态子代理上下文一致。

## `scheduling`

```yaml
scheduling:
  priority: 70
  phase: INTERFACE
  dependencies:
    - modular-design
    - data-design
```

| 字段 | 类型 | 当前作用 |
|---|---|---|
| `scheduling.priority` | integer | 任务队列构建时按优先级降序稳定排序；同阶段内也用于展示和执行摘要排序。默认 `50`。 |
| `scheduling.dependencies` | list[string] | 运行时解析为任务 ID 依赖。每个专家总是依赖 Planner；这里声明的依赖只有在该上游专家也被选中时才会生效。 |
| `scheduling.phase` | string | 阶段兜底。当前优先使用 `config/phases.yaml` 中的专家绑定；如果没有绑定，才回退到此字段或旧的 `AGENT_PHASE_MAP`。 |

注意：

- 新专家必须绑定到 `config/phases.yaml` 的一个可执行阶段，否则项目配置中启用该专家会被后端拒绝。
- 依赖应该来自更早阶段。依赖图校验会报 `BACKWARD_PHASE_DEPENDENCY`，阻止同阶段或后续阶段倒挂依赖。
- 缺失依赖在任务构建时是弱语义：如果依赖专家没有被本次选中，就不会加入依赖列表；但依赖图校验会检查 YAML 中引用的专家是否存在。

## `upstream_artifacts`

```yaml
upstream_artifacts:
  modular-design:
    - architecture.md
    - module-map.json
```

该字段声明“本专家从哪个上游专家消费哪些产物”。它有三个作用：

- Registry 依赖图校验：检查上游专家是否存在、是否在 `scheduling.dependencies` 中、产物名是否存在于上游 `outputs.expected`。
- 动态子代理上下文：运行时会把相关上游产物作为候选输入，避免专家凭空设计。
- 交付边界：帮助 Planner 和专家明确哪些事实来自上游，哪些内容不能由当前专家重写。

常见校验问题：

| Code | 含义 |
|---|---|
| `MISSING_UPSTREAM_ARTIFACT_MAPPING` | 声明了依赖，但没有任何上游产物映射。 |
| `DEPENDENCY_WITHOUT_ARTIFACT_MAPPING` | 某个依赖专家有输出，但当前专家没有声明消费哪些输出。 |
| `UNKNOWN_UPSTREAM_ARTIFACT` | 映射的文件名不在上游专家 `outputs.expected` 中。 |
| `UPSTREAM_NOT_IN_DEPENDENCIES` | 映射了某专家产物，但没有在 `scheduling.dependencies` 中声明依赖。 |

## `tools`

```yaml
tools:
  allowed:
    - clone_repository
    - query_database
    - query_knowledge_base
    - write_file
    - patch_file
```

`tools.allowed` 是显式工具授权。运行时会通过 `build_effective_tools()` 生成最终可用工具：

- 默认总是加入只读工具：`list_files`、`extract_structure`、`grep_search`、`read_file_chunk`、`extract_lookup_values`、`clone_repository`、`query_database`、`query_knowledge_base`。
- 显式声明的工具会追加到 effective tools。
- 如果有写入能力，会自动补 companion 写入工具：声明 `write_file`、`patch_file` 或 `append_file` 时，通常会补齐 `append_file` 和 `upsert_markdown_sections`。
- `tools.allowed: ["*"]` 会开放所有已知运行期工具。

已知运行期工具：

```text
list_files, clone_repository, extract_structure, grep_search,
read_file_chunk, extract_lookup_values, query_database,
query_knowledge_base, write_file, append_file,
upsert_markdown_sections, patch_file, run_command,
validate_artifacts
```

建议：

- 普通设计专家通常只需要 `write_file`、`patch_file` 和资产查询工具。
- `validator` 可以使用 `validate_artifacts`。
- 只有确实需要执行命令的专家才授予 `run_command`。

## `outputs`

```yaml
outputs:
  expected:
    - api-design.md
    - errors-rfc9457.json
  evidence:
    - api-design.json
  conditional:
    - when: audience in [internal, both]
      path: api-internal.yaml
```

| 字段 | 类型 | 当前作用 |
|---|---|---|
| `outputs.expected` | list[string] | 强运行字段。Registry、任务成功推断、上游产物校验、动态输出规划和交付 checklist 都会使用。 |
| `outputs.evidence` | list[string] | 当前主要是约定和提示语义；专家 SKILL 通常会要求写入 evidence 文件。 |
| `outputs.conditional` | list[object] | 当前主要是配置约定；可表达按 audience、场景或条件生成的额外产物。 |

建议：

- `expected` 中的文件名要稳定，避免多个专家产出同名文件。依赖校验会对重复 `expected` 输出给出 warning。
- 如果一个产物会被下游消费，必须列入 `expected`，否则下游 `upstream_artifacts` 会校验失败。
- 结构化文件建议使用 `.json`、`.yaml`、`.sql`，最终设计说明建议使用 `.md`。

## `metadata.boundary_contract`

```yaml
metadata:
  boundary_contract:
    owns:
      - synchronous API contracts and error models
    excludes:
      - schema/index redesign
      - ops runbooks and test inventory
    upstream_inputs:
      - modular-design
      - data-design
```

| 字段 | 类型 | 当前作用 |
|---|---|---|
| `owns` | list[string] | 渲染为专家 scope boundary，告诉动态子代理当前专家负责什么。 |
| `excludes` | list[string] | 渲染为禁止越界内容，防止当前专家重写其他专家领域。 |
| `upstream_inputs` | list[string] | 与 `scheduling.dependencies` 做一致性校验；也会进入 boundary note。 |

依赖图校验会检查 `boundary_contract.upstream_inputs` 与 `scheduling.dependencies` 是否一致，不一致时给出 `BOUNDARY_INPUT_MISMATCH` warning。

## `metadata.topic_ownership`

```yaml
metadata:
  topic_ownership:
    topics:
      - endpoint_contracts
      - error_model
    owns_shared_context: false
    shared_context_topics:
      - project_background
      - requirement_overview
    generic_shared_context_section_examples: 项目背景 / 需求背景 / 建设目标
```

| 字段 | 类型 | 当前作用 |
|---|---|---|
| `topics` | list[string] | 当前专家负责的主题标签，会进入 `topic_ownership` payload 和专家 prompt。 |
| `owns_shared_context` | boolean | 是否允许该专家维护通用共享上下文章节。非 owner 遇到通用背景类标题会被约束不要扩写。 |
| `shared_context_topics` | list[string] | 共享上下文主题集合，通常由 shared context owner 声明。 |
| `generic_shared_context_section_examples` | string | 用于提示哪些标题属于通用共享上下文，例如“项目背景 / 需求概述”。 |

推荐只有架构/模块化专家和最终聚合专家拥有 `owns_shared_context: true`，其他专家聚焦自己的专业主题。

## `metadata.routing`

```yaml
metadata:
  routing:
    keywords:
      - API
      - OpenAPI
      - endpoint
      - 错误码
```

`routing.keywords` 会进入 runtime profile 的路由关键词。当前主要用于动态子代理的 profile 语义和后续扩展；如果缺失，会回退到 YAML 顶层 `keywords`，再回退到 capability 分词。

建议把中英文业务词、技术词和常见用户输入词都放进去，便于 Planner 和运行期提示更稳定。

## `metadata.prompt_hints`

```yaml
metadata:
  prompt_hints:
    file_guidance:
      api-design.md: 明确接口路径、方法、认证授权、核心入参/出参、分页筛选、幂等和错误返回。
      errors-rfc9457.json: 保持 RFC 9457 problem details 结构稳定。
    default_file_guidance: 聚焦同步 API 契约可联调性，避免重写数据模型、异步事件或测试方案。
```

| 字段 | 类型 | 当前作用 |
|---|---|---|
| `file_guidance` | map[path,string] | 按输出文件提供精确写作指导；runtime profile 会归一化并保留。 |
| `default_file_guidance` | string | 对未匹配文件的默认指导。 |

这些字段会进入专家 runtime profile，并与输出规划、交付 checklist 共同影响动态子代理 prompt。建议每个 `outputs.expected` 文件都配置一条 `file_guidance`。

## `metadata.delivery_contract`

```yaml
metadata:
  delivery_contract:
    must_answer:
      - 每个核心接口的路径、方法、调用方、鉴权、入参、出参和错误返回是否明确。
    evidence_expectations:
      - 接口字段需要回指上游数据模型、领域对象或模块职责。
    artifact_review_checklist:
      api-design.md:
        - 接口清单要覆盖路径、方法、调用方、鉴权、入参、出参、幂等、错误和兼容策略。
```

| 字段 | 类型 | 当前作用 |
|---|---|---|
| `must_answer` | list[string] | 动态子代理 coverage brief 中的核心回答要求。 |
| `evidence_expectations` | list[string] | 证据要求，指导专家不要无依据生成。 |
| `artifact_review_checklist` | map[path,list[string]] | 按文件合并通用 checklist，进入产物生成和最终校验提示。 |

如果缺失，系统会根据专家 ID 和输出文件后缀生成 legacy/generic checklist。建议显式配置，以减少泛化输出。

## `metadata.execution`

`metadata.execution` 是保留扩展字段。Registry 会把顶层 `execution` 合并进 `ExpertConfig.metadata["execution"]`，runtime profile 会识别该键但当前没有统一硬编码策略。可用于后续记录专家执行偏好，但不要依赖它实现强行为。

## `policies`

```yaml
policies:
  asset_baseline_required: true
  evidence_required: true
  output_must_be_structured: true
  manual_override_forbidden: true
  descriptions_prefer_chinese: true
  planner_auto_select:
    enabled: true
    trigger: keyword_any
    keywords:
      - performance
      - p95
      - 性能
```

| 字段 | 类型 | 当前作用 |
|---|---|---|
| `asset_baseline_required` | boolean | 配置语义，表达专家需要基线资产。 |
| `evidence_required` | boolean | 配置语义，表达必须产出证据。 |
| `output_must_be_structured` | boolean | 配置语义，表达输出应结构化。 |
| `manual_override_forbidden` | boolean | 配置语义，当前没有阻止用户在 Planner 确认阶段增删专家。 |
| `descriptions_prefer_chinese` | boolean | 配置语义，约束输出语言风格。 |
| `planner_auto_select` | mapping | 强运行字段。Planner 在 LLM 推荐后会根据关键词规则自动补选专家。 |

`planner_auto_select` 支持：

| 字段 | 类型 | 说明 |
|---|---|---|
| `enabled` | boolean | 是否启用自动补选。 |
| `trigger` | `keyword_any` 或 `keyword_all` | `keyword_any` 表示任一关键词命中即可补选；`keyword_all` 表示全部命中。 |
| `keywords` | list[string] | 在需求文本和人工输入汇总中做大小写无关匹配。 |

只有项目中已经启用的专家才会被自动补选；未启用专家不会因为 policy 被加入。

## `error_handling`

```yaml
error_handling:
  on_missing_required_input: fail
  on_validation_failure: fail
  on_partial_generation: emit_evidence_and_fail
```

| 字段 | 建议值 | 当前作用 |
|---|---|---|
| `on_missing_required_input` | `fail`, `warn` | 配置语义，表示缺输入时专家应如何处理。 |
| `on_validation_failure` | `fail`, `warn` | 配置语义，`validator` 可设置为 `warn`。 |
| `on_partial_generation` | `emit_evidence_and_fail`, `warn` | 配置语义，指导部分产出时如何落证据。 |

当前这组字段主要服务于专家 profile 和提示约束，不是统一的强制执行开关。需要强约束时，应同时在 SKILL、delivery checklist 和 validator 中体现。

## 阶段配置关系

`config/phases.yaml` 是阶段和专家绑定的优先来源：

```yaml
phases:
  - id: ARCHITECTURE
    label_zh: 架构设计
    label_en: Architecture
    executable: true
    order: 3
    experts:
      - modular-design
      - integration-design
```

规则：

- `INIT`、`PLANNING`、`DONE` 是固定系统阶段，不建议承载普通专家。
- 只有 `executable: true` 的阶段可以绑定普通专家。
- 每个专家只能绑定到一个阶段；重复绑定会产生 `DUPLICATE_PHASE_ASSIGNMENT`。
- 阶段顺序由 `order` 决定，依赖必须来自更早阶段。
- 前端 Expert Center 的“Phase Orchestration”会读写这个文件。

## 新专家模板建议

```yaml
name: Example Design Expert
name_en: Example Design Expert
name_zh: 示例设计专家
capability: example-design
description: 负责示例领域的详细设计产物。
version: 0.1.0
skills:
  - example-design
keywords:
  - 示例
inputs:
  required:
    - requirements
    - existing_assets
    - output_root
  optional:
    - constraints
    - context
scheduling:
  priority: 50
  dependencies:
    - modular-design
upstream_artifacts:
  modular-design:
    - architecture.md
    - module-map.json
tools:
  allowed:
    - clone_repository
    - query_database
    - query_knowledge_base
    - write_file
    - patch_file
outputs:
  expected:
    - example-design.md
  evidence:
    - example-design.json
metadata:
  boundary_contract:
    owns:
      - example-domain design decisions
    excludes:
      - architecture redesign
      - API/schema/test redesign
    upstream_inputs:
      - modular-design
  topic_ownership:
    topics:
      - example_domain
    owns_shared_context: false
  routing:
    keywords:
      - example
      - 示例
  prompt_hints:
    file_guidance:
      example-design.md: 聚焦示例领域设计决策、约束、风险和落地说明。
    default_file_guidance: 不重写上游架构，不扩展到其他专家职责。
  delivery_contract:
    must_answer:
      - 示例领域的核心设计问题是否被完整回答。
    evidence_expectations:
      - 结论需要回指需求或上游架构产物。
    artifact_review_checklist:
      example-design.md:
        - 章节完整，包含设计决策、约束、风险和待确认项。
policies:
  asset_baseline_required: true
  evidence_required: true
  output_must_be_structured: true
  descriptions_prefer_chinese: true
error_handling:
  on_missing_required_input: fail
  on_validation_failure: fail
  on_partial_generation: emit_evidence_and_fail
```

新增后还需要：

1. 创建 `skills/example-design/SKILL.md`。
2. 把 `example-design` 加入 `config/phases.yaml` 的某个可执行阶段。
3. 调用 `/api/v1/expert-center/reload`。
4. 调用 `/api/v1/expert-center/experts/validate-dependencies`，修复 error 和重要 warning。
5. 在项目配置中启用专家后运行一次完整设计链路。
