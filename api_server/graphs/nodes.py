import os
import json
import asyncio
import sys
from pathlib import Path
from typing import Dict, Any, List
from .state import DesignState, Task
from scripts.llm_generator import generate_with_llm, SubagentOutput

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# --- Supervisor Node (保持不变) ---
def supervisor(state: DesignState) -> Dict[str, Any]:
    queue = state.get("task_queue", [])
    phase = state.get("workflow_phase", "INIT")
    
    running_tasks = [t for t in queue if t["status"] == "running"]
    if running_tasks: return {"next": "END"}

    todo_tasks = [t for t in queue if t["status"] == "todo"]
    if todo_tasks:
        for task in sorted(todo_tasks, key=lambda x: x["priority"], reverse=True):
            deps = task.get("dependencies", [])
            deps_met = True
            for d_id in deps:
                dep_task = next((t for t in queue if t["id"] == d_id), None)
                if not dep_task or dep_task["status"] != "success":
                    deps_met = False
                    break
            if deps_met:
                return {"next": task["agent_type"], "current_task_id": task["id"]}
    
    phases = ["INIT", "ANALYSIS", "ARCHITECTURE", "MODELING", "INTERFACE", "READINESS", "DELIVERY", "DONE"]
    try:
        current_idx = phases.index(phase)
        if current_idx < len(phases) - 1:
            return {"next": "supervisor_advance", "workflow_phase": phases[current_idx + 1]}
        return {"next": "END"}
    except ValueError:
        return {"next": "END"}

# --- Worker Adapter Node Factory (保持不变) ---
def create_worker_node(agent_type: str):
    async def worker_node(state: DesignState) -> Dict[str, Any]:
        project_id = state["project_id"]
        version = state["version"]
        project_path = BASE_DIR / "projects" / project_id / version
        baseline_path = project_path / "baseline" / "requirements.json"
        logs_dir = project_path / "logs"
        
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

        script_name_map = {
            "api-design": "render_contract_stub.py",
            "architecture-mapping": "render_architecture_mapping_stub.py",
            "config-design": "render_config_design_stub.py",
            "data-design": "render_data_stub.py",
            "ddd-structure": "render_ddd_structure_stub.py",
            "flow-design": "render_flow_design_stub.py",
            "integration-design": "render_integration_design_stub.py",
            "ops-readiness": "render_ops_readiness_stub.py",
            "test-design": "render_test_design_stub.py",
            "design-assembler": "render_design_assembler_stub.py",
            "validator": "validate_artifacts.py"
        }
        
        script_name = script_name_map.get(agent_type)
        if not script_name: return {"history": [f"[ERROR] Unknown agent {agent_type}"]}

        script_path = BASE_DIR / "scripts" / script_name if agent_type == "validator" else BASE_DIR / "skills" / agent_type / "scripts" / script_name
        if not script_path.exists(): return {"history": [f"[ERROR] Script not found: {script_path}"]}

        import subprocess
        def run_sync_process():
            cmd = [sys.executable, str(script_path), "--project", str(project_path)] if agent_type == "validator" else [sys.executable, str(script_path), str(baseline_path), str(project_path)]
            return subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')

        start_msg = f"[SYSTEM] Agent '{agent_type}' is now running..."
        result = await asyncio.to_thread(run_sync_process)
        
        # 捕获完整输出
        stdout_clean = result.stdout.strip() if result.stdout else ""
        stderr_clean = result.stderr.strip() if result.stderr else ""
        
        if agent_type == "validator":
            (logs_dir / "validator.log").write_text(f"{stdout_clean}\n{stderr_clean}", encoding="utf-8")
        
        status = "success" if result.returncode == 0 else "failed"
        
        # 构建日志列表
        history_updates = [start_msg, f"[{agent_type}] Completed with status: {status}"]
        if stderr_clean:
            history_updates.append(f"[{agent_type}] [ERROR] {stderr_clean}")
        # 如果失败了，把 stdout 也放进去，方便看具体报错
        if status == "failed" and stdout_clean:
            history_updates.append(f"[{agent_type}] [STDOUT] {stdout_clean}")

        return {
            "history": history_updates,
            "task_queue": _update_task_status(state["task_queue"], agent_type, status),
            "human_intervention_required": False,
            "last_worker": agent_type
        }
    return worker_node

def _update_task_status(queue: List[Task], agent_type: str, status: str) -> List[Task]:
    return [ {**t, "status": status} if t["agent_type"] == agent_type else t for t in queue ]

