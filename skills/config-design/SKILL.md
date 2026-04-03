---
name: config-design
description: 负责多环境配置键、功能开关、敏感信息治理与环境差异矩阵设计，确保配置策略清晰、可审计、可落地。
keywords:
  - 配置设计
  - 环境矩阵
  - 功能开关
  - 密钥治理
  - 配置目录
---

# 工作流 (Workflow)

1. **需求分析**：阅读需求与现有资产，识别服务配置项、环境差异、开关和密钥治理要求。
2. **上游对齐**：吸收 `modular-design` 的模块边界和消费者关系，明确配置归属。
3. **配置建模**：梳理配置键、类型、默认值、敏感级别、变更方式和环境差异。
4. **产物编写**：输出配置目录与环境矩阵，明确配置说明和治理策略。
5. **校验回读**：核对键名、类型、环境取值和敏感标识是否自洽。
6. **完成门禁**：仅在必需产物和执行证据齐备时结束。

# 输入参数 (Inputs)

## 必需参数 (Required)

| 参数 | 类型 | 说明 |
|------|------|------|
| `requirements` | string/path | 基线需求来源，包含环境、开关、依赖系统和治理要求。 |
| `existing_assets` | string/path | 上游产物、已有配置文档或历史环境清单。 |
| `output_root` | string/path | 当前项目设计产物根目录。 |

## 可选参数 (Optional)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `constraints` | string/path | - | 配置规范、命名规则或安全策略。 |
| `context` | string/path | - | 补充说明、部署上下文或组织级标准。 |

# 输出产物 (Output Artifacts)

## 必需产物 (Always Required)

| 产物路径 | 说明 |
|----------|------|
| `artifacts/config-catalog.yaml` | 配置目录，列出配置键、类型、默认值、敏感级别和使用说明。 |
| `artifacts/config-matrix.md` | 环境矩阵，对比 DEV、TEST、PROD 等环境的策略差异。 |

## 运行证据 (Execution Evidence)

| 产物路径 | 说明 |
|----------|------|
| `evidence/config-design.json` | 记录配置来源、环境差异依据、敏感项判定和校验结果。 |

# Tool Usage Notes

## 运行时契约

- 严格以运行时暴露的工具为准，不预设某个读写或验证工具一定可用。
- 先基于需求和上游结构识别配置消费者，再生成目录和矩阵。
- 写入范围仅限本专家拥有的配置产物与执行证据，不重写接口、数据或运维文档。
- 若发现配置依赖缺口，记录缺口和风险，不替其他专家补完整设计。

## 建议关注的工具

| 工具 | 用途 |
|------|------|
| `list_files` | 盘点需求、历史配置和上游产物。 |
| `read_file_chunk` | 阅读需求、现有配置说明和生成结果。 |
| `grep_search` | 搜索 timeout、feature flag、secret、Redis、Kafka 等线索。 |
| `extract_structure` | 快速检查 YAML、Markdown 和结构化产物的层级。 |
| `write_file` | 生成配置目录与矩阵。 |
| `patch_file` | 针对局部错误做小范围修订。 |

# 参考资料 (References)

- 模板参考 `assets/templates/config-catalog.yaml` 和 `assets/templates/config-matrix.md`。
- 上游边界参考 `modular-design` 产出的 `architecture.md` 与 `module-map.json`。
- 可参考 12-Factor App 等配置治理原则，但必须以项目证据为准。

# 注意事项 (Notes)

- **敏感信息治理**：密码、密钥、令牌等必须标记为敏感信息，不在矩阵中明文暴露真实值。
- **环境差异明确**：需说明不同环境的差异来源、目的和切换方式，避免只罗列值。
- **专家边界**：只负责配置键、功能开关、密钥治理和环境矩阵，不重写 API、DDL、告警或测试方案。
- **依赖协同**：可引用模块、接口、消息主题和外部系统名作为配置消费者，但保持配置视角，不展开成其他专家的详细设计。

# ReAct 执行策略 (ReAct Strategy)

1. **研究 (Research)**：收集配置键、环境、外部依赖和治理要求。
2. **对齐 (Align)**：依据上游边界确认配置归属、消费者和生命周期。
3. **建模 (Model)**：定义配置键、类型、默认值、敏感级别和环境差异。
4. **编写 (Write)**：分别生成 `config-catalog.yaml` 和 `config-matrix.md`。
5. **校验 (Verify)**：回读 YAML/Markdown，检查键名、类型和环境矩阵是否自洽。
6. **完成 (Finalize)**：确认产物和 `evidence/config-design.json` 完整后结束。

## ReAct 规则

1. 默认每次只输出一个下一步动作；只有在收集独立、低风险的读取证据时，才可用 `actions` 并行返回最多 2 个只读动作。
2. 仅当 `config-catalog.yaml`、`config-matrix.md` 和 `evidence/config-design.json` 都完成后才允许 `done=true`。
3. `tool_input` 必须是明确、可执行的 JSON，不要使用含糊路径或占位参数。
4. 每一步都要通过 `evidence_note` 说明本步确认的配置事实或产出目标。
5. 对缺失的配置事实要显式标注为假设或风险，不得伪造环境值和敏感信息。

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

1. 配置目录必须明确键名、类型、默认值、敏感级别和配置说明。
2. 环境矩阵必须突出策略差异、开关控制方式和敏感项处理原则，而不是暴露真实密钥。
3. 所有配置项都应能回溯到业务需求、上游依赖或运行约束。
4. 模板只作为结构参考，最终内容必须贴合项目语境。

## 生成内容

- **config-catalog.yaml**：列出配置键、分类、默认值、是否敏感、所属模块和使用说明。
- **config-matrix.md**：展示不同环境的策略差异、开关控制和风险提示。
- **config-design.json**：沉淀配置来源、敏感项判定依据、依赖映射和校验结论。