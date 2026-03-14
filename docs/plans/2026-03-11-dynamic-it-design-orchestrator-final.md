# 动态 IT 设计编排器最终设计方案 (Dynamic IT Design Orchestrator)

## 1. 概述
本方案旨在基于 LangGraph 实现一个“可感知、可干预、动态扩展”的 IT 详细设计编排引擎。通过引入“任务队列优先”的混合调度模式，解决传统线性编排在处理复杂依赖和突发设计任务时的局限性。

## 2. 核心架构：环形调度与数据驱动 (Circular Dispatching & Data-Driven)

### 2.1 全局状态 (Unified State)
使用 `TypedDict` 定义状态，确保所有节点共享一致的上下文：
- `design_context`: 资产池 (Markdown/YAML/JSON)，包含从《需求分析》输入的 IR 清单、LDM/PDM、数据字典等。
- `task_queue`: 结构化任务列表（包含 `agent_type`, `priority`, `input_keys`, `metadata`）。
- `workflow_phase`: 主干阶段标记 (INIT -> CORE -> MODEL -> LOGIC -> API -> QUALITY -> DONE)。
- `history`: 步骤审计与 Reasoning 日志。

### 2.2 Supervisor 调度策略 (Queue-First & Dependency-Aware)
1. **输入消费 (Input Sync)**: INIT 阶段优先解析上游资产（IR 需求、逻辑/物理数据模型、数据字典、Lookup 清单）。
2. **检查队列**: 只要 `task_queue` 不为空，按优先级弹出任务并路由至对应 Worker。
3. **主干推进 (Phase Gating)**: 队列为空时，根据 `workflow_phase` 注入下一个阶段的任务集。
   - **CORE (核心基座)**: 触发 `architecture-mapping` & `data-design` (并行)。
   - **MODEL (领域建模)**: 触发 `ddd-structure` (依赖 CORE 产出)。
   - **LOGIC (行为设计)**: 触发 `flow-design` & `integration-design` (并行，依赖 MODEL)。
   - **API (契约与配置)**: 触发 `api-design` & `config-design` (并行，依赖 LOGIC & DATA)。
   - **QUALITY (质量准备)**: 触发 `ops-readiness` & `test-design` (并行，依赖 API & LOGIC)。
4. **结束判定**: 主干阶段到达 `DONE` 且队列清空时，触发 `design-assembler` 并进入 `END`。

## 3. Sub-Agent 依赖拓扑与映射

| 阶段 | Agent | 核心输入 (Dependencies) | 核心输出 |
| :--- | :--- | :--- | :--- |
| **CORE** | `data-design` | **LDM/PDM, 数据字典**, IR 清单 | 物理表结构、迁移方案、数据字典校验 |
| **CORE** | `architecture-mapping` | IR 清单 | 系统分层、组件映射、部署拓扑初步 |
| **MODEL** | `ddd-structure` | `data-design`, `arch-mapping` | 领域实体、聚合根、类结构设计 |
| **LOGIC** | `flow-design` | `ddd-structure`, IR 清单 | 业务时序图、状态机、核心算法逻辑 |
| **LOGIC** | `integration-design` | `arch-mapping` | 第三方系统集成方案、AsyncAPI |
| **API** | `api-design` | `flow-design`, **data-design**, `ddd-structure` | OpenAPI 规范、错误码定义 |
| **API** | `config-design` | `arch-mapping` | 系统配置矩阵、Feature Flag 定义 |
| **QUALITY** | `ops-readiness` | `arch-mapping` | SLO 规格、监控指标、观测性设计 |
| **QUALITY** | `test-design` | `api-design`, `flow-design` | 单元/集成测试用例、测试输入数据 |
| **DONE** | `design-assembler` | **ALL ABOVE** | 详细设计总装、全链路可追溯性检查 |

## 4. 组件设计

### 4.1 AgentAdapters (动态适配器)
- **职责**: 封装现有的静态 `*.agent.yaml`。
- **动态注入**: 解析 Agent 产出，识别潜藏的子任务（Sub-tasks）并推入 `task_queue`。
- **上下文提取**: 自动根据依赖关系从 `design_context` 组装上下文。

### 4.2 人机协同 (Human-in-the-loop)
- **挂起逻辑**: 当任务标记为 `pending_human` 或 Supervisor 触发 `interrupt` 时，流程中断并持久化。
- **指令注入**: 通过接口向 State 合并人工决策（Approval/Revision/Re-plan），随后恢复执行。
- **质量门禁**: 在 `DATA` 转 `MODEL`、`LOGIC` 转 `API` 等关键环节强制执行人工确认或自动化校验。

## 5. 运行保障机制

### 5.1 持久化与状态看板 (Kanban Control)
- 使用 `SqliteSaver` 记录每个 Checkpoint。
- UI 层将 `task_queue` 呈现为可视化看板：
    - **To-do**: 依赖已满足、待调度的任务。
    - **Blocked**: 依赖未满足、等待前置 Agent 产出的任务。
    - **Timeline**: 支持回溯历史 Checkpoint 进行设计回滚或分支探索 (Forking)。

### 5.2 验证与自动化校验
系统集成 `validate_artifacts.py` 作为流程中的质量关卡。每个阶段完成后，Supervisor 可选择触发自动化校验，确保生成资产符合 `traceability.schema.json` 规范。