# --- Init Node (Planner 2.0：LLM 驱动的智能调度) ---
async def init_node(state: DesignState) -> Dict[str, Any]:
    project_id = state["project_id"]
    version = state["version"]
    requirement_text = state.get("requirement", "")
    project_path = BASE_DIR / "projects" / project_id / version
    baseline_dir = project_path / "baseline"
    
    # 获取上传的文件列表作为上下文
    uploaded_files = []
    if baseline_dir.exists():
        uploaded_files = [f.name for f in baseline_dir.iterdir() if f.is_file()]

    # 1. 构造面向 LLM 的 Planner Prompt
    system_prompt = """You are an Expert IT Design Orchestrator. 
Your task is to analyze the user's requirements and provide a tailored design pipeline.
We have the following Subagents available:
- architecture-mapping: Core system structure.
- integration-design: External service calls, MQ, Kafka.
- data-design: DB schemas, SQL tables.
- ddd-structure: Domain entities, aggregates.
- flow-design: Sequence diagrams, logic flows.
- api-design: REST/RPC interface contracts.
- config-design: App parameters, lookup lists.
- test-design: Test cases, coverage.
- ops-readiness: Monitoring, deployment specs.

ALWAYS INCLUDE: architecture-mapping, design-assembler, validator.
ONLY INCLUDE others if the requirement clearly involves those domains.

Output JSON format:
{
  "reasoning": "Your step-by-step thinking about which agents to select based on text and files.",
  "artifacts": {
    "active_agents": ["agent-id-1", "agent-id-2"]
  }
}"""

    user_prompt = f"Requirement Text: {requirement_text}\nUploaded Files: {', '.join(uploaded_files)}"

    # 2. 调用 LLM 进行智能分析
    try:
        print("[DEBUG] Planner: Calling LLM for intent analysis...")
        # 为了兼容性，我们利用 SubagentOutput 结构，artifacts 里面存我们的配置
        llm_decision = await asyncio.to_thread(
            generate_with_llm, 
            system_prompt, 
            user_prompt, 
            ["active_agents"]
        )
        
        # 解析活跃 Agent 列表
        decision_data = json.loads(llm_decision.artifacts.get("active_agents", "[]"))
        # 兜底：如果 LLM 输出不是列表，尝试手动解析
        if isinstance(decision_data, dict) and "active_agents" in decision_data:
            active_agents = set(decision_data["active_agents"])
        elif isinstance(decision_data, list):
            active_agents = set(decision_data)
        else:
            active_agents = {"architecture-mapping"} # 最后的保底
            
    except Exception as e:
        print(f"[ERROR] Planner LLM failed: {e}. Falling back to default.")
        active_agents = {"architecture-mapping", "data-design", "api-design", "flow-design"}

    # 强制包含基础节点
    active_agents.update({"architecture-mapping", "design-assembler", "validator"})

    # 3. 动态构建任务依赖链
    tasks = [{"id": "0", "agent_type": "planner", "status": "success", "dependencies": [], "priority": 100}]
    
    def add_task_if_active(id, agent, priority, deps):
        if agent in active_agents:
            tasks.append({"id": id, "agent_type": agent, "status": "todo", "dependencies": deps, "priority": priority})
            return True
        return False

    add_task_if_active("1", "architecture-mapping", 90, ["0"])
    add_task_if_active("2", "integration-design", 85, ["1"])
    has_data = add_task_if_active("3", "data-design", 80, ["1"])
    add_task_if_active("4", "ddd-structure", 75, ["3" if has_data else "1"])
    add_task_if_active("5", "api-design", 70, ["1"])
    add_task_if_active("6", "config-design", 65, ["1"])
    add_task_if_active("7", "flow-design", 60, ["1"])
    add_task_if_active("8", "test-design", 50, ["7" if "flow-design" in active_agents else "1"])
    add_task_if_active("9", "ops-readiness", 45, ["1"])
    
    current_ids = [t["id"] for t in tasks if t["id"] != "0"]
    tasks.append({"id": "10", "agent_type": "design-assembler", "status": "todo", "dependencies": current_ids, "priority": 20})
    tasks.append({"id": "11", "agent_type": "validator", "status": "todo", "dependencies": ["10"], "priority": 10})

    # 4. 保存持久化决策日志
    reasoning_content = f"### 🧠 LLM Orchestration Reasoning\n\n{llm_decision.reasoning}\n\n**Selected Pipeline:** {', '.join(sorted(list(active_agents)))}"
    (project_path / "logs" / "planner-reasoning.md").write_text(reasoning_content, encoding="utf-8")

    # 5. 【核心修复】生成 requirements.json 基线文件
    # 所有的 subagent 脚本都依赖这个文件来获取上下文
    baseline_payload = {
        "project_name": project_id,
        "project_id": project_id,
        "version": version,
        "requirement": requirement_text,
        "uploaded_files": uploaded_files,
        "active_agents": list(active_agents),
        "domain_name": "Domain", # 默认占位
        "aggregate_root": "Entity",
        "provider": "ExternalSystem",
        "consumer": "ConsumerSystem"
    }
    (baseline_dir / "requirements.json").write_text(
        json.dumps(baseline_payload, ensure_ascii=False, indent=2), 
        encoding="utf-8"
    )

    return {
        "workflow_phase": "ARCHITECTURE",
        "task_queue": tasks,
        "history": ["[SYSTEM] Planner: LLM-driven intent analysis completed and baseline initialized."]
    }
