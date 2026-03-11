# 架构与边界映射: {{project_name}}

## 1. 系统级上下文 (C4 Context)
本视图明确了 `{{project_name}}` 与外部系统和消费者的交互边界。

```mermaid
C4Context
    title 系统级上下文: {{project_name}}
    
    Person(user, "业务用户", "系统功能的使用者")
    System(core, "{{project_name}}", "本需求涉及的核心重构系统")
    System_Ext(provider, "{{provider}}", "提供核心依赖能力的外部系统")
    System_Ext(consumer, "{{consumer}}", "消费本系统事件或API的外部系统")
    
    Rel(user, core, "发起业务请求", "HTTPS")
    Rel(core, provider, "同步调用/数据核对", "RPC/HTTP")
    Rel(core, consumer, "推送异步事件", "Kafka/MQ")
```

## 2. 容器架构部署 (C4 Container)
本视图明确了 `{{project_name}}` 内部的物理进程分布。

```mermaid
C4Container
    title 容器部署架构: {{project_name}}
    
    Person(user, "业务用户", "流量入口")
    
    System_Boundary(c1, "{{project_name}} 边界") {
        Container(api, "API 接入网关", "Kong / Nginx", "负责 TLS 卸载、限流与鉴权")
        Container(app, "核心应用服务", "Java/Go 进程", "承载 {{domain_name}} 领域的业务编排与规则执行")
        
        %% 基于需求中的 dependencies 动态映射存储组件
        ContainerDb(db, "主关系型数据库", "MySQL/PostgreSQL", "持久化 {{aggregate_root}} 核心业务数据")
        ContainerDb(cache, "分布式缓存", "Redis", "缓存查询热点，提供分布式锁控制并发")
    }
    
    Rel(user, api, "访问 API", "HTTPS")
    Rel(api, app, "路由转发", "gRPC/HTTP")
    Rel(app, db, "读写核心状态", "TCP/JDBC")
    Rel(app, cache, "加锁与读写缓存", "TCP/RESP")
```

## 3. 架构级合规与约束
1. **依赖隔离**: 核心应用服务与 `{{provider}}` 的通信必须在基础设施层实现 防腐层 (Anti-Corruption Layer)，严禁将 `{{provider}}` 的领域模型直接暴露给内部业务逻辑。
2. **读写分离**: 针对 `{{aggregate_root}}` 的高频查询，优先命中 Redis 缓存；写入操作必须双写或利用 Binlog 订阅更新缓存，保证最终一致性。
