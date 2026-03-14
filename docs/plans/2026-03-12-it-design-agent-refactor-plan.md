# IT Design Agent 重构与偏差修正计划 (2026-03-12)

## 1. 现状分析与偏差评估

经过对 `it-design-agent` 代码库与 `docs/plans` 设计稿的对比分析，发现当前实现存在重大偏差：

### 1.1 架构偏差 (Architecture Deviation)
- **设计稿要求**: 基于 **LangGraph** 构建“可感知、可干预、动态扩展”的编排引擎，包含 `Supervisor`、结构化 `task_queue` 和 `SqliteSaver` 状态持久化。
- **当前现状**: 仅为简单的 `subprocess` + `ThreadPoolExecutor` 并行运行脚本 (`agent_run_llm.py`)。这是一个静态的管道，而非动态图，无法处理复杂的依赖流转。

### 1.2 任务管理偏差 (Task Management Deviation)
- **设计稿要求**: 核心是动态的 `task_queue`，Worker 节点执行完后可根据产物动态推送新任务。
- **当前现状**: 意图识别（Planner）一次性生成所有 Agent 列表后并行执行，节点间没有反馈回路。

### 1.3 ".worktrees" 实现偏差
- **用户反馈**: 提到 `.worktrees` 实现偏离。
- **分析**: 代码中缺失 `git worktree` 逻辑，仅在 `.gitignore` 中存在占位符。目前的“版本管理”只是简单的文件夹复制（`projects/`），无法实现设计稿要求的“分支探索 (Forking)”和“状态回滚”。
- **目标**: 升级为真正的 **Git Worktree** 隔离机制，每个设计版本对应一个独立的工作树，支持版本间的强隔离与 Diff。

### 1.4 前端体验问题 (UI/UX Confusion)
- **现状**: `ProjectDetail.tsx` (40KB+) 逻辑极其臃肿。
- **核心痛点**: 前端目前通过**正则表达式解析日志**（`rebuildHistoryState`）来“猜”后端的执行状态，这导致 UI 显示不准确、滞后，且让用户感到逻辑晦涩难懂。

---

## 2. 核心任务分解

### 第一阶段：LangGraph 核心引擎重构 (Backend)
- **2.1 定义全局状态 (State)**: 实现 `TypedDict`，包含 `task_queue` (结构化任务)、`design_context` (资产池) 和 `workflow_phase`。
- **2.2 实现 Supervisor 调度器**: 编写根据 `task_queue` 优先级弹出任务并动态路由至 Worker 的逻辑。
- **2.3 Worker 适配器改造**: 将现有的渲染脚本封装为 LangGraph 节点，使其能读写全局 State。
- **2.4 持久化层**: 集成 `langgraph.checkpoint.sqlite.SqliteSaver`，记录每个设计步骤的 Checkpoints。

### 第二阶段：Git Worktree 版本控制 (Infrastructure)
- **2.5 实现 Worktree 管理器**: 编写 Python 类，在创建新版本时执行 `git worktree add .worktrees/{id}_{version}`。
- **2.6 Forking 机制**: 实现从特定 Checkpoint 恢复并创建新 Git 分支的逻辑，开启“设计分支”探索。

### 第三阶段：人机协同 (Human-in-the-loop)
- **2.7 挂起与恢复**: 在关键节点插入 `interrupt` 中断，配合前端实现“设计审批/人工修改”后再继续。
- **2.8 指令注入 API**: 提供接口允许人工动态向 `task_queue` 插入新任务。

### 第四阶段：前端 UI 彻底重构 (Frontend)
- **2.9 状态驱动升级**: 废弃日志解析黑客手段，改为直接订阅 LangGraph 的状态快照（State API）。
- **2.10 可视化看板 (Kanban)**: 实现设计稿要求的 `task_queue` 可视化组件（To-do, Running, Blocked）。
- **2.11 组件拆分**: 将 `ProjectDetail.tsx` 拆分为 `TaskKanban`, `ArtifactViewer`, `Timeline` 等独立组件，降低复杂度。

---

## 3. 验证与交付标准
- **功能**: LangGraph 能够根据任务优先级正确触发串行/并行 Agent。
- **隔离**: 修改 `.worktrees/` 下的文件不影响主分支。
- **UI**: 看板状态能实时反映后端 `task_queue` 的真实变动。
