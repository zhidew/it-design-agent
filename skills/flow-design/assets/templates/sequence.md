# 时序图: {{scenario_name}}

## 1. 业务场景说明
- **场景描述**: {{scenario_desc}}
- **触发条件**: (描述触发该流程的用户行为或定时任务)
- **前置依赖**: (描述执行该流程必须满足的条件，如：用户已登录)

## 2. 参与者与后端分层 (Actors & DDD Layers)
| 参与者/层级 | 类型 | 职责说明 |
| :--- | :--- | :--- |
| User / Client | Actor | 发起操作的用户或客户端应用 |
| API Gateway | System | 负责统一鉴权、限流与路由分发 |
| **Interfaces** | Layer | 后端接入层，处理 HTTP/RPC 协议，数据校验与 DTO 转换 |
| **Application** | Layer | 后端应用层，负责用例编排、事务控制与权限校验 |
| **Domain** | Layer | 后端领域层，执行纯粹的核心业务逻辑和状态扭转 |
| **Infrastructure** | Layer | 后端基础设施层，负责数据库持久化、缓存及外部 API 调用 |

## 3. 详细交互时序 (Mermaid)
本图详细展示了请求在后端 DDD 四层架构中的流转过程。

```mermaid
sequenceDiagram
    autonumber
    
    actor C as Client
    participant GW as API Gateway
    
    box rgb(240, 248, 255) "Backend Service: {{project_name}}"
        participant I as Interfaces<br/>(Controller)
        participant A as Application<br/>({{aggregate_root}}AppService)
        participant D as Domain<br/>(Class: {{aggregate_root}})
        participant Infra as Infrastructure<br/>({{aggregate_root}}Repository)
    end
    
    participant DB as Database
    participant Ext as External System

    C->>GW: 1. 发起业务请求
    activate GW
    GW->>GW: 2. Token 鉴权与限流
    GW->>I: 3. 转发请求 (如: POST /api/v1/resource)
    activate I
    
    I->>I: 4. 参数校验与 DTO 转换
    I->>A: 5. 发起应用层命令 (Command)
    activate A
    
    A->>Infra: 6. 开启本地事务
    
    A->>Infra: 7. 查询前置数据 (调用 {{aggregate_root}}Repository.findById)
    activate Infra
    Infra->>DB: 8. 执行 SQL Select
    DB-->>Infra: 返回数据行
    Infra-->>A: 返回 {{aggregate_root}} 实体对象
    deactivate Infra

    A->>D: 9. 调用领域对象执行核心逻辑
    activate D
    D->>D: 10. {{aggregate_root}}.process() 状态扭转与规则校验
    D-->>A: 11. 返回执行结果及领域事件
    deactivate D

    A->>Infra: 12. 调用防腐层 (ACL) 集成外部系统
    activate Infra
    Infra->>Ext: 13. 发起 HTTP/gRPC 请求
    Ext-->>Infra: 返回外部系统响应
    Infra-->>A: 返回集成结果
    deactivate Infra

    A->>Infra: 14. 持久化数据 (调用 {{aggregate_root}}Repository.save)
    activate Infra
    Infra->>DB: 15. 执行 SQL Update/Insert
    DB-->>Infra: 写入成功
    Infra-->>A: 持久化完成
    deactivate Infra
    
    A->>Infra: 16. 提交事务并发布领域事件 (Message Queue)
    
    A-->>I: 17. 返回应用层执行结果
    deactivate A
    
    I->>I: 18. 装配 Response DTO
    I-->>GW: 19. 接口响应 (200 OK)
    deactivate I
    
    GW-->>C: 20. 返回最终结果给客户端
    deactivate GW
```

## 4. 关键设计约束
- **事务边界**: 事务必须在 `Application` 层开启和提交，严禁跨外部系统调用（如步骤 12）时长时间持有本地数据库事务。
- **依赖倒置**: `Application` 层只依赖 `Repository` 的接口定义（属于 Domain 层），真实的持久化实现由 `Infrastructure` 层在运行时注入。
- **异常处理**: 任何 `Domain` 层抛出的业务异常（如余额不足、状态不对），由 `Interfaces` 层的统一异常拦截器转换为规范的 RFC 9457 格式返回。
