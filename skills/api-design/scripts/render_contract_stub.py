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
    
    project_name = payload.get("project_name", "Unknown Project")
    audience = payload.get("audience", "both")
    scenario_desc = payload.get("scenario_desc", "")

    artifacts_dir = output_root / "artifacts"
    evidence_dir = output_root / "evidence"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    internal_tpl = (TEMPLATE_DIR / "api-internal.yaml").read_text(encoding="utf-8-sig")
    public_tpl = (TEMPLATE_DIR / "api-public.yaml").read_text(encoding="utf-8-sig")
    errors_tpl = (TEMPLATE_DIR / "errors-rfc9457.json").read_text(encoding="utf-8-sig")

    expected_files = ["api-design.md", "errors-rfc9457.json"]
    if audience in ["internal", "both"]:
        expected_files.append("api-internal.yaml")
    if audience in ["external", "both"]:
        expected_files.append("api-public.yaml")

    system_prompt = f"""
    你是一个资深的API架构师。任务是根据项目需求设计符合 OpenAPI 3.1 规范的 API 契约和符合 RFC 9457 的错误码。
    
    项目背景：
    - 项目名称: {project_name}
    - 业务需求: {scenario_desc}
    - 目标受众: {audience}

    【核心要求】
    1. 生成必需的 OpenAPI yaml 文件。内部接口包含详细字段，外部接口注重安全与脱敏。
    2. 必须生成 `errors-rfc9457.json`，列出所有可能的业务错误码。
    3. 必须生成一份 `api-design.md` 作为人类可读的接口摘要文档。

    以下是参考模板：
    [api-internal.yaml]
    {internal_tpl}
    
    [api-public.yaml]
    {public_tpl}
    
    [errors-rfc9457.json]
    {errors_tpl}
    """

    user_prompt = f"需求基线数据：\n{json.dumps(payload, ensure_ascii=False)}"

    try:
        llm_output = generate_with_llm(system_prompt, user_prompt, expected_files)
        
        for line in llm_output.reasoning.splitlines():
            if line.strip():
                print(f"[api-design] [LLM Reasoning] {line}")
        
        reasoning_file = artifacts_dir / "api-design-reasoning.md"
        reasoning_file.write_text(f"# API 设计大模型思考过程\n\n{llm_output.reasoning}\n", encoding="utf-8")
        
        for filename in expected_files:
            content = llm_output.artifacts.get(filename, "")
            (artifacts_dir / filename).write_text(content, encoding="utf-8")

        (evidence_dir / "api-design.json").write_text(json.dumps({"status": "success"}), encoding="utf-8")
        return 0
    except Exception as e:
        print(f"调用大模型失败: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())