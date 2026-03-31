---
name: ops-design
description: 设计 SLO、告警规则、监控指标及发布回滚的运行手册，确保服务生产就绪。
---

# Tool Usage Notes

- Follow the runtime-generated tool contract from the expert YAML. Do not assume a tool is available unless the controller prompt exposes it.
- Prefer read and grounding steps first. Use write tools only to persist owned artifacts or make bounded corrections under `artifacts/`.
- Treat optional validators or external techniques as non-guaranteed unless the runtime explicitly exposes them for this run.
# 参考资料 (References)

- 模板使用 `assets/templates/slo.yaml`、`assets/templates/observability-spec.yaml` 和 `assets/templates/deployment-runbook.md`。
- 参考 Google SRE 手册：SLI/SLO/SLA 定义。

# 注意事项 (Notes)

- **SLO 必须量化**：可用性、延迟等目标必须为具体数值（如 99.99%、200ms）。
- **告警可行动**：告警规则必须关联具体的排查步骤或自动修复动作。
- **回滚触发明确**：必须定义错误率、延迟等回滚触发阈值。
- **专家边界**：只负责 SLO、指标、告警、发布检查和回滚 runbook；可以引用配置键、API、消息链路作为运维依赖，但不要重新设计它们的详细内容。
- **依赖协同**：把 `config-design` 及其他上游产物视为事实来源。若发现上游缺少运维所需信息，记录缺口和风险，不在本专家产物里反向补完整体设计。

# ReAct 执行策略 (ReAct Strategy)

在执行过程中，按以下策略循环操作：

1. **研究 (Research)**：使用读取工具从需求文件中收集 SLO、可观测性、告警、部署检查、回滚触发的证据。
2. **编写 (Write)**：使用 `write_file` 生成草稿产物。
3. **验证 (Verify)**：使用 `read_file_chunk` 回读已写入的内容进行验证。
4. **修补 (Patch)**：基于验证结果或新发现，使用 `patch_file` 进行微调。
5. **完成 (Finalize)**：仅当所有预期产物正确写入并验证后，设置 done=true。

## ReAct 规则

1. 默认每次只输出一个下一步动作；只有在收集独立、低风险的读取证据时，才可使用 `actions` 返回最多 2 个只读动作。
2. 仅当收集到足够证据且已写入 SLO、可观测性规范和 Runbook 时才停止。
3. 先使用 `extract_structure` 检查标题和 JSON 键，再读取大块内容。
4. 使用 `grep_search` 搜索 availability, latency, rollback, alert, Kafka, tracing, error rate, p99, dependency 等关键词。
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
    {"tool_name": "grep_search", "tool_input": {"pattern": "availability|latency|rollback|alert|Kafka|tracing|error rate|p99|dependency"}}
  ],
  "evidence_note": "这一步应该确认或产出什么"
}
```

# 最终生成策略 (Final Generation)

当 ReAct 循环结束后，基于收集的证据生成最终产物：

## 生成要求

1. slo.yaml 必须定义具体的 SLI/SLO 目标，并基于证据支撑。
2. observability-spec.yaml 必须定义指标、Span 和告警，并基于证据支撑。
3. deployment-runbook.md 必须定义发布检查和回滚触发条件，并基于证据支撑。
4. 将模板作为风格参考，而非强制内容。

## 生成内容

- **slo.yaml**: 包含 service、slos 数组（sli_name、target）。
- **observability-spec.yaml**: 包含 service、tracing、alerts 定义。
- **deployment-runbook.md**: 包含检查清单、回滚触发条件、核心场景保护策略。


