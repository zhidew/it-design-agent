from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Dict


def run_command(root_dir: Path, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    cmd = tool_input.get("command")
    if not cmd or not isinstance(cmd, list):
        raise ValueError("`command` is required and must be a list of strings.")

    # Convert cmd elements to strings for safety
    cmd_str_list = [str(item) for item in cmd]

    # Special handling for python to use current executable
    if cmd_str_list[0] == "python":
        cmd_str_list[0] = sys.executable

    try:
        result = subprocess.run(
            cmd_str_list,
            cwd=str(root_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "command": cmd_str_list,
        }
    except Exception as exc:
        raise RuntimeError(f"Failed to execute command {' '.join(cmd_str_list)}: {exc}")
