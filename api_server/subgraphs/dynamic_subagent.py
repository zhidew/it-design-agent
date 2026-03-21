"""
Dynamic Subagent Execution Module.

This module provides a unified interface for executing subagents based on their
configuration from AgentRegistry. It replaces hardcoded subgraph files with
a configuration-driven approach.

Usage:
    from subgraphs.dynamic_subagent import run_dynamic_subagent
    
    result = await run_dynamic_subagent(
        capability="data-design",
        state=state,
        base_dir=base_dir,
        ...
    )
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from services.llm_service import SubagentOutput

if TYPE_CHECKING:
    from registry.agent_registry import AgentFullConfig


MAX_REACT_STEPS = int(os.getenv("AGENT_MAX_REACT_STEPS", "12"))

# Default tools available to all subagents
DEFAULT_READ_TOOLS = {"list_files", "extract_structure", "grep_search", "read_file_chunk", "extract_lookup_values"}
DEFAULT_WRITE_TOOLS = {"write_file", "patch_file", "run_command"}




def build_react_system_prompt(
    capability: str,
    prompt_instructions: str,
    tools_allowed: List[str],
    candidate_files: List[str],
    workflow_steps: Optional[List[str]] = None,
    upstream_artifacts: Optional[Dict[str, List[str]]] = None,
) -> str:
    """
    Build the ReAct system prompt from agent configuration.
    
    Args:
        capability: Agent capability identifier
        prompt_instructions: Instructions extracted from SKILL.md
        tools_allowed: List of allowed tools
        candidate_files: Files available for reading
        workflow_steps: Optional workflow steps from SKILL.md
        upstream_artifacts: Dict mapping upstream agent -> list of artifact files
        (enables cross-agent memory)
        
    Returns:
        Formatted system prompt for ReAct loop
    """
    # Build tools section
    tools_section = """
Available tools:
- list_files / read_file_chunk / grep_search / extract_structure / extract_lookup_values (Read operations)
- write_file (Write design artifacts)
- patch_file (Make partial corrections)
- run_command (Execute shell commands, use with caution)
"""
    
    # Build workflow section if available
    workflow_section = ""
    if workflow_steps:
        workflow_section = f"""
Workflow Steps:
{chr(10).join(f'{i+1}. {step}' for i, step in enumerate(workflow_steps))}
"""
    
    # Build custom instructions section
    custom_section = ""
    if prompt_instructions:
        custom_section = f"""
Custom Instructions from SKILL.md:
{prompt_instructions}
"""
    
    # Build cross-agent memory section
    memory_section = ""
    if upstream_artifacts:
        memory_lines = []
        for upstream_agent, artifacts in upstream_artifacts.items():
            if artifacts:
                artifact_paths = [f"artifacts/{a}" for a in artifacts]
                memory_lines.append(f"- {upstream_agent}: {', '.join(artifact_paths)}")
        if memory_lines:
            memory_section = f"""
Cross-Agent Memory (upstream artifacts available for reading):
{chr(10).join(memory_lines)}

You can read these files using read_file_chunk with file_path like "artifacts/schema.sql".
"""
    
    system_prompt = f"""
You are the {capability} ReAct controller.
Choose one next action at a time to ground design artifacts.
{custom_section}
{tools_section}
{workflow_section}{memory_section}
Strategy:
1. Research: Use read tools to collect evidence from baseline/ and upstream artifacts/.
2. Write: Use write_file to produce draft artifacts.
3. Verify: Use read_file_chunk to read back and verify content if needed.
4. Patch: Use patch_file for minor adjustments.
5. Finalize: Set done=true only when all expected artifacts are correctly written.

Rules:
1. Only output one next action.
2. Stop only when you have enough evidence and have written all expected files.
3. Keep tool_input concise and machine-readable JSON.
4. Candidate files in baseline/: {candidate_files}

