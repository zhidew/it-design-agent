---
name: validator
description: 验证所有设计产物的完整性和一致性，生成验证报告。
---

# 工作流 (Workflow)

1. **产物扫描**：扫描所有设计产物目录结构（artifacts/、release/）。
2. **必需产物检查**：验证必需产物是否存在（architecture.md, schema.sql, api-design.md 等）。
3. **格式规范验证**：验证各产物格式是否符合规范（Markdown、SQL、JSON、YAML）。
4. **一致性检查**：检查模块名称、API 路径、数据库表与领域模型的一致性。
5. **追踪矩阵检查**：验证需求追踪矩阵的完整性。
6. **报告生成**：生成验证报告，列出通过项和待改进项。
7. **证据沉淀**：记录验证证据到 `evidence/validator.json`。

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
| `validation-report.md` | 验证报告，包含各产物的检查结果（通过/警告/失败）|
| `evidence/validator.json` | 验证证据记录 |

# 验证检查项 (Validation Checks)

## 必需产物检查

| 产物名称 | 检查项 |
|----------|--------|
| `architecture.md` | 架构设计文档是否存在且格式正确 |
| `schema.sql` | 数据库设计是否存在且 SQL 语法有效 |
| `api-design.md` | API 设计文档是否存在 |
| `ddd-structure.md` | DDD 结构设计是否存在 |
| `detailed-design.md` | 详细设计文档是否存在 |

## 格式规范检查

| 格式类型 | 检查项 |
|----------|--------|
| Markdown | 文件格式正确，包含必要的标题和章节 |
| SQL | 语法有效，符合规范 |
| JSON | 文件可解析，格式正确 |
| YAML | 文件格式正确，缩进规范 |

## 一致性检查

| 检查项 | 说明 |
|--------|------|
| 模块名称 | 在各文档中保持一致 |
| API 路径 | 与模块映射匹配 |
| 数据库表 | 与领域模型对应 |
| 术语使用 | 统一且符合业务语境 |

# 工具集 (Tools)

## 文件系统工具

| 工具名称 | 说明 |
|----------|------|
| `list_files` | 列出目录下的文件 |
| `read_file_chunk` | 读取文件片段 |
| `grep_search` | 搜索文件内容 |
| `extract_structure` | 提取文件结构 |

## 数据处理工具

| 工具名称 | 说明 |
|----------|------|
| `run_command` | 执行验证命令（如 SQL 语法检查、JSON/YAML 解析）|

# 注意事项 (Notes)

- **非阻塞式验证**：验证失败不应阻止流程，而是记录问题供人工审核。
- **优先级分级**：关键产物缺失标记为失败，次要产物缺失仅作警告。
- **报告清晰性**：输出清晰的验证报告，便于开发者快速定位问题。
- **证据记录**：所有验证结果必须记录到 evidence/validator.json 供追溯。
