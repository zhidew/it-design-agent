---
name: flow-design
description: 基于业务需求生成系统交互时序图与状态机，覆盖主链路与异常链路。
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
- `artifacts/sequence-example.md`
- `artifacts/state-example.md`
- `evidence/flow-design.json`

# 工具集 (Tools)
- `python:design-system/skills/flow-design/scripts/render_flow_design_stub.py`

# 注意事项 (Notes)
- 必须遵循项目全局架构规范。
