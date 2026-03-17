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
    
    project_name = payload.get("project_name", "CoreService")
    domain_name = payload.get("domain_name", "Domain")
    aggregate_root = payload.get("aggregate_root", "Entity")

    artifacts_dir = output_root / "artifacts"
    logs_dir = output_root / "logs"
    evidence_dir = output_root / "evidence"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    class_template = (TEMPLATE_DIR / "class.md").read_text(encoding="utf-8-sig")
    ddd_template = (TEMPLATE_DIR / "ddd-structure.md").read_text(encoding="utf-8-sig")

    class_file_name = f"class-{domain_name.lower()}.md"
    expected_files = [class_file_name, "ddd-structure.md"]

    system_prompt = f"""
    你是一个资深的后端架构师。任务是进行领域驱动设计(DDD)，划分领域边界并提取核心聚合根、实体和值对象。
    
    项目背景：
    - 项目名称: {project_name}
    - 限界上下文: {domain_name}
    - 核心聚合根: {aggregate_root}

    【核心要求】
    1. 必须生成一份 `{class_file_name}`。使用 Mermaid 的 classDiagram 语法绘制核心实体的类图及其关联关系。
    2. 必须生成一份 `ddd-structure.md`，定义工程代码内部的应用层、领域层接口设计（如 Commands/Events）。
    3. 严禁暴露具体的技术框架（如 MyBatis/Spring）。必须使用真实的业务名词。

    以下是参考模板：
    [class.md 模板]
    {class_template}
    
    [ddd-structure.md 模板]
    {ddd_template}
    """

    user_prompt = f"需求基线数据：\n{json.dumps(payload, ensure_ascii=False)}"

    try:
        llm_output = generate_with_llm(system_prompt, user_prompt, expected_files)
        
        for line in llm_output.reasoning.splitlines():
            if line.strip():
                print(f"[ddd-structure] [LLM Reasoning] {line}")
        
        reasoning_file = logs_dir / "ddd-structure-reasoning.md"
        reasoning_file.write_text(f"# DDD 领域建模思考过程\n\n{llm_output.reasoning}\n", encoding="utf-8")
        
        for filename in expected_files:
            content = llm_output.artifacts.get(filename, "")
            (artifacts_dir / filename).write_text(content, encoding="utf-8")

        (evidence_dir / "ddd-structure.json").write_text(json.dumps({"status": "success"}), encoding="utf-8")
        return 0
    except Exception as e:
        print(f"调用大模型失败: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
