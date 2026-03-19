"""
Agent Registry - Centralized agent configuration management

Provides:
- AgentManifest: Lightweight metadata for planner discovery
- AgentFullConfig: Complete configuration for execution
- AgentRegistry: Thread-safe singleton for managing agent configurations

Design principles:
1. Pre-load metadata at startup for fast planner queries
2. Lazy-load full configurations when needed for execution
3. Validate configurations and provide clear error messages
"""

import asyncio
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any
import yaml
import threading

from .errors import (
    ConfigLoadError,
    SkillParseError,
    AgentNotFoundError,
    ValidationError,
)
from .skill_parser import SkillParser


@dataclass
class AgentManifest:
    """
    Agent metadata for planner discovery and routing.
    
    This is a lightweight representation loaded at startup,
    used by the planner to determine which agents to invoke.
    """
    
    # Unique identifier (e.g., "api-design")
    capability: str
    
    # Display name (e.g., "API Design Agent")
    name: str
    
    # Short description for planner prompt
    description: str
    
    # Keywords for matching requirements to agents
    keywords: List[str] = field(default_factory=list)
    
    # Input requirements
    required_inputs: List[str] = field(default_factory=list)
    
    # Expected output artifacts
    expected_outputs: List[str] = field(default_factory=list)
    
    # Source file paths (for debugging and hot-reload)
    agent_yaml_path: Optional[str] = None
    skill_md_path: Optional[str] = None
    
    def to_planner_description(self) -> str:
        """Generate description text for planner prompt."""
        return f"- {self.capability}: {self.description}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    def matches_keywords(self, search_terms: List[str]) -> bool:
        """Check if any search term matches this agent's keywords."""
        search_lower = [t.lower() for t in search_terms]
        keyword_lower = [k.lower() for k in self.keywords]
        
        return any(
            term in keyword_lower or 
            any(term in kw for kw in keyword_lower)
            for term in search_lower
        )


@dataclass
class AgentFullConfig:
    """
    Complete agent configuration for execution.
    
    Loaded lazily when a subgraph is about to execute.
    Contains all information needed to run the agent.
    """
    
    # Base manifest
    manifest: AgentManifest
    
    # Tool permissions from agent.yaml
    tools_allowed: List[str] = field(default_factory=list)
    
    # Policy constraints from agent.yaml
    policies: Dict[str, Any] = field(default_factory=dict)
    
    # Workflow steps extracted from SKILL.md
    workflow_steps: List[str] = field(default_factory=list)
    
    # Prompt instructions built from SKILL.md
    prompt_instructions: str = ""
    
    # Template files from assets/templates/
    templates: Dict[str, str] = field(default_factory=dict)
    
    # Additional metadata from agent.yaml
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "capability": self.manifest.capability,
            "name": self.manifest.name,
            "description": self.manifest.description,
            "tools_allowed": self.tools_allowed,
            "policies": self.policies,
            "workflow_steps": self.workflow_steps,
            "prompt_instructions_length": len(self.prompt_instructions),
            "templates": list(self.templates.keys()),
            "metadata": self.metadata,
        }
        return result
    
    def has_tool_permission(self, tool_name: str) -> bool:
        """Check if the tool is allowed for this agent.
        
        Default read tools are always allowed:
        - list_files, extract_structure, grep_search, read_file_chunk, extract_lookup_values
        """
        DEFAULT_READ_TOOLS = {
            "list_files", 
            "extract_structure", 
            "grep_search", 
            "read_file_chunk", 
            "extract_lookup_values"
        }
        return (
            tool_name in self.tools_allowed or 
            "*" in self.tools_allowed or
            tool_name in DEFAULT_READ_TOOLS
        )


