---
name: test-design
description: 提取测试输入条件，生成覆盖率映射矩阵，覆盖边界测试、异常用例、混沌测试和并发测试。
---

# Tool Usage Notes

- Follow the runtime-generated tool contract from the expert YAML. Do not assume a tool is available unless the controller prompt exposes it.
- Prefer read and grounding steps first. Use write tools only to persist owned artifacts or make bounded corrections under `artifacts/`.
- Treat optional validators or external techniques as non-guaranteed unless the runtime explicitly exposes them for this run.
# 参考资料 (References)

- 模板使用 `assets/templates/test-inputs.md` 和 `assets/templates/coverage-map.json`。
- 参考测试金字塔：单元测试、集成测试、端到端测试比例。

# 注意事项 (Notes)

- **边界测试**：数值边界、状态边界、时间边界等必须覆盖。
- **无效用例**：必须包含无效输入、异常状态的测试想法。
- **混沌测试**：超时、重试、下游故障等场景必须覆盖。
- **并发测试**：重复提交、并发竞态等场景必须覆盖。
- **专家边界**：只负责测试输入、覆盖率映射和验证场景；不要在测试文档中反向重写架构、领域模型、接口/事件契约、DDL、配置矩阵或运维方案。
- **依赖协同**：优先消费 `flow-design`、`api-design`、`integration-design`、`ops-design` 等上游产物，把它们转成可验证场景；若上游定义模糊，记录测试前提和缺口，而不是替上游补详细设计。

# ReAct 执行策略 (ReAct Strategy)

在执行过程中，按以下策略循环操作：

1. **研究 (Research)**：使用读取工具从需求文件中收集边界测试、无效用例、混沌测试、并发测试、覆盖率映射的证据。
2. **编写 (Write)**：使用 `write_file` 生成草稿产物。
3. **验证 (Verify)**：使用 `read_file_chunk` 回读已写入的内容进行验证。
4. **修补 (Patch)**：基于验证结果或新发现，使用 `patch_file` 进行微调。
5. **完成 (Finalize)**：仅当所有预期产物正确写入并验证后，设置 done=true。

## ReAct 规则

1. 默认每次只输出一个下一步动作；只有在收集独立、低风险的读取证据时，才可使用 `actions` 返回最多 2 个只读动作。
2. 仅当收集到足够证据且已写入测试输入和覆盖率映射时才停止。
3. 先使用 `extract_structure` 检查标题和 JSON 键，再读取大块内容。
4. 使用 `grep_search` 搜索 invalid, boundary, idempotent, timeout, retry, concurrency, duplicate, status, callback 等关键词。
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
    {"tool_name": "grep_search", "tool_input": {"pattern": "invalid|boundary|idempotent|timeout|retry|concurrency|duplicate|status|callback"}}
  ],
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


