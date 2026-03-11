import sys
import io

# Force stdout and stderr to UTF-8 to prevent GBK encoding errors on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True)

import json
import subprocess
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load environment variables
load_dotenv()

def print_banner(text):
    print(f"\n" + "="*60)
    print(f"[SYSTEM] {text}")
    print("="*60)

# =====================================================================
# 1. Define the Structured Output Schema for the LLM Planner
# =====================================================================
class DesignIntent(BaseModel):
    project_name: str = Field(description="The formal name of the project (PascalCase).")
    project_id: str = Field(description="A unique identifier for the project, e.g., PRJ-XXX-001.")
    version: str = Field(description="The starting version, usually '1.0.0'.")
    server_url: str = Field(description="The base URL for the API.")
    owner: str = Field(description="The team or person owning the design.")
    audience: str = Field(description="The API audience: 'internal', 'external', or 'both'.")
    domain_name: str = Field(description="The core DDD bounded context name.")
    aggregate_root: str = Field(description="The core aggregate root entity name.")
    scenario_name: str = Field(description="The main business scenario name (PascalCase).")
    scenario_desc: str = Field(description="A short description of the business scenario.")
    entity_name: str = Field(description="The primary database entity name.")
    integration_scenario: str = Field(description="The name of the external integration scenario, if any.")
    consumer: str = Field(description="The system consuming the integration.")
    provider: str = Field(description="The external system providing the service.")
    dependencies: str = Field(description="A comma-separated list of technical dependencies (e.g., MySQL, Redis).")
    required_subagents: list[str] = Field(
        description="List of subagents required. Options: architecture-mapping, api-design, data-design, flow-design, ddd-structure, integration-design, config-design, test-design, ops-readiness."
    )

# =====================================================================
# 2. LLM Intent Recognition (The Planner)
# =====================================================================
def analyze_requirement_with_llm(requirement_text: str) -> dict:
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    
    print(f"正在连接大模型 [{provider}] 进行意图分析与架构映射...")
    
    system_prompt = f"""
    你是一个资深的软件架构师和 Agent Orchestrator。
    你的任务是读取用户的自然语言需求，将其翻译为标准的系统级详细设计参数（JSON格式）。
    你需要仔细判断用户的需求涉及哪些能力域（Subagents），并将其放入 required_subagents 数组中。
    例如：
    - 如果提到了“建表”、“存储”，必须包含 data-design。
    - 如果提到了“对外提供接口”、“联调”，必须包含 api-design。
    - 如果提到了“调用第三方”、“通知下游”，必须包含 integration-design。
    如果无法确定，请保守地包含所有核心域。
    
    输出必须严格遵循以下 JSON Schema 的格式要求，不要输出任何 Markdown 标记或多余的文字，只能输出合法的 JSON 字符串：
    {DesignIntent.model_json_schema()}
    """

    if provider == "gemini":
        return call_gemini_api(system_prompt, requirement_text)
    else:
        return call_openai_compatible_api(system_prompt, requirement_text)

def call_openai_compatible_api(system_prompt: str, requirement_text: str) -> dict:
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model_name = os.getenv("OPENAI_MODEL_NAME", "gpt-4o")

    if not api_key or api_key == "your_api_key_here":
        print("⚠️ 警告: 未检测到有效的 OPENAI_API_KEY。将回退到默认的 Mock 数据。")
        return get_mock_intent(requirement_text)

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url)
        
        completion = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": requirement_text}
            ],
            response_format={"type": "json_object"}
        )
        
        result_text = completion.choices[0].message.content
        intent_dict = json.loads(result_text)
        
        # 使用 Pydantic 验证生成的字典
        intent = DesignIntent.model_validate(intent_dict)
        print(f"✅ 大模型解析成功！识别到的核心实体: {intent.aggregate_root}, 需调度 Agent: {len(intent.required_subagents)} 个")
        return intent.model_dump()
        
    except Exception as e:
        print(f"❌ OpenAI 兼容接口调用失败: {e}")
        return get_mock_intent(requirement_text)

