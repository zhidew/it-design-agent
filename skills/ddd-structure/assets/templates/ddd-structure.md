# DDD 领域结构设计: {{domain_name}}

> **所属微服务**: {{project_name}}
> **核心限界上下文**: {{domain_name}} Context

本文档基于 DDD 四层架构规范，提炼了当前业务需求下所需的**核心类和对象**，用于直接指导工程代码的包结构与类定义。

---

## 1. 领域层 (Domain Layer)
最核心的业务逻辑封装，不依赖任何外部技术框架。

### 1.1 聚合根 (Aggregate Root)
- **`{{aggregate_root}}`**
  - **职责**: 维护自身状态的一致性边界，是领域内其他实体的入口。
  - **状态字段**: (例如 `status`, `createdAt`, `version`)
  - **核心行为**: (例如 `create()`, `process()`, `cancel()`)

### 1.2 领域实体 (Entities)
*(属于 `{{aggregate_root}}` 内部的从属实体，具有独立生命周期但对外不可见)*
- **`{{aggregate_root}}Item`** (示例，请根据实际需求替换)
  - **职责**: 描述聚合内部的明细项。
  - **核心属性**: (如 `itemId`, `quantity`, `price`)

### 1.3 值对象 (Value Objects)
*(无唯一标识，通过属性组合来判断相等性的不可变对象)*
- **`Money`** (示例)
  - 属性: `amount` (Decimal), `currency` (String)
- **`Address`** (示例)
  - 属性: `province`, `city`, `detail`

### 1.4 仓储接口 (Repository Interfaces)
- **`{{aggregate_root}}Repository`**
  - 方法: `save({{aggregate_root}})`, `findById(String)`

---

## 2. 应用层 (Application Layer)
负责业务用例的编排、事务管理和权限校验。

### 2.1 应用服务 (AppService)
- **`{{aggregate_root}}AppService`**
  - 负责接收外部的 Command/Query，调用领域层执行逻辑并提交事务。

### 2.2 命令与查询模型 (CQS)
- **命令 (Commands)** - 改变系统状态的操作：
  - `Create{{aggregate_root}}Command`: 包含初始化聚合根所需的所有输入参数。
  - `Process{{aggregate_root}}Command`: 驱动聚合根状态流转的操作指令。
- **查询 (Queries)** - 不改变状态的读取操作：
  - `Get{{aggregate_root}}DetailQuery`: 获取领域对象详情。

---

## 3. 领域事件 (Domain Events)
用于解耦系统内部模块，或通过基础设施层发布给外部系统。

- **`{{aggregate_root}}CreatedEvent`**
  - **触发时机**: `{{aggregate_root}}` 被成功创建并持久化后。
  - **包含数据**: 实体 ID、创建时间、关键业务属性。
- **`{{aggregate_root}}StatusChangedEvent`**
  - **触发时机**: 实体的核心状态发生流转（如进入 `COMPLETED` 或 `FAILED`）时。

---

## 4. 基础设施层 (Infrastructure Layer) 映射要求
- **持久化实现**: 必须提供 `{{aggregate_root}}RepositoryImpl`，负责将领域对象转换为 PO(Persistent Object) 并通过 ORM (如 MyBatis/JPA) 写入数据库。
- **防腐层实现**: 若调用了外部系统 (如 `{{provider}}`)，需在此层实现对应的 Gateway 适配器。

---

## 5. 代码包结构树 (Code Package Structure Tree)

以下为依据上述领域模型推导出的推荐工程目录结构，采用**按业务模块/聚合分包 (Package by Feature)** 模式，实现高内聚，用于指导实际的代码落地：

```text
src/main/java/com/example/{{domain_name_lower}}
└── {{aggregate_root_lower}}/             # 核心聚合根/业务模块
    ├── application/            # 2. 应用层 (Application Layer)
    │   ├── service/            # 应用服务编排 (e.g. {{aggregate_root}}AppService)
    │   ├── command/            # CQRS: 命令模型
    │   ├── query/              # CQRS: 查询模型
    │   └── dto/                # 外部通信数据传输对象
    ├── domain/                 # 1. 领域层 (Domain Layer)
    │   ├── entity/             # 领域实体
    │   ├── valobj/             # 值对象
    │   ├── repository/         # 仓储接口定义 (e.g. {{aggregate_root}}Repository)
    │   ├── service/            # 领域服务
    │   ├── event/              # 领域事件定义
    │   └── {{aggregate_root}}.java # 聚合根
    ├── infrastructure/         # 4. 基础设施层 (Infrastructure Layer)
    │   ├── repository/         # 仓储具体实现与数据持久化
    │   │   ├── impl/           # 仓储接口的实现 (e.g. {{aggregate_root}}RepositoryImpl)
    │   │   └── mapper/         # ORM 映射与数据访问对象
    │   ├── gateway/            # 外部服务网关/防腐层实现
    │   └── messaging/          # 消息发布与消费实现
    └── interfaces/             # 用户接口层 (User Interfaces Layer)
        ├── controller/         # REST API / RPC 端点入口 (e.g. {{aggregate_root}}Controller)
        └── assembler/          # DTO 与 领域对象的装配/转换器
```
