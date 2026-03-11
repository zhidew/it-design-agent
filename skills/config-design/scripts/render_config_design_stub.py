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
    provider = payload.get("provider", "ExternalProvider")
    dependencies = payload.get("dependencies", "MySQL, Redis")
    scenario_name = payload.get("scenario_name", "CoreFeature")

    artifacts_dir = output_root / "artifacts"
    evidence_dir = output_root / "evidence"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    catalog_tpl = (TEMPLATE_DIR / "config-catalog.yaml").read_text(encoding="utf-8-sig")
    matrix_tpl = (TEMPLATE_DIR / "config-matrix.md").read_text(encoding="utf-8-sig")

    expected_files = ["config-catalog.yaml", "config-matrix.md"]

    system_prompt = f"""
    你是一个负责微服务配置治理的架构师。任务是设计多环境配置矩阵与动态降级开关。
    
    项目背景：
    - 项目名称: {project_name}
    - 外部依赖提供方: {provider}
    - 中间件依赖: {dependencies}
    - 核心业务开关名: {scenario_name}

    【核心要求】
    1. 必须生成一份 `config-catalog.yaml`，枚举所有必需的外部化配置（如 DB URL、外部 API URL、业务开关）。
    2. 必须生成一份 `config-matrix.md`，给出 DEV、TEST、PROD 各个环境的取值策略，并强调密码必须通过 KMS 等工具管理，禁止明文。

    以下是参考模板：
    [config-catalog.yaml 模板]
    {catalog_tpl}
    
    [config-matrix.md 模板]
    {matrix_tpl}
    """

    user_prompt = f"需求基线数据：\n{json.dumps(payload, ensure_ascii=False)}"

    try:
        llm_output = generate_with_llm(system_prompt, user_prompt, expected_files)
        
        for line in llm_output.reasoning.splitlines():
            if line.strip():
                print(f"[config-design] [LLM Reasoning] {line}")
        
        reasoning_file = artifacts_dir / "config-design-reasoning.md"
        reasoning_file.write_text(f"# 配置设计大模型思考过程\n\n{llm_output.reasoning}\n", encoding="utf-8")
        
        for filename in expected_files:
            content = llm_output.artifacts.get(filename, "")
            (artifacts_dir / filename).write_text(content, encoding="utf-8")

        (evidence_dir / "config-design.json").write_text(json.dumps({"status": "success"}), encoding="utf-8")
        return 0
    except Exception as e:
        print(f"调用大模型失败: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())