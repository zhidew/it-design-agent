---
name: api-design
description: 负责REST/RPC接口设计、请求响应结构定义、枚举值规范化以及错误码体系构建。确保API设计的一致性和可扩展性。
---

# 工作流 (Workflow)

1. **需求分析**：读取需求基线，识别接口需求、数据流向和业务场景。
2. **枚举提取**：从配置文件和需求文档中提取枚举值，确保枚举值的一致性。
3. **接口定义**：基于需求生成 OpenAPI 规范，定义请求/响应结构。
4. **错误体系**：设计符合 RFC 9457 标准的错误响应结构。
5. **证据沉淀**：将设计依据写入 `evidence/api-design.json`。
6. **校验门禁**：确保所有接口定义符合规范，枚举值与 lookup 一致。

# 输入参数 (Inputs)

## 必需参数 (Required)

| 参数 | 类型 | 说明 |
|------|------|------|
| `requirements` | string/path | 接口层面的业务需求文件路径 |
| `existing_assets` | string/path | 现有接口资产目录路径 |
| `output_root` | string/path | 项目设计包的根路径 |

## 可选参数 (Optional)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `constraints` | string/path | - | 约束策略文件路径 |
| `context` | string/path | - | 上下文信息文件路径 |
| `audience` | enum | "both" | 接口受众类型：<br/>- `internal`: 仅内部接口<br/>- `external`: 仅外部接口<br/>- `both`: 内部+外部接口 |

# 输出产物 (Output Artifacts)

## 必需产物 (Always Required)

| 产物路径 | 说明 |
|----------|------|
| `artifacts/errors-rfc9457.json` | RFC 9457 标准的错误响应定义 |
| `artifacts/api-design.md` | API 设计说明文档 |
| `evidence/api-design.json` | 设计依据和决策证据 |

## 条件产物 (Conditional)

根据 `audience` 参数决定产出：

| 条件 | 产物路径 | 说明 |
|------|----------|------|
| `audience == "internal"` 或 `"both"` | `artifacts/api-internal.yaml` | 内部 API 接口定义（OpenAPI 格式）|
| `audience == "external"` 或 `"both"` | `artifacts/api-public.yaml` | 外部 API 接口定义（OpenAPI 格式）|

# 工具集 (Tools)

## 文件系统工具

| 工具名称 | 说明 |
|----------|------|
| `list_files` | 列出目录下的文件 |
| `read_file_chunk` | 读取文件片段 |
| `grep_search` | 搜索文件内容 |
| `extract_structure` | 提取文件结构 |
| `write_file` | 写入设计产物 |
| `patch_file` | 修补已有文件 |

## 数据处理工具

| 工具名称 | 说明 |
|----------|------|
| `extract_lookup_values` | 提取枚举值（关键工具）|
| `spectral` | OpenAPI 规范校验工具 |
| `ajv` | JSON Schema 校验工具 |

# 参考资料 (References)

- 模板使用 `assets/templates/api-internal.yaml`、`assets/templates/api-public.yaml` 和 `assets/templates/errors-rfc9457.json`。
- 枚举值必须与 `extract_lookup_values` 提取的值完全一致。

# 注意事项 (Notes)

- **枚举一致性**：OpenAPI 中的枚举值必须与 lookup 数据完全匹配。
- **版本管理**：接口变更需考虑向后兼容性。
- **命名规范**：使用 snake_case 命名，避免使用保留字。

# ReAct 执行策略 (ReAct Strategy)

在执行过程中，按以下策略循环操作：

1. **研究 (Research)**：使用读取工具从需求文件和 lookup 数据中收集证据。
2. **编写 (Write)**：使用 `write_file` 生成草稿产物（如 api-internal.yaml）。
3. **验证 (Verify)**：使用 `read_file_chunk` 回读已写入的内容进行验证。
4. **修补 (Patch)**：基于验证结果或新发现，使用 `patch_file` 进行微调。
5. **完成 (Finalize)**：仅当所有预期产物正确写入并验证后，设置 done=true。

## ReAct 规则

1. 每次只输出一个下一步动作。
2. 仅当收集到足够证据且已写入所有预期文件时才停止。
3. 保持 tool_input 简洁且为机器可读的 JSON 格式。
4. 特别关注 `extract_lookup_values` 提取的枚举值。

## 返回格式

```json
{
  "done": false,
  "thought": "为什么需要这一步",
  "tool_name": "list_files | extract_lookup_values | grep_search | read_file_chunk | write_file | patch_file | none",
  "tool_input": {},
  "evidence_note": "这一步应该确认或产出什么"
}
```

# 最终生成策略 (Final Generation)

当 ReAct 循环结束后，基于收集的证据生成最终产物：

## 生成要求

1. 仅反映观察结果支持的接口定义。
2. 如果存在 lookup 条目，OpenAPI 中的枚举值必须与它们完全匹配。
3. 使用模板作为风格参考。

## 生成内容

- **api-internal.yaml**: 内部接口定义，包含所有内部服务的 API 规范。
- **api-public.yaml**: 外部接口定义（如适用），面向外部调用方的 API 规范。
- **errors-rfc9457.json**: 符合 RFC 9457 标准的错误响应结构定义。
