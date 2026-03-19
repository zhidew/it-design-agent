---
name: test-design
description: 提取测试输入条件，生成覆盖率映射矩阵，覆盖边界测试、异常用例、混沌测试和并发测试。
---

# 工作流 (Workflow)

1. **资产读取**：读取需求基线以及现有的测试相关资产（如历史测试用例、测试策略文档）。
2. **测试分析**：使用 `extract_structure` 和 `grep_search` 分析边界测试、无效用例、混沌测试、并发测试。
3. **测试输入生成**：生成测试输入条件 `artifacts/test-inputs.md`。
4. **覆盖率映射生成**：生成测试覆盖率映射 `artifacts/coverage-map.json`。
5. **证据沉淀**：将测试设计依据写入 `evidence/test-design.json`。

# 输入参数 (Inputs)

## 必需参数 (Required)

| 参数 | 类型 | 说明 |
|------|------|------|
| `requirements` | string/path | 测试层面的业务需求文件路径 |
| `existing_assets` | string/path | 当前生产环境的测试用例或测试策略文档路径 |
| `output_root` | string/path | 项目设计包的根路径 |

## 可选参数 (Optional)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `context` | string/path | - | 上下文信息文件路径 |

# 输出产物 (Output Artifacts)

## 必需产物 (Always Required)

| 产物路径 | 说明 |
|----------|------|
| `artifacts/test-inputs.md` | 测试输入条件列表（边界、无效、集成失败、并发测试想法）|
| `artifacts/coverage-map.json` | 设计关注点到自动化测试预期的映射 |
| `evidence/test-design.json` | 测试设计依据和证据 |

# 工具集 (Tools)

## 文件系统工具

| 工具名称 | 说明 |
|----------|------|
| `list_files` | 列出目录下的文件 |
| `read_file_chunk` | 读取文件片段 |
| `grep_search` | 搜索测试关键词（invalid, boundary, idempotent, timeout, retry, concurrency, duplicate, status, callback）|
| `extract_structure` | 提取文件结构 |
| `write_file` | 写入设计产物 |
| `patch_file` | 修补已有文件 |

# 参考资料 (References)

- 模板使用 `assets/templates/test-inputs.md` 和 `assets/templates/coverage-map.json`。
- 参考测试金字塔：单元测试、集成测试、端到端测试比例。

# 注意事项 (Notes)

- **边界测试**：数值边界、状态边界、时间边界等必须覆盖。
- **无效用例**：必须包含无效输入、异常状态的测试想法。
- **混沌测试**：超时、重试、下游故障等场景必须覆盖。
- **并发测试**：重复提交、并发竞态等场景必须覆盖。

# ReAct 执行策略 (ReAct Strategy)

在执行过程中，按以下策略循环操作：

1. **研究 (Research)**：使用读取工具从需求文件中收集边界测试、无效用例、混沌测试、并发测试、覆盖率映射的证据。
2. **编写 (Write)**：使用 `write_file` 生成草稿产物。
3. **验证 (Verify)**：使用 `read_file_chunk` 回读已写入的内容进行验证。
4. **修补 (Patch)**：基于验证结果或新发现，使用 `patch_file` 进行微调。
5. **完成 (Finalize)**：仅当所有预期产物正确写入并验证后，设置 done=true。

## ReAct 规则

1. 每次只输出一个下一步动作。
2. 仅当收集到足够证据且已写入测试输入和覆盖率映射时才停止。
3. 先使用 `extract_structure` 检查标题和 JSON 键，再读取大块内容。
4. 使用 `grep_search` 搜索 invalid, boundary, idempotent, timeout, retry, concurrency, duplicate, status, callback 等关键词。

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

1. test-inputs.md 必须包含边界、无效、集成失败、并发测试想法，并基于证据支撑。
2. coverage-map.json 必须将关键设计关注点映射到具体的自动化测试预期，并基于证据支撑。
3. 将模板作为风格参考，而非强制内容。
4. 保持 coverage-map.json 为有效的 JSON 格式。

## 生成内容

- **test-inputs.md**: 包含边界测试、无效用例、混沌测试、并发测试的测试想法列表。
- **coverage-map.json**: 包含 coverage_rules 和 mapped_test_cases 数组。
