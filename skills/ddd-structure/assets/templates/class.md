# 领域类图设计: {{domain_name}}

## 1. 领域模型概览
- **限界上下文 (Bounded Context)**: {{domain_name}} Context
- **聚合根 (Aggregate Root)**: `{{aggregate_root}}`

## 2. 领域类图 (Mermaid)
```mermaid
classDiagram
    %% 聚合根
    class {{aggregate_root}} {
        <<AggregateRoot>>
        -String id
        -String status
        -Date createdAt
        +create() void
        +process() void
    }

    %% 实体
    class OrderItem {
        <<Entity>>
        -String skuId
        -Integer quantity
        -Decimal price
        +calculateTotal() Decimal
    }

    %% 值对象
    class Address {
        <<ValueObject>>
        -String province
        -String city
        -String detail
    }

    %% 关联关系
    {{aggregate_root}} "1" *-- "many" OrderItem : contains
    {{aggregate_root}} "1" o-- "1" Address : ships_to
```

## 3. 核心领域规则
1. **不变性 (Invariants)**: `{{aggregate_root}}` 的状态必须由其自身的方法（如 `process()`）进行修改，严禁外部直接 set 属性。
2. **工厂/装配**: 复杂聚合的创建应通过 `{{aggregate_root}}Factory` 统一完成，确保创建时的实体一致性。
3. **仓储 (Repository)**: 仅针对 `{{aggregate_root}}` 提供 Repository 接口，`OrderItem` 的持久化伴随聚合根一并完成。
