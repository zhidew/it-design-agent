# LangGraph 集成设计方案：动态 IT 设计编排器 (Part 1)

## 1. 核心目标
解决当前系统在流程灵活性、状态持久化以及人机协同方面的局限。引入 LangGraph 实现一个“可暂停、可恢复、动态组装”的 IT 设计长程工作流。

## 2. 核心架构：动态路由 (Dynamic Routing)
采用 **Supervisor-Worker** 模式，核心组件包括：

### 2.1 状态定义 (The State)
使用 `TypedDict` 定义全局状态，包含：
- `design_context`: 包含原始需求及已生成的各领域设计文档（Markdown, YAML 等）。
- `task_queue`: 动态任务队列，存储待执行的设计任务。
- `execution_history`: 审计日志，记录每一步的执行细节。
- `human_checkpoint`: 标记当前是否挂起等待人工干预，存储干预所需的元数据。

### 2.2 节点角色 (Nodes)
- **Supervisor Node (调度器)**: 逻辑大脑。分析 `task_queue` 和当前设计完整度，动态决定下一步路由：是执行 Agent、等待人工、还是结束。
- **Worker Nodes (执行器)**: 封装现有的 `*.agent.yaml`。执行特定生成任务，并将结果和建议的后续任务（Sub-tasks）反馈给 Supervisor。
- **Human Node (人工干预)**: 专门处理审批、文档直改和决策冲突。通过 LangGraph 的 `interrupt` (中断) 机制实现流程挂起，配合 Checkpointer 实现状态持久化。

### 2.3 动态逻辑运作
工作流不再是固定的 DAG 图，而是由 Supervisor 根据 `task_queue` 实时驱动的。Agent 执行完成后可以向 `task_queue` 推送新任务（例如：架构映射完成后，根据模块划分动态推送多个 API 设计任务），从而实现真正意义上的按需组装。
