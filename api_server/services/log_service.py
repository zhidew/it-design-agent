import os
import json
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

def get_run_log(project_id: str, version: str, base_dir: Path) -> list:
    """
    读取指定版本的持久化执行日志
    """
    log_file = base_dir / "projects" / project_id / version / "logs" / "orchestrator_run.log"
    if log_file.exists():
        with open(log_file, "r", encoding="utf-8") as f:
            return [line.strip() for line in f.readlines()]
    return []
