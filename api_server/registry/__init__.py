"""
Registry Module - Agent and Skill Configuration Management

This module provides:
- AgentRegistry: Pre-loaded agent metadata for planner discovery
- SkillParser: Parse SKILL.md files into structured data
- Tool permission validation
"""

from .errors import (
    RegistryError,
    ConfigLoadError,
    SkillParseError,
    ToolNotAllowedError,
)
from .skill_parser import SkillParser
from .agent_registry import (
    AgentManifest,
    AgentFullConfig,
    AgentRegistry,
)

__all__ = [
    # Exceptions
    "RegistryError",
    "ConfigLoadError",
    "SkillParseError",
    "ToolNotAllowedError",
    # Parser
    "SkillParser",
    # Registry
    "AgentManifest",
    "AgentFullConfig",
    "AgentRegistry",
]
