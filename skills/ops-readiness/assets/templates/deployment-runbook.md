# 发布与运行手册 (Deployment Runbook): {{project_name}}

## 1. 发布前置检查 (Pre-flight Checklist)
*(负责人: 研发 & SRE)*
- [ ] 确认 CI 流水线 (单测、Sonar) 已全部通过。
- [ ] 确认本次重构涉及的 DDL (`schema.sql`) 已由 DBA 审核并在生产环境前置执行。
- [ ] 确认依赖的上游系统 `{{provider}}` 和底层组件 `{{dependencies}}` 当前状态正常。
- [ ] 确认已在生产环境的配置中心 (Apollo/Nacos) 中注入了 `config-matrix.md` 约定的 PROD 变量，**特别是 `{{provider}}` 的生产网关地址**。

## 2. 流量切换与部署 (Deployment Steps)
1. **停止引流**: 在负载均衡层 (Nginx/Gateway) 将老版本实例权重调至 0。
2. **应用发版**: 在 K8s 部署 `{{project_name}}` 新版本镜像。
3. **探活检查**: 检查应用的 `/actuator/health` 端口，确保 DB 和 Redis 连通性。
4. **灰度引流**: 按 1% -> 10% -> 50% -> 100% 的节奏放量，重点观察是否出现 `{{provider}}` 的调用报错。

## 3. 紧急回滚方案 (Rollback Strategy)
**触发条件 (参照 SLO 阈值)**: 
- `{{scenario_name}}` 核心业务错误率连续 3 分钟 > 5%。
- 或者调用 `{{provider}}` 的 P99 延迟突增至 2000ms 以上。

**回滚步骤**:
1. **阻断流量**: 立即通过配置中心将开关 `features.{{scenario_name}}.enabled` 置为 `false`，阻止新错产生。
2. **应用回滚**: K8s 一键回滚到上一个稳定版本镜像 (Scale up old RS, Scale down new RS)。
3. **数据对账**: 导出发布期间（约 10 分钟）的错误日志，通过异步补偿脚本修复错乱的 `{{entity_name}}` 状态。
