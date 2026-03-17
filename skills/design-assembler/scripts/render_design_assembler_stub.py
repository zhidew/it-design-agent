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
    version = payload.get("version", "1.0.0")

    artifacts_dir = output_root / "artifacts"
    logs_dir = output_root / "logs"
    release_dir = output_root / "release"
    evidence_dir = output_root / "evidence"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    release_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    doc_tpl = (TEMPLATE_DIR / "detailed-design.md").read_text(encoding="utf-8-sig")
    trace_tpl = (TEMPLATE_DIR / "traceability.json").read_text(encoding="utf-8-sig")
    review_tpl = (TEMPLATE_DIR / "review-checklist.md").read_text(encoding="utf-8-sig")

    expected_files = ["detailed-design.md", "traceability.json", "review-checklist.md"]

    system_prompt = f"""
    你是一个负责最终评审和组装的项目级架构师。任务是撰写系统详细设计的执行摘要，并生成可追踪的需求矩阵与评审清单。
    
    项目背景：
    - 项目名称: {project_name}
    - 交付版本: {version}

    【核心要求】
    1. 必须生成一份 `detailed-design.md`，对整个架构设计包做高层摘要。
    2. 必须生成一份 `traceability.json`，将输入的业务场景映射到各个 artifacts 产物上。
    3. 必须生成一份 `review-checklist.md`，制定架构师和QA团队在开会评审时的打勾清单。

    以下是参考模板：
    [detailed-design.md 模板]
    {doc_tpl}
    
    [traceability.json 模板]
    {trace_tpl}
    
    [review-checklist.md 模板]
    {review_tpl}
    """

    user_prompt = f"需求基线数据：\n{json.dumps(payload, ensure_ascii=False)}"

    try:
        llm_output = generate_with_llm(system_prompt, user_prompt, expected_files)
        
        for line in llm_output.reasoning.splitlines():
            if line.strip():
                print(f"[design-assembler] [LLM Reasoning] {line}")
        
        reasoning_file = logs_dir / "design-assembler-reasoning.md"
        reasoning_file.write_text(f"# 设计组装大模型思考过程\n\n{llm_output.reasoning}\n", encoding="utf-8")
        
        for filename in expected_files:
            content = llm_output.artifacts.get(filename, "")
            (release_dir / filename).write_text(content, encoding="utf-8")

        (evidence_dir / "design-assembler.json").write_text(json.dumps({"status": "success"}), encoding="utf-8")
        return 0
    except Exception as e:
        print(f"调用大模型失败: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
