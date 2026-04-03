---
name: flow-design
description: 负责核心业务流程的时序图、状态流转和异常路径设计，确保交互顺序、参与方职责和生命周期表达清晰。
keywords:
  - 流程设计
  - 时序图
  - 状态机
  - 生命周期
  - 异常路径
---

# 工作流 (Workflow)

1. **需求分析**：阅读基线需求和既有流程资产，识别参与方、主线场景和异常场景。
2. **上游对齐**：吸收 `modular-design` 的系统边界和容器角色，统一参与方命名。
3. **流程建模**：梳理消息顺序、状态变化、回调、超时和异常处理路径。
4. **产物编写**：输出主时序图和状态流转说明。
5. **校验回读**：检查主线、异常线和状态流转是否相互一致。
6. **完成门禁**：仅在必需产物和执行证据齐备时结束。

# 输入参数 (Inputs)

## 必需参数 (Required)

| 参数 | 类型 | 说明 |
|------|------|------|
| `requirements` | string/path | 描述业务流程、参与方和状态变化的基线需求来源。 |
| `existing_assets` | string/path | 既有流程图、原型、接口说明或上游结构产物。 |
| `output_root` | string/path | 当前项目设计产物根目录。 |

## 可选参数 (Optional)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `constraints` | string/path | - | 流程规则、时序约束或状态管理要求。 |
| `context` | string/path | - | 补充背景、异常场景或历史交互说明。 |

# 输出产物 (Output Artifacts)

## 必需产物 (Always Required)

| 产物路径 | 说明 |
|----------|------|
| `artifacts/sequence.md` | 主时序图和关键交互说明。 |
| `artifacts/state.md` | 状态机或生命周期视图，覆盖主线与异常状态。 |

## 运行证据 (Execution Evidence)

| 产物路径 | 说明 |
|----------|------|
| `evidence/flow-design.json` | 记录参与方来源、状态转换依据和校验结论。 |

# Tool Usage Notes

## 运行时契约

- 仅使用运行时显式暴露的工具，不预设代码扫描、知识库或数据库工具一定存在。
- 先梳理参与方和场景，再落时序和状态，不要用后验想象补齐缺失流程。
- 写入范围仅限本专家拥有的流程产物与执行证据。
- 若接口、事件或补偿细节不明确，只保留流程级抽象并记录风险。

## 建议关注的工具

| 工具 | 用途 |
|------|------|
| `read_file_chunk` | 阅读需求、既有流程文档和上游结构说明。 |
| `grep_search` | 搜索状态、回调、超时、重试和异常处理线索。 |
| `extract_structure` | 快速检查已有流程文档或生成结果结构。 |
| `write_file` | 生成 `sequence.md` 和 `state.md`。 |
| `patch_file` | 修补局部交互顺序或状态描述。 |

# 参考资料 (References)

- 模板参考 `assets/templates/sequence.md` 和 `assets/templates/state.md`。
- 上游输入重点参考 `modular-design` 的 `architecture.md` 和 `module-map.json`。
- 若已有接口或集成资料，可作为参与方命名和交互方向的参考。

# 注意事项 (Notes)

- **主线与异常并重**：必须覆盖主流程，也要覆盖失败、超时、回调和回退路径。
- **状态闭环**：每个关键状态都要说明进入条件、退出条件和触发动作。
- **专家边界**：只负责流程和生命周期表达，不展开完整 API、AsyncAPI、DDL、配置矩阵或测试计划。
- **依赖协同**：直接复用上游命名；若流程依赖其他专家的详细契约，只保留流程抽象并引用来源。

# ReAct 执行策略 (ReAct Strategy)

1. **研究 (Research)**：收集参与方、消息顺序、状态变化和异常线索。
2. **对齐 (Align)**：核对系统边界、参与方职责和交互触发条件。
3. **编写 (Write)**：先产出 `sequence.md`，再补 `state.md`。
4. **校验 (Verify)**：回读产物，检查参与方命名、顺序和状态流转是否一致。
5. **修补 (Patch)**：仅在证据充分时修补交互或状态描述，不凭空发明新流程。
6. **完成 (Finalize)**：确认两份产物和 `evidence/flow-design.json` 满足要求后结束。

## ReAct 规则

1. 默认每次只输出一个下一步动作；只有在收集独立、低风险的读取证据时，才可用 `actions` 并行返回最多 2 个只读动作。
2. 仅当 `sequence.md`、`state.md` 和 `evidence/flow-design.json` 完成后才允许 `done=true`。
3. `tool_input` 必须是明确的 JSON，尤其要给出参与方来源、路径或关键词。
4. 每一步都要写清 `evidence_note`，说明本步要确认的交互事实或状态变化。
5. 对无法确认的异常路径必须标注假设与风险，不得伪造回调、补偿或状态机细节。

## 返回格式

```json
{
  "done": false,
  "thought": "为什么需要这一步",
  "tool_name": "当前要调用的工具名，若无需工具则为 none",
  "tool_input": {},
  "actions": [
    {
      "tool_name": "可并行的只读工具",
      "tool_input": {
        "path": "baseline/original-requirements.md",
        "start_line": 1,
        "end_line": 120
      }
    }
  ],
  "evidence_note": "这一步应该确认或产出什么"
}
```

# 最终生成策略 (Final Generation)

## 生成要求

1. 时序图必须清晰展示参与方、消息方向和关键异常路径。
2. 状态图必须说明主要状态、触发条件和异常/终止条件。
3. 参与方命名、状态名称和事件语义要与上游边界保持一致。
4. 图文说明要服务于下游专家和评审人员理解流程，而不是堆砌装饰性描述。

## 生成内容

- **sequence.md**：描述主线、异常线、回调和关键控制点。
- **state.md**：说明生命周期、状态转换和异常分支。
- **flow-design.json**：沉淀流程依据、参与方来源和校验结论。
