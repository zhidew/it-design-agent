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
    provider = payload.get("provider", "ExternalSystem")
    consumer = payload.get("consumer", "ConsumerSystem")
    domain_name = payload.get("domain_name", "Domain")
    aggregate_root = payload.get("aggregate_root", "Entity")

    artifacts_dir = output_root / "artifacts"
    logs_dir = output_root / "logs"
    evidence_dir = output_root / "evidence"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    arch_template = (TEMPLATE_DIR / "architecture.md").read_text(encoding="utf-8-sig")
    module_template = (TEMPLATE_DIR / "module-map.json").read_text(encoding="utf-8-sig")

    system_prompt = f"""
    你是一个资深的软件架构师。
    你的任务是根据传入的项目需求，设计系统的高层架构视图 (C4 Model) 和模块依赖关系。
    
    项目背景信息：
    - 项目名称: {project_name}
    - 核心限界上下文: {domain_name}
    - 核心实体: {aggregate_root}
    - 外部依赖系统 (Provider): {provider}
    - 消费方系统 (Consumer): {consumer}

    【核心要求】
    1. 必须生成一份 `architecture.md`。使用 Mermaid C4Context 和 C4Container 语法，准确描绘当前系统与外部系统的交互。
    2. 必须生成一份 `module-map.json`，描述工程代码内部的依赖限制（如 domain 不能依赖 infrastructure）。
    3. 生成的架构图必须使用实际的业务名词。

    以下是参考模板：
    [architecture.md 模板]
    {arch_template}
    
    [module-map.json 模板]
    {module_template}
    """

    user_prompt = f"这是完整的需求基线数据：\n{json.dumps(payload, ensure_ascii=False)}"
    expected_files = ["architecture.md", "module-map.json"]

    try:
        llm_output = generate_with_llm(system_prompt, user_prompt, expected_files)
        
        for line in llm_output.reasoning.splitlines():
            if line.strip():
                print(f"[architecture-mapping] [LLM Reasoning] {line}")
        
        reasoning_file = logs_dir / "architecture-mapping-reasoning.md"
        reasoning_file.write_text(f"# 架构映射大模型思考过程\n\n{llm_output.reasoning}\n", encoding="utf-8")
        
        for filename in expected_files:
            content = llm_output.artifacts.get(filename, "")
            (artifacts_dir / filename).write_text(content, encoding="utf-8")

        evidence = {
            "capability": "architecture-mapping",
            "status": "success"
        }
        (evidence_dir / "architecture-mapping.json").write_text(json.dumps(evidence), encoding="utf-8")
        return 0
    except Exception as e:
        print(f"调用大模型失败: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
