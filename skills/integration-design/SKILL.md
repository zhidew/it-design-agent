---
name: integration-design
description: 设计跨服务和外部系统的集成协议，包括异步事件契约(AsyncAPI)、幂等策略、重试机制与补偿方案。
---

# 工作流 (Workflow)

1. **资产读取**：读取需求基线以及现有的集成相关资产（如历史接口文档、事件契约）。
2. **集成分析**：使用 `extract_structure` 和 `grep_search` 分析下游调用、异步事件、幂等、重试、补偿。
3. **集成文档生成**：生成集成设计文档 `artifacts/integration-{provider}.md`。
4. **AsyncAPI 生成**：生成异步事件契约 `artifacts/asyncapi.yaml`。
5. **证据沉淀**：将集成设计依据写入 `evidence/integration-design.json`。

# 输入参数 (Inputs)

## 必需参数 (Required)

| 参数 | 类型 | 说明 |
|------|------|------|
| `requirements` | string/path | 集成层面的业务需求文件路径 |
| `existing_assets` | string/path | 当前生产环境的接口文档或事件定义路径 |
| `output_root` | string/path | 项目设计包的根路径 |

## 可选参数 (Optional)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `context` | string/path | - | 上下文信息文件路径 |
| `provider` | string | "externalsystem" | 外部服务提供者名称（用于命名输出文件）|

# 输出产物 (Output Artifacts)

## 必需产物 (Always Required)

| 产物路径 | 说明 |
|----------|------|
| `artifacts/integration-{provider}.md` | 集成设计文档（幂等、重试、熔断、补偿策略）|
| `artifacts/asyncapi.yaml` | AsyncAPI 格式的事件契约定义 |
| `evidence/integration-design.json` | 集成设计依据和证据 |

# 工具集 (Tools)

## 文件系统工具

| 工具名称 | 说明 |
|----------|------|
| `list_files` | 列出目录下的文件 |
| `read_file_chunk` | 读取文件片段 |
| `grep_search` | 搜索集成关键词（idempotency, retry, outbox, callback, event, queue, Kafka, request-id, compensation）|
| `extract_structure` | 提取文件结构 |
| `write_file` | 写入设计产物 |
| `patch_file` | 修补已有文件 |

# 参考资料 (References)

- 模板使用 `assets/templates/integration.md` 和 `assets/templates/asyncapi.yaml`。
- 参考 AsyncAPI 3.0 规范。
- 参考 Outbox 模式实现最终一致性。

# 注意事项 (Notes)

- **幂等设计**：必须明确幂等键（如 x-request-id）和去重策略。
- **重试策略**：必须定义指数退避和最大重试次数。
- **熔断机制**：必须定义下游错误率阈值和降级策略。
- **补偿方案**：必须定义 Outbox 中继和回放任务。

# ReAct 执行策略 (ReAct Strategy)

在执行过程中，按以下策略循环操作：

1. **研究 (Research)**：使用读取工具从需求文件中收集下游调用、异步事件、幂等、重试、补偿的证据。
2. **编写 (Write)**：使用 `write_file` 生成草稿产物。
3. **验证 (Verify)**：使用 `read_file_chunk` 回读已写入的内容进行验证。
4. **修补 (Patch)**：基于验证结果或新发现，使用 `patch_file` 进行微调。
5. **完成 (Finalize)**：仅当所有预期产物正确写入并验证后，设置 done=true。

## ReAct 规则

1. 每次只输出一个下一步动作。
2. 仅当收集到足够证据且已写入集成文档和 AsyncAPI 时才停止。
3. 先使用 `extract_structure` 检查标题和 JSON 键，再读取大块内容。
4. 使用 `grep_search` 搜索 idempotency, retry, outbox, callback, event, queue, Kafka, request-id, compensation 等关键词。

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

1. 集成文档必须描述幂等、重试、熔断、补偿策略，并基于证据支撑。
2. asyncapi.yaml 必须定义具体的领域事件和操作，并基于证据支撑。
3. 将模板作为风格参考，而非强制内容。
4. 保持 asyncapi.yaml 语法正确且与场景一致。

## 生成内容

- **integration-{provider}.md**: 包含 Consumer、Provider、幂等键、重试策略、熔断策略、补偿方案。
- **asyncapi.yaml**: 包含 asyncapi 版本、channels、operations 定义。
