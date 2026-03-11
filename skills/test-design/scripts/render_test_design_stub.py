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
    scenario_name = payload.get("scenario_name", "Scenario")
    entity_name = payload.get("entity_name", "Entity")
    provider = payload.get("provider", "ExternalProvider")
    dependencies = payload.get("dependencies", "MySQL, Redis")

    artifacts_dir = output_root / "artifacts"
    evidence_dir = output_root / "evidence"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    test_inputs_tpl = (TEMPLATE_DIR / "test-inputs.md").read_text(encoding="utf-8-sig")
    coverage_map_tpl = (TEMPLATE_DIR / "coverage-map.json").read_text(encoding="utf-8-sig")

    expected_files = ["test-inputs.md", "coverage-map.json"]

    system_prompt = f"""
    你是一个资深的质量保证架构师 (QA Architect)。任务是提取系统的测试边界条件、异常测试场景并定义覆盖率要求。
    
    项目背景：
    - 核心业务场景: {scenario_name}
    - 核心实体: {entity_name}
    - 外部依赖提供方: {provider}
    - 中间件依赖: {dependencies}

    【核心要求】
    1. 必须生成一份 `test-inputs.md`。使用黑盒测试思维（等价类、边界值）列出业务关键字段的测试输入。必须针对 {provider} 和中间件设计集成异常与混沌测试用例，并针对并发高频接口设计并发测试用例。
    2. 必须生成一份 `coverage-map.json`，确保核心设计要素（API、状态机流转等）都被要求写入自动化测试用例中。

    以下是参考模板：
    [test-inputs.md 模板]
    {test_inputs_tpl}
    
    [coverage-map.json 模板]
    {coverage_map_tpl}
    """

    user_prompt = f"需求基线数据：\n{json.dumps(payload, ensure_ascii=False)}"

    try:
        llm_output = generate_with_llm(system_prompt, user_prompt, expected_files)
        
        for line in llm_output.reasoning.splitlines():
            if line.strip():
                print(f"[test-design] [LLM Reasoning] {line}")
        
        reasoning_file = artifacts_dir / "test-design-reasoning.md"
        reasoning_file.write_text(f"# 测试设计大模型思考过程\n\n{llm_output.reasoning}\n", encoding="utf-8")
        
        for filename in expected_files:
            content = llm_output.artifacts.get(filename, "")
            (artifacts_dir / filename).write_text(content, encoding="utf-8")

        (evidence_dir / "test-design.json").write_text(json.dumps({"status": "success"}), encoding="utf-8")
        return 0
    except Exception as e:
        print(f"调用大模型失败: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())