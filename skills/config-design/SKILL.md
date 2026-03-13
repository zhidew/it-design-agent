---
name: config-design
description: 规划多环境配置、开关策略和密钥规范。
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
- `artifacts/config-catalog.yaml`
- `artifacts/config-matrix.md`
- `evidence/config-design.json`

# 工具集 (Tools)
- `python:design-system/skills/config-design/scripts/render_config_design_stub.py`

# 注意事项 (Notes)
- 必须遵循项目全局架构规范。
