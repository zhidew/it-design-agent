from __future__ import annotations

import json
import sys
import io
from pathlib import Path

# Force stdout to UTF-8 for Windows compatibility
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True)

# Add the base scripts directory to sys.path so we can import llm_generator
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.append(str(BASE_DIR / "scripts"))

from llm_generator import generate_with_llm

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
TEMPLATE_DIR = SKILL_DIR / "assets" / "templates"

def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python render_flow_design_stub.py <input-json> <output-root>", file=sys.stderr)
        return 1

    input_path = Path(sys.argv[1]).resolve()
    output_root = Path(sys.argv[2]).resolve()

    payload = json.loads(input_path.read_text(encoding="utf-8-sig"))
    
    scenario_name = payload.get("scenario_name", "OrderCreation")
    scenario_desc = payload.get("scenario_desc", "User initiates an order creation process.")
    entity_name = payload.get("entity_name", "Order")
    aggregate_root = payload.get("aggregate_root", entity_name)
    project_name = payload.get("project_name", "CoreSystem")

    artifacts_dir = output_root / "artifacts"
    evidence_dir = output_root / "evidence"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    sequence_template = (TEMPLATE_DIR / "sequence.md").read_text(encoding="utf-8-sig")
    state_template = (TEMPLATE_DIR / "state.md").read_text(encoding="utf-8-sig")

    seq_file_name = f"sequence-{scenario_name.lower()}.md"
    state_file_name = f"state-{entity_name.lower()}.md"

    system_prompt = f"""
    你是一个资深的软件架构师。
    你的任务是根据传入的项目需求，设计业务的流程时序图 (Sequence Diagram) 和核心实体的状态机图 (State Diagram)。
    
    项目背景信息：
    - 项目名称: {project_name}
    - 核心业务场景: {scenario_name} ({scenario_desc})
    - 核心实体/聚合根: {aggregate_root}

    【核心要求】
    1. 必须生成一份 `{seq_file_name}`。时序图需要使用 Mermaid 语法，严格遵循 DDD 四层架构（Interfaces, Application, Domain, Infrastructure），展示请求从网关到后端的流转过程，以及事务边界。
    2. 必须生成一份 `{state_file_name}`。状态机需要使用 Mermaid 的 stateDiagram 语法，定义实体的状态扭转规则，并说明并发防重策略。
    3. 生成的图表和文档必须基于业务场景，不能是空洞的模板。如果是外卖派单系统，就必须出现“骑手”、“派单中”、“已送达”等具体业务名词。

    以下是参考模板结构（你必须保留其 Markdown 标题和 Mermaid 结构，但内容要替换为真实的业务逻辑）：
    [sequence.md 参考模板]
    {sequence_template}
    
    [state.md 参考模板]
    {state_template}
    """

    user_prompt = f"这是完整的需求基线数据：\n{json.dumps(payload, ensure_ascii=False)}"
    
    expected_files = [seq_file_name, state_file_name]

    try:
        llm_output = generate_with_llm(system_prompt, user_prompt, expected_files)
        
        # 打印推理日志到标准输出供前端抓取
        for line in llm_output.reasoning.splitlines():
            if line.strip():
                print(f"[flow-design] [LLM Reasoning] {line}")
        
        reasoning_file = artifacts_dir / "flow-design-reasoning.md"
        reasoning_file.write_text(f"# 流程与状态大模型思考过程 (Flow Design LLM Reasoning)\n\n{llm_output.reasoning}\n", encoding="utf-8")
        
        for filename in expected_files:
            content = llm_output.artifacts.get(filename, f"-- Failed to generate {filename}")
            (artifacts_dir / filename).write_text(content, encoding="utf-8")

        evidence = {
            "capability": "flow-design",
            "asset_type": "baseline",
            "source": str(input_path),
            "tool": "LLM API",
            "result_summary": f"LLM successfully generated {seq_file_name} and {state_file_name}.",
            "confidence": 0.95,
        }
        (evidence_dir / "flow-design.json").write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
        return 0

    except Exception as e:
        print(f"调用大模型失败: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
