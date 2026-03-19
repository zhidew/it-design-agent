---
name: design-assembler
description: 汇编所有结构化设计产物，生成最终的详细设计文档及需求追踪矩阵。
---

# 工作流 (Workflow)

1. **资产读取**：读取所有子代理生成的设计产物（artifacts/）和需求基线。
2. **内容汇编**：整合架构、数据、API、流程、DDD 等设计内容。
3. **文档生成**：生成最终详细设计文档 `release/detailed-design.md`。
4. **追踪矩阵**：生成需求追踪矩阵 `release/traceability.json`。
5. **评审清单**：生成评审检查清单 `release/review-checklist.md`。
6. **证据沉淀**：记录汇编依据到 `evidence/design-assembler.json`。

# 输入参数 (Inputs)

## 必需参数 (Required)

| 参数 | 类型 | 说明 |
|------|------|------|
| `requirements` | string/path | 业务需求说明文件路径 |
| `existing_assets` | string/path | 所有子代理产出的设计产物目录路径 |
| `output_root` | string/path | 根输出目录路径 |

## 可选参数 (Optional)

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `context` | string/path | - | 上下文信息文件路径 |

# 输出产物 (Output Artifacts)

## 必需产物 (Always Required)

| 产物路径 | 说明 |
|----------|------|
| `release/detailed-design.md` | 最终详细设计文档（整合所有设计内容）|
| `release/traceability.json` | 需求追踪矩阵（需求→设计→实现的映射）|
| `release/review-checklist.md` | 设计评审检查清单 |
| `evidence/design-assembler.json` | 汇编依据和证据 |

# 工具集 (Tools)

## 文件系统工具

| 工具名称 | 说明 |
|----------|------|
| `list_files` | 列出目录下的文件 |
| `read_file_chunk` | 读取文件片段 |
| `grep_search` | 搜索文件内容 |
| `extract_structure` | 提取文件结构 |
| `write_file` | 写入设计产物 |
| `patch_file` | 修补已有文件 |

# 参考资料 (References)

- 模板使用 `assets/templates/detailed-design.md`、`assets/templates/traceability.json` 和 `assets/templates/review-checklist.md`。
- 必须遵循项目全局架构规范。

# 注意事项 (Notes)

- **完整性**：必须包含所有子代理产物的关键内容。
- **一致性**：确保需求、架构、数据、API、流程等设计的术语和概念一致。
- **可追溯性**：traceability.json 必须建立需求到设计的完整映射关系。
