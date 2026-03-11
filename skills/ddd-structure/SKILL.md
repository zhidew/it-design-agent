---
name: ddd-structure
description: 进行领域建模和结构设计，产出类图、DDD 结构说明及上下文映射。
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

# 输出契约 (Output Contract)
- `artifacts/class-example.md`
- `artifacts/ddd-structure.md`
- `artifacts/context-map.md`
- `evidence/ddd-structure.json`

# 工具集 (Tools)
- `python:design-system/skills/ddd-structure/scripts/render_ddd_structure_stub.py`

# 注意事项 (Notes)
- 必须遵循项目全局架构规范。
