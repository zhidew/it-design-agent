# 核心配置矩阵 (Configuration Matrix): {{project_name}}

> 本文档描述不同环境下的具体配置取值策略。请注意，**严禁在文档中明文记录任何生产环境的密钥或密码**。

## 1. 外部依赖端点 (Endpoints)
*(确保本系统能正确连通外部 `{{provider}}` 等依赖系统)*

| 配置键 (Config Key) | DEV | TEST | PROD |
| :--- | :--- | :--- | :--- |
| `integration.{{provider}}.url` | `http://mock-{{provider}}.internal` | `https://api.sandbox.{{provider}}.com` | `https://api.{{provider}}.com` |
| `integration.{{provider}}.timeout_ms` | `5000` | `3000` | `2000` |

## 2. 存储与中间件配置 (Backing Services)
*(基于需求识别出的中间件依赖: `{{dependencies}}`)*

| 配置键 (Config Key) | DEV | TEST | PROD | 备注 |
| :--- | :--- | :--- | :--- | :--- |
| `spring.datasource.url` | `jdbc:mysql://db.dev...` | `jdbc:mysql://db.test...` | `jdbc:mysql://db.prod...` | 生产必须走主从分离连接串 |
| `spring.datasource.password` | `dev_123` | `test_456` | *[KMS/Vault 动态获取]* | **严禁明文** |
| `spring.redis.host` | `redis.dev` | `redis.test` | `redis.prod.cluster` | 生产走 Cluster 模式 |

## 3. 业务开关与容灾降级 (Feature Toggles)
| 配置键 (Config Key) | 默认值 | 作用描述 | 动态刷新 |
| :--- | :--- | :--- | :--- |
| `features.{{scenario_name}}.enabled` | `true` | 是否开放该核心业务入口 | ✅ 支持 |
| `degrade.{{provider}}.fallback_enabled` | `false` | 当调用 {{provider}} 连续超时，是否强制降级返回默认值 | ✅ 支持 |
