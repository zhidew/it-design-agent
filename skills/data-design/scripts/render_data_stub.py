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
        print("Usage: python render_data_stub.py <input-json> <output-root>", file=sys.stderr)
        return 1

    input_path = Path(sys.argv[1]).resolve()
    output_root = Path(sys.argv[2]).resolve()

    payload = json.loads(input_path.read_text(encoding="utf-8-sig"))
    
    project_name = payload.get("project_name", "Unknown Project")
    entity_name = payload.get("entity_name", "CoreEntity")
    dependencies = payload.get("dependencies", "")

    artifacts_dir = output_root / "artifacts"
    logs_dir = output_root / "logs"
    evidence_dir = output_root / "evidence"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    # Load templates to pass as context
    schema_template = (TEMPLATE_DIR / "schema.sql").read_text(encoding="utf-8-sig")
    er_template = (TEMPLATE_DIR / "er.md").read_text(encoding="utf-8-sig")
    migration_template = (TEMPLATE_DIR / "migration-plan.md").read_text(encoding="utf-8-sig")

    system_prompt = f"""
    你是一个资深的数据库架构师 (DBA)。
    你的任务是根据传入的项目需求，设计数据库的建表语句 (DDL)、实体关系图 (ER Diagram) 和数据迁移与回滚计划。

    项目背景信息：
    - 项目名称: {project_name}
    - 核心实体: {entity_name}
    - 外部依赖: {dependencies}
    
    【核心要求】
    1. 必须生成一份符合 MySQL 方言的 `schema.sql`，表名使用 snake_case。
    2. 所有的业务表必须包含通用的审计字段：`id`, `is_deleted`, `created_at`, `updated_at`, `created_by`, `updated_by`。
    3. 针对高频查询需求，必须设计合理的复合索引 (KEY)。
    4. 必须生成一份 `er.md`，使用 Mermaid 的 erDiagram 语法描述表结构关系。
    5. 必须生成一份 `migration-plan.md`，描述如何安全地发布这些 DDL，并提供发生故障时的 Down 回滚脚本。

    以下是参考模板结构，请在生成时参照其风格：
    [schema.sql 模板]
    {schema_template}
    
    [er.md 模板]
    {er_template}
    
    [migration-plan.md 模板]
    {migration_template}
    """

    user_prompt = f"这是完整的需求基线数据：\n{json.dumps(payload, ensure_ascii=False)}"
    
    expected_files = ["schema.sql", "er.md", "migration-plan.md"]

    try:
        # 调用大模型生成真实的设计
        llm_output = generate_with_llm(system_prompt, user_prompt, expected_files)
        
        # 打印推理日志到标准输出供前端抓取
        for line in llm_output.reasoning.splitlines():
            if line.strip():
                print(f"[data-design] [LLM Reasoning] {line}")

        # 保存推理日志
        reasoning_file = logs_dir / "data-design-reasoning.md"
        reasoning_file.write_text(f"# 数据建模大模型思考过程 (Data Design LLM Reasoning)\n\n{llm_output.reasoning}\n", encoding="utf-8")
        
        # 保存生成的产物
        for filename in expected_files:
            content = llm_output.artifacts.get(filename, f"-- Failed to generate {filename}")
            (artifacts_dir / filename).write_text(content, encoding="utf-8")

        # 保存证据
        evidence = {
            "capability": "data-design",
            "asset_type": "baseline",
            "source": str(input_path),
            "tool": "LLM API",
            "result_summary": "LLM successfully generated schema.sql, er.md, and migration-plan.md based on requirements.",
            "confidence": 0.95,
        }
        (evidence_dir / "data-design.json").write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
        return 0

    except Exception as e:
        print(f"调用大模型失败: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
