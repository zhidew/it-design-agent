import subprocess
import sys
import uuid
import os
import asyncio
import yaml
import datetime
import json
from pathlib import Path
from services.log_service import save_run_log, get_run_log
from graphs.builder import create_design_graph

BASE_DIR = Path(__file__).resolve().parent.parent.parent
PROJECTS_DIR = BASE_DIR / "projects"
AGENTS_DIR = BASE_DIR / "agents"
SKILLS_DIR = BASE_DIR / "skills"

jobs = {}
design_graph = create_design_graph()

async def run_orchestrator_task(job_id: str, project_id: str, version: str, requirement_text: str):
    print(f"\n[DEBUG] Starting/Resuming Job: {job_id} for Thread: {project_id}_{version}")
    jobs[job_id] = {"status": "running", "logs": []}
    thread_id = f"{project_id}_{version}"
    
    try:
        project_path = PROJECTS_DIR / project_id / version
        baseline_path = project_path / "baseline"
        baseline_path.mkdir(parents=True, exist_ok=True)
        (project_path / "logs").mkdir(parents=True, exist_ok=True)
        
        if requirement_text:
            (baseline_path / "original-requirements.md").write_text(requirement_text, encoding="utf-8")
            
        persisted_state = get_workflow_state(project_id, version)
        
        initial_state = {
            "project_id": project_id,
            "version": version,
            "requirement": requirement_text,
            "design_context": {},
            "task_queue": persisted_state["task_queue"] if persisted_state else [],
            "workflow_phase": persisted_state["workflow_phase"] if persisted_state and persisted_state["workflow_phase"] != "UNKNOWN" else "INIT",
            "history": persisted_state["history"] if persisted_state else [],
            "human_intervention_required": False,
            "last_worker": None
        }
        
        if not initial_state["history"]:
            initial_state["history"].append(f"[SYSTEM] Initializing design session for {project_id}...")

        config = {"configurable": {"thread_id": thread_id}}
        
        async for event in design_graph.astream(initial_state, config=config, stream_mode="updates"):
            for node_name, output in event.items():
                if isinstance(output, dict) and "history" in output:
                    for h in output["history"]:
                        jobs[job_id]["logs"].append(h)
            
        jobs[job_id]["status"] = "success"
    except Exception as e:
        import traceback
        error_msg = f"[ERROR] LangGraph execution error: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["logs"].append(error_msg)
    finally:
        latest_state = get_workflow_state(project_id, version)
        if latest_state and "history" in latest_state:
            save_run_log(project_id, version, BASE_DIR, latest_state["history"])