class AgentRegistry:
    """
    Thread-safe singleton for managing agent configurations.
    
    Lifecycle:
    1. At startup: Call initialize() to load all manifests
    2. At runtime: Use get_manifest() for planner queries
    3. Before execution: Use load_full_config() for complete config
    
    Example:
        # Startup
        registry = await AgentRegistry.initialize(base_dir)
        
        # Planner query
        manifests = registry.get_all_manifests()
        descriptions = registry.get_planner_agent_descriptions()
        
        # Execution
        config = registry.load_full_config("api-design")
        if config.has_tool_permission("write_file"):
            # ... execute with permission
    """
    
    _instance: Optional['AgentRegistry'] = None
    _lock = threading.Lock()
    
    def __init__(self, base_dir: Optional[Path] = None):
        """
        Initialize the registry.
        
        Args:
            base_dir: Base directory containing subagents/ and skills/ directories
        """
        # Prevent re-initialization
        if hasattr(self, '_initialized') and self._initialized:
            return
        
        if base_dir:
            self._base_dir = Path(base_dir)
            self._manifests: Dict[str, AgentManifest] = {}
            self._configs: Dict[str, AgentFullConfig] = {}
            self._skill_parser = SkillParser()
            self._load_errors: List[str] = []
            self._initialized = True
    
    @classmethod
    def get_instance(cls) -> 'AgentRegistry':
        """
        Get the singleton instance.
        
        Raises:
            RuntimeError: If registry not initialized
        """
        if cls._instance is None or not getattr(cls._instance, '_initialized', False):
            raise RuntimeError(
                "AgentRegistry not initialized. "
                "Call AgentRegistry.initialize() first."
            )
        return cls._instance
    
    @classmethod
    def initialize(cls, base_dir: Path) -> 'AgentRegistry':
        """
        Initialize the registry synchronously.
        
        Call this at application startup.
        
        Args:
            base_dir: Base directory containing subagents/ and skills/
            
        Returns:
            The initialized registry instance
        """
        with cls._lock:
            # Double-check locking pattern
            if cls._instance is not None and getattr(cls._instance, '_initialized', False):
                return cls._instance
            
            # Create new instance
            instance = object.__new__(cls)
            instance._base_dir = Path(base_dir)
            instance._manifests = {}
            instance._configs = {}
            instance._skill_parser = SkillParser()
            instance._load_errors = []
            instance._initialized = False
            
            # Set instance before loading to prevent recursion
            cls._instance = instance
            
            # Load manifests
            instance._load_all_manifests()
            instance._initialized = True
            
            return instance
    
    @classmethod
    async def initialize_async(cls, base_dir: Path) -> 'AgentRegistry':
        """
        Initialize the registry asynchronously.
        
        Call this at application startup in async context.
        
        Args:
            base_dir: Base directory containing subagents/ and skills/
            
        Returns:
            The initialized registry instance
        """
        # Use synchronous initialization with thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: cls.initialize(base_dir))
    
    @classmethod
    def reset(cls):
        """
        Reset the singleton instance.
        
        Use only for testing!
        """
        with cls._lock:
            cls._instance = None
    
    def _load_all_manifests(self) -> None:
        """Load all agent manifests from subagents/ directory."""
        agents_dir = self._base_dir / "subagents"
        skills_dir = self._base_dir / "skills"
        
        self._load_errors = []
        
        if not agents_dir.exists():
            self._load_errors.append(f"Subagents directory not found: {agents_dir}")
            return
        
        for agent_file in agents_dir.glob("*.agent.yaml"):
            try:
                manifest = self._load_agent_manifest(agent_file, skills_dir)
                if manifest:
                    self._manifests[manifest.capability] = manifest
            except Exception as e:
                error_msg = f"Failed to load {agent_file.name}: {e}"
                self._load_errors.append(error_msg)
                # Continue loading other agents
    
    def _load_agent_manifest(
        self, 
        agent_file: Path, 
        skills_dir: Path
    ) -> Optional[AgentManifest]:
        """
        Load a single agent manifest from agent.yaml file.
        
        Args:
            agent_file: Path to the agent.yaml file
            skills_dir: Path to the skills directory
            
        Returns:
            AgentManifest or None if loading fails
        """
        try:
            with open(agent_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ConfigLoadError(str(agent_file), f"Invalid YAML: {e}")
        except Exception as e:
            raise ConfigLoadError(str(agent_file), f"Failed to read file: {e}")
        
        # Extract capability from filename if not in YAML
        capability = data.get('capability')
        if not capability:
            # Extract from filename: "api-design.agent.yaml" -> "api-design"
            stem = agent_file.stem  # "api-design.agent"
            capability = stem.replace('.agent', '')
        
        if not capability:
            raise ValidationError('capability', None, 'Missing capability')
        
        # Try to load corresponding SKILL.md
        skill_path = skills_dir / capability / "SKILL.md"
        skill_frontmatter = {}
        
        if skill_path.exists():
            try:
                skill_frontmatter, _ = self._skill_parser.parse(skill_path)
            except Exception as e:
                # Log warning but continue
                self._load_errors.append(
                    f"Warning: Could not parse {skill_path}: {e}"
                )
        
        # Build manifest with fallbacks
        name = (
            data.get('name') or 
            skill_frontmatter.get('name') or 
            capability
        )
        description = (
            skill_frontmatter.get('description') or 
            data.get('description') or 
            f"Agent for {capability}"
        )
        keywords = (
            skill_frontmatter.get('keywords') or 
            data.get('keywords') or 
            []
        )
        
        # Handle keywords that might be string instead of list
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(',')]
        
        return AgentManifest(
            capability=capability,
            name=name,
            description=description,
            keywords=list(keywords),
            required_inputs=data.get('inputs', {}).get('required', []),
            expected_outputs=data.get('outputs', {}).get('expected', []),
            agent_yaml_path=str(agent_file),
            skill_md_path=str(skill_path) if skill_path.exists() else None,
        )
    
    # === Query Methods ===
    
    def get_all_manifests(self) -> List[AgentManifest]:
        """Get all agent manifests for planner."""
        return list(self._manifests.values())
    
    def get_manifest(self, capability: str) -> Optional[AgentManifest]:
        """Get a single agent manifest by capability."""
        return self._manifests.get(capability)
    
    def get_manifests_by_keywords(self, keywords: List[str]) -> List[AgentManifest]:
        """Get agents matching any of the given keywords."""
        return [
            m for m in self._manifests.values()
            if m.matches_keywords(keywords)
        ]
    
    def get_planner_agent_descriptions(self) -> str:
        """
        Generate agent descriptions for planner prompt.
        
        Returns a formatted string listing all available agents.
        """
        descriptions = [
            m.to_planner_description() 
            for m in sorted(
                self._manifests.values(), 
                key=lambda x: x.capability
            )
        ]
        return '\n'.join(descriptions)
    
    def get_capabilities(self) -> List[str]:
        """Get list of all capability names."""
        return list(self._manifests.keys())
    
    def get_load_errors(self) -> List[str]:
        """Get any errors that occurred during loading."""
        return list(self._load_errors)
    
    # === Configuration Loading ===
    
    def load_full_config(self, capability: str) -> AgentFullConfig:
        """
        Load complete configuration for an agent.
        
        This is called lazily before the agent executes.
        Results are cached for subsequent calls.
        
        Args:
            capability: The agent's capability identifier
            
        Returns:
            AgentFullConfig with all settings
            
        Raises:
            AgentNotFoundError: If agent not in registry
        """
        # Check cache first
        if capability in self._configs:
            return self._configs[capability]
        
        manifest = self._manifests.get(capability)
        if not manifest:
            raise AgentNotFoundError(capability)
        
        # Load agent.yaml content
        agent_data = {}
        if manifest.agent_yaml_path:
            try:
                with open(manifest.agent_yaml_path, 'r', encoding='utf-8') as f:
                    agent_data = yaml.safe_load(f) or {}
            except Exception as e:
                self._load_errors.append(
                    f"Failed to reload {manifest.agent_yaml_path}: {e}"
                )
        
        # Parse SKILL.md for workflow
        workflow_steps = []
        prompt_instructions = ""
        
        if manifest.skill_md_path:
            try:
                skill_path = Path(manifest.skill_md_path)
                _, body = self._skill_parser.parse(skill_path)
                workflow_steps = self._skill_parser.extract_workflow(body)
                prompt_instructions = self._skill_parser.build_prompt_instructions(body)
            except Exception as e:
                self._load_errors.append(
                    f"Failed to parse {manifest.skill_md_path}: {e}"
                )
        
        # Load templates
        templates = self._load_templates(capability)
        
        # Build full config
        config = AgentFullConfig(
            manifest=manifest,
            tools_allowed=agent_data.get('tools', {}).get('allowed', []),
            policies=agent_data.get('policies', {}),
            workflow_steps=workflow_steps,
            prompt_instructions=prompt_instructions,
            templates=templates,
            metadata={
                **agent_data.get('metadata', {}),
                "expected_outputs": manifest.expected_outputs
            },
        )
        
        # Cache and return
        self._configs[capability] = config
        return config
    
    def _load_templates(self, capability: str) -> Dict[str, str]:
        """Load template files for a capability."""
        templates = {}
        template_dir = self._base_dir / "skills" / capability / "assets" / "templates"
        
        if not template_dir.exists():
            return templates
        
        for template_file in template_dir.glob("*"):
            if template_file.is_file():
                try:
                    templates[template_file.name] = template_file.read_text(
                        encoding='utf-8'
                    )
                except Exception as e:
                    self._load_errors.append(
                        f"Failed to load template {template_file}: {e}"
                    )
        
        return templates
    
    def clear_config_cache(self, capability: str = None) -> None:
        """
        Clear cached configurations.
        
        Args:
            capability: Specific capability to clear, or None for all
        """
        if capability:
            self._configs.pop(capability, None)
        else:
            self._configs.clear()
    
    def reload(self) -> None:
        """
        Reload all manifests and clear config cache.
        
        Use for hot-reloading after configuration changes.
        """
        self._manifests.clear()
        self._configs.clear()
        self._load_errors.clear()
        self._load_all_manifests()
    
    # === Statistics ===
    
    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        return {
            "total_agents": len(self._manifests),
            "cached_configs": len(self._configs),
            "load_errors": len(self._load_errors),
            "capabilities": self.get_capabilities(),
        }
