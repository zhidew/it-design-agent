from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any


def normalize_path_text(raw_path: str) -> str:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError("Path must be a non-empty string.")

    normalized = PurePosixPath(raw_path.strip().replace("\\", "/")).as_posix()
    return normalized or "."


def resolve_root_dir(raw_root: str) -> Path:
    if not isinstance(raw_root, str) or not raw_root.strip():
        raise ValueError("`root_dir` must be a non-empty string.")

    root_dir = Path(raw_root.strip()).expanduser().resolve()
    if not root_dir.exists() or not root_dir.is_dir():
        raise FileNotFoundError(f"Root directory not found: {raw_root}")
    return root_dir


def ensure_within_root(candidate_path: Path, root_dir: Path, *, label: str) -> None:
    try:
        candidate_path.resolve().relative_to(root_dir.resolve())
    except ValueError as exc:
        raise ValueError(f"Path escapes root directory: {label}") from exc


def resolve_path_within_root(
    root_dir: Path,
    raw_path: str,
    *,
    must_exist: bool = False,
    expected_kind: str = "any",
) -> tuple[Path, str]:
    normalized_path = normalize_path_text(raw_path)
    candidate_path = Path(raw_path.strip()).expanduser()
    if not candidate_path.is_absolute():
        candidate_path = root_dir / normalized_path

    resolved_path = candidate_path.resolve()
    ensure_within_root(resolved_path, root_dir, label=normalized_path)

    if must_exist and not resolved_path.exists():
        raise FileNotFoundError(f"Path not found: {normalized_path}")

    if resolved_path.exists():
        if expected_kind == "file" and not resolved_path.is_file():
            raise ValueError(f"Expected file path but found directory: {normalized_path}")
        if expected_kind == "dir" and not resolved_path.is_dir():
            raise ValueError(f"Expected directory path but found file: {normalized_path}")

    relative_path = resolved_path.relative_to(root_dir.resolve()).as_posix()
    return resolved_path, relative_path


def resolve_directory_reference(
    base_dir: Path,
    raw_path: str,
    *,
    must_exist: bool = True,
) -> tuple[Path, str]:
    normalized_path = normalize_path_text(raw_path)
    candidate_path = Path(raw_path.strip()).expanduser()

    if candidate_path.is_absolute():
        resolved_path = candidate_path.resolve()
        display_path = resolved_path.as_posix()
    else:
        resolved_path = (base_dir / normalized_path).resolve()
        ensure_within_root(resolved_path, base_dir, label=normalized_path)
        display_path = normalized_path

    if must_exist and not resolved_path.exists():
        raise FileNotFoundError(f"Directory not found: {raw_path}")
    if must_exist and not resolved_path.is_dir():
        raise ValueError(f"Expected directory path but found file: {raw_path}")

    return resolved_path, display_path


def resolve_search_roots(root_dir: Path, repos_dir: Any) -> list[dict[str, Path | str]]:
    search_roots: list[dict[str, Path | str]] = [{"label": ".", "path": root_dir}]
    if repos_dir is None:
        return search_roots

    values = repos_dir if isinstance(repos_dir, list) else [repos_dir]
    for raw_value in values:
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ValueError("`repos_dir` entries must be non-empty strings.")
        repo_path, display_path = resolve_directory_reference(root_dir, raw_value)
        search_roots.append({"label": display_path, "path": repo_path})
    return search_roots
