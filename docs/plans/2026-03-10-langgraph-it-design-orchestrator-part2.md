# LangGraph 集成设计方案：组件细节与系统集成 (Part 2)

## 1. 组件职责划分 (Layered Architecture)

为了实现“动态”和“持久化”，系统将分为三层管理 LangGraph 逻辑：

### 1.1 WorkflowGraph (图形层)
- **职责**: 定义节点（Supervisor, Worker Nodes, Human Node）及其之间的条件边（Conditional Edges）。
- **持久化**: 集成 `langgraph.checkpoint.sqlite.SqliteSaver`，通过 `thread_id` 实现状态的断点续传和多版本回溯。
- **并发控制**: 管理图的执行生命周期，处理 `interrupt`（中断）信号。

### 1.2 AgentAdapters (增强型适配器层)
- **职责**: 充当现有 `*.agent.yaml` 与 LangGraph State 之间的桥梁。
- **Context Mapping**: 从全局 State 中提取 Agent 所需的最小上下文（如：将架构文档转换为 API 设计的输入）。
- **Result Interpretation (结果解析)**: 扫描 Agent 产出的 Markdown/YAML，根据特定规则（如模块列表、冲突标记）动态更新 State 中的 `task_queue`。

### 1.3 WorkflowSupervisor (调度层)
- **职责**: 作为 StateGraph 的核心调度节点，分析 `task_queue`。
- **调度逻辑**: 
    - 如果 `task_queue` 有待办任务，路由至对应的 Worker Node。
    - 如果遇到重大里程碑或 Agent 请求决策，路由至 Human Node。
    - 如果任务全部完成，路由至 `END`。

## 2. 人机协同机制 (Human-in-the-loop)

### 2.1 挂起与恢复 (Interrupt & Resume)
- **中断**: 当流程流向 Human Node 或 Supervisor 触发审批请求时，利用 LangGraph 的 `interrupt` 机制挂起执行，状态自动固化至 SQLite。
- **恢复 API**: 后端提供 `/workflow/{thread_id}/resume` 接口，接收人工输入（如修改后的 Markdown 或 审批指令），合并入 State 后恢复流转。

### 2.2 状态同步
- **State API**: 提供 `/workflow/{thread_id}/state` 接口，允许 `admin-ui` 获取当前执行路径、已产出文档快照及 `task_queue` 里的待办列表。

## 3. 结构化任务队列 (Structured TaskQueue)
`task_queue` 演进为结构化对象列表，支持优先级和上下文绑定：
- `agent_type`: 目标 Agent 类型（如 `api-design`）。
- `context_keys`: 指定该任务依赖的 State 键值。
- `priority`: 调度优先级。
- `metadata`: 存储任务触发来源或特定指令。
