---
name: flow-design
description: 基于业务需求生成系统交互时序图与状态机，覆盖主链路与异常链路。
---

# 工作流 (Workflow)

1. **资产读取**：读取需求基线以及现有的流程相关资产（如业务流程图、状态定义）。
2. **流程分析**：使用 `extract_structure` 和 `grep_search` 分析序列步骤、参与者和状态转换。
3. **时序图生成**：生成业务场景的时序图 `artifacts/sequence-{scenario}.md`。
4. **状态机生成**：生成实体状态机 `artifacts/state-{entity}.md`。
5. **证据沉淀**：将流程设计依据写入 `evidence/flow-design.json`。

# 输入参数 (Inputs)

## 必需参数 (Required)

| 参数 | 类型 | 说明 |
|------|------|------|
| `requirements` | string/path | 流程层面的业务需求文件路径 |
| `existing_assets` | string/path | 当前生产环境的流程文档或状态定义路径 |
| `output_root` | string/path | 项目设计包的根路径 |

## 可选参数 (Optional)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `context` | string/path | - | 上下文信息文件路径 |
| `scenario_name` | string | "example" | 业务场景名称（用于命名时序图）|
| `entity_name` | string | "example" | 实体名称（用于命名状态机）|

# 输出产物 (Output Artifacts)

## 必需产物 (Always Required)

| 产物路径 | 说明 |
|----------|------|
| `artifacts/sequence-{scenario}.md` | Mermaid 格式的时序图（主链路和异常链路）|
| `artifacts/state-{entity}.md` | Mermaid 格式的状态机图（状态转换和幂等性）|
| `evidence/flow-design.json` | 流程设计依据和证据 |

# 工具集 (Tools)

## 文件系统工具

| 工具名称 | 说明 |
|----------|------|
| `list_files` | 列出目录下的文件 |
| `read_file_chunk` | 读取文件片段 |
| `grep_search` | 搜索流程关键词（state, status, transition, callback, reserve, cancel, confirm, event）|
| `extract_structure` | 提取文件结构 |
| `write_file` | 写入设计产物 |
| `patch_file` | 修补已有文件 |

# 参考资料 (References)

- 模板使用 `assets/templates/sequence.md` 和 `assets/templates/state.md`。
- 参考 UML 时序图和状态机图规范。

# 注意事项 (Notes)

- **主链路优先**：时序图必须覆盖正常业务流程的完整路径。
- **异常处理**：状态机必须包含异常状态和回退路径。
- **幂等性**：回调、重试等操作必须标注幂等处理方式。

# ReAct 执行策略 (ReAct Strategy)

在执行过程中，按以下策略循环操作：

1. **研究 (Research)**：使用读取工具从需求文件中收集序列步骤、参与者和状态转换的证据。
2. **编写 (Write)**：使用 `write_file` 生成草稿产物。
3. **验证 (Verify)**：使用 `read_file_chunk` 回读已写入的内容进行验证。
4. **修补 (Patch)**：基于验证结果或新发现，使用 `patch_file` 进行微调。
5. **完成 (Finalize)**：仅当所有预期产物正确写入并验证后，设置 done=true。

## ReAct 规则

1. 每次只输出一个下一步动作。
2. 仅当收集到足够证据且已写入时序图和状态机时才停止。
3. 先使用 `extract_structure` 检查场景和状态相关章节。
4. 使用 `grep_search` 搜索 state, status, transition, callback, reserve, cancel, confirm, event, queue, gateway 等关键词。

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

1. 时序图产物必须描述具体的参与者、系统和有序交互。
2. 状态机产物必须描述有效的状态转换、幂等性和并发注意事项。
3. 将模板作为风格参考，而非强制内容。
4. 保持 Mermaid 代码块有效且基于证据。

## 生成内容

- **sequence-{scenario}.md**: 包含 Mermaid sequenceDiagram，展示 Client、Gateway、Application、Repository 等参与者交互。
- **state-{entity}.md**: 包含 Mermaid stateDiagram，展示 CREATED、PROCESSING、COMPLETED、FAILED 等状态转换。