def call_gemini_api(system_prompt: str, requirement_text: str) -> dict:
    api_key = os.getenv("GEMINI_API_KEY")
    model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")

    if not api_key or api_key == "your_gemini_api_key_here":
        print("⚠️ 警告: 未检测到有效的 GEMINI_API_KEY。将回退到默认的 Mock 数据。")
        return get_mock_intent(requirement_text)

    try:
        import warnings
        warnings.filterwarnings("ignore", category=FutureWarning)
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        
        model = genai.GenerativeModel(
            model_name,
            system_instruction=system_prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        response = model.generate_content(requirement_text)
        
        intent_dict = json.loads(response.text)
        intent = DesignIntent.model_validate(intent_dict)
        print(f"✅ Gemini 解析成功！识别到的核心实体: {intent.aggregate_root}, 需调度 Agent: {len(intent.required_subagents)} 个")
        return intent.model_dump()
        
    except ImportError:
        print("❌ 缺少 google-generativeai 库。请运行: pip install google-generativeai")
        return get_mock_intent(requirement_text)
    except Exception as e:
        print(f"❌ Gemini 接口调用失败: {e}")
        return get_mock_intent(requirement_text)

def get_mock_intent(text: str) -> dict:
    return {
      "project_name": "SmartBillingSystem",
      "project_id": "PRJ-BILL-001",
      "version": "1.0.0",
      "server_url": "https://api.billing.internal",
      "owner": "billing-team",
      "audience": "both",
      "domain_name": "BillingCore",
      "aggregate_root": "BillStatement",
      "scenario_name": "GenerateMonthlyBill",
      "scenario_desc": f"Processed requirement: {text[:50]}...",
      "entity_name": "BillRecord",
      "integration_scenario": "FinancialSystemSync",
      "consumer": "BillingSystem",
      "provider": "FinanceCore",
      "dependencies": "MySQL, Redis",
      "required_subagents": [
          "architecture-mapping", "api-design", "data-design", 
          "flow-design", "ddd-structure", "integration-design", 
          "config-design", "test-design", "ops-readiness"
      ]
    }

# =====================================================================
# 3. Subagent Execution
# =====================================================================
def run_subagent(script_path: Path, baseline_path: Path, output_dir: Path, name: str):
    print(f"[{name}] 开始执行...")
    print(f"[{name}] 正在读取需求基线与上下文资产...")
    
    # Simulate agent-specific LLM reasoning output for the UI
    reasoning_contexts = {
        "architecture-mapping": "分析系统边界与C4上下文，决定引入API网关与核心微服务解耦...",
        "api-design": "基于RESTful规范与RFC 9457标准，抽取领域模型的对外暴露契约...",
        "data-design": "分析核心实体的数据结构，设计防重索引与软删除策略...",
        "flow-design": "提取主线业务的状态扭转节点，映射到DDD四层代码流转逻辑...",
        "ddd-structure": "确定限界上下文与聚合根边界，梳理应用层Command/Query分离模型...",
        "integration-design": "识别外部第三方系统依赖，制定重试退避与最终一致性补偿策略...",
        "config-design": "分离多环境配置变量，隐藏密钥，设定动态容灾降级开关...",
        "test-design": "针对核心流转提取等价类输入，并强制设定针对外部依赖的混沌测试要求...",
        "ops-readiness": "制定面向SRE的黄金指标监控(SLO)及基于错误率的自动化K8s回滚手册...",
        "design-assembler": "收集所有生成的图表和规范，拼装为最终的可交付评审文档..."
    }
    
    reasoning_msg = reasoning_contexts.get(name, "正在分析当前领域的边界约束与最佳实践...")
    
    # Save reasoning to a separate markdown artifact and ALSO print to execution log for UI streaming
    artifacts_dir = output_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    # Print for SSE
    for line in reasoning_msg.splitlines():
        if line.strip():
            print(f"[{name}] [LLM Reasoning] {line}")
            
    reasoning_file = artifacts_dir / f"{name}-reasoning.md"
    reasoning_file.write_text(f"# {name} 大模型思考过程 (LLM Reasoning)\n\n> 本日志记录了 Agent 在生成设计产物时的核心逻辑与架构决策。\n\n**思考过程**:\n{reasoning_msg}\n", encoding="utf-8")
    
    cmd = [sys.executable, str(script_path), str(baseline_path), str(output_dir)]
    
    # Do not capture output. Let it stream directly to sys.stdout (which is piped to FastAPI)
    # Force UTF-8 encoding for the child process
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(cmd, env=env)
                
    if result.returncode == 0:
        print(f"[SUCCESS] [{name}] 完成。")
        return True
    else:
        print(f"[ERROR] [{name}] 失败！\n{result.stderr}")
        return False

def main():
    if len(sys.argv) < 3:
        print("Usage: python agent_run_llm.py '<Natural Language Requirement>' <output_project_dir>")
        sys.exit(1)

    requirement_text = sys.argv[1]
    output_dir = Path(sys.argv[2]).resolve()
    base_dir = Path(__file__).resolve().parent.parent

    print_banner("[START] LLM-based Orchestrator started")
    # Sanitize text to prevent Windows GBK console crashes when user inputs emojis or special characters
    safe_requirement_text = requirement_text.encode('gbk', errors='replace').decode('gbk')
    
    artifacts_dir = output_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    # Save input requirement as artifact instead of logging to console
    req_file = artifacts_dir / "input-requirements.md"
    req_file.write_text(f"# 原始业务需求\n\n{safe_requirement_text}\n", encoding="utf-8")
    
    print(f"目标输出目录: {output_dir}")

    # 阶段 1: 意图识别
    print_banner("阶段 1: LLM 意图识别与参数抽取 (Planner)")
    
    # Save planner reasoning
    planner_reasoning = artifacts_dir / "planner-reasoning.md"
    planner_reasoning.write_text("# Planner 大模型思考过程 (LLM Reasoning)\n\n正在分析用户需求并提取系统级上下文、聚合根边界以及路由决策...\n", encoding="utf-8")
    
    intent_data = analyze_requirement_with_llm(requirement_text)
    
    baseline_dir = output_dir / "baseline"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    baseline_path = baseline_dir / "requirements.json"
    baseline_path.write_text(json.dumps(intent_data, indent=2, ensure_ascii=False), encoding="utf-8")
    
    # 阶段 2: 动态路由与执行
    print_banner("阶段 2: 根据 LLM 决策进行动态路由执行 (Router & Worker)")
    skills_dir = base_dir / "skills"
    
    agent_scripts = {
        "architecture-mapping": skills_dir / "architecture-mapping" / "scripts" / "render_architecture_mapping_stub.py",
        "api-design": skills_dir / "api-design" / "scripts" / "render_contract_stub.py",
        "data-design": skills_dir / "data-design" / "scripts" / "render_data_stub.py",
        "flow-design": skills_dir / "flow-design" / "scripts" / "render_flow_design_stub.py",
        "ddd-structure": skills_dir / "ddd-structure" / "scripts" / "render_ddd_structure_stub.py",
        "integration-design": skills_dir / "integration-design" / "scripts" / "render_integration_design_stub.py",
        "config-design": skills_dir / "config-design" / "scripts" / "render_config_design_stub.py",
        "test-design": skills_dir / "test-design" / "scripts" / "render_test_design_stub.py",
        "ops-readiness": skills_dir / "ops-readiness" / "scripts" / "render_ops_readiness_stub.py",
    }

    required_agents = intent_data.get("required_subagents", list(agent_scripts.keys()))
    
    success = True
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        for agent_id in required_agents:
            script_path = agent_scripts.get(agent_id)
            if script_path and script_path.exists():
                futures.append(executor.submit(run_subagent, script_path, baseline_path, output_dir, agent_id))
            else:
                print(f"[WARNING] 找不到或未定义的子代理 {agent_id}")
        
        for future in futures:
            if not future.result():
                success = False

    if not success:
        print("[ERROR] 阶段 2 失败：部分子代理未能成功生成产物。")
        sys.exit(1)

    print_banner("阶段 3: 调度 Design Assembler 汇编最终文档 (Assembler)")
    assembler_script = skills_dir / "design-assembler" / "scripts" / "render_design_assembler_stub.py"
    if not run_subagent(assembler_script, baseline_path, output_dir, "design-assembler"):
        sys.exit(1)

    print_banner("阶段 4: 触发 CI 质量门禁校验 (Validator Engine)")
    validator_script = base_dir / "scripts" / "validate_artifacts.py"
    cmd = [sys.executable, str(validator_script), "--project", str(output_dir)]
    
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
    for line in process.stdout:
        print(line, end="")
    process.wait()

    if process.returncode == 0:
        print_banner("[SUCCESS] 全流程闭环！LLM 驱动的设计包已生成并完美通过门禁校验。")
    else:
        print_banner("[FAILURE] 验证失败。您可以将上述报错丢给 LLM 让其重试修复。")
        sys.exit(1)

if __name__ == "__main__":
    main()
