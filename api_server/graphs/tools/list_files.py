from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def _resolve_search_roots(root_dir: Path, tool_input: Dict[str, Any]):
    search_roots = [{"label": ".", "path": root_dir}]
    repos_dir = tool_input.get("repos_dir")
    if repos_dir is None:
        return search_roots

    values = repos_dir if isinstance(repos_dir, list) else [repos_dir]
    for raw_value in values:
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ValueError("`repos_dir` entries must be non-empty strings.")
        repo_path = Path(raw_value)
        if not repo_path.is_absolute():
            repo_path = (root_dir / repo_path).resolve()
        if not repo_path.exists() or not repo_path.is_dir():
            raise ValueError(f"Repository directory not found: {raw_value}")
        search_roots.append({"label": raw_value.replace("\\", "/"), "path": repo_path})
    return search_roots


def list_files(root_dir: Path, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    files = []
    search_roots = _resolve_search_roots(root_dir, tool_input)
    for search_root in search_roots:
        base_path = search_root["path"]
        for file_path in sorted(path for path in base_path.rglob("*") if path.is_file()):
            files.append(
                {
                    "name": file_path.name,
                    "path": file_path.relative_to(base_path).as_posix(),
                    "search_root": search_root["label"],
                    "extension": file_path.suffix.lower(),
                    "size_bytes": file_path.stat().st_size,
                }
            )
    return {
        "root_dir": str(root_dir),
        "search_roots": [item["label"] for item in search_roots],
        "files": files,
    }
