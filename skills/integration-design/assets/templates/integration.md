# 系统集成设计: {{integration_scenario}}

> **业务背景**: {{scenario_desc}}

## 1. 集成链路定义
- **上游调用方 (Consumer)**: `{{consumer}}`
- **下游提供方 (Provider)**: `{{provider}}`
- **集成模式**: 异步事件驱动 (Async Event) / 同步 RPC

## 2. {{consumer}} 的防重与补偿设计
*(指导 {{consumer}} 如何安全地调用 {{provider}})*

- **幂等控制**: 在向 `{{provider}}` 发起请求时，必须在 HTTP Header 或 Message Payload 中注入唯一的 `x-request-id` 或业务流水号。
- **重试策略**: 采用指数退避重试 (Exponential Backoff)。初始延迟 1s，最大重试 3 次。
- **故障熔断**: 若对 `{{provider}}` 的调用在 1 分钟内失败率超过 50%，触发熔断，接口降级返回“处理中”。
- **最终一致性**: 必须在本地数据库建立 `integration_outbox_table`（本地消息表），对于调用失败的记录，通过定时任务轮询补偿。

## 3. {{provider}} 的安全性与约束
*(指导 {{provider}} 如何安全地暴露服务)*

- **身份认证**: `{{provider}}` 必须校验来自 `{{consumer}}` 的 JWT Token 或内部 HMAC 签名。
- **限流策略**: 针对 `{{consumer}}` 配置单机 QPS 限流（例如 max 500 QPS），超出部分快速失败。
- **幂等实现**: `{{provider}}` 必须基于 `x-request-id` 在 Redis 或 DB 唯一索引中实现防重，如果收到重复请求，直接返回上一次的成功结果，**严禁再次执行业务状态扭转**。