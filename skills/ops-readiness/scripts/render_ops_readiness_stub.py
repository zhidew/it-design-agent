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

    slo_tpl = (TEMPLATE_DIR / "slo.yaml").read_text(encoding="utf-8-sig")
    obs_tpl = (TEMPLATE_DIR / "observability-spec.yaml").read_text(encoding="utf-8-sig")
    runbook_tpl = (TEMPLATE_DIR / "deployment-runbook.md").read_text(encoding="utf-8-sig")

    expected_files = ["slo.yaml", "observability-spec.yaml", "deployment-runbook.md"]

    system_prompt = f"""
    你是一个资深的 Site Reliability Engineer (SRE)。任务是为即将上线的系统设计可观测性指标、SLO 以及发布与回滚手册。
    
    项目背景：
    - 项目名称: {project_name}
    - 核心业务场景: {scenario_name}
    - 外部依赖提供方: {provider}
    - 中间件依赖: {dependencies}

    【核心要求】
    1. 必须生成一份 `slo.yaml`，定义核心场景的 SLI 和 SLO 目标。
    2. 必须生成一份 `observability-spec.yaml`，给出需要的监控指标、分布式追踪的埋点要求（如针对 {provider} 的调用）和关键告警规则。
    3. 必须生成一份 `deployment-runbook.md`，给出发布前置检查、灰度引流步骤，并依据核心错误率和 {provider} 延迟定义量化的回滚触发条件。

    以下是参考模板：
    [slo.yaml 模板]
    {slo_tpl}
    
    [observability-spec.yaml 模板]
    {obs_tpl}
    
    [deployment-runbook.md 模板]
    {runbook_tpl}
    """

    user_prompt = f"需求基线数据：\n{json.dumps(payload, ensure_ascii=False)}"

    try:
        llm_output = generate_with_llm(system_prompt, user_prompt, expected_files)
        
        for line in llm_output.reasoning.splitlines():
            if line.strip():
                print(f"[ops-readiness] [LLM Reasoning] {line}")
        
        reasoning_file = artifacts_dir / "ops-readiness-reasoning.md"
        reasoning_file.write_text(f"# 运维与可观测性设计思考过程\n\n{llm_output.reasoning}\n", encoding="utf-8")
        
        for filename in expected_files:
            content = llm_output.artifacts.get(filename, "")
            (artifacts_dir / filename).write_text(content, encoding="utf-8")

        (evidence_dir / "ops-readiness.json").write_text(json.dumps({"status": "success"}), encoding="utf-8")
        return 0
    except Exception as e:
        print(f"调用大模型失败: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())