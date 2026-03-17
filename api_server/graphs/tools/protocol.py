from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Dict

from .extract_structure import extract_structure
from .extract_lookup_values import extract_lookup_values
from .grep_search import grep_search
from .list_files import list_files
from .read_file_chunk import read_file_chunk
from .write_file import write_file
from .patch_file import patch_file
from .run_command import run_command


TOOL_ERROR_OK = "OK"
TOOL_ERROR_INVALID_INPUT = "INVALID_INPUT"
TOOL_ERROR_NOT_FOUND = "NOT_FOUND"
TOOL_ERROR_UNSUPPORTED = "UNSUPPORTED_TOOL"
TOOL_ERROR_INTERNAL = "INTERNAL_ERROR"


class ToolInputError(ValueError):
    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code


def execute_tool(tool_name: str, tool_input: Dict[str, Any] | None) -> Dict[str, Any]:
    started = time.perf_counter()
    tool_input = dict(tool_input or {})
    try:
        handler = _TOOL_REGISTRY.get(tool_name)
        if handler is None:
            raise ToolInputError(TOOL_ERROR_UNSUPPORTED, f"Unsupported tool: {tool_name}")
        output = handler(tool_input)
        status = "success"
        error_code = TOOL_ERROR_OK
    except ToolInputError as exc:
        output = {"message": str(exc)}
        status = "error"
        error_code = exc.error_code
    except Exception as exc:
        output = {"message": str(exc)}
        status = "error"
        error_code = TOOL_ERROR_INTERNAL

    return {
        "tool_name": tool_name,
        "status": status,
        "error_code": error_code,
        "duration_ms": max(0, int((time.perf_counter() - started) * 1000)),
        "input": tool_input,
        "output": output,
    }


def _require_root_dir(tool_input: Dict[str, Any]) -> Path:
    raw_root = tool_input.get("root_dir")
    if not isinstance(raw_root, str) or not raw_root.strip():
        raise ToolInputError(TOOL_ERROR_INVALID_INPUT, "`root_dir` must be a non-empty string.")

    root_dir = Path(raw_root).resolve()
    if not root_dir.exists() or not root_dir.is_dir():
        raise ToolInputError(TOOL_ERROR_NOT_FOUND, f"Root directory not found: {raw_root}")
    return root_dir


def _run_list_files(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    return list_files(_require_root_dir(tool_input), tool_input)


def _run_extract_structure(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return extract_structure(_require_root_dir(tool_input), tool_input)
    except ValueError as exc:
        raise ToolInputError(TOOL_ERROR_INVALID_INPUT, str(exc)) from exc


def _run_grep_search(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return grep_search(_require_root_dir(tool_input), tool_input)
    except ValueError as exc:
        raise ToolInputError(TOOL_ERROR_INVALID_INPUT, str(exc)) from exc


def _run_read_file_chunk(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return read_file_chunk(_require_root_dir(tool_input), tool_input)
    except ValueError as exc:
        raise ToolInputError(TOOL_ERROR_INVALID_INPUT, str(exc)) from exc
    except FileNotFoundError as exc:
        raise ToolInputError(TOOL_ERROR_NOT_FOUND, str(exc)) from exc


def _run_extract_lookup_values(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return extract_lookup_values(_require_root_dir(tool_input), tool_input)
    except ValueError as exc:
        raise ToolInputError(TOOL_ERROR_INVALID_INPUT, str(exc)) from exc


def _run_write_file(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return write_file(_require_root_dir(tool_input), tool_input)
    except ValueError as exc:
        raise ToolInputError(TOOL_ERROR_INVALID_INPUT, str(exc)) from exc


def _run_patch_file(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return patch_file(_require_root_dir(tool_input), tool_input)
    except ValueError as exc:
        raise ToolInputError(TOOL_ERROR_INVALID_INPUT, str(exc)) from exc
    except FileNotFoundError as exc:
        raise ToolInputError(TOOL_ERROR_NOT_FOUND, str(exc)) from exc


def _run_run_command(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return run_command(_require_root_dir(tool_input), tool_input)
    except ValueError as exc:
        raise ToolInputError(TOOL_ERROR_INVALID_INPUT, str(exc)) from exc
    except RuntimeError as exc:
        raise ToolInputError(TOOL_ERROR_INTERNAL, str(exc)) from exc


_TOOL_REGISTRY: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "list_files": _run_list_files,
    "extract_structure": _run_extract_structure,
    "grep_search": _run_grep_search,
    "read_file_chunk": _run_read_file_chunk,
    "extract_lookup_values": _run_extract_lookup_values,
    "write_file": _run_write_file,
    "patch_file": _run_patch_file,
    "run_command": _run_run_command,
}
