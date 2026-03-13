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
- `requirements`: 数据层面的业务需求（如新增属性、优化查询）。
- `existing_assets`: 当前生产环境的 DDL、数据字典或索引信息。
- `output_root`: 项目设计包的根路径。
- `data_volume_estimation` (可选): 预估的数据量，用于指导是否需要分库分表或调整索引策略。

# 输出产物 (Output Artifacts)
- `artifacts/schema.sql`: 数据库 DDL 脚本。
- `artifacts/er.md`: 基于 Mermaid 的实体关系图及说明。
- `artifacts/migration-plan.md`: 数据迁移、兼容性处理及回滚计划。
- `evidence/data-design.json`: 资产采纳和校验过程的证据。

# 工具集 (Tools)
- `python:design-system/skills/data-design/scripts/render_data_stub.py`
- `sqlfluff` (用于 SQL 语法与规范校验)

# 参考资料 (References)
- 模板使用 `assets/templates/schema.sql`、`assets/templates/er.md` 和 `assets/templates/migration-plan.md`。
- 参考项目全局的数据规范（如有），如公共审计字段（created_at, updated_at）及软删除约定。

# 注意事项 (Notes)
- **回滚必须**：任何涉及表结构修改的设计，必须成对提供升级脚本（Up）和降级脚本（Down）。
- **兼容性**：尽量采用“扩容式修改”（如新增字段、新增表），避免“破坏式修改”（如重命名、删除在用字段）。
- **索引感知**：新增查询需求必须评估并设计配套的数据库索引。
