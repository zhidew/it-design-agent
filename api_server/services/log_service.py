import os
import json
import datetime
import hashlib
from pathlib import Path

# =====================================================================
# 持久化日志存储功能
# =====================================================================

def save_run_log(project_id: str, version: str, base_dir: Path, logs: list):
    """
    将执行日志持久化到项目的对应版本目录下
    """
    try:
        log_dir = base_dir / "projects" / project_id / version / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "orchestrator_run.log"
        
        with open(log_file, "w", encoding="utf-8") as f:
            for log in logs:
                f.write(log + "\n")
        print(f"[LogService] Successfully saved {len(logs)} logs to {log_file}")
    except Exception as e:
        print(f"[LogService] Error saving logs: {e}")

def _get_content_hash(content: str) -> str:
    return hashlib.md5(content.encode("utf-8")).hexdigest()

def _get_timestamp_id() -> str:
    """Generate a high-precision timestamp ID: YYYYMMDD_HHMMSS_mmm"""
    now = datetime.datetime.now()
    return now.strftime("%Y%m%d_%H%M%S_%f")[:-3]  # Keep 3 digits of microsecond for milliseconds

def save_llm_interaction(
    project_id: str,
    version: str,
    base_dir: Path,
    node_id: str,
    system_prompt: str,
    user_prompt: str,
    response: dict | str | None,
    provider: str,
    model: str,
    status: str = "success",
    error: str | None = None,
    include_full_artifacts: bool = False
):
    """
    ULTIMATE OPTIMIZATION WITH CHRONOLOGICAL FILENAMES:
    1. System Prompt -> prompts/{ts}_{node}_sys.txt
    2. User Prompt -> prompts/{ts}_{node}_user.txt
    3. LLM Response -> responses/{ts}_{node}_res.json
    4. JSONL -> Lightweight index with timestamped refs.
    """
    try:
        log_dir = base_dir / "projects" / project_id / version / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Setup Storage Folders
        prompt_dir = log_dir / "prompts"
        response_dir = log_dir / "responses"
        prompt_dir.mkdir(exist_ok=True)
        response_dir.mkdir(exist_ok=True)

        # 2. Generate Base ID for this interaction
        ts_id = _get_timestamp_id()
        file_prefix = f"{ts_id}_{node_id}"

        # 3. Save System Prompt (Chronological)
        sys_ref = f"prompts/{file_prefix}_sys.txt"
        sys_file = log_dir / sys_ref
        sys_file.write_text(system_prompt, encoding="utf-8")

        # 4. Save User Prompt (Chronological)
        user_ref = f"prompts/{file_prefix}_user.txt"
        user_file = log_dir / user_ref
        user_file.write_text(user_prompt, encoding="utf-8")
        
        # 5. Save FULL Response (Chronological)
        res_ref = "none"
        res_summary = "no_response"
        if response:
            res_str = json.dumps(response, ensure_ascii=False)
            res_ref = f"responses/{file_prefix}_res.json"
            res_file = log_dir / res_ref
            res_file.write_text(res_str, encoding="utf-8")
            
            # Create lightweight summary for JSONL
            if isinstance(response, dict):
                res_summary = {
                    "reasoning_preview": (response.get("reasoning") or "")[:200] + "...",
                    "artifacts_summary": {k: f"{len(str(v))} bytes" for k, v in response.get("artifacts", {}).items()}
                }
            else:
                res_summary = str(response)[:200] + "..."

        # 6. Write to JSONL (Chronological reference)
        log_file = log_dir / "llm_interactions.jsonl"
        log_entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "node_id": node_id,
            "status": status,
            "provider": provider,
            "model": model,
            "refs": {
                "system": sys_ref,
                "user": user_ref,
                "response": res_ref
            },
            "preview": {
                "user": user_prompt[:200] + "...",
                "response": res_summary
            },
            "error": error
        }
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            
    except Exception as e:
        print(f"[LogService] Error saving LLM interaction: {e}")

def get_run_log(project_id: str, version: str, base_dir: Path) -> list:
    """
    读取指定版本的持久化执行日志
    """
    log_file = base_dir / "projects" / project_id / version / "logs" / "orchestrator_run.log"
    if log_file.exists():
        with open(log_file, "r", encoding="utf-8") as f:
            return [line.strip() for line in f.readlines()]
    return []
