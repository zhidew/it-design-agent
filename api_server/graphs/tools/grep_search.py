from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def grep_search(root_dir: Path, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    pattern = tool_input.get("pattern")
    if not isinstance(pattern, str) or not pattern.strip():
        raise ValueError("`pattern` must be a non-empty string.")

    matches = []
    for file_path in sorted(path for path in root_dir.rglob("*") if path.is_file()):
        content = file_path.read_text(encoding="utf-8", errors="replace")
        for line_number, line in enumerate(content.splitlines(), start=1):
            if pattern.lower() in line.lower():
                matches.append(
                    {
                        "path": file_path.relative_to(root_dir).as_posix(),
                        "line_number": line_number,
                        "line": line.strip(),
                    }
                )

    return {"root_dir": str(root_dir), "pattern": pattern, "matches": matches[:50]}
