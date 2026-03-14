import os
from pathlib import Path

agents = {
    "flow-design": {
        "name": "流程与状态设计子代理",
        "desc": "基于业务需求生成系统交互时序图与状态机，覆盖主链路与异常链路。",
        "outputs": ["artifacts/sequence-example.md", "artifacts/state-example.md", "evidence/flow-design.json"]
    },
    "ddd-structure": {
        "name": "领域与类图设计子代理",
        "desc": "进行领域建模和结构设计，产出类图、DDD 结构说明及上下文映射。",
        "outputs": ["artifacts/class-example.md", "artifacts/ddd-structure.md", "artifacts/context-map.md", "evidence/ddd-structure.json"]
    },
    "ops-readiness": {
        "name": "可观测与运行就绪子代理",
        "desc": "设计 SLO、告警规则、监控指标及发布回滚的运行手册。",
        "outputs": ["artifacts/slo.yaml", "artifacts/observability-spec.yaml", "artifacts/deployment-runbook.md", "evidence/ops-readiness.json"]
    },
    "design-assembler": {
        "name": "设计产物汇编子代理",
        "desc": "汇编所有结构化设计产物，生成最终的详细设计文档及需求追踪矩阵。",
        "outputs": ["release/detailed-design.md", "release/traceability.json", "release/review-checklist.md", "evidence/design-assembler.json"]
    },
    "architecture-mapping": {
        "name": "架构映射子代理",
        "desc": "根据代码和架构规范，输出模块边界与依赖关系映射。",
        "outputs": ["artifacts/architecture.md", "artifacts/module-map.json", "evidence/architecture-mapping.json"]
    },
    "integration-design": {
        "name": "集成设计子代理",
        "desc": "设计跨服务和外部系统的集成协议，包括异步事件契约(AsyncAPI)与补偿策略。",
        "outputs": ["artifacts/integration-example.md", "artifacts/asyncapi.yaml", "evidence/integration-design.json"]
    },
    "config-design": {
        "name": "配置设计子代理",
        "desc": "规划多环境配置、开关策略和密钥规范。",
        "outputs": ["artifacts/config-catalog.yaml", "artifacts/config-matrix.md", "evidence/config-design.json"]
    },
    "test-design": {
        "name": "测试可设计性子代理",
        "desc": "提取测试输入条件，生成覆盖率映射矩阵。",
        "outputs": ["artifacts/test-inputs.md", "artifacts/coverage-map.json", "evidence/test-design.json"]
    }
}

base_dir = Path("design-system")
agents_dir = base_dir / "agents"
skills_dir = base_dir / "skills"

agents_dir.mkdir(parents=True, exist_ok=True)
skills_dir.mkdir(parents=True, exist_ok=True)

def generate_agent_yaml(cap, data):
    content = f"""name: {data['name']}
capability: {cap}
description: {data['desc']}
version: 0.1.0
skills:
  - {cap}
inputs:
  required:
    - requirements
    - existing_assets
    - output_root
  optional:
    - context
outputs:
  required:
"""
    for out in data['outputs']:
        content += f"    - {out}\n"
    content += f"""  schema_locked: true
tools:
  allowed:
    - filesystem
    - python:design-system/skills/{cap}/scripts/render_{cap.replace('-', '_')}_stub.py
policies:
  asset_baseline_required: true
  evidence_required: true
  output_must_be_structured: true
  descriptions_prefer_chinese: true
error_handling:
  on_missing_required_input: fail
  on_validation_failure: fail
"""
    (agents_dir / f"{cap}.agent.yaml").write_text(content, encoding='utf-8')

def generate_skill_md(cap, data):
    content = f"""---
name: {cap}
description: {data['desc']}
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
"""
    for out in data['outputs']:
        content += f"- `{out}`\n"
    content += f"""
# 工具集 (Tools)
- `python:design-system/skills/{cap}/scripts/render_{cap.replace('-', '_')}_stub.py`

# 注意事项 (Notes)
- 必须遵循项目全局架构规范。
"""
    skill_root = skills_dir / cap
    skill_root.mkdir(parents=True, exist_ok=True)
    (skill_root / "SKILL.md").write_text(content, encoding='utf-8')
    
def generate_script(cap, data):
    script_name = f"render_{cap.replace('-', '_')}_stub.py"
    script_dir = skills_dir / cap / "scripts"
    script_dir.mkdir(parents=True, exist_ok=True)
    
    content = f"""import sys
import json
from pathlib import Path

def main():
    if len(sys.argv) != 3:
        return 1
    input_path = Path(sys.argv[1])
    output_root = Path(sys.argv[2])
    
    files_to_create = {data['outputs']}
    
    for f in files_to_create:
        out_file = output_root / f
        out_file.parent.mkdir(parents=True, exist_ok=True)
        if str(out_file).endswith('.json'):
            if 'evidence' in str(out_file):
                out_file.write_text(json.dumps({{"capability": "{cap}", "status": "stub rendered"}}), encoding='utf-8')
            else:
                out_file.write_text('{{}}', encoding='utf-8')
        else:
            out_file.write_text(f"Stub for {{f}}\\n", encoding='utf-8')

    return 0

if __name__ == "__main__":
    sys.exit(main())
"""
    (script_dir / script_name).write_text(content, encoding='utf-8')

for cap, data in agents.items():
    generate_agent_yaml(cap, data)
    generate_skill_md(cap, data)
    generate_script(cap, data)

print("Scaffolding complete.")
