# 性能设计说明

> **项目**: {{project_name}}
> **需求标识**: {{requirement_id}}
> **需求主题**: {{requirement_name}}
> **性能目标窗口**: {{target_window}}

## 1. 设计范围

- 需求概述：{{requirement_summary}}
- 关键场景数量：{{scenario_count}}
- 设计原则：预算可追踪、瓶颈可定位、容量可评估、治理可执行
- 负载画像：峰值 {{peak_qps}} QPS，平均 {{avg_qps}} QPS，峰谷比 {{peak_ratio}}

## 2. 关键场景与链路边界

| 场景 | 处理单元 | 处理职责 | 调用类型 | 关键依赖 | 边界判断 |
|------|----------|----------|----------|----------|----------|
| {{scenario_name}} | {{component_name}} | {{component_responsibility}} | {{path_type}} | {{dependencies}} | {{boundary_assessment}} |

## 3. 性能预算

| 场景/单元 | P95 时延 | 峰值吞吐 | 峰值并发 | DB 访问上限 | 远程调用上限 | Payload 上限 | 预算说明 |
|-----------|----------|----------|----------|-------------|---------------|--------------|----------|
| {{component_name}} | {{latency_p95}} | {{peak_throughput}} | {{peak_concurrency}} | {{db_calls}} | {{remote_calls}} | {{payload_limit}} | {{budget_reason}} |

## 4. 关键热点与瓶颈

### 4.1 热点路径

1. `{{hot_path_name}}`
   - 链路步骤：{{hot_path_steps}}
   - 主要成本：{{hot_path_cost}}
   - 风险说明：{{hot_path_risk}}

### 4.2 边界与容量风险

| 场景/单元 | 风险类型 | 风险表现 | 触发条件 | 影响 | 建议动作 |
|-----------|----------|----------|----------|------|----------|
| {{component_name}} | {{risk_type}} | {{risk_signal}} | {{trigger_condition}} | {{impact}} | {{recommended_action}} |

## 5. 性能治理策略

| 场景/单元 | 主要策略 | 触发阈值 | 预期收益 | 代价/约束 |
|-----------|----------|----------|----------|----------|
| {{component_name}} | {{control_strategy}} | {{control_threshold}} | {{expected_benefit}} | {{tradeoff}} |

可选策略包括：
- 限流与配额
- 缓存与预计算
- 异步化与削峰填谷
- 批处理与合并请求
- 读写分离与索引优化
- 熔断、降级与快速失败

## 6. 验收与后续协同

- 对 `ops-design` 的输入：{{ops_inputs}}
- 对 `test-design` 的输入：{{test_inputs}}
- 待确认假设：{{open_assumptions}}
- 残余风险：{{residual_risks}}
