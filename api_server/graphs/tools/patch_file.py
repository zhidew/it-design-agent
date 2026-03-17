from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def patch_file(root_dir: Path, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    file_path_str = tool_input.get("path")
    old_content = tool_input.get("old_content")
    new_content = tool_input.get("new_content")

    if not file_path_str or not isinstance(file_path_str, str):
        raise ValueError("`path` is required and must be a string.")
    if old_content is None or not isinstance(old_content, str):
        raise ValueError("`old_content` is required and must be a string.")
    if new_content is None or not isinstance(new_content, str):
        raise ValueError("`new_content` is required and must be a string.")

    target_path = (root_dir / file_path_str).resolve()
    if not str(target_path).startswith(str(root_dir)):
        raise ValueError(f"Path is outside of root directory: {file_path_str}")

    if not target_path.exists():
        raise FileNotFoundError(f"File not found: {file_path_str}")

    content = target_path.read_text(encoding="utf-8")
    if old_content not in content:
        raise ValueError(f"Old content not found in {file_path_str}")

    # For safety, ensure there's exactly one occurrence
    count = content.count(old_content)
    if count > 1:
        raise ValueError(f"Ambiguous patch: {count} occurrences of old_content found.")

    new_full_content = content.replace(old_content, new_content)
    target_path.write_text(new_full_content, encoding="utf-8")

    return {
        "path": file_path_str,
        "size_bytes": target_path.stat().st_size,
        "message": f"Successfully patched {file_path_str}",
    }
