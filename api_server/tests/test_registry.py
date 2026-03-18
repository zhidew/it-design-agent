"""
Unit Tests for Registry Module

Tests for:
- SkillParser: SKILL.md parsing
- AgentManifest: Metadata structure
- AgentRegistry: Configuration management
"""

import os
import sys

# Ensure the api_server directory is in the path
_api_server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _api_server_dir not in sys.path:
    sys.path.insert(0, _api_server_dir)

import pytest
import tempfile
from pathlib import Path
import yaml

# Import the modules under test
from registry.errors import (
    RegistryError,
    ConfigLoadError,
    SkillParseError,
    ToolNotAllowedError,
    AgentNotFoundError,
)
from registry.skill_parser import SkillParser
from registry.agent_registry import (
    AgentManifest,
    AgentFullConfig,
    AgentRegistry,
)


# ============================================================================
# SkillParser Tests
# ============================================================================

class TestSkillParser:
    """Tests for SkillParser class."""
    
    def test_parse_no_frontmatter(self, tmp_path):
        """Test parsing a SKILL.md without frontmatter."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("# Workflow\n1. Step one\n2. Step two", encoding='utf-8')
        
        parser = SkillParser()
        frontmatter, body = parser.parse(skill_file)
        
        assert frontmatter == {}
        assert "# Workflow" in body
    
    def test_parse_with_frontmatter(self, tmp_path):
        """Test parsing a SKILL.md with YAML frontmatter."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""---
name: test-skill
description: Test description
keywords:
  - test
  - demo
---
# Workflow
1. Step one
2. Step two
""", encoding='utf-8')
        
        parser = SkillParser()
        frontmatter, body = parser.parse(skill_file)
        
        assert frontmatter['name'] == 'test-skill'
        assert frontmatter['description'] == 'Test description'
        assert frontmatter['keywords'] == ['test', 'demo']
        assert "# Workflow" in body
    
    def test_parse_file_not_found(self, tmp_path):
        """Test parsing a non-existent file."""
        parser = SkillParser()
        
        with pytest.raises(ConfigLoadError) as exc_info:
            parser.parse(tmp_path / "nonexistent.md")
        
        assert "File not found" in str(exc_info.value)
    
    def test_parse_invalid_yaml(self, tmp_path):
        """Test parsing a file with invalid YAML frontmatter."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""---
