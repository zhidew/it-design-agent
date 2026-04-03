---
name: api-design
description: 负责同步 API 契约、请求响应结构、错误模型与枚举规范设计，确保接口定义一致、可演进且可验证。
keywords:
  - 接口设计
  - API
  - OpenAPI
  - 错误模型
  - 枚举规范
---

# 工作流 (Workflow)

1. **需求分析**：阅读基线需求、既有接口资产和约束，识别接口边界、调用方与关键业务场景。
2. **上游对齐**：优先吸收 `modular-design`、`data-design`、`ddd-structure` 的边界、命名和数据结构约束。
3. **枚举与错误建模**：梳理枚举、状态、错误场景和兼容性要求。
4. **契约生成**：输出 API 说明文档、错误模型，以及按受众决定的 OpenAPI 契约文件。
5. **校验回读**：回读已写文件，确认命名、枚举值、错误结构和引用一致。
6. **完成门禁**：仅在必需产物、条件产物和执行证据都落盘后结束。

# 输入参数 (Inputs)

## 必需参数 (Required)

| 参数 | 类型 | 说明 |
|------|------|------|
| `requirements` | string/path | 基线需求来源，描述业务目标、接口行为和约束。 |
| `existing_assets` | string/path | 既有接口资产或上游设计产物目录。 |
| `output_root` | string/path | 当前项目设计产物根目录。 |

## 可选参数 (Optional)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `constraints` | string/path | - | 额外约束、命名规范或兼容性策略。 |
| `context` | string/path | - | 业务上下文、术语表或外部接口背景资料。 |
| `audience` | enum | `both` | 接口受众，取值为 `internal`、`external`、`both`。 |

# 输出产物 (Output Artifacts)

## 必需产物 (Always Required)

| 产物路径 | 说明 |
|----------|------|
| `artifacts/api-design.md` | API 设计说明，解释资源、操作、字段、错误和兼容性决策。 |
| `artifacts/errors-rfc9457.json` | 基于 RFC 9457 的错误响应模型定义。 |

## 条件产物 (Conditional)

| 条件 | 产物路径 | 说明 |
|------|----------|------|
| `audience` 为 `internal` 或 `both` | `artifacts/api-internal.yaml` | 面向内部调用方的 OpenAPI 契约。 |
| `audience` 为 `external` 或 `both` | `artifacts/api-public.yaml` | 面向外部调用方的 OpenAPI 契约。 |

## 运行证据 (Execution Evidence)

| 产物路径 | 说明 |
|----------|------|
| `evidence/api-design.json` | 记录需求依据、接口决策、枚举来源和校验结论。 |

# Tool Usage Notes

## 运行时契约

- 仅使用控制器在本轮显式暴露的工具；不要假设某个工具一定可用。
- 先读后写，先基于证据对齐上游边界，再生成或修补自己拥有的接口产物。
- `write_file` 和 `patch_file` 只用于本专家负责的 `artifacts/` 与 `evidence/` 内容。
- 若上游定义缺失或冲突，记录假设与风险，不在本专家产物中重写数据、领域或运维设计。

## 建议关注的工具

| 工具 | 用途 |
|------|------|
| `list_files` | 盘点基线、上游产物与既有接口文件。 |
| `read_file_chunk` | 阅读需求、上游文档和已生成契约。 |
| `grep_search` | 搜索接口动作、状态、错误和兼容性约束。 |
| `extract_lookup_values` | 提取枚举、字典值或状态码候选。 |
| `write_file` | 生成 API 说明、错误模型和契约文件。 |
| `patch_file` | 针对回读发现的问题做小范围修订。 |

# 参考资料 (References)

- 模板参考 `assets/templates/api-design.md`、`assets/templates/api-internal.yaml`、`assets/templates/api-public.yaml`、`assets/templates/errors-rfc9457.json`。
- 优先复用上游的领域名词、聚合边界、数据字段与模块划分。
- 错误模型应兼容 RFC 9457，枚举值应与需求或 lookup 来源保持一致。

# 注意事项 (Notes)

- **枚举一致性**：契约中的枚举值、状态值和错误码必须能回溯到明确证据。
- **版本兼容性**：涉及接口演进时，要明确向后兼容策略，不做破坏式变更假设。
- **专家边界**：只负责同步 API 契约、错误模型和请求响应结构，不展开 AsyncAPI、DDL、运维 runbook 或测试方案。
- **依赖协同**：把 `modular-design`、`data-design`、`ddd-structure` 视为事实来源；保持原命名和边界，不重新发明。

# ReAct 执行策略 (ReAct Strategy)

1. **研究 (Research)**：收集需求、既有接口和上游结构，确认资源、动作和受众。
2. **对齐 (Align)**：核对模块边界、领域命名、字段结构和枚举来源。
3. **编写 (Write)**：先产出 `api-design.md`，再落错误模型与契约文件。
4. **校验 (Verify)**：回读生成结果，检查字段命名、枚举值、错误结构和引用一致性。
5. **修补 (Patch)**：仅在证据充分时做局部修正，不新增无依据的接口范围。
6. **完成 (Finalize)**：确认必需产物、条件产物和执行证据满足要求后结束。

## ReAct 规则

1. 默认每次只输出一个下一步动作；只有在收集独立、低风险的读取证据时，才可用 `actions` 并行返回最多 2 个只读动作。
2. 仅当 `api-design.md`、`errors-rfc9457.json`、所需 OpenAPI 文件和 `evidence/api-design.json` 均完成后才允许 `done=true`。
3. `tool_input` 必须保持为机器可读的 JSON，对路径、行号和关键参数给出明确值。
4. 每一步都要写明 `evidence_note`，说明本步要确认什么事实或生成什么结果。
5. 若发现上游边界不清，先记录假设与风险，再决定是否继续；不得直接编造接口契约细节。

## 返回格式

```json
{
  "done": false,
  "thought": "为什么需要这一步",
  "tool_name": "当前要调用的工具名，若无需工具则为 none",
  "tool_input": {},
  "actions": [
    {
      "tool_name": "可并行的只读工具",
      "tool_input": {
        "path": "baseline/original-requirements.md",
        "start_line": 1,
        "end_line": 120
      }
    }
  ],
  "evidence_note": "这一步应该确认或产出什么"
}
```

# 最终生成策略 (Final Generation)

## 生成要求

1. 只输出有证据支撑的接口、字段、状态和错误定义。
2. 对外暴露的命名、路径、枚举和值对象要与上游事实和需求语义一致。
3. 对兼容性、幂等性、分页、过滤、错误语义等关键决策给出明确说明。
4. 模板只作为结构参考，最终内容必须贴合项目语境。

## 生成内容

- **api-design.md**：解释接口边界、资源模型、操作语义、错误处理和兼容性原则。
- **errors-rfc9457.json**：定义统一错误结构、字段含义和错误响应示例。
- **api-internal.yaml**：在需要时产出内部契约，覆盖内部服务调用路径与结构。
- **api-public.yaml**：在需要时产出外部契约，突出外部受众关心的稳定接口。
- **api-design.json**：沉淀接口设计证据、上游依赖与校验结论。