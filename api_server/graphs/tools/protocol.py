from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

from .extract_structure import extract_structure
from .extract_lookup_values import extract_lookup_values
from .clone_repository import clone_repository
from .grep_search import grep_search
from .list_files import list_files
from .query_database import query_database
from .query_knowledge_base import query_knowledge_base
from .read_file_chunk import read_file_chunk
from .write_file import write_file
from .patch_file import patch_file
from .run_command import run_command

if TYPE_CHECKING:
    from registry.agent_registry import AgentFullConfig


TOOL_ERROR_OK = "OK"
TOOL_ERROR_INVALID_INPUT = "INVALID_INPUT"
TOOL_ERROR_NOT_FOUND = "NOT_FOUND"
TOOL_ERROR_UNSUPPORTED = "UNSUPPORTED_TOOL"
TOOL_ERROR_INTERNAL = "INTERNAL_ERROR"
TOOL_ERROR_NOT_ALLOWED = "NOT_ALLOWED"


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


def execute_tool_with_permission(
    tool_name: str,
    tool_input: Dict[str, Any] | None,
    agent_config: Optional["AgentFullConfig"] = None,
    agent_capability: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute a tool with permission check based on agent configuration.
    
    This function first verifies that the agent has permission to use the tool,
    then executes the tool if allowed.
    
    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool
        agent_config: AgentFullConfig object (preferred)
        agent_capability: Capability string to load config from registry (fallback)
        
    Returns:
        Tool execution result with status and output
        
    Raises:
        ToolInputError: If tool is not allowed for the agent
        
    Example:
        # With AgentFullConfig
        config = registry.load_full_config("api-design")
        result = execute_tool_with_permission("write_file", {...}, agent_config=config)
        
        # With capability string (loads from registry)
        result = execute_tool_with_permission("list_files", {...}, agent_capability="api-design")
    """
    # Resolve agent config
    config = agent_config
    if config is None and agent_capability:
        try:
            from registry.agent_registry import AgentRegistry
            registry = AgentRegistry.get_instance()
            config = registry.load_full_config(agent_capability)
        except RuntimeError:
            # Registry not initialized, skip permission check
            pass
    
    # Check permission
    if config is not None:
        if not config.has_tool_permission(tool_name):
            allowed = config.tools_allowed or []
            from registry.errors import ToolNotAllowedError
            raise ToolInputError(
                TOOL_ERROR_NOT_ALLOWED,
                f"Tool '{tool_name}' is not allowed for agent '{config.manifest.capability}'. "
                f"Allowed tools: {allowed}"
            )
    
    # Execute the tool
    return execute_tool(tool_name, tool_input)


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


def _run_clone_repository(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return clone_repository(_require_root_dir(tool_input), tool_input)
    except ValueError as exc:
        raise ToolInputError(TOOL_ERROR_INVALID_INPUT, str(exc)) from exc
    except FileNotFoundError as exc:
        raise ToolInputError(TOOL_ERROR_NOT_FOUND, str(exc)) from exc
    except RuntimeError as exc:
        raise ToolInputError(TOOL_ERROR_INTERNAL, str(exc)) from exc


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


def _run_query_database(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return query_database(_require_root_dir(tool_input), tool_input)
    except ValueError as exc:
        raise ToolInputError(TOOL_ERROR_INVALID_INPUT, str(exc)) from exc
    except RuntimeError as exc:
        raise ToolInputError(TOOL_ERROR_INTERNAL, str(exc)) from exc


def _run_query_knowledge_base(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return query_knowledge_base(_require_root_dir(tool_input), tool_input)
    except ValueError as exc:
        raise ToolInputError(TOOL_ERROR_INVALID_INPUT, str(exc)) from exc
    except RuntimeError as exc:
        raise ToolInputError(TOOL_ERROR_INTERNAL, str(exc)) from exc


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
    "clone_repository": _run_clone_repository,
    "extract_structure": _run_extract_structure,
    "grep_search": _run_grep_search,
    "read_file_chunk": _run_read_file_chunk,
    "extract_lookup_values": _run_extract_lookup_values,
    "query_database": _run_query_database,
    "query_knowledge_base": _run_query_knowledge_base,
    "write_file": _run_write_file,
    "patch_file": _run_patch_file,
    "run_command": _run_run_command,
}