invalid: [unclosed
---
# Workflow
""", encoding='utf-8')
        
        parser = SkillParser()
        
        with pytest.raises(SkillParseError):
            parser.parse(skill_file)
    
    def test_extract_workflow_english(self, tmp_path):
        """Test extracting workflow steps in English."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""
# Workflow
1. First step
2. Second step
3. Third step

# Tools
- tool1
""", encoding='utf-8')
        
        parser = SkillParser()
        _, body = parser.parse(skill_file)
        steps = parser.extract_workflow(body)
        
        assert len(steps) == 3
        assert "First step" in steps[0]
        assert "Second step" in steps[1]
    
    def test_extract_workflow_chinese(self, tmp_path):
        """Test extracting workflow steps in Chinese."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""
# 工作流
1. 第一步：读取配置
2. 第二步：处理数据
3. 第三步：输出结果
""", encoding='utf-8')
        
        parser = SkillParser()
        _, body = parser.parse(skill_file)
        steps = parser.extract_workflow(body)
        
        assert len(steps) == 3
        assert "读取配置" in steps[0]
    
    def test_extract_sections(self, tmp_path):
        """Test extracting all markdown sections."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""
# Workflow
1. Step one

# Tools
- tool1: Description
- tool2: Description

# Policies
- policy1: value1
""", encoding='utf-8')
        
        parser = SkillParser()
        _, body = parser.parse(skill_file)
        sections = parser.extract_sections(body)
        
        assert 'Workflow' in sections
        assert 'Tools' in sections
        assert 'Policies' in sections
        assert 'tool1' in sections['Tools']
    
    def test_build_prompt_instructions(self, tmp_path):
        """Test building prompt instructions."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""
# Workflow
1. Step one

# Tools
- tool1
""", encoding='utf-8')
        
        parser = SkillParser()
        _, body = parser.parse(skill_file)
        instructions = parser.build_prompt_instructions(body)
        
        assert "## Workflow" in instructions
        assert "Step one" in instructions
    
    def test_build_prompt_instructions_max_length(self, tmp_path):
        """Test prompt truncation with max_length."""
        # Create a long content
        long_content = "# Workflow\n" + "\n".join(
            f"{i}. Step {i} " + "x" * 100 
            for i in range(1, 50)
        )
        
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(long_content, encoding='utf-8')
        
        parser = SkillParser()
        _, body = parser.parse(skill_file)
        instructions = parser.build_prompt_instructions(body, max_length=500)
        
        assert len(instructions) <= 550  # Some buffer for truncation message
        assert "truncated" in instructions.lower()
    
    def test_extract_tool_list(self, tmp_path):
        """Test extracting tool names from Tools section."""
        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("""
# Tools
- read_file
- write_file
- grep_search
""", encoding='utf-8')
        
        parser = SkillParser()
        _, body = parser.parse(skill_file)
        tools = parser.extract_tool_list(body)
        
        assert 'read_file' in tools
        assert 'write_file' in tools
        assert 'grep_search' in tools


# ============================================================================
# AgentManifest Tests
# ============================================================================

class TestAgentManifest:
    """Tests for AgentManifest dataclass."""
    
    def test_to_planner_description(self):
        """Test generating planner description."""
        manifest = AgentManifest(
            capability="api-design",
            name="API Design Agent",
            description="Designs REST APIs",
        )
        
        desc = manifest.to_planner_description()
        assert desc == "- api-design: Designs REST APIs"
    
    def test_matches_keywords(self):
        """Test keyword matching."""
        manifest = AgentManifest(
            capability="api-design",
            name="API Design Agent",
            description="Designs REST APIs",
            keywords=["api", "rest", "openapi", "interface"],
        )
        
        assert manifest.matches_keywords(["api"])
        assert manifest.matches_keywords(["REST"])  # Case insensitive
        assert manifest.matches_keywords(["interface design"])
        assert not manifest.matches_keywords(["database"])
    
    def test_to_dict(self):
        """Test serialization to dictionary."""
        manifest = AgentManifest(
            capability="api-design",
            name="API Design Agent",
            description="Designs REST APIs",
            keywords=["api"],
            required_inputs=["requirements"],
            expected_outputs=["api.yaml"],
        )
        
        result = manifest.to_dict()
        
        assert result['capability'] == "api-design"
        assert result['name'] == "API Design Agent"
        assert result['keywords'] == ["api"]


# ============================================================================
# AgentFullConfig Tests
# ============================================================================

class TestAgentFullConfig:
    """Tests for AgentFullConfig dataclass."""
    
    def test_has_tool_permission(self):
        """Test tool permission checking."""
        manifest = AgentManifest(
            capability="api-design",
            name="API Design Agent",
            description="Designs REST APIs",
        )
        
        config = AgentFullConfig(
            manifest=manifest,
            tools_allowed=["read_file", "write_file", "grep_search"],
        )
        
        assert config.has_tool_permission("read_file")
        assert config.has_tool_permission("write_file")
        assert not config.has_tool_permission("run_command")
    
    def test_wildcard_permission(self):
        """Test wildcard tool permission."""
        manifest = AgentManifest(
            capability="admin",
            name="Admin Agent",
            description="Full access",
        )
        
        config = AgentFullConfig(
            manifest=manifest,
            tools_allowed=["*"],
        )
        
        assert config.has_tool_permission("any_tool")
        assert config.has_tool_permission("run_command")


# ============================================================================
# AgentRegistry Tests
# ============================================================================

class TestAgentRegistry:
    """Tests for AgentRegistry singleton."""
    
    def test_singleton_pattern(self):
        """Test that AgentRegistry is a singleton."""
        AgentRegistry.reset()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            (base_dir / "agents").mkdir()
            (base_dir / "skills").mkdir()
            
            registry1 = AgentRegistry.initialize(base_dir)
            registry2 = AgentRegistry.get_instance()
            
            assert registry1 is registry2
        
        AgentRegistry.reset()
    
    def test_initialize_loads_agents(self, tmp_path):
        """Test that initialization loads agent manifests."""
        AgentRegistry.reset()
        
        # Create test agent
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        
        agent_file = agents_dir / "test.agent.yaml"
        agent_file.write_text(yaml.dump({
            'capability': 'test',
            'name': 'Test Agent',
            'description': 'A test agent',
            'tools': {'allowed': ['read_file']},
        }), encoding='utf-8')
        
        skill_dir = skills_dir / "test"
        skill_dir.mkdir()
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("""---
name: test-skill
description: Test skill description
keywords: [test, demo]
---
# Workflow
1. Step one
""", encoding='utf-8')
        
        registry = AgentRegistry.initialize(tmp_path)
        
        assert len(registry.get_all_manifests()) == 1
        manifest = registry.get_manifest('test')
        assert manifest is not None
        assert manifest.name == 'Test Agent'
        assert 'test' in manifest.keywords
        
        AgentRegistry.reset()
    
    def test_capability_extraction_from_filename(self, tmp_path):
        """Test capability extraction from filename."""
        AgentRegistry.reset()
        
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        
        # Agent file without capability field
        agent_file = agents_dir / "my-design.agent.yaml"
        agent_file.write_text(yaml.dump({
            'name': 'My Design Agent',
        }), encoding='utf-8')
        
        registry = AgentRegistry.initialize(tmp_path)
        
        manifest = registry.get_manifest('my-design')
        assert manifest is not None
        assert manifest.capability == 'my-design'
        
        AgentRegistry.reset()
    
    def test_get_planner_agent_descriptions(self, tmp_path):
        """Test generating planner descriptions."""
        AgentRegistry.reset()
        
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        
        # Create multiple agents
        for cap in ['alpha', 'beta', 'gamma']:
            agent_file = agents_dir / f"{cap}.agent.yaml"
            agent_file.write_text(yaml.dump({
                'capability': cap,
                'name': f'{cap.upper()} Agent',
                'description': f'Description for {cap}',
            }), encoding='utf-8')
        
        registry = AgentRegistry.initialize(tmp_path)
        descriptions = registry.get_planner_agent_descriptions()
        
        assert '- alpha: Description for alpha' in descriptions
        assert '- beta: Description for beta' in descriptions
        assert '- gamma: Description for gamma' in descriptions
        
        AgentRegistry.reset()
    
    def test_load_full_config(self, tmp_path):
        """Test loading full configuration."""
        AgentRegistry.reset()
        
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        skills_dir = tmp_path / "skills"
        skill_dir = skills_dir / "test"
        skill_dir.mkdir(parents=True)
        
        agent_file = agents_dir / "test.agent.yaml"
        agent_file.write_text(yaml.dump({
            'capability': 'test',
            'name': 'Test Agent',
            'tools': {'allowed': ['read_file', 'write_file']},
            'policies': {'evidence_required': True},
        }), encoding='utf-8')
        
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("""---
name: test-skill
---
# Workflow
1. First step
2. Second step

# Tools
- read_file
""", encoding='utf-8')
        
        # Create template
        template_dir = skill_dir / "assets" / "templates"
        template_dir.mkdir(parents=True)
        (template_dir / "template.yaml").write_text("key: value", encoding='utf-8')
        
        registry = AgentRegistry.initialize(tmp_path)
        config = registry.load_full_config('test')
        
        assert config.manifest.capability == 'test'
        assert 'read_file' in config.tools_allowed
        assert 'write_file' in config.tools_allowed
        assert config.policies.get('evidence_required') == True
        assert len(config.workflow_steps) == 2
        assert 'template.yaml' in config.templates
        
        AgentRegistry.reset()
    
    def test_agent_not_found(self, tmp_path):
        """Test error when agent not found."""
        AgentRegistry.reset()
        
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        
        registry = AgentRegistry.initialize(tmp_path)
        
        with pytest.raises(AgentNotFoundError):
            registry.load_full_config('nonexistent')
        
        AgentRegistry.reset()
    
    def test_config_caching(self, tmp_path):
        """Test that configurations are cached."""
        AgentRegistry.reset()
        
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        
        agent_file = agents_dir / "test.agent.yaml"
        agent_file.write_text(yaml.dump({'capability': 'test'}), encoding='utf-8')
        
        registry = AgentRegistry.initialize(tmp_path)
        
        config1 = registry.load_full_config('test')
        config2 = registry.load_full_config('test')
        
        assert config1 is config2  # Same object reference
        
        AgentRegistry.reset()
    
    def test_query_by_keywords(self, tmp_path):
        """Test querying agents by keywords."""
        AgentRegistry.reset()
        
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        
        # Create agents with different keywords
        for name, keywords in [
            ('api', ['api', 'rest', 'http']),
            ('database', ['sql', 'database', 'schema']),
            ('ui', ['frontend', 'ui', 'css']),
        ]:
            agent_file = agents_dir / f"{name}.agent.yaml"
            agent_file.write_text(yaml.dump({
                'capability': name,
                'keywords': keywords,
            }), encoding='utf-8')
        
        registry = AgentRegistry.initialize(tmp_path)
        
        results = registry.get_manifests_by_keywords(['api', 'http'])
        assert len(results) == 1
        assert results[0].capability == 'api'
        
        results = registry.get_manifests_by_keywords(['database'])
        assert len(results) == 1
        assert results[0].capability == 'database'
        
        AgentRegistry.reset()
    
    def test_load_errors_tracking(self, tmp_path):
        """Test that load errors are tracked."""
        AgentRegistry.reset()
        
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        
        # Create invalid YAML file
        invalid_file = agents_dir / "invalid.agent.yaml"
        invalid_file.write_text("invalid: [unclosed", encoding='utf-8')
        
        # Create valid file
        valid_file = agents_dir / "valid.agent.yaml"
        valid_file.write_text(yaml.dump({'capability': 'valid'}), encoding='utf-8')
        
        registry = AgentRegistry.initialize(tmp_path)
        
        # Should have loaded valid agent
        assert registry.get_manifest('valid') is not None
        # Should have recorded error for invalid file
        errors = registry.get_load_errors()
        assert any('invalid.agent.yaml' in e for e in errors)
        
        AgentRegistry.reset()
    
    def test_reload(self, tmp_path):
        """Test reloading the registry."""
        AgentRegistry.reset()
        
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        
        # Create initial agent
        agent_file = agents_dir / "test.agent.yaml"
        agent_file.write_text(yaml.dump({'capability': 'test'}), encoding='utf-8')
        
        registry = AgentRegistry.initialize(tmp_path)
        assert len(registry.get_all_manifests()) == 1
        
        # Add new agent
        new_agent = agents_dir / "new.agent.yaml"
        new_agent.write_text(yaml.dump({'capability': 'new'}), encoding='utf-8')
        
        # Before reload
        assert registry.get_manifest('new') is None
        
        # After reload
        registry.reload()
        assert registry.get_manifest('new') is not None
        
        AgentRegistry.reset()


# ============================================================================
# Error Classes Tests
# ============================================================================

class TestErrorClasses:
    """Tests for error classes."""
    
    def test_config_load_error(self):
        """Test ConfigLoadError formatting."""
        error = ConfigLoadError("/path/to/file.yaml", "File not found")
        
        assert error.path == "/path/to/file.yaml"
        assert error.reason == "File not found"
        assert "File not found" in str(error)
    
    def test_tool_not_allowed_error(self):
        """Test ToolNotAllowedError formatting."""
        error = ToolNotAllowedError(
            tool="run_command",
            capability="api-design",
            allowed=["read_file", "write_file"]
        )
        
        assert error.tool == "run_command"
        assert "run_command" in str(error)
        assert "api-design" in str(error)
    
    def test_error_to_dict(self):
        """Test error serialization."""
        error = ConfigLoadError("/path", "reason", details={"extra": "info"})
        result = error.to_dict()
        
        assert result['error_type'] == 'ConfigLoadError'
        assert result['message']
        assert result['details']['extra'] == 'info'


# ============================================================================
# Tool Permission Tests
# ============================================================================

class TestToolPermission:
    """Tests for tool permission checking."""
    
    def test_execute_tool_with_permission_allowed(self, tmp_path, monkeypatch):
        """Test that allowed tools execute successfully."""
        from graphs.tools.protocol import execute_tool_with_permission, TOOL_ERROR_OK
        
        # Create a mock agent config
        manifest = AgentManifest(
            capability="test-agent",
            name="Test Agent",
            description="Test",
        )
        config = AgentFullConfig(
            manifest=manifest,
            tools_allowed=["list_files", "read_file_chunk", "grep_search"],
        )
        
        # Create a test directory
        test_dir = tmp_path / "test_root"
        test_dir.mkdir()
        
        # Execute allowed tool
        result = execute_tool_with_permission(
            "list_files",
            {"root_dir": str(test_dir)},
            agent_config=config,
        )
        
        assert result["status"] == "success"
        assert result["error_code"] == TOOL_ERROR_OK
    
    def test_execute_tool_with_permission_denied(self, tmp_path):
        """Test that denied tools raise an error."""
        from graphs.tools.protocol import (
            execute_tool_with_permission,
            ToolInputError,
            TOOL_ERROR_NOT_ALLOWED,
        )
        
        # Create a mock agent config with limited tools
        manifest = AgentManifest(
            capability="limited-agent",
            name="Limited Agent",
            description="Limited access",
        )
        config = AgentFullConfig(
            manifest=manifest,
            tools_allowed=["list_files", "read_file_chunk"],
        )
        
        # Create a test directory
        test_dir = tmp_path / "test_root"
        test_dir.mkdir()
        
        # Execute denied tool - should fail with NOT_ALLOWED
        result = execute_tool_with_permission(
            "run_command",  # This tool is NOT in allowed list
            {"root_dir": str(test_dir), "command": "echo test"},
            agent_config=config,
        )
        
        assert result["status"] == "error"
        assert result["error_code"] == TOOL_ERROR_NOT_ALLOWED
        assert "not allowed" in result["output"]["message"].lower()
    
    def test_execute_tool_with_wildcard_permission(self, tmp_path):
        """Test that wildcard allows all tools."""
        from graphs.tools.protocol import execute_tool_with_permission, TOOL_ERROR_OK
        
        # Create agent with wildcard permission
        manifest = AgentManifest(
            capability="admin-agent",
            name="Admin Agent",
            description="Full access",
        )
        config = AgentFullConfig(
            manifest=manifest,
            tools_allowed=["*"],
        )
        
        # Create a test directory
        test_dir = tmp_path / "test_root"
        test_dir.mkdir()
        
        # Any tool should work
        result = execute_tool_with_permission(
            "list_files",
            {"root_dir": str(test_dir)},
            agent_config=config,
        )
        
        assert result["status"] == "success"
    
    def test_execute_tool_with_capability_string(self, tmp_path):
        """Test using capability string instead of config object."""
        AgentRegistry.reset()
        
        from graphs.tools.protocol import execute_tool_with_permission
        
        # Setup registry
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        
        agent_file = agents_dir / "test-perm.agent.yaml"
        agent_file.write_text(yaml.dump({
            'capability': 'test-perm',
            'tools': {'allowed': ['list_files']},
        }), encoding='utf-8')
        
        test_root = tmp_path / "root"
        test_root.mkdir()
        
        registry = AgentRegistry.initialize(tmp_path)
        
        # Use capability string
        result = execute_tool_with_permission(
            "list_files",
            {"root_dir": str(test_root)},
            agent_capability="test-perm",
        )
        
        assert result["status"] == "success"
        
        AgentRegistry.reset()
    
    def test_execute_tool_without_config_or_capability(self, tmp_path):
        """Test fallback when no config or capability provided."""
        from graphs.tools.protocol import execute_tool_with_permission, TOOL_ERROR_OK
        
        # Create a test directory
        test_dir = tmp_path / "test_root"
        test_dir.mkdir()
        
        # Without any permission check, tool should execute
        result = execute_tool_with_permission(
            "list_files",
            {"root_dir": str(test_dir)},
            # No agent_config or agent_capability
        )
        
        # Should still work (falls back to no permission check)
        assert result["status"] == "success"
        assert result["error_code"] == TOOL_ERROR_OK
    
    def test_execute_tool_registry_not_initialized(self, tmp_path):
        """Test behavior when registry is not initialized."""
        AgentRegistry.reset()
        
        from graphs.tools.protocol import execute_tool_with_permission, TOOL_ERROR_OK
        
        # Create a test directory
        test_dir = tmp_path / "test_root"
        test_dir.mkdir()
        
        # Try to use capability string when registry not initialized
        # Should fall back to no permission check (not crash)
        result = execute_tool_with_permission(
            "list_files",
            {"root_dir": str(test_dir)},
            agent_capability="any-agent",  # Registry not initialized
        )
        
        # Should still work (graceful degradation)
        assert result["status"] == "success"


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
