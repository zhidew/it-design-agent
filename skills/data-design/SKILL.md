---
name: data-design
description: 负责数据库表结构设计、索引优化、实体关系映射（ER图）以及平滑的数据迁移与回滚策略。确保数据设计的向后兼容性和高性能。
---

# Tool Usage Notes

- Follow the runtime-generated tool contract from the expert YAML. Do not assume a tool is available unless the controller prompt exposes it.
- Prefer read and grounding steps first. Use write tools only to persist owned artifacts or make bounded corrections under `artifacts/`.
- Treat optional validators or external techniques as non-guaranteed unless the runtime explicitly exposes them for this run.
# 参考资料 (References)

- 模板使用 `assets/templates/schema.sql`、`assets/templates/er.md` 和 `assets/templates/migration-plan.md`。
- 参考项目全局的数据规范（如有），如公共审计字段（created_at, updated_at）及软删除约定。

# 注意事项 (Notes)

- **回滚必须**：任何涉及表结构修改的设计，必须成对提供升级脚本（Up）和降级脚本（Down）。
- **兼容性**：尽量采用"扩容式修改"（如新增字段、新增表），避免"破坏式修改"（如重命名、删除在用字段）。
- **索引感知**：新增查询需求必须评估并设计配套的数据库索引。
- **专家边界**：只负责表结构、字段、约束、索引、ER 关系和迁移回滚；不要重写系统架构叙事、完整 API/AsyncAPI 协议、配置矩阵、运维 runbook 或测试方案。
- **依赖协同**：应把 `architecture-mapping` 产物视为边界输入，遵守既定模块边界；若边界不清，仅在迁移计划中标注假设和影响，不在本专家产物内重新定义整体架构。

# ReAct 执行策略 (ReAct Strategy)

在执行过程中，按以下策略循环操作：

1. **研究 (Research)**：使用读取工具（list_files, read_file_chunk, grep_search）从需求文件中收集证据。
2. **编写 (Write)**：使用 `write_file` 生成草稿产物（如 schema.sql）。
3. **验证 (Verify)**：使用 `read_file_chunk` 回读已写入的内容进行验证。
4. **修补 (Patch)**：基于验证结果或新发现，使用 `patch_file` 进行微调。
5. **完成 (Finalize)**：仅当所有预期产物正确写入并验证后，设置 done=true。

## ReAct 规则

1. 默认每次只输出一个下一步动作；只有在收集独立、低风险的读取证据时，才可使用 `actions` 返回最多 2 个只读动作。
2. 仅当收集到足够证据且已写入所有预期文件时才停止。
3. 保持 tool_input 简洁且为机器可读的 JSON 格式。
4. 每个步骤记录 evidence_note 说明该步骤的目的。
5. `actions` 只可包含 `read_file_chunk`、`extract_structure`、`grep_search`、`extract_lookup_values` 等只读工具，且不得混入 `write_file`、`patch_file`、`run_command`、`clone_repository`、`query_database` 或 `query_knowledge_base`。

## 返回格式

```json
{
  "done": false,
  "thought": "为什么需要这一步",
  "tool_name": "grep_search | read_file_chunk | write_file | patch_file | none",
  "tool_input": {},
  "actions": [
    {"tool_name": "read_file_chunk", "tool_input": {"path": "baseline/original-requirements.md", "start_line": 1, "end_line": 120}},
    {"tool_name": "grep_search", "tool_input": {"pattern": "table|column|index|constraint|migration"}}
  ],
  "evidence_note": "这一步应该确认或产出什么"
}
```

# 最终生成策略 (Final Generation)

当 ReAct 循环结束后，基于收集的证据生成最终产物：

## 生成要求

1. 仅反映观察结果支持的表、字段和关系。
2. 使用 snake_case 命名。
3. 包含足够的结构供 assembler 和 validator 消费。
4. 将模板作为风格参考，而非强制内容。

## 生成内容

- **schema.sql**: 包含所有表结构定义、字段类型、约束和索引。
- **er.md**: Mermaid 格式的实体关系图，展示表之间的关联关系。
- **migration-plan.md**: 迁移步骤、兼容性处理和回滚方案。