def get_workflow_state(project_id: str, version: str):
    thread_id = f"{project_id}_{version}"
    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = design_graph.get_state(config)
        if state and state.values:
            return state.values
        
        project_root = PROJECTS_DIR / project_id / version
        persisted_logs = get_run_log(project_id, version, BASE_DIR)
        target_dir = project_root / "artifacts"
        logs_dir = project_root / "logs"
        baseline_file = project_root / "baseline" / "requirements.json"
        
        # 1. 读取当初被选中的活跃 Agent 列表
        active_agents = set()
        if baseline_file.exists():
            try:
                base_data = json.loads(baseline_file.read_text(encoding="utf-8"))
                active_agents = set(base_data.get("active_agents", []))
            except Exception: pass
        
        # 2. 如果没读到(极旧版本)，则默认只显示基础节点
        if not active_agents:
            active_agents = {"planner", "architecture-mapping", "design-assembler", "validator"}

        def check_success(file_patterns):
            if not target_dir.exists(): return False
            for p in file_patterns:
                if any(target_dir.glob(p)): return True
            return False

        validator_status = "todo"
        val_log_path = logs_dir / "validator.log"
        if val_log_path.exists():
            content = val_log_path.read_text(encoding="utf-8")
            validator_status = "success" if "[SUCCESS]" in content else "failed"

        # 3. 动态构建推断列表，只包含当初活跃的 Agent
        full_map = [
            {"id": "0", "agent_type": "planner", "status": "success"},
            {"id": "1", "agent_type": "architecture-mapping", "status": "success" if check_success(["architecture.md"]) else "todo"},
            {"id": "2", "agent_type": "integration-design", "status": "success" if check_success(["integration-*", "asyncapi.yaml"]) else "todo"},
            {"id": "3", "agent_type": "data-design", "status": "success" if check_success(["schema.sql", "er.md"]) else "todo"},
            {"id": "4", "agent_type": "ddd-structure", "status": "success" if check_success(["ddd-structure.md"]) else "todo"},
            {"id": "5", "agent_type": "api-design", "status": "success" if check_success(["api-internal.yaml", "api-public.yaml"]) else "todo"},
            {"id": "6", "agent_type": "config-design", "status": "success" if check_success(["config-catalog.yaml"]) else "todo"},
            {"id": "7", "agent_type": "flow-design", "status": "success" if check_success(["sequence-*", "state-*"]) else "todo"},
            {"id": "8", "agent_type": "test-design", "status": "success" if check_success(["test-inputs.md", "coverage-map.json"]) else "todo"},
            {"id": "9", "agent_type": "ops-readiness", "status": "success" if check_success(["slo.yaml", "observability-spec.yaml"]) else "todo"},
            {"id": "10", "agent_type": "design-assembler", "status": "success" if check_success(["detailed-design.md"]) else "todo"},
            {"id": "11", "agent_type": "validator", "status": validator_status},
        ]
        
        inferred_tasks = [t for t in full_map if t["agent_type"] in active_agents or t["agent_type"] == "planner"]

        return {
            "project_id": project_id,
            "version": version,
            "workflow_phase": "ARCHIVED",
            "task_queue": inferred_tasks,
            "history": persisted_logs if persisted_logs else []
        }
    except Exception:
        return None

async def resume_workflow(project_id: str, version: str, human_input: dict):
    thread_id = f"{project_id}_{version}"
    config = {"configurable": {"thread_id": thread_id}}
    
    state = design_graph.get_state(config)
    if not state or not state.values:
        asyncio.create_task(run_orchestrator_task(str(uuid.uuid4()), project_id, version, ""))
        return True

    design_graph.update_state(config, {
        "human_intervention_required": False,
        "history": [f"[HUMAN] Decision: {'Approved' if human_input.get('approved') else 'Revised'}. Feedback: {human_input.get('feedback', 'None')}"]
    })
    
    async def run_resumption():
        try:
            async for event in design_graph.astream(None, config=config, stream_mode="updates"):
                pass
        except Exception as e:
            print(f"[ERROR] Resumption failed: {e}")

    asyncio.create_task(run_resumption())
    return True

def trigger_orchestrator(project_id: str, version: str, requirement_text: str) -> str:
    job_id = str(uuid.uuid4())
    asyncio.create_task(run_orchestrator_task(job_id, project_id, version, requirement_text))
    return job_id

def get_job_status(job_id: str):
    return jobs.get(job_id, {"status": "not_found", "logs": []})

def list_projects():
    if not PROJECTS_DIR.exists(): return []
    return [{"id": d.name, "name": d.name} for d in PROJECTS_DIR.iterdir() if d.is_dir()]

def create_project(project_id: str):
    (PROJECTS_DIR / project_id).mkdir(parents=True, exist_ok=True)

def list_versions(project_id: str):
    proj_dir = PROJECTS_DIR / project_id
    if not proj_dir.exists(): return []
    return sorted([d.name for d in proj_dir.iterdir() if d.is_dir()], reverse=True)

def get_artifacts_tree(project_id: str, version: str):
    project_root = PROJECTS_DIR / project_id / version
    tree = {}
    dirs = {"baseline": "baseline", "artifacts": "artifacts", "logs": "logs"}
    for key, dirname in dirs.items():
        dir_path = project_root / dirname
        if dir_path.exists():
            for item in dir_path.iterdir():
                if item.is_file():
                    try: tree[item.name] = item.read_text(encoding="utf-8")
                    except Exception: tree[item.name] = "[Binary]"
    return tree

def get_version_logs(project_id: str, version: str) -> list:
    return get_run_log(project_id, version, BASE_DIR)