Return JSON in artifacts.decision:
{{
  "done": false,
  "thought": "why this step is needed",
  "tool_name": "grep_search" | "read_file_chunk" | "write_file" | "patch_file" | "none",
  "tool_input": {{}},
  "evidence_note": "what this step should confirm or produce"
}}
""".strip()
    
    return system_prompt


def build_final_artifacts_prompt(
    capability: str,
    prompt_instructions: str,
    expected_files: List[str],
    templates: Dict[str, str],
) -> str:
    """
    Build the final artifacts generation prompt.
    
    Args:
        capability: Agent capability identifier
        prompt_instructions: Instructions from SKILL.md
        expected_files: Files to generate
        templates: Template content for each file
        
    Returns:
        Formatted system prompt for final generation
    """
    template_sections = []
    for file_name in expected_files:
        template_content = templates.get(file_name, "")
        if template_content:
            # Truncate long templates
            preview = template_content[:800] if len(template_content) > 800 else template_content
            template_sections.append(f"[{file_name}]\n{preview}")
    
    templates_block = "\n\n".join(template_sections)
    
    custom_section = ""
    if prompt_instructions:
        custom_section = f"""
Additional Guidelines:
{prompt_instructions[:1000]}
"""
    
    system_prompt = f"""
You are a senior designer for {capability}.
Generate {', '.join(expected_files)} only from grounded evidence collected during the ReAct loop.

Requirements:
1. Reflect only content supported by the observations.
2. Use consistent naming conventions.
3. Include enough structure for downstream consumers.
4. Use the templates as style references.

