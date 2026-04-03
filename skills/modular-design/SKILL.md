---
name: modular-design
description: 负责系统上下文、容器划分、模块边界和允许依赖关系设计，为后续专家提供统一的结构约束。
keywords:
  - 模块化设计
  - 系统上下文
  - 容器划分
  - 依赖映射
  - 架构边界
---

# 工作流 (Workflow)

1. **需求分析**：阅读基线需求和既有系统结构，识别系统边界、外部参与方和核心能力。
2. **上下文建模**：确定系统上下文、主要容器以及关键交互关系。
3. **模块拆分**：定义模块归属、责任边界和允许依赖关系。
4. **产物编写**：输出架构说明与模块依赖映射。
5. **校验回读**：检查上下文、容器和模块依赖是否前后一致。
6. **完成门禁**：仅在必需产物和执行证据齐备时结束。

# 输入参数 (Inputs)

## 必需参数 (Required)

| 参数 | 类型 | 说明 |
|------|------|------|
| `requirements` | string/path | 基线需求来源，描述业务范围、角色和关键场景。 |
| `existing_assets` | string/path | 既有系统结构文档、代码目录或历史架构资产。 |
| `output_root` | string/path | 当前项目设计产物根目录。 |

## 可选参数 (Optional)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `constraints` | string/path | - | 组织级架构原则、命名规则或部署边界要求。 |
| `context` | string/path | - | 补充业务背景、组织结构或系统现状说明。 |

# 输出产物 (Output Artifacts)

## 必需产物 (Always Required)

| 产物路径 | 说明 |
|----------|------|
| `artifacts/architecture.md` | 系统上下文、容器划分和模块边界说明。 |
| `artifacts/module-map.json` | 模块清单、责任归属和允许依赖关系。 |

## 运行证据 (Execution Evidence)

| 产物路径 | 说明 |
|----------|------|
| `evidence/modular-design.json` | 记录边界依据、容器划分理由和依赖约束说明。 |

# Tool Usage Notes

## 运行时契约

- 仅使用当前运行时暴露的工具；读结构优先，写产物次之。
- 先确定上下文和容器，再定义模块责任和允许依赖，不要反向从细节拼装架构。
- 写入范围仅限本专家拥有的架构与模块产物。
- 若下游设计需要更多细节，只记录约束与风险，不替下游专家完成详细方案。

## 建议关注的工具

| 工具 | 用途 |
|------|------|
| `list_files` | 浏览现有目录、架构资料和参考资产。 |
| `read_file_chunk` | 阅读需求、历史架构和边界说明。 |
| `extract_structure` | 快速理解代码或文档结构。 |
| `grep_search` | 搜索模块名、服务边界、外部系统和调用关系。 |
| `write_file` | 生成 `architecture.md` 与 `module-map.json`。 |
| `patch_file` | 修补局部边界、命名或依赖关系。 |

# 参考资料 (References)

- 模板参考 `assets/templates/architecture.md` 和 `assets/templates/module-map.json`。
- 可参考 C4 视角组织上下文和容器描述，但最终以项目事实为准。
- 该专家是其他设计专家的重要上游输入，命名和边界要保持稳定。

# 注意事项 (Notes)

- **上下文先行**：必须先明确系统与外部角色/系统的关系，再讨论内部模块。
- **依赖可控**：`module-map.json` 中的依赖必须清晰表达允许关系和边界约束。
- **专家边界**：只负责系统上下文、容器和模块边界，不展开 API、AsyncAPI、DDL、配置矩阵、运维或测试细节。
- **依赖协同**：后续专家会直接消费本专家产物；若发现风险，只记录约束、输入和影响，不抢做下游设计。

# ReAct 执行策略 (ReAct Strategy)

1. **研究 (Research)**：收集系统目标、外部参与方、部署单元和已有结构事实。
2. **建模 (Model)**：定义上下文、容器和模块边界。
3. **编写 (Write)**：先产出 `architecture.md`，再生成 `module-map.json`。
4. **校验 (Verify)**：回读产物，确认上下文、容器与依赖映射一致。
5. **修补 (Patch)**：仅对边界或依赖做局部修正，不凭空新增系统范围。
6. **完成 (Finalize)**：确认产物和 `evidence/modular-design.json` 满足要求后结束。

## ReAct 规则

1. 默认每次只输出一个下一步动作；只有在收集独立、低风险的读取证据时，才可用 `actions` 并行返回最多 2 个只读动作。
2. 仅当 `architecture.md`、`module-map.json` 和 `evidence/modular-design.json` 完成后才允许 `done=true`。
3. `tool_input` 必须是明确的 JSON，避免模糊的目录、文件或搜索范围。
4. 每一步都要写清 `evidence_note`，说明正在确认的边界事实或结构决策。
5. 不得在缺乏证据时擅自定义下游契约、表结构或运维方案。

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

1. `architecture.md` 必须清楚说明系统上下文、容器角色和模块边界。
2. `module-map.json` 必须给出稳定的模块清单和允许依赖关系。
3. 所有边界和命名都应能回溯到需求、现有结构或明确约束。
4. 内容要为下游专家提供可复用的结构输入，而不是零散观点集合。

## 生成内容

- **architecture.md**：描述系统上下文、容器划分、关键交互和边界原则。
- **module-map.json**：列出模块名称、职责归属和允许依赖关系。
- **modular-design.json**：沉淀边界依据、风险、命名选择和校验结论。