---
name: design-assembler
description: 汇编所有结构化设计产物，生成最终的详细设计文档及需求追踪矩阵。
---

# 工作流 (Workflow)
1. 读取输入需求与资产。
2. 调用模板渲染脚本生成默认设计产物。
3. 校验生成产物的结构与规范。
4. 记录证据到 evidence 目录。

# 输入参数 (Inputs)
- `requirements`: 业务需求说明。
- `existing_assets`: 相关存量资产。
- `output_root`: 根输出目录。

# 输出产物 (Output Artifacts)
- `release/detailed-design.md`
- `release/traceability.json`
- `release/review-checklist.md`
- `evidence/design-assembler.json`

# 工具集 (Tools)
- `python:design-system/skills/design-assembler/scripts/render_design_assembler_stub.py`

# 注意事项 (Notes)
- 必须遵循项目全局架构规范。
