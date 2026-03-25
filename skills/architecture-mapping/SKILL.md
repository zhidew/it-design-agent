---
name: architecture-mapping
description: 分析业务需求与既有系统结构，识别系统边界、容器划分及模块约束，产出 C4 架构图与模块依赖映射。
---

# 工作流 (Workflow)

1. **资产读取**：读取需求基线以及现有的架构资产（如历史架构文档、系统边界说明）。
2. **结构分析**：使用 `extract_structure` 分析需求文件的结构和关键概念。
3. **架构生成**：基于需求，生成 C4 上下文视图和容器视图的 `artifacts/architecture.md`。
4. **模块映射**：定义模块边界和允许的依赖关系，生成 `artifacts/module-map.json`。
5. **证据沉淀**：将架构决策依据写入 `evidence/architecture-mapping.json`。

# 输入参数 (Inputs)

## 必需参数 (Required)

| 参数 | 类型 | 说明 |
|------|------|------|
| `requirements` | string/path | 架构层面的业务需求文件路径 |
| `existing_assets` | string/path | 当前生产环境的架构文档或模块说明路径 |
| `output_root` | string/path | 项目设计包的根路径 |

## 可选参数 (Optional)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `context` | string/path | - | 上下文信息文件路径 |

# 输出产物 (Output Artifacts)

## 必需产物 (Always Required)

| 产物路径 | 说明 |
|----------|------|
| `artifacts/architecture.md` | 包含 C4 Context 和 Container 视图的架构文档（Mermaid 格式）|
| `artifacts/module-map.json` | 模块边界和依赖约束定义 |
| `evidence/architecture-mapping.json` | 架构决策依据和证据 |

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
| `extract_lookup_values` | 提取枚举值 |

# 参考资料 (References)

- 模板使用 `assets/templates/architecture.md` 和 `assets/templates/module-map.json`。
- 参考 C4 模型规范：Context、Container、Component、Code 四层视图。

# 注意事项 (Notes)

- **上下文视图必须**：必须包含系统与外部角色/系统的交互关系。
- **容器视图必须**：必须清晰展示应用服务、数据库、缓存、消息队列等容器。
- **模块约束**：module-map.json 中的依赖关系必须符合 DDD 分层规范。

# ReAct 执行策略 (ReAct Strategy)

在执行过程中，按以下策略循环操作：

1. **研究 (Research)**：使用读取工具（list_files, extract_structure, grep_search, read_file_chunk）从需求文件中收集系统边界和容器划分的证据。
2. **编写 (Write)**：使用 `write_file` 生成草稿产物（如 architecture.md）。
3. **验证 (Verify)**：使用 `read_file_chunk` 回读已写入的内容进行验证。
4. **修补 (Patch)**：基于验证结果或新发现，使用 `patch_file` 进行微调。
5. **完成 (Finalize)**：仅当所有预期产物正确写入并验证后，设置 done=true。

## ReAct 规则

1. 默认每次只输出一个下一步动作；只有在收集独立、低风险的读取证据时，才可使用 `actions` 返回最多 2 个只读动作。
2. 仅当收集到足够证据且已写入 architecture.md 和 module-map.json 时才停止。
3. 保持 tool_input 简洁且为机器可读的 JSON 格式。
4. 每个步骤记录 evidence_note 说明该步骤的目的。
5. `actions` 只可包含 `read_file_chunk`、`extract_structure`、`grep_search`、`extract_lookup_values` 等只读工具，且不得混入 `write_file`、`patch_file`、`run_command`、`clone_repository`、`query_database` 或 `query_knowledge_base`。

## 返回格式

```json
{
  "done": false,
  "thought": "为什么需要这一步",
  "tool_name": "list_files | extract_structure | grep_search | read_file_chunk | write_file | patch_file | none",
  "tool_input": {},
  "actions": [
    {"tool_name": "read_file_chunk", "tool_input": {"path": "baseline/original-requirements.md", "start_line": 1, "end_line": 120}},
    {"tool_name": "extract_structure", "tool_input": {"files": ["baseline/original-requirements.md"]}}
  ],
  "evidence_note": "这一步应该确认或产出什么"
}
```

# 最终生成策略 (Final Generation)

当 ReAct 循环结束后，基于收集的证据生成最终产物：

## 生成要求

1. architecture.md 必须包含基于证据的 C4 Context 视图和 Container 视图。
2. module-map.json 必须定义合理的模块边界和允许的依赖关系。
3. 将模板作为风格参考，而非强制内容。
4. 保持 module-map.json 为有效的 JSON 格式。

## 生成内容

- **architecture.md**: 包含 Mermaid 格式的 C4Context 和 C4Container 图表。
- **module-map.json**: 包含 modules 数组，每个模块定义 name 和 allowed_dependencies。
