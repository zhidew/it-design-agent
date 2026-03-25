---
name: data-design
description: 负责数据库表结构设计、索引优化、实体关系映射（ER图）以及平滑的数据迁移与回滚策略。确保数据设计的向后兼容性和高性能。
---

# 工作流 (Workflow)

1. **资产读取**：在开始设计前，读取需求基线以及现有的数据库设计资产（如历史 DDL、数据字典、慢查询日志）。
2. **结构生成**：基于需求，利用 `assets/templates/` 中的模板，生成增量或全量的 `artifacts/schema.sql`，明确表结构、字段类型、约束和索引。
3. **ER 图渲染**：抽取 `schema.sql` 中的实体与外键/逻辑关系，生成 Mermaid 格式的实体关系图 `artifacts/er.md`。
4. **迁移策略**：评估结构变更对存量数据的影响。如果存在破坏性变更或大表 DDL，必须在 `artifacts/migration-plan.md` 中提供详细的迁移与数据回滚方案。
5. **证据沉淀**：将设计依据（如依赖了哪些现存表）和校验结果（如通过了 sqlfluff 检查）写入 `evidence/data-design.json`。
6. **校验门禁**：如果缺少回滚方案或 `schema.sql` 语法有误，则直接终止工作流并抛出错误。

# 输入参数 (Inputs)

## 必需参数 (Required)

| 参数 | 类型 | 说明 |
|------|------|------|
| `requirements` | string/path | 数据层面的业务需求文件路径（如新增属性、优化查询）|
| `existing_assets` | string/path | 当前生产环境的 DDL、数据字典或索引信息路径 |
| `output_root` | string/path | 项目设计包的根路径 |

## 可选参数 (Optional)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `constraints` | string/path | - | 约束策略文件路径 |
| `context` | string/path | - | 上下文信息文件路径 |
| `data_volume_estimation` | string | - | 预估的数据量，用于指导分库分表或索引策略 |

# 输出产物 (Output Artifacts)

## 必需产物 (Always Required)

| 产物路径 | 说明 |
|----------|------|
| `artifacts/schema.sql` | 数据库 DDL 脚本（表结构、字段类型、约束和索引）|
| `artifacts/er.md` | 基于 Mermaid 的实体关系图及说明 |
| `artifacts/migration-plan.md` | 数据迁移、兼容性处理及回滚计划 |
| `evidence/data-design.json` | 资产采纳和校验过程的证据 |

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
| `run_command` | 执行命令（如 sqlfluff 校验）|

# 参考资料 (References)

- 模板使用 `assets/templates/schema.sql`、`assets/templates/er.md` 和 `assets/templates/migration-plan.md`。
- 参考项目全局的数据规范（如有），如公共审计字段（created_at, updated_at）及软删除约定。

# 注意事项 (Notes)

- **回滚必须**：任何涉及表结构修改的设计，必须成对提供升级脚本（Up）和降级脚本（Down）。
- **兼容性**：尽量采用"扩容式修改"（如新增字段、新增表），避免"破坏式修改"（如重命名、删除在用字段）。
- **索引感知**：新增查询需求必须评估并设计配套的数据库索引。

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
