from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def list_files(root_dir: Path, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    files = []
    for file_path in sorted(path for path in root_dir.rglob("*") if path.is_file()):
        files.append(
            {
                "name": file_path.name,
                "path": file_path.relative_to(root_dir).as_posix(),
                "extension": file_path.suffix.lower(),
                "size_bytes": file_path.stat().st_size,
            }
        )
    return {"root_dir": str(root_dir), "files": files}
