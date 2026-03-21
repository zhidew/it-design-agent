---
name: ops-design
description: 设计 SLO、告警规则、监控指标及发布回滚的运行手册，确保服务生产就绪。
---

# 工作流 (Workflow)

1. **资产读取**：读取需求基线以及现有的运维相关资产（如历史 SLO、告警规则）。
2. **SLO 分析**：使用 `extract_structure` 和 `grep_search` 分析可用性、延迟、回滚、告警等指标。
3. **SLO 生成**：生成服务等级目标 `artifacts/slo.yaml`。
4. **可观测性生成**：生成监控指标和告警规范 `artifacts/observability-spec.yaml`。
5. **Runbook 生成**：生成部署运行手册 `artifacts/deployment-runbook.md`。
6. **证据沉淀**：将运维设计依据写入 `evidence/ops-design.json`。

# 输入参数 (Inputs)

## 必需参数 (Required)

| 参数 | 类型 | 说明 |
|------|------|------|
| `requirements` | string/path | 运维层面的业务需求文件路径 |
| `existing_assets` | string/path | 当前生产环境的 SLO 文档或告警配置路径 |
| `output_root` | string/path | 项目设计包的根路径 |

## 可选参数 (Optional)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `context` | string/path | - | 上下文信息文件路径 |

# 输出产物 (Output Artifacts)

## 必需产物 (Always Required)

| 产物路径 | 说明 |
|----------|------|
| `artifacts/slo.yaml` | SLI/SLO 目标定义（可用性、延迟等）|
| `artifacts/observability-spec.yaml` | 监控指标、Trace Span、告警规则定义 |
| `artifacts/deployment-runbook.md` | 部署检查清单和回滚触发条件 |
| `evidence/ops-design.json` | 运维设计依据和证据 |

# 工具集 (Tools)

## 文件系统工具

| 工具名称 | 说明 |
|----------|------|
| `list_files` | 列出目录下的文件 |
| `read_file_chunk` | 读取文件片段 |
| `grep_search` | 搜索运维关键词（availability, latency, rollback, alert, Kafka, tracing, error rate, p99, dependency）|
| `extract_structure` | 提取文件结构 |
| `write_file` | 写入设计产物 |
| `patch_file` | 修补已有文件 |

# 参考资料 (References)

- 模板使用 `assets/templates/slo.yaml`、`assets/templates/observability-spec.yaml` 和 `assets/templates/deployment-runbook.md`。
- 参考 Google SRE 手册：SLI/SLO/SLA 定义。

# 注意事项 (Notes)

- **SLO 必须量化**：可用性、延迟等目标必须为具体数值（如 99.99%、200ms）。
- **告警可行动**：告警规则必须关联具体的排查步骤或自动修复动作。
- **回滚触发明确**：必须定义错误率、延迟等回滚触发阈值。

# ReAct 执行策略 (ReAct Strategy)

在执行过程中，按以下策略循环操作：

1. **研究 (Research)**：使用读取工具从需求文件中收集 SLO、可观测性、告警、部署检查、回滚触发的证据。
2. **编写 (Write)**：使用 `write_file` 生成草稿产物。
3. **验证 (Verify)**：使用 `read_file_chunk` 回读已写入的内容进行验证。
4. **修补 (Patch)**：基于验证结果或新发现，使用 `patch_file` 进行微调。
5. **完成 (Finalize)**：仅当所有预期产物正确写入并验证后，设置 done=true。

## ReAct 规则

1. 每次只输出一个下一步动作。
2. 仅当收集到足够证据且已写入 SLO、可观测性规范和 Runbook 时才停止。
3. 先使用 `extract_structure` 检查标题和 JSON 键，再读取大块内容。
4. 使用 `grep_search` 搜索 availability, latency, rollback, alert, Kafka, tracing, error rate, p99, dependency 等关键词。

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

1. slo.yaml 必须定义具体的 SLI/SLO 目标，并基于证据支撑。
2. observability-spec.yaml 必须定义指标、Span 和告警，并基于证据支撑。
3. deployment-runbook.md 必须定义发布检查和回滚触发条件，并基于证据支撑。
4. 将模板作为风格参考，而非强制内容。

## 生成内容

- **slo.yaml**: 包含 service、slos 数组（sli_name、target）。
- **observability-spec.yaml**: 包含 service、tracing、alerts 定义。
- **deployment-runbook.md**: 包含检查清单、回滚触发条件、核心场景保护策略。
