# 详细设计评审清单 (Design Review Checklist)

> **项目名称**: {{project_name}}
> **评审时间**: _________

## 1. 架构与领域门禁 (Architecture & Domain) - 架构师/后端
- [ ] 领域模型 (`class-*.md`) 是否正确反映了业务需求？聚合根边界是否清晰？
- [ ] 系统上下文 (`architecture.md`) 是否遗漏了与外部系统的交互？
- [ ] 模块间依赖 (`module-map.json`) 是否存在循环依赖？

## 2. 接口与数据门禁 (API & Data) - 前后端/DBA
- [ ] API 设计 (`api-*.yaml`) 是否符合 RESTful 或 RFC 9457 规范？是否提供了完整的分页和报错示例？
- [ ] 状态机 (`state-*.md`) 的异常扭转和并发修改是否有防重/幂等处理？
- [ ] 数据库变更 (`schema.sql`) 是否包含必要的索引和审计字段？
- [ ] 是否提供了完备的数据回滚与降级方案 (`migration-plan.md`)？

## 3. 测试可设计性门禁 (Testability) - 测试
- [ ] 需求是否已100%映射到设计产物 (`traceability.json`)？是否存在断链？
- [ ] 核心场景的异常边界输入是否已明确提取 (`test-inputs.md`)？

## 4. 运行就绪门禁 (Ops Readiness) - SRE
- [ ] 是否为新增的核心链路定义了 SLO (`slo.yaml`)？
- [ ] 配置矩阵 (`config-matrix.md`) 中是否暴露了敏感密钥？
- [ ] 运行手册 (`deployment-runbook.md`) 的回滚条件是否具备可执行性？

## 5. 评审结论
- **结论**: [通过 / 条件通过 / 驳回]
- **遗留风险及跟进人**: 
  - 1. __________________
  - 2. __________________