{templates_block}
{custom_section}
""".strip()
    
    return system_prompt


def default_next_react_decision(
    generate_with_llm_fn: Callable[[str, str, List[str], int, Dict[str, Any] | None, str | None, str | None, str | None], SubagentOutput],
    capability: str,
    project_id: str,
    version: str,
    payload: Dict[str, Any],
    candidate_files: List[str],
    observations: List[Dict[str, Any]],
    templates: Dict[str, str],
    step: int,
    agent_config: Optional["AgentFullConfig"] = None,
    upstream_artifacts: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    """
    Default implementation for ReAct decision making.
    
    Uses AgentFullConfig for prompt construction if available.
    Supports cross-agent memory via upstream_artifacts parameter.
    """
    # Get configuration
    prompt_instructions = ""
    workflow_steps = None
    tools_allowed = []
    
    if agent_config:
        prompt_instructions = agent_config.prompt_instructions or ""
        workflow_steps = agent_config.workflow_steps or None
        tools_allowed = agent_config.tools_allowed or []
    
    system_prompt = build_react_system_prompt(
        capability=capability,
        prompt_instructions=prompt_instructions,
        tools_allowed=tools_allowed,
        candidate_files=candidate_files,
        workflow_steps=workflow_steps,
        upstream_artifacts=upstream_artifacts,
    )
    
    # Build template hints
    template_hints = {}
    for name, content in templates.items():
        if content:
            template_hints[name.replace(".", "_")] = content[:400]
    
    user_prompt = json.dumps(
        {
            "project": project_id,
            "version": version,
            "step": step,
            "requirements_payload": payload,
            "observations": observations,
            "template_hints": template_hints,
        },
        ensure_ascii=False,
        indent=2,
    )
    
    llm_output = generate_with_llm_fn(
        system_prompt, 
        user_prompt, 
        ["decision"],
        project_id=project_id,
        version=version,
        node_id=f"{capability}-react-step-{step}"
    )
    raw_decision = llm_output.artifacts.get("decision", "")
    
    try:
        decision = json.loads(raw_decision) if raw_decision else _fallback_decision(candidate_files)
    except json.JSONDecodeError:
        decision = _fallback_decision(candidate_files)
    
    if not isinstance(decision, dict):
        decision = _fallback_decision(candidate_files)
    
    decision.setdefault("done", False)
    decision.setdefault("tool_name", "none")
    decision.setdefault("tool_input", {})
    decision.setdefault("thought", "")
    decision.setdefault("evidence_note", "")
    decision["reasoning"] = llm_output.reasoning
    
    return decision


def default_generate_final_artifacts(
    generate_with_llm_fn: Callable[[str, str, List[str], int, Dict[str, Any] | None, str | None, str | None, str | None], SubagentOutput],
    capability: str,
    project_id: str,
    version: str,
    payload: Dict[str, Any],
    observations: List[Dict[str, Any]],
    templates: Dict[str, str],
    expected_files: List[str],
    agent_config: Optional["AgentFullConfig"] = None,
) -> SubagentOutput:
    """
    Default implementation for final artifacts generation.
    
    Uses AgentFullConfig for prompt construction if available.
    """
    prompt_instructions = ""
    if agent_config:
        prompt_instructions = agent_config.prompt_instructions or ""
    
    system_prompt = build_final_artifacts_prompt(
        capability=capability,
        prompt_instructions=prompt_instructions,
        expected_files=expected_files,
        templates=templates,
    )
    
    user_prompt = json.dumps(
        {
            "project": project_id,
            "version": version,
            "requirements_payload": payload,
            "grounded_observations": observations,
            "expected_files": expected_files,
        },
        ensure_ascii=False,
        indent=2,
    )
    
    return generate_with_llm_fn(
        system_prompt, 
        user_prompt, 
        expected_files,
        project_id=project_id,
        version=version,
        node_id=f"{capability}-final"
    )


def _fallback_decision(candidate_files: List[str]) -> Dict[str, Any]:
    """Generate a fallback decision when LLM fails."""
    if candidate_files:
        return {
            "done": False,
            "thought": "Starting evidence collection from available files",
            "tool_name": "read_file_chunk",
            "tool_input": {"file_name": candidate_files[0], "start_line": 1, "limit": 100},
            "evidence_note": "Reading initial requirements",
        }
    return {
        "done": True,
        "thought": "No candidate files available, proceeding to final generation",
        "tool_name": "none",
        "tool_input": {},
        "evidence_note": "",
    }


def default_fallback_artifacts(
    capability: str,
    payload: Dict[str, Any],
    observations: List[Dict[str, Any]],
    expected_files: List[str],
) -> SubagentOutput:
    """Generate minimal fallback artifacts when LLM generation fails."""
    artifacts = {}
    reasoning = f"Fallback generation for {capability} due to empty LLM output."
    
    for file_name in expected_files:
        # Create empty placeholder
        if file_name.endswith(".sql"):
            artifacts[file_name] = "-- Placeholder generated by fallback\n"
        elif file_name.endswith(".md"):
            artifacts[file_name] = f"# {file_name}\n\nPlaceholder content.\n"
        elif file_name.endswith(".yaml") or file_name.endswith(".yml"):
            artifacts[file_name] = "# Placeholder configuration\n"
        elif file_name.endswith(".json"):
            artifacts[file_name] = "{}\n"
        else:
            artifacts[file_name] = ""
    
    return SubagentOutput(reasoning=reasoning, artifacts=artifacts)


def default_tool_history_entries(tool_name: str, tool_result: Dict[str, Any]) -> List[str]:
    """Generate history entries from tool execution."""
    entries = []
    status = tool_result.get("status", "unknown")
    duration = tool_result.get("duration_ms", 0)
    
    if status == "success":
        entries.append(f"[TOOL] {tool_name} completed in {duration}ms")
    else:
        error_code = tool_result.get("error_code", "UNKNOWN")
        entries.append(f"[TOOL] {tool_name} failed: {error_code}")
    
    return entries


def default_build_evidence(
    capability: str,
    payload: Dict[str, Any],
    artifacts: Dict[str, str],
    observations: List[Dict[str, Any]],
    react_trace: List[Dict[str, Any]],
    tool_results: List[Dict[str, Any]],
    expected_files: List[str],
) -> Dict[str, Any]:
    """Build evidence document from execution trace."""
    return {
        "capability": capability,
        "mode": "dynamic_subagent",
        "expected_files": expected_files,
        "artifacts_generated": list(artifacts.keys()),
        "observation_count": len(observations),
        "tool_calls": len(tool_results),
        "success_rate": sum(1 for r in tool_results if r.get("status") == "success") / max(len(tool_results), 1),
    }


async def run_dynamic_subagent(
    *,
    capability: str,
    state: Dict[str, Any],
    base_dir: Path,
    generate_with_llm_fn: Callable[[str, str, List[str], int, Dict[str, Any] | None, str | None, str | None, str | None], SubagentOutput],
    execute_tool_fn: Callable[[str, Dict[str, Any] | None], Dict[str, Any]],
    update_task_status_fn: Callable[[List[Dict[str, Any]], str, str], List[Dict[str, Any]]],
    agent_config: Optional["AgentFullConfig"] = None,
    max_react_steps: int = MAX_REACT_STEPS,
    enable_permission_check: bool = True,
    # Optional overrides for custom behavior
    next_decision_fn: Optional[Callable] = None,
    generate_final_artifacts_fn: Optional[Callable] = None,
    fallback_artifacts_fn: Optional[Callable] = None,
    expected_files_fn: Optional[Callable] = None,
    candidate_files_fn: Optional[Callable] = None,
) -> Dict[str, Any]:
    """
    Execute a subagent dynamically based on its configuration.
    
    This function loads the agent configuration from AgentRegistry and uses
    it to construct prompts, validate tool permissions, and determine expected
    outputs.
    
    Args:
        capability: Agent capability identifier (e.g., "data-design")
        state: Current workflow state
        base_dir: Project base directory
        generate_with_llm_fn: LLM generation function
        execute_tool_fn: Tool execution function
        update_task_status_fn: Task status update function
        agent_config: Pre-loaded AgentFullConfig (optional, loads from registry if not provided)
        max_react_steps: Maximum ReAct loop iterations
        enable_permission_check: Whether to check tool permissions
        next_decision_fn: Override for ReAct decision function
        generate_final_artifacts_fn: Override for final generation function
        fallback_artifacts_fn: Override for fallback generation function
        expected_files_fn: Override for expected files function
        candidate_files_fn: Override for candidate files function
        
    Returns:
        Updated state dictionary with execution results
    """
    import asyncio
    from registry.agent_registry import AgentRegistry
    
    # Load agent config if not provided
    if agent_config is None:
        try:
            registry = AgentRegistry.get_instance()
            agent_config = registry.load_full_config(capability)
        except RuntimeError:
            # Registry not initialized, proceed without config
            pass
    
    project_id = state["project_id"]
    version = state["version"]
    project_path = base_dir / "projects" / project_id / version
    baseline_path = project_path / "baseline" / "requirements.json"
    baseline_dir = baseline_path.parent
    artifacts_dir = project_path / "artifacts"
    logs_dir = project_path / "logs"
    evidence_dir = project_path / "evidence"

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    payload = json.loads(baseline_path.read_text(encoding="utf-8-sig"))
    history_updates = []
    
    # Determine candidate files
    if candidate_files_fn:
        candidate_files = candidate_files_fn(payload)
    else:
        candidate_files = payload.get("uploaded_files", []) or ["original-requirements.md"]
        candidate_files = [f for f in candidate_files if f.endswith((".md", ".txt", ".json", ".yaml", ".yml"))]
        if not candidate_files:
            candidate_files = ["original-requirements.md"]
    
    # Determine expected files
    if expected_files_fn:
        expected_files = expected_files_fn(payload)
    elif agent_config and agent_config.metadata.get("expected_outputs"):
        expected_files = agent_config.metadata["expected_outputs"]
    else:
        # Default based on capability
        expected_files = _default_expected_files(capability)
    
    # Discover upstream artifacts for cross-agent memory
    upstream_artifacts = _discover_upstream_artifacts(capability, artifacts_dir)
    if upstream_artifacts:
        upstream_summary = {k: v for k, v in upstream_artifacts.items() if v}
        history_updates.append(
            f"[SYSTEM] Cross-agent memory: found upstream artifacts: {upstream_summary}"
        )
    
    # Load templates
    templates = await asyncio.to_thread(
        _load_templates_for_capability,
        base_dir,
        capability,
        agent_config,
    )

    history_updates.append(f"[SYSTEM] Dynamic subagent '{capability}' is now running.")
    tool_results: List[Dict[str, Any]] = []
    react_trace: List[Dict[str, Any]] = []
    observations: List[Dict[str, Any]] = []

    # Permission-aware tool executor
    def _execute_tool_with_permission(tool_name: str, tool_input: Dict[str, Any] | None) -> Dict[str, Any]:
        if enable_permission_check:
            from api_server.graphs.tools.protocol import execute_tool_with_permission
            return execute_tool_with_permission(
                tool_name, tool_input, agent_capability=capability
            )
        return execute_tool_fn(tool_name, tool_input)

    try:
        for step in range(1, max_react_steps + 1):
            # Use custom or default decision function
            if next_decision_fn:
                decision = await asyncio.to_thread(
                    next_decision_fn,
                    payload,
                    observations,
                    templates,
                    step,
                )
            else:
                decision = await asyncio.to_thread(
                    default_next_react_decision,
                    generate_with_llm_fn,
                    capability,
                    project_id,
                    version,
                    payload,
                    candidate_files,
                    observations,
                    templates,
                    step,
                    agent_config,
                    upstream_artifacts,
                )
            
            react_trace.append({"step": step, **decision})
            thought = decision.get("thought", "")
            if thought:
                history_updates.append(f"[{capability}] ReAct step {step}: {thought}")


            if decision.get("done"):
                history_updates.append(f"[{capability}] ReAct step {step}: evidence collection complete.")
                break

            tool_name = decision.get("tool_name") or "none"
            tool_input = dict(decision.get("tool_input") or {})
            
            # Set root_dir based on tool type for cross-agent memory
            # - Write tools: write to artifacts directory
            # - Read tools: can read from project root (baseline/, artifacts/, evidence/)
            # This enables downstream agents to read upstream artifacts
            if tool_name in DEFAULT_WRITE_TOOLS:
                tool_input["root_dir"] = str(artifacts_dir)
            else:
                # Read tools can access project root for cross-agent memory
                tool_input["root_dir"] = str(project_path)

            tool_result = await asyncio.to_thread(_execute_tool_with_permission, tool_name, tool_input)
            tool_results.append(tool_result)
            react_trace[-1]["tool_result"] = {
                "status": tool_result.get("status"),
                "error_code": tool_result.get("error_code"),
                "duration_ms": tool_result.get("duration_ms"),
            }
            
            history_updates.extend(default_tool_history_entries(tool_name, tool_result))
            observations.append(
                {
                    "step": step,
                    "tool_name": tool_name,
                    "tool_input": tool_result.get("input") or {},
                    "tool_output": tool_result.get("output") or {},
                    "evidence_note": decision.get("evidence_note", ""),
                }
            )
        else:
            history_updates.append(
                f"[{capability}] ReAct step {max_react_steps}: reached max steps."
            )

        # Generate final artifacts
        if generate_final_artifacts_fn:
            llm_output = await asyncio.to_thread(
                generate_final_artifacts_fn,
                payload,
                observations,
                templates,
                expected_files,
            )
        else:
            llm_output = await asyncio.to_thread(
                default_generate_final_artifacts,
                generate_with_llm_fn,
                capability,
                project_id,
                version,
                payload,
                observations,
                templates,
                expected_files,
                agent_config,
            )

        # Fallback if empty
        if any(not (llm_output.artifacts.get(name) or "").strip() for name in expected_files):
            if fallback_artifacts_fn:
                llm_output = fallback_artifacts_fn(payload, observations, expected_files)
            else:
                llm_output = default_fallback_artifacts(capability, payload, observations, expected_files)

        # Write reasoning
        reasoning_sections = [entry.get("reasoning", "") for entry in react_trace if entry.get("reasoning")]
        reasoning_sections.append(llm_output.reasoning)
        (logs_dir / f"{capability}-reasoning.md").write_text(
            "\n\n".join(section for section in reasoning_sections if section),
            encoding="utf-8",
        )

        # Write artifacts
        for artifact_name in expected_files:
            (artifacts_dir / artifact_name).write_text(
                llm_output.artifacts.get(artifact_name, ""),
                encoding="utf-8"
            )

        # Build evidence
        evidence = default_build_evidence(
            capability,
            payload,
            llm_output.artifacts,
            observations,
            react_trace,
            tool_results,
            expected_files,
        )
        evidence.setdefault("source_files", candidate_files)
        evidence.setdefault(
            "tool_trace",
            [
                {
                    "tool_name": result["tool_name"],
                    "status": result["status"],
                    "error_code": result["error_code"],
                    "duration_ms": result["duration_ms"],
                }
                for result in tool_results
            ],
        )
        evidence.setdefault("react_trace", react_trace)
        (evidence_dir / f"{capability}.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        history_updates.append(f"[{capability}] Completed with status: success")
        return {
            "history": history_updates,
            "task_queue": update_task_status_fn(state["task_queue"], capability, "success"),
            "human_intervention_required": False,
            "last_worker": capability,
            "tool_results": tool_results,
        }
    except Exception as exc:
        history_updates.append(f"[{capability}] [ERROR] {exc}")
        return {
            "history": history_updates,
            "task_queue": update_task_status_fn(state["task_queue"], capability, "failed"),
            "human_intervention_required": False,
            "last_worker": capability,
            "tool_results": tool_results,
        }


def _load_templates_for_capability(
    base_dir: Path,
    capability: str,
    agent_config: Optional["AgentFullConfig"],
) -> Dict[str, str]:
    """Load templates for a specific capability."""
    templates = {}
    
    # First, try to use templates from agent_config
    if agent_config and agent_config.templates:
        templates.update(agent_config.templates)
    
    # Then, load from default template directory
    template_dir = base_dir / "skills" / capability / "assets" / "templates"
    if template_dir.exists():
        for template_file in template_dir.glob("*"):
            if template_file.is_file():
                templates[template_file.name] = template_file.read_text(encoding="utf-8")
    
    # Also check global templates
    global_template_dir = base_dir / "assets" / "templates"
    if global_template_dir.exists():
        for template_file in global_template_dir.glob("*"):
            if template_file.is_file() and template_file.name not in templates:
                templates[template_file.name] = template_file.read_text(encoding="utf-8")
    
    return templates


# Cross-agent memory: upstream artifact mapping
# Defines which upstream artifacts each agent should read for cross-agent memory
# Note: This is a fallback when registry is not available; prefer registry configuration
UPSTREAM_ARTIFACT_MAPPING_FALLBACK: Dict[str, Dict[str, List[str]]] = {
    "api-design": {
        "data-design": ["schema.sql", "er.md"],
        "ddd-structure": ["ddd-structure.md", "class-domain.md"],
    },
    "integration-design": {
        "api-design": ["api-internal.yaml", "api-public.yaml"],
        "data-design": ["schema.sql"],
    },
    "test-design": {
        "flow-design": ["sequence-example.md", "state-example.md"],
        "api-design": ["api-internal.yaml"],
    },
    "ops-design": {
        "config-design": ["config-catalog.yaml"],
        "flow-design": ["sequence-example.md"],
    },
    "ddd-structure": {
        "data-design": ["schema.sql", "er.md"],
    },
}


def _get_expected_artifacts_by_agent() -> Dict[str, List[str]]:
    """Get expected artifacts mapping from registry. Returns {capability: [expected_outputs]}."""
    try:
        from registry.expert_registry import ExpertRegistry
        registry = ExpertRegistry.get_instance()
        return {
            manifest.capability: manifest.expected_outputs
            for manifest in registry.get_all_manifests()
            if manifest.expected_outputs
        }
    except RuntimeError:
        return {}


def _get_upstream_artifact_mapping() -> Dict[str, Dict[str, List[str]]]:
    """Get upstream artifact mapping from registry config.
    
    Reads from expert.yaml `upstream_artifacts` field if defined.
    Falls back to UPSTREAM_ARTIFACT_MAPPING_FALLBACK.
    """
    try:
        from registry.expert_registry import ExpertRegistry
        registry = ExpertRegistry.get_instance()
        result: Dict[str, Dict[str, List[str]]] = {}
        for manifest in registry.get_all_manifests():
            if manifest.expert_yaml_path:
                import yaml
                try:
                    with open(manifest.expert_yaml_path, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f) or {}
                    upstream = data.get("upstream_artifacts", {})
                    if upstream:
                        result[manifest.capability] = upstream
                except Exception:
                    pass
        return result if result else UPSTREAM_ARTIFACT_MAPPING_FALLBACK
    except RuntimeError:
        return UPSTREAM_ARTIFACT_MAPPING_FALLBACK


def _discover_upstream_artifacts(capability: str, artifacts_dir: Path) -> Dict[str, List[str]]:
    """
    Discover upstream artifacts that exist in the artifacts directory.
    
    This enables cross-agent memory: downstream agents can read artifacts
    produced by upstream agents.
    
    Args:
        capability: Current agent's capability
        artifacts_dir: Path to the artifacts directory
        
    Returns:
        Dict mapping upstream agent -> list of existing artifact files
    """
    upstream_map = _get_upstream_artifact_mapping().get(capability, {})
    if not upstream_map:
        return {}
    
    discovered: Dict[str, List[str]] = {}
    
    if not artifacts_dir.exists():
        return discovered
    
    existing_files = set()
    for f in artifacts_dir.iterdir():
        if f.is_file():
            existing_files.add(f.name)
    
    for upstream_agent, expected_files in upstream_map.items():
        found = [f for f in expected_files if f in existing_files]
        if found:
            discovered[upstream_agent] = found
    
    return discovered


def _default_expected_files(capability: str) -> List[str]:
    """Get default expected files for a capability from registry."""
    artifacts_map = _get_expected_artifacts_by_agent()
    if capability in artifacts_map:
        return artifacts_map[capability]
    return ["output.md"]
