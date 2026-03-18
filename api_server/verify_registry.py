#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Quick verification script for the Registry module.
Run this to verify the module is correctly implemented.
"""

import sys
import os
import tempfile
from pathlib import Path

# Ensure correct working directory
os.chdir(Path(__file__).parent)
sys.path.insert(0, os.getcwd())

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

print("=" * 60)
print("Registry Module Verification")
print("=" * 60)

# Test 1: Import modules
print("\n[1] Testing imports...")
try:
    from registry.errors import (
        RegistryError, ConfigLoadError, SkillParseError,
        ToolNotAllowedError, AgentNotFoundError
    )
    print("  [OK] registry.errors imported")
except ImportError as e:
    print(f"  [FAIL] Failed to import registry.errors: {e}")
    sys.exit(1)

try:
    from registry.skill_parser import SkillParser
    print("  [OK] registry.skill_parser imported")
except ImportError as e:
    print(f"  [FAIL] Failed to import registry.skill_parser: {e}")
    sys.exit(1)

try:
    from registry.agent_registry import (
        AgentManifest, AgentFullConfig, AgentRegistry
    )
    print("  [OK] registry.agent_registry imported")
except ImportError as e:
    print(f"  [FAIL] Failed to import registry.agent_registry: {e}")
    sys.exit(1)


# Test 2: SkillParser
print("\n[2] Testing SkillParser...")
parser = SkillParser()

with tempfile.TemporaryDirectory() as tmpdir:
    skill_file = Path(tmpdir) / "SKILL.md"
    skill_file.write_text("""---
name: test-skill
description: Test description
keywords: [test, demo]
---
# Workflow
1. Step one
2. Step two

# Tools
- read_file
- write_file
""", encoding='utf-8')
    
    frontmatter, body = parser.parse(skill_file)
    assert frontmatter['name'] == 'test-skill', "Frontmatter parsing failed"
    print("  [OK] Frontmatter parsing works")
    
    steps = parser.extract_workflow(body)
    assert len(steps) == 2, f"Expected 2 steps, got {len(steps)}"
    print("  [OK] Workflow extraction works")
    
    tools = parser.extract_tool_list(body)
    assert 'read_file' in tools, "Tool extraction failed"
    print("  [OK] Tool extraction works")

# Test 3: AgentManifest
print("\n[3] Testing AgentManifest...")
manifest = AgentManifest(
    capability="test",
    name="Test Agent",
    description="Test description",
    keywords=["test", "demo"],
)

desc = manifest.to_planner_description()
assert desc == "- test: Test description", f"Unexpected description: {desc}"
print("  [OK] to_planner_description works")

assert manifest.matches_keywords(["test"]), "Keyword matching failed"
assert not manifest.matches_keywords(["other"]), "Keyword matching should fail"
print("  [OK] matches_keywords works")

# Test 4: AgentFullConfig
print("\n[4] Testing AgentFullConfig...")
config = AgentFullConfig(
    manifest=manifest,
    tools_allowed=["read_file", "write_file"],
)

assert config.has_tool_permission("read_file"), "Permission check failed"
assert not config.has_tool_permission("run_command"), "Should not have permission"
print("  [OK] has_tool_permission works")

# Test 5: AgentRegistry
print("\n[5] Testing AgentRegistry...")
AgentRegistry.reset()

with tempfile.TemporaryDirectory() as tmpdir:
    base_dir = Path(tmpdir)
    agents_dir = base_dir / "agents"
    skills_dir = base_dir / "skills"
    agents_dir.mkdir()
    skills_dir.mkdir()
    
    # Create test agent
    import yaml
    agent_file = agents_dir / "test.agent.yaml"
    agent_file.write_text(yaml.dump({
        'capability': 'test',
        'name': 'Test Agent',
        'tools': {'allowed': ['read_file']},
    }), encoding='utf-8')
    
    # Create test skill
    skill_dir = skills_dir / "test"
    skill_dir.mkdir()
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text("---\nname: test\n---\n# Workflow\n1. Step", encoding='utf-8')
    
    registry = AgentRegistry.initialize(base_dir)
    
    manifests = registry.get_all_manifests()
    assert len(manifests) == 1, f"Expected 1 manifest, got {len(manifests)}"
    print("  [OK] Registry initialization works")
    
    descriptions = registry.get_planner_agent_descriptions()
    assert "test:" in descriptions, "Description should contain 'test:'"
    print("  [OK] get_planner_agent_descriptions works")
    
    full_config = registry.load_full_config('test')
    assert full_config.manifest.calpability == 'test', "Config loading failed"
    print("  [OK] load_full_config works")

AgentRegistry.reset()

# Summary
print("\n" + "=" * 60)
print("[PASS] All verification tests passed!")
print("=" * 60)
print("\nModule is ready for integration.")
