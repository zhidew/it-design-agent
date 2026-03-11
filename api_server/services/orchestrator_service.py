import subprocess
import sys
import uuid
import os
import asyncio
import yaml
import datetime
from pathlib import Path
from services.log_service import save_run_log, get_run_log

BASE_DIR = Path(__file__).resolve().parent.parent.parent
PROJECTS_DIR = BASE_DIR / "projects"
AGENTS_DIR = BASE_DIR / "agents"
SKILLS_DIR = BASE_DIR / "skills"

# In-memory store for job statuses and logs for MVP
jobs = {}

# --- Project & Run Management ---

async def run_orchestrator_task(job_id: str, project_id: str, version: str, requirement_text: str):
    jobs[job_id] = {"status": "running", "logs": []}
    
    project_path = PROJECTS_DIR / project_id / version
    project_path.mkdir(parents=True, exist_ok=True)
    
    script_path = BASE_DIR / "scripts" / "agent_run_llm.py"
    
    try:
        # Run the orchestrator script
        process = await asyncio.create_subprocess_exec(
            sys.executable, str(script_path), requirement_text, str(project_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(BASE_DIR)
        )
        
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            decoded_line = line.decode('utf-8', errors='replace').strip()
            if decoded_line:
                jobs[job_id]["logs"].append(decoded_line)
                
        await process.wait()
        
        if process.returncode == 0:
            jobs[job_id]["status"] = "success"
        else:
            jobs[job_id]["status"] = "failed"
            
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["logs"].append(f"System Error: {str(e)}")
    finally:
        # Persist logs to disk so historical versions can be inspected
        save_run_log(project_id, version, BASE_DIR, jobs[job_id]["logs"])

def get_version_logs(project_id: str, version: str) -> list:
    """Retrieve persisted logs for a specific historical version."""
    return get_run_log(project_id, version, BASE_DIR)

def trigger_orchestrator(project_id: str, version: str, requirement_text: str) -> str:
    job_id = str(uuid.uuid4())
    # Start the task in the background
    asyncio.create_task(run_orchestrator_task(job_id, project_id, version, requirement_text))
    return job_id

def get_job_status(job_id: str):
    return jobs.get(job_id, {"status": "not_found", "logs": []})

def list_projects():
    if not PROJECTS_DIR.exists():
        return []
    return [{"id": d.name, "name": d.name} for d in PROJECTS_DIR.iterdir() if d.is_dir()]

def create_project(project_id: str):
    (PROJECTS_DIR / project_id).mkdir(parents=True, exist_ok=True)

def list_versions(project_id: str):
    proj_dir = PROJECTS_DIR / project_id
    if not proj_dir.exists():
        return []
    versions = [d.name for d in proj_dir.iterdir() if d.is_dir()]
    # Sort versions, assuming they are named v1, v2, or timestamps
    return sorted(versions, reverse=True)

def get_artifacts_tree(project_id: str, version: str):
    target_dir = PROJECTS_DIR / project_id / version / "artifacts"
    if not target_dir.exists():
        return {}
    
    tree = {}
    for item in target_dir.iterdir():
        if item.is_file():
            try:
                tree[item.name] = item.read_text(encoding="utf-8")
            except Exception:
                tree[item.name] = "[Binary or Unreadable File]"
    return tree

# --- Management Methods ---

def list_agents():
    if not AGENTS_DIR.exists():
        return []
    
    agents = []
    for item in AGENTS_DIR.glob("*.agent.yaml"):
        try:
            with open(item, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                agents.append({
                    "id": item.stem.replace(".agent", ""),
                    "name": config.get("name", item.stem),
                    "description": config.get("description", ""),
                    "config_path": str(item.relative_to(BASE_DIR)),
                    "skills": config.get("skills", []),
                    "current_config": item.read_text(encoding="utf-8")
                })
        except Exception as e:
            print(f"Error reading agent config {item}: {e}")
    return agents

def get_agent(agent_id: str):
    config_file = AGENTS_DIR / f"{agent_id}.agent.yaml"
    if not config_file.exists():
        return None
    
    content = config_file.read_text(encoding="utf-8")
    config = yaml.safe_load(content)
    
    # Version history from .versions sub-directory
    versions = []
    versions_dir = AGENTS_DIR / ".versions" / agent_id
    if versions_dir.exists():
        v_files = sorted(list(versions_dir.glob("*.v*")), key=os.path.getmtime, reverse=True)
        for v_file in v_files:
            try:
                name_parts = v_file.name.split(".v")
                ts_str = name_parts[0]
                v_id = name_parts[1]
                versions.append({
                    "version_id": v_id,
                    "timestamp": ts_str,
                    "content": v_file.read_text(encoding="utf-8")
                })
            except Exception:
                pass
                
    return {
        "id": agent_id,
        "name": config.get("name", agent_id),
        "description": config.get("description", ""),
        "config_path": str(config_file.relative_to(BASE_DIR)),
        "current_config": content,
        "versions": versions,
        "skills": config.get("skills", [])
    }

def update_agent(agent_id: str, new_config_yaml: str):
    config_file = AGENTS_DIR / f"{agent_id}.agent.yaml"
    if not config_file.exists():
        return False
    
    # Validate YAML before saving
    try:
        yaml.safe_load(new_config_yaml)
    except Exception:
        return False

    old_content = config_file.read_text(encoding="utf-8")
    
    # Save current as a version
    versions_dir = AGENTS_DIR / ".versions" / agent_id
    versions_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    v_count = len(list(versions_dir.glob("*.v*"))) + 1
    version_file = versions_dir / f"{timestamp}.v{v_count}"
    version_file.write_text(old_content, encoding="utf-8")
    
    # Update current
    config_file.write_text(new_config_yaml, encoding="utf-8")
    return True

def list_skills():
    if not SKILLS_DIR.exists():
        return []
    
    skills = []
    for item in SKILLS_DIR.iterdir():
        if item.is_dir() and (item / "SKILL.md").exists():
            # Try to read name/description from frontmatter if it exists
            name = item.name
            desc = ""
            try:
                content = (item / "SKILL.md").read_text(encoding="utf-8")
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        fm = yaml.safe_load(parts[1])
                        name = fm.get("name", name)
                        desc = fm.get("description", desc)
            except Exception:
                pass

            templates = []
            tpl_dir = item / "assets" / "templates"
            if tpl_dir.exists():
                templates = [t.name for t in tpl_dir.iterdir() if t.is_file()]

            skills.append({
                "id": item.name,
                "name": name,
                "description": desc,
                "path": str(item.relative_to(BASE_DIR)),
                "templates": templates
            })
    return skills

def get_template(skill_id: str, template_name: str):
    tpl_path = SKILLS_DIR / skill_id / "assets" / "templates" / template_name
    if not tpl_path.exists():
        return None
    
    content = tpl_path.read_text(encoding="utf-8")
    
    # Version history from .versions sub-directory
    versions = []
    versions_dir = tpl_path.parent / ".versions" / template_name
    if versions_dir.exists():
        # List all version files and sort by creation time (implicitly by timestamp in name)
        v_files = sorted(list(versions_dir.glob("*.v*")), key=os.path.getmtime, reverse=True)
        for v_file in v_files:
            try:
                # Format: timestamp.v{version_id}
                name_parts = v_file.name.split(".v")
                ts_str = name_parts[0]
                v_id = name_parts[1] if len(name_parts) > 1 else "unknown"
                versions.append({
                    "version_id": v_id,
                    "timestamp": ts_str,
                    "content": v_file.read_text(encoding="utf-8")
                })
            except Exception:
                pass
                
    return {
        "id": template_name,
        "name": template_name,
        "skill_id": skill_id,
        "current_content": content,
        "versions": versions
    }

def update_template(skill_id: str, template_name: str, new_content: str):
    tpl_path = SKILLS_DIR / skill_id / "assets" / "templates" / template_name
    if not tpl_path.exists():
        # Create directory if it doesn't exist (e.g. adding a new template)
        tpl_path.parent.mkdir(parents=True, exist_ok=True)
        old_content = ""
    else:
        old_content = tpl_path.read_text(encoding="utf-8")
    
    # Save current as a version before overwriting (if it existed)
    if old_content:
        versions_dir = tpl_path.parent / ".versions" / template_name
        versions_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        v_count = len(list(versions_dir.glob("*.v*"))) + 1
        version_file = versions_dir / f"{timestamp}.v{v_count}"
        version_file.write_text(old_content, encoding="utf-8")
    
    # Update current
    tpl_path.write_text(new_content, encoding="utf-8")
    return True
