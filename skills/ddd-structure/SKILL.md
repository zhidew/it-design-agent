---
name: ddd-structure
description: 进行领域建模和结构设计，产出类图、DDD 结构说明（聚合、实体、值对象、仓储、命令、查询、领域事件）。
---

# 工作流 (Workflow)

1. **资产读取**：读取需求基线以及现有的领域模型资产（如历史 DDD 文档、领域词汇表）。
2. **领域分析**：使用 `extract_structure` 和 `grep_search` 分析聚合、实体、值对象、仓储等概念。
3. **类图生成**：生成领域类图 `artifacts/class-{domain}.md`。
4. **DDD 结构**：生成 DDD 结构说明 `artifacts/ddd-structure.md`。
5. **证据沉淀**：将领域建模依据写入 `evidence/ddd-structure.json`。

# 输入参数 (Inputs)

## 必需参数 (Required)

| 参数 | 类型 | 说明 |
|------|------|------|
| `requirements` | string/path | 领域层面的业务需求文件路径 |
| `existing_assets` | string/path | 当前生产环境的领域模型文档或实体定义路径 |
| `output_root` | string/path | 项目设计包的根路径 |

## 可选参数 (Optional)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `context` | string/path | - | 上下文信息文件路径 |
| `domain_name` | string | "domain" | 领域名称（用于命名输出文件）|

# 输出产物 (Output Artifacts)

## 必需产物 (Always Required)

| 产物路径 | 说明 |
|----------|------|
| `artifacts/class-{domain}.md` | Mermaid 格式的领域类图（聚合根、实体、值对象）|
| `artifacts/ddd-structure.md` | DDD 结构说明（聚合、仓储、命令、查询、事件）|
| `artifacts/context-map.md` | 上下文映射图（限界上下文关系）|
| `evidence/ddd-structure.json` | 领域建模依据和证据 |

# 工具集 (Tools)

## 文件系统工具

| 工具名称 | 说明 |
|----------|------|
| `list_files` | 列出目录下的文件 |
| `read_file_chunk` | 读取文件片段 |
| `grep_search` | 搜索领域关键词（aggregate, entity, value object, repository, command, query, event）|
| `extract_structure` | 提取文件结构 |
| `write_file` | 写入设计产物 |
| `patch_file` | 修补已有文件 |

# 参考资料 (References)

- 模板使用 `assets/templates/class.md` 和 `assets/templates/ddd-structure.md`。
- 参考 DDD 战术设计：聚合根、实体、值对象、领域服务、仓储、领域事件。

# 注意事项 (Notes)

- **聚合边界**：必须清晰定义聚合边界和一致性边界。
- **命名规范**：聚合、实体、值对象应使用领域通用语言（Ubiquitous Language）。
- **事件驱动**：领域事件应使用过去时命名（如 OrderCreatedEvent）。

# ReAct 执行策略 (ReAct Strategy)

在执行过程中，按以下策略循环操作：

1. **研究 (Research)**：使用读取工具从需求文件中收集聚合、实体、值对象、仓储、命令、查询、领域事件的证据。
2. **编写 (Write)**：使用 `write_file` 生成草稿产物。
3. **验证 (Verify)**：使用 `read_file_chunk` 回读已写入的内容进行验证。
4. **修补 (Patch)**：基于验证结果或新发现，使用 `patch_file` 进行微调。
5. **完成 (Finalize)**：仅当所有预期产物正确写入并验证后，设置 done=true。

## ReAct 规则

1. 每次只输出一个下一步动作。
2. 仅当收集到足够证据且已写入类图和 DDD 结构文档时才停止。
3. 先使用 `extract_structure` 检查标题和 JSON 键，再读取大块内容。
4. 使用 `grep_search` 搜索 aggregate, entity, value object, repository, command, query, event, status, refund, money 等关键词。

## 返回格式

```json
{
  "done": false,
  "thought": "为什么需要这一步",
  "tool_name": "list_files | extract_structure | grep_search | read_file_chunk | none",
  "tool_input": {},
  "evidence_note": "这一步应该确认或产出什么"
}
```

# 最终生成策略 (Final Generation)

当 ReAct 循环结束后，基于收集的证据生成最终产物：

## 生成要求

1. 类图产物必须描述具体的聚合、实体、值对象及其关系。
2. ddd-structure.md 必须描述仓储、命令、查询、领域事件，并基于证据支撑。
3. 将模板作为风格参考，而非强制内容。
4. 保持 Mermaid 代码块和 Markdown 格式正确。

## 生成内容

- **class-{domain}.md**: 包含 Mermaid classDiagram，展示聚合根、实体、值对象。
- **ddd-structure.md**: 包含聚合根、仓储、命令、查询、领域事件的列表和说明。
