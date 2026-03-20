import subprocess
from pathlib import Path
from typing import Any, Dict

from services.db_service import metadata_db


BASE_DIR = Path(__file__).resolve().parents[3]
PROJECTS_DIR = BASE_DIR / "projects"


def _resolve_project_id(root_dir: Path, tool_input: Dict[str, Any]) -> str:
    project_id = tool_input.get("project_id")
    if isinstance(project_id, str) and project_id.strip():
        return project_id.strip()

    try:
        relative = root_dir.resolve().relative_to(PROJECTS_DIR.resolve())
    except ValueError as exc:
        raise ValueError("`project_id` is required when `root_dir` is outside the projects directory.") from exc

    parts = relative.parts
    if not parts:
        raise ValueError("Unable to infer project ID from root_dir.")
    return parts[0]


def _inject_credentials(url: str, username: str | None, token: str | None) -> str:
    if not token or "://" not in url:
        return url
    scheme, remainder = url.split("://", 1)
    auth_user = username or "token"
    return f"{scheme}://{auth_user}:{token}@{remainder}"


def clone_repository(root_dir: Path, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    repo_id = tool_input.get("repo_id")
    if not isinstance(repo_id, str) or not repo_id.strip():
        raise ValueError("`repo_id` must be a non-empty string.")

    project_id = _resolve_project_id(root_dir, tool_input)
    repo_config = metadata_db.get_repository(project_id, repo_id, include_secrets=True)
    if repo_config is None and not tool_input.get("repo_url"):
        raise ValueError(f"Repository config not found for repo_id='{repo_id}'.")

    repo_url = tool_input.get("repo_url") or repo_config["url"]
    branch = tool_input.get("branch") or repo_config.get("branch") or "main"
    depth = tool_input.get("depth")
    if depth is not None:
        try:
            depth = int(depth)
        except (TypeError, ValueError) as exc:
            raise ValueError("`depth` must be an integer when provided.") from exc
        if depth < 1:
            raise ValueError("`depth` must be >= 1.")

    target_dir = PROJECTS_DIR / project_id / "cloned_repos" / repo_id
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    if target_dir.exists():
        subprocess.run(["git", "-C", str(target_dir), "fetch", "--all", "--prune"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(target_dir), "checkout", branch], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(target_dir), "pull", "--ff-only"], check=True, capture_output=True, text=True)
    else:
        command = ["git", "clone", "--branch", branch]
        if depth:
            command.extend(["--depth", str(depth)])
        clone_url = _inject_credentials(
            repo_url,
            repo_config.get("username") if repo_config else None,
            repo_config.get("token") if repo_config else None,
        )
        command.extend([clone_url, str(target_dir)])
        subprocess.run(command, check=True, capture_output=True, text=True)

    commit_hash = subprocess.run(
        ["git", "-C", str(target_dir), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    file_count = sum(1 for path in target_dir.rglob("*") if path.is_file())
    local_path = str(target_dir)

    if repo_config is not None and repo_config.get("local_path") != local_path:
        metadata_db.upsert_repository(
            project_id,
            {
                **repo_config,
                "local_path": local_path,
            },
        )

    return {
        "project_id": project_id,
        "repo_id": repo_id,
        "local_path": local_path,
        "branch": branch,
        "commit_hash": commit_hash,
        "file_count": file_count,
    }
