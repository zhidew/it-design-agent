---
name: architecture-mapping
description: 分析业务需求与既有系统结构，识别系统边界、容器划分及模块约束，产出 C4 架构图与模块依赖映射。
---

# Tool Usage Notes

- Follow the runtime-generated tool contract from the expert YAML. Do not assume a tool is available unless the controller prompt exposes it.
- Prefer read and grounding steps first. Use write tools only to persist owned artifacts or make bounded corrections under `artifacts/`.
- Treat optional validators or external techniques as non-guaranteed unless the runtime explicitly exposes them for this run.
# 参考资料 (References)

- 模板使用 `assets/templates/architecture.md` 和 `assets/templates/module-map.json`。
- 参考 C4 模型规范：Context、Container、Component、Code 四层视图。

# 注意事项 (Notes)

- **上下文视图必须**：必须包含系统与外部角色/系统的交互关系。
- **容器视图必须**：必须清晰展示应用服务、数据库、缓存、消息队列等容器。
- **模块约束**：module-map.json 中的依赖关系必须符合 DDD 分层规范。
- **专家边界**：只负责系统上下文、容器划分、模块边界和允许依赖；可以点到接口、数据、配置、运维、测试影响，但不得展开为 AsyncAPI、DDL/索引、配置矩阵、监控/runbook、测试用例的详细设计。
- **依赖协同**：后续专家会依赖 `architecture.md` 和 `module-map.json`。如果发现下游设计风险，只记录“约束、输入、风险”，不要在本专家产物里替下游专家完成详细方案。

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