# --- Management 逻辑保持不变 ---
def list_agents():
    if not AGENTS_DIR.exists(): return []
    agents = []
    for item in AGENTS_DIR.glob("*.agent.yaml"):
        try:
            with open(item, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                agents.append({"id": item.stem.replace(".agent", ""),"name": config.get("name", item.stem),"description": config.get("description", ""),"config_path": str(item.relative_to(BASE_DIR)),"skills": config.get("skills", []),"current_config": item.read_text(encoding="utf-8")})
        except Exception: pass
    return agents

def get_agent(agent_id: str):
    config_file = AGENTS_DIR / f"{agent_id}.agent.yaml"
    if not config_file.exists(): return None
    content = config_file.read_text(encoding="utf-8")
    config = yaml.safe_load(content)
    versions = []
    versions_dir = AGENTS_DIR / ".versions" / agent_id
    if versions_dir.exists():
        v_files = sorted(list(versions_dir.glob("*.v*")), key=os.path.getmtime, reverse=True)
        for v_file in v_files:
            try:
                name_parts = v_file.name.split(".v")
                versions.append({"version_id": name_parts[1],"timestamp": name_parts[0],"content": v_file.read_text(encoding="utf-8")})
            except Exception: pass
    return {"id": agent_id,"name": config.get("name", agent_id),"description": config.get("description", ""),"config_path": str(config_file.relative_to(BASE_DIR)),"current_config": content,"versions": versions,"skills": config.get("skills", [])}

def update_agent(agent_id: str, new_config_yaml: str):
    config_file = AGENTS_DIR / f"{agent_id}.agent.yaml"
    if not config_file.exists(): return False
    try: yaml.safe_load(new_config_yaml)
    except Exception: return False
    old_content = config_file.read_text(encoding="utf-8")
    versions_dir = AGENTS_DIR / ".versions" / agent_id
    versions_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    v_count = len(list(versions_dir.glob("*.v*"))) + 1
    (versions_dir / f"{timestamp}.v{v_count}").write_text(old_content, encoding="utf-8")
    config_file.write_text(new_config_yaml, encoding="utf-8")
    return True

def list_skills():
    if not SKILLS_DIR.exists(): return []
    skills = []
    for item in SKILLS_DIR.iterdir():
        if item.is_dir() and (item / "SKILL.md").exists():
            name = item.name
            try:
                content = (item / "SKILL.md").read_text(encoding="utf-8")
                if content.startswith("---"):
                    fm = yaml.safe_load(content.split("---")[1])
                    name = fm.get("name", name)
            except Exception: pass
            skills.append({"id": item.name,"name": name,"path": str(item.relative_to(BASE_DIR)),"templates": [t.name for t in (item / "assets" / "templates").iterdir() if t.is_file()] if (item / "assets" / "templates").exists() else []})
    return skills

def get_template(skill_id: str, template_name: str):
    tpl_path = SKILLS_DIR / skill_id / "assets" / "templates" / template_name
    if not tpl_path.exists(): return None
    content = tpl_path.read_text(encoding="utf-8")
    versions = []
    versions_dir = tpl_path.parent / ".versions" / template_name
    if versions_dir.exists():
        v_files = sorted(list(versions_dir.glob("*.v*")), key=os.path.getmtime, reverse=True)
        for v_file in v_files:
            try:
                name_parts = v_file.name.split(".v")
                versions.append({"version_id": name_parts[1],"timestamp": name_parts[0],"content": v_file.read_text(encoding="utf-8")})
            except Exception: pass
    return {"id": template_name,"name": template_name,"skill_id": skill_id,"current_content": content,"versions": versions}

def update_template(skill_id: str, template_name: str, new_content: str):
    tpl_path = SKILLS_DIR / skill_id / "assets" / "templates" / template_name
    if not tpl_path.exists(): tpl_path.parent.mkdir(parents=True, exist_ok=True); old_content = ""
    else: old_content = tpl_path.read_text(encoding="utf-8")
    if old_content:
        versions_dir = tpl_path.parent / ".versions" / template_name
        versions_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        v_count = len(list(versions_dir.glob("*.v*"))) + 1
        (versions_dir / f"{timestamp}.v{v_count}").write_text(old_content, encoding="utf-8")
    tpl_path.write_text(new_content, encoding="utf-8")
    return True
