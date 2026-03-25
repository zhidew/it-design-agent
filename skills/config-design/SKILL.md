---
name: config-design
description: 规划多环境配置键、功能开关策略和密钥规范，产出配置目录与环境对比矩阵。
---

# 工作流 (Workflow)

1. **资产读取**：读取需求基线以及现有的配置相关资产（如历史配置文件、环境变量说明）。
2. **配置分析**：使用 `extract_structure` 和 `grep_search` 分析配置键、环境差异和功能开关。
3. **目录生成**：生成外部化配置键清单 `artifacts/config-catalog.yaml`。
4. **矩阵生成**：生成 DEV、TEST、PROD 环境对比矩阵 `artifacts/config-matrix.md`。
5. **证据沉淀**：将配置设计依据写入 `evidence/config-design.json`。

# 输入参数 (Inputs)

## 必需参数 (Required)

| 参数 | 类型 | 说明 |
|------|------|------|
| `requirements` | string/path | 配置层面的业务需求文件路径 |
| `existing_assets` | string/path | 当前生产环境的配置文件或环境变量列表路径 |
| `output_root` | string/path | 项目设计包的根路径 |

## 可选参数 (Optional)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `context` | string/path | - | 上下文信息文件路径 |

# 输出产物 (Output Artifacts)

## 必需产物 (Always Required)

| 产物路径 | 说明 |
|----------|------|
| `artifacts/config-catalog.yaml` | 配置键目录，包含类型、是否敏感等元数据 |
| `artifacts/config-matrix.md` | 环境对比矩阵（DEV/TEST/PROD），展示各环境配置差异 |
| `evidence/config-design.json` | 配置设计依据和证据 |

# 工具集 (Tools)

## 文件系统工具

| 工具名称 | 说明 |
|----------|------|
| `list_files` | 列出目录下的文件 |
| `read_file_chunk` | 读取文件片段 |
| `grep_search` | 搜索配置关键词（timeout, feature flag, Redis, MySQL, Kafka, URL, password, secret, env, prod）|
| `extract_structure` | 提取文件结构 |
| `write_file` | 写入设计产物 |
| `patch_file` | 修补已有文件 |

# 参考资料 (References)

- 模板使用 `assets/templates/config-catalog.yaml` 和 `assets/templates/config-matrix.md`。
- 参考 12-Factor App 配置管理原则。

# 注意事项 (Notes)

- **敏感配置**：密码、密钥等敏感配置必须标记为 secret，不在矩阵中明文展示。
- **环境隔离**：DEV、TEST、PROD 配置值必须清晰区分。
- **类型推断**：布尔开关、超时毫秒数、字符串连接等类型应正确推断。

# ReAct 执行策略 (ReAct Strategy)

在执行过程中，按以下策略循环操作：

1. **研究 (Research)**：使用读取工具从需求文件中收集配置键、环境差异和功能开关的证据。
2. **编写 (Write)**：使用 `write_file` 生成草稿产物。
3. **验证 (Verify)**：使用 `read_file_chunk` 回读已写入的内容进行验证。
4. **修补 (Patch)**：基于验证结果或新发现，使用 `patch_file` 进行微调。
5. **完成 (Finalize)**：仅当所有预期产物正确写入并验证后，设置 done=true。

## ReAct 规则

1. 默认每次只输出一个下一步动作；只有在收集独立、低风险的读取证据时，才可使用 `actions` 返回最多 2 个只读动作。
2. 仅当收集到足够证据且已写入 config-catalog.yaml 和 config-matrix.md 时才停止。
3. 先使用 `extract_structure` 检查标题和 JSON 键，再读取大块内容。
4. 使用 `grep_search` 搜索 timeout, feature flag, Redis, MySQL, Kafka 等关键词。
5. `actions` 只可包含 `read_file_chunk`、`extract_structure`、`grep_search`、`extract_lookup_values` 等只读工具，且不得混入 `write_file`、`patch_file`、`run_command`、`clone_repository`、`query_database` 或 `query_knowledge_base`。

## 返回格式

```json
{
  "done": false,
  "thought": "为什么需要这一步",
  "tool_name": "list_files | extract_structure | grep_search | read_file_chunk | none",
  "tool_input": {},
  "actions": [
    {"tool_name": "extract_structure", "tool_input": {"files": ["baseline/original-requirements.md"]}},
    {"tool_name": "grep_search", "tool_input": {"pattern": "timeout|feature flag|Redis|MySQL|Kafka"}}
  ],
  "evidence_note": "这一步应该确认或产出什么"
}
```

# 最终生成策略 (Final Generation)

当 ReAct 循环结束后，基于收集的证据生成最终产物：

## 生成要求

1. config-catalog.yaml 必须枚举外部化配置键、类型和是否敏感。
2. config-matrix.md 必须对比 DEV、TEST、PROD 策略，不在明文中暴露生产密钥。
3. 将模板作为风格参考，而非强制内容。

## 生成内容

- **config-catalog.yaml**: 包含 service、version、properties 数组。
- **config-matrix.md**: 包含表格形式的配置键与环境值对比。
