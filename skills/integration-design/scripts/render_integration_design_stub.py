from __future__ import annotations

import json
import sys
import io
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True)

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.append(str(BASE_DIR / "scripts"))
from llm_generator import generate_with_llm

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
TEMPLATE_DIR = SKILL_DIR / "assets" / "templates"

def main() -> int:
    if len(sys.argv) != 3:
        return 1

    input_path = Path(sys.argv[1]).resolve()
    output_root = Path(sys.argv[2]).resolve()
    payload = json.loads(input_path.read_text(encoding="utf-8-sig"))
    
    project_name = payload.get("project_name", "CoreSystem")
    integration_scenario = payload.get("integration_scenario", "ExternalIntegration")
    scenario_desc = payload.get("scenario_desc", "")
    consumer = payload.get("consumer", "Consumer")
    provider = payload.get("provider", "Provider")

    artifacts_dir = output_root / "artifacts"
    evidence_dir = output_root / "evidence"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    integration_tpl = (TEMPLATE_DIR / "integration.md").read_text(encoding="utf-8-sig")
    asyncapi_tpl = (TEMPLATE_DIR / "asyncapi.yaml").read_text(encoding="utf-8-sig")

    integration_file = f"integration-{provider.replace(' ', '').lower()}.md"
    expected_files = [integration_file, "asyncapi.yaml"]

    system_prompt = f"""
    你是一个系统集成架构师。任务是设计跨服务或跨系统的集成协议与容灾补偿策略。
    
    项目背景：
    - 项目名称: {project_name}
    - 集成场景: {integration_scenario} ({scenario_desc})
    - 调用方 (Consumer): {consumer}
    - 提供方 (Provider): {provider}

    【核心要求】
    1. 必须生成一份 `{integration_file}`，设计幂等、重试与最终一致性补偿策略。
    2. 必须生成一份 `asyncapi.yaml`，符合 AsyncAPI 3.0 规范，定义相关的领域事件格式。
    3. 内容必须基于具体的业务场景名词。

    以下是参考模板：
    [integration.md 模板]
    {integration_tpl}
    
    [asyncapi.yaml 模板]
    {asyncapi_tpl}
    """

    user_prompt = f"需求基线数据：\n{json.dumps(payload, ensure_ascii=False)}"

    try:
        llm_output = generate_with_llm(system_prompt, user_prompt, expected_files)
        
        for line in llm_output.reasoning.splitlines():
            if line.strip():
                print(f"[integration-design] [LLM Reasoning] {line}")
        
        reasoning_file = artifacts_dir / "integration-design-reasoning.md"
        reasoning_file.write_text(f"# 集成设计大模型思考过程\n\n{llm_output.reasoning}\n", encoding="utf-8")
        
        for filename in expected_files:
            content = llm_output.artifacts.get(filename, "")
            (artifacts_dir / filename).write_text(content, encoding="utf-8")

        (evidence_dir / "integration-design.json").write_text(json.dumps({"status": "success"}), encoding="utf-8")
        return 0
    except Exception as e:
        print(f"调用大模型失败: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())