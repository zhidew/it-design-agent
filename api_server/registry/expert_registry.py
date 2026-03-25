"""
Expert Registry - Centralized expert profile management.

The runtime still exposes compatibility aliases for the historical
Agent* class names so existing orchestrator code can keep working while
the product surface shifts to the Expert mental model.
"""

import asyncio
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .errors import AgentNotFoundError, ConfigLoadError, ValidationError
from .skill_parser import SkillParser


@dataclass
class ExpertProfile:
    """Lightweight expert metadata used for discovery and routing."""

    capability: str
    name: str
    description: str
    keywords: List[str] = field(default_factory=list)
    required_inputs: List[str] = field(default_factory=list)
    expected_outputs: List[str] = field(default_factory=list)
    expert_yaml_path: Optional[str] = None
    skill_md_path: Optional[str] = None
    # Hot-pluggable task scheduling configuration
    dependencies: List[str] = field(default_factory=list)
    priority: int = 50

    @property
    def expertise(self) -> List[str]:
        return list(self.keywords)

    @property
    def agent_yaml_path(self) -> Optional[str]:
        return self.expert_yaml_path

    def to_planner_description(self) -> str:
        return f"- {self.capability}: {self.description}"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def matches_keywords(self, search_terms: List[str]) -> bool:
        search_lower = [t.lower() for t in search_terms]
        keyword_lower = [k.lower() for k in self.keywords]
        return any(
            term in keyword_lower or any(term in kw for kw in keyword_lower)
            for term in search_lower
        )


@dataclass
class ExpertConfig:
    """Complete expert configuration used at execution time."""

    manifest: ExpertProfile
    tools_allowed: List[str] = field(default_factory=list)
    policies: Dict[str, Any] = field(default_factory=dict)
    workflow_steps: List[str] = field(default_factory=list)
    prompt_instructions: str = ""
    templates: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def dependencies(self) -> List[str]:
        """Get expert dependencies for task scheduling."""
        return self.manifest.dependencies

    @property
    def priority(self) -> int:
        """Get expert priority for task scheduling."""
        return self.manifest.priority

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability": self.manifest.capability,
            "name": self.manifest.name,
            "description": self.manifest.description,
            "tools_allowed": self.tools_allowed,
            "policies": self.policies,
            "workflow_steps": self.workflow_steps,
            "prompt_instructions_length": len(self.prompt_instructions),
            "templates": list(self.templates.keys()),
            "metadata": self.metadata,
            "dependencies": self.dependencies,
            "priority": self.priority,
        }

    def has_tool_permission(self, tool_name: str) -> bool:
        default_read_tools = {
            "list_files",
            "extract_structure",
            "grep_search",
            "read_file_chunk",
            "extract_lookup_values",
            "clone_repository",
            "query_database",
            "query_knowledge_base",
        }
        return (
            tool_name in self.tools_allowed
            or "*" in self.tools_allowed
            or tool_name in default_read_tools
        )


class ExpertRegistry:
    """Thread-safe singleton for managing expert profiles."""

    _instance: Optional["ExpertRegistry"] = None
    _lock = threading.Lock()

    def __init__(self, base_dir: Optional[Path] = None):
        if hasattr(self, "_initialized") and self._initialized:
            return
        if base_dir:
            self._base_dir = Path(base_dir)
            self._manifests: Dict[str, ExpertProfile] = {}
            self._configs: Dict[str, ExpertConfig] = {}
            self._skill_parser = SkillParser()
            self._load_errors: List[str] = []
            self._initialized = True

    @classmethod
    def get_instance(cls) -> "ExpertRegistry":
        if cls._instance is None or not getattr(cls._instance, "_initialized", False):
            raise RuntimeError(
                "ExpertRegistry not initialized. "
                "Call ExpertRegistry.initialize() first."
            )
        return cls._instance

    @classmethod
    def initialize(cls, base_dir: Path) -> "ExpertRegistry":
        with cls._lock:
            if cls._instance is not None and getattr(cls._instance, "_initialized", False):
                return cls._instance

            instance = object.__new__(cls)
            instance._base_dir = Path(base_dir)
            instance._manifests = {}
            instance._configs = {}
            instance._skill_parser = SkillParser()
            instance._load_errors = []
            instance._initialized = False

            cls._instance = instance
            instance._load_all_manifests()
            instance._initialized = True
            return instance

    @classmethod
    async def initialize_async(cls, base_dir: Path) -> "ExpertRegistry":
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: cls.initialize(base_dir))

    @classmethod
    def reset(cls):
        with cls._lock:
            cls._instance = None

    def _resolve_experts_dir(self) -> Path:
        preferred = self._base_dir / "experts"
        legacy = self._base_dir / "subagents"
        if preferred.exists():
            return preferred
        return legacy

    def _load_all_manifests(self) -> None:
        experts_dir = self._resolve_experts_dir()
        skills_dir = self._base_dir / "skills"

        self._load_errors = []
        if not experts_dir.exists():
            self._load_errors.append(f"Experts directory not found: {experts_dir}")
            return

        expert_files = list(experts_dir.glob("*.expert.yaml")) + list(experts_dir.glob("*.agent.yaml"))
        for expert_file in expert_files:
            try:
                manifest = self._load_expert_profile(expert_file, skills_dir)
                if manifest:
                    self._manifests[manifest.capability] = manifest
            except Exception as exc:
                self._load_errors.append(f"Failed to load {expert_file.name}: {exc}")

    def _load_expert_profile(
        self,
        expert_file: Path,
        skills_dir: Path,
    ) -> Optional[ExpertProfile]:
        try:
            with open(expert_file, "r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
        except yaml.YAMLError as exc:
            raise ConfigLoadError(str(expert_file), f"Invalid YAML: {exc}")
        except Exception as exc:
            raise ConfigLoadError(str(expert_file), f"Failed to read file: {exc}")

        capability = data.get("capability")
        if not capability:
            stem = expert_file.stem
            capability = stem.replace(".expert", "").replace(".agent", "")
        if not capability:
            raise ValidationError("capability", None, "Missing capability")

        skill_path = skills_dir / capability / "SKILL.md"
        skill_frontmatter: Dict[str, Any] = {}
        if skill_path.exists():
            try:
                skill_frontmatter, _ = self._skill_parser.parse(skill_path)
            except Exception as exc:
                self._load_errors.append(f"Warning: Could not parse {skill_path}: {exc}")

        name = data.get("name") or skill_frontmatter.get("name") or capability
        description = (
            skill_frontmatter.get("description")
            or data.get("description")
            or f"Expert for {capability}"
        )
        keywords = skill_frontmatter.get("keywords") or data.get("keywords") or []
        if isinstance(keywords, str):
            keywords = [item.strip() for item in keywords.split(",")]

        # Parse hot-pluggable scheduling configuration
        scheduling = data.get("scheduling", {})
        dependencies = scheduling.get("dependencies", [])
        priority = scheduling.get("priority", 50)

        return ExpertProfile(
            capability=capability,
            name=name,
            description=description,
            keywords=list(keywords),
            required_inputs=data.get("inputs", {}).get("required", []),
            expected_outputs=data.get("outputs", {}).get("expected", []),
            expert_yaml_path=str(expert_file),
            skill_md_path=str(skill_path) if skill_path.exists() else None,
            dependencies=list(dependencies),
            priority=int(priority),
        )

    def get_all_manifests(self) -> List[ExpertProfile]:
        return list(self._manifests.values())

    def get_manifest(self, capability: str) -> Optional[ExpertProfile]:
        return self._manifests.get(capability)

    def get_manifests_by_keywords(self, keywords: List[str]) -> List[ExpertProfile]:
        return [m for m in self._manifests.values() if m.matches_keywords(keywords)]

    def get_planner_agent_descriptions(self, filter_ids: Optional[List[str]] = None) -> str:
        """Get description of all experts, optionally filtered by IDs."""
        manifests = self._manifests.values()
        if filter_ids is not None:
            manifests = [m for m in manifests if m.capability in filter_ids]

        descriptions = [
            manifest.to_planner_description()
            for manifest in sorted(manifests, key=lambda item: item.capability)
        ]
        return "\n".join(descriptions)

    def get_capabilities(self) -> List[str]:
        return list(self._manifests.keys())

    def get_load_errors(self) -> List[str]:
        return list(self._load_errors)

    def load_full_config(self, capability: str) -> ExpertConfig:
        if capability in self._configs:
            return self._configs[capability]

        manifest = self._manifests.get(capability)
        if not manifest:
            raise AgentNotFoundError(capability)

        expert_data: Dict[str, Any] = {}
        if manifest.expert_yaml_path:
            try:
                with open(manifest.expert_yaml_path, "r", encoding="utf-8") as handle:
                    expert_data = yaml.safe_load(handle) or {}
            except Exception as exc:
                self._load_errors.append(f"Failed to reload {manifest.expert_yaml_path}: {exc}")

        workflow_steps: List[str] = []
        prompt_instructions = ""
        if manifest.skill_md_path:
            try:
                skill_path = Path(manifest.skill_md_path)
                _, body = self._skill_parser.parse(skill_path)
                workflow_steps = self._skill_parser.extract_workflow(body)
                prompt_instructions = self._skill_parser.build_prompt_instructions(body)
            except Exception as exc:
                self._load_errors.append(f"Failed to parse {manifest.skill_md_path}: {exc}")

        config = ExpertConfig(
            manifest=manifest,
            tools_allowed=expert_data.get("tools", {}).get("allowed", []),
            policies=expert_data.get("policies", {}),
            workflow_steps=workflow_steps,
            prompt_instructions=prompt_instructions,
            templates=self._load_templates(capability),
            metadata={
                **expert_data.get("metadata", {}),
                "execution": expert_data.get("execution", {}),
                "expected_outputs": manifest.expected_outputs,
            },
        )
        self._configs[capability] = config
        return config

    def _load_templates(self, capability: str) -> Dict[str, str]:
        templates: Dict[str, str] = {}
        template_dir = self._base_dir / "skills" / capability / "assets" / "templates"
        if not template_dir.exists():
            return templates

        for template_file in template_dir.glob("*"):
            if template_file.is_file():
                try:
                    templates[template_file.name] = template_file.read_text(encoding="utf-8")
                except Exception as exc:
                    self._load_errors.append(f"Failed to load template {template_file}: {exc}")
        return templates

    def clear_config_cache(self, capability: str = None) -> None:
        if capability:
            self._configs.pop(capability, None)
        else:
            self._configs.clear()

    def reload(self) -> None:
        self._manifests.clear()
        self._configs.clear()
        self._load_errors.clear()
        self._load_all_manifests()

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_experts": len(self._manifests),
            "total_agents": len(self._manifests),
            "cached_configs": len(self._configs),
            "load_errors": list(self._load_errors),
            "capabilities": self.get_capabilities(),
        }


# Backward-compatible aliases for existing runtime imports.
AgentManifest = ExpertProfile
AgentFullConfig = ExpertConfig
AgentRegistry = ExpertRegistry
