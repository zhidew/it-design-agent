"""
Expert Generation Script

This script provides the core logic for intelligently generating new design experts.
It reads instructions from SKILL.md and executes the generation workflow.

Usage:
    from skills.expert_creator.scripts.generate_expert import ExpertGenerator
    
    generator = ExpertGenerator(base_dir)
    expert = generator.create_expert("api-design", "API Design Expert", "Design APIs...")
"""

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


class ToolRegistry:
    """System tool registry manager."""
    
    def __init__(self, registry_path: Path):
        self.registry_path = registry_path
        self._data = self._load_registry()
    
    def _load_registry(self) -> Dict[str, Any]:
        """Load tool registry from YAML file."""
        if not self.registry_path.exists():
            return {"tools": [], "categories": [], "tool_combinations": []}
        
        with open(self.registry_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {"tools": [], "categories": [], "tool_combinations": []}
    
    def get_all_tools(self) -> List[Dict[str, Any]]:
        """Get all registered tools."""
        return self._data.get("tools", [])
    
    def recommend_tools_for_domain(self, domain_keywords: List[str]) -> List[str]:
        """Recommend tools based on domain keywords."""
        recommended = set()
        
        # Keyword to tool mapping
        keyword_tool_map = {
            "database": ["query_database"],
            "db": ["query_database"],
            "sql": ["query_database"],
            "data": ["query_database", "extract_lookup_values"],
            "api": ["query_database", "query_knowledge_base", "write_file"],
            "code": ["clone_repository", "grep_search", "read_file_chunk"],
            "repo": ["clone_repository"],
            "git": ["clone_repository"],
            "structure": ["extract_structure", "list_files"],
            "knowledge": ["query_knowledge_base"],
            "business": ["query_knowledge_base"],
            "config": ["read_file_chunk", "write_file", "patch_file"],
            "security": ["grep_search", "query_knowledge_base"],
            "test": ["run_command", "read_file_chunk"],
            "ops": ["run_command", "read_file_chunk"],
            "architecture": ["clone_repository", "extract_structure", "grep_search"],
            "integration": ["clone_repository", "query_database", "query_knowledge_base"],
            "flow": ["query_knowledge_base", "write_file"],
        }
        
        # Always include basic file tools
        recommended.add("write_file")
        recommended.add("read_file_chunk")
        
        # Map keywords to tools
        for keyword in domain_keywords:
            keyword_lower = keyword.lower()
            for key, tools in keyword_tool_map.items():
                if key in keyword_lower:
                    recommended.update(tools)
        
        return list(recommended)


class ExpertGenerator:
    """Intelligent expert generation engine."""
    
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.experts_dir = self.base_dir / "experts"
        self.skills_dir = self.base_dir / "skills"
        
        # Load tool registry
        registry_path = self.base_dir / "skills" / "expert-creator" / "assets" / "TOOL_REGISTRY.yaml"
        self.tool_registry = ToolRegistry(registry_path)
        
        # Load skill instructions
        self.skill_path = self.base_dir / "skills" / "expert-creator" / "SKILL.md"
    
    def _resolve_expert_profile_path(self, expert_id: str) -> Path:
        """Resolve the path for an expert profile file."""
        return self.experts_dir / f"{expert_id}.expert.yaml"
    
    def _clean_expert_id(self, raw_id: str) -> str:
        """Clean and normalize an expert ID to Kebab-case."""
        cleaned = "".join(ch for ch in raw_id.lower() if ch.isalnum() or ch == "-")
        return cleaned.strip("-") or f"expert-{uuid.uuid4().hex[:8]}"
    
    def _analyze_domain_keywords(self, name: str, description: str) -> List[str]:
        """Extract domain keywords from name and description."""
        text = f"{name} {description}".lower()
        
        # Common domain keywords
        domain_keywords = [
            "api", "data", "database", "db", "sql", "security", "test", "ops",
            "architecture", "integration", "flow", "config", "code", "repo",
            "git", "structure", "knowledge", "business"
        ]
        
        found = []
        for keyword in domain_keywords:
            if keyword in text:
                found.append(keyword)
        
        return found
    
    def _generate_with_llm(self, name: str, description: str) -> Dict[str, Any]:
        """Use LLM to generate expert content based on SKILL.md instructions."""
        try:
            from api_server.services.llm_service import generate_with_llm
            
            # Read skill instructions
            skill_instructions = self.skill_path.read_text(encoding="utf-8") if self.skill_path.exists() else ""
            
            # Extract the "LLM Instructions" section from SKILL.md
            llm_section_start = skill_instructions.find("## LLM Instructions")
            llm_section_end = skill_instructions.find("## Tool Registry Reference")
            if llm_section_start > 0 and llm_section_end > llm_section_start:
                llm_instructions = skill_instructions[llm_section_start:llm_section_end]
            else:
                llm_instructions = skill_instructions
            
            # Get tool recommendations
            domain_keywords = self._analyze_domain_keywords(name, description)
            recommended_tools = self.tool_registry.recommend_tools_for_domain(domain_keywords)
            
            # Generate metadata
            metadata_prompt = f"""
{llm_instructions}

---

Now generate expert metadata for:

**Expert Name**: {name}
**Description**: {description}

**Domain Keywords**: {domain_keywords}
**Recommended Tools**: {recommended_tools}

Generate a JSON object following Step 2 instructions. Return ONLY the JSON, no explanations.
"""
            
            metadata_result = generate_with_llm(
                metadata_prompt,
                f"Generate metadata for expert: {name}",
                ["meta.json"]
            )
            
            meta = json.loads(metadata_result.artifacts.get("meta.json", "{}"))
            expert_id = self._clean_expert_id(meta.get("expert_id", name))
            
            # Override tools if not provided
            if not meta.get("tools_allowed"):
                meta["tools_allowed"] = recommended_tools
            
            # Generate full content
            template_name = meta.get("core_template_name", "output_template.md.j2")
            script_name = meta.get("needed_script_tool")
            tools_allowed = meta.get("tools_allowed", recommended_tools)
            
            expected_files = ["profile.yaml", "skill.md", template_name]
            if script_name:
                expected_files.append(script_name)
            
            content_prompt = f"""
{llm_instructions}

---

Now generate complete expert files for:

**Expert ID**: {expert_id}
**Name (Chinese)**: {meta.get('name_zh', name)}
**Name (English)**: {meta.get('name_en', expert_id)}
**Description**: {meta.get('description', description)}
**Tools**: {json.dumps(tools_allowed)}

Generate the following files following Step 3-6 instructions:
1. profile.yaml - Expert configuration
2. skill.md - Skill guide with ReAct workflow
3. {template_name} - Output template
{"4. " + script_name + " - Python script" if script_name else ""}

Return each file in a code block with the filename as header.
"""
            
            content_result = generate_with_llm(
                content_prompt,
                f"Generate complete expert files for: {name}",
                expected_files
            )
            
            return {
                "success": True,
                "meta": meta,
                "expert_id": expert_id,
                "profile": self._clean_yaml(content_result.artifacts.get("profile.yaml", "")),
                "skill": content_result.artifacts.get("skill.md", ""),
                "template": content_result.artifacts.get(template_name, ""),
                "template_name": template_name,
                "script": content_result.artifacts.get(script_name, "") if script_name else "",
                "script_name": script_name,
                "tools_recommended": tools_allowed,
            }
            
        except Exception as e:
            print(f"[ExpertGenerator] LLM generation failed: {e}")
            return {"success": False, "error": str(e)}
    
    def _clean_yaml(self, raw: str) -> str:
        """Clean YAML content from markdown code blocks."""
        cleaned = raw.strip()
        import re
        if cleaned.startswith("```"):
            match = re.match(r"^```(?:yaml)?\s+([\s\S]*?)\s*```$", cleaned)
            if match:
                cleaned = match.group(1).strip()
            else:
                match = re.match(r"^```(?:yaml)?\s+([\s\S]*)", cleaned)
                if match:
                    cleaned = match.group(1).strip()
                    if cleaned.endswith("```"):
                        cleaned = cleaned[:-3].strip()

        try:
            if "capability:" in cleaned:
                yaml.safe_load(cleaned)
                return cleaned
        except Exception:
            pass
        return ""
    
    def _generate_fallback_content(self, expert_id: str, name: str, description: str) -> Dict[str, Any]:
        """Generate fallback content when LLM fails."""
        
        # Analyze domain and recommend tools
        domain_keywords = self._analyze_domain_keywords(name, description)
        recommended_tools = self.tool_registry.recommend_tools_for_domain(domain_keywords)
        
        profile = f"""name: {name}
capability: {expert_id}
description: "{description}"
version: 0.1.0
skills:
  - {expert_id}
scheduling:
  priority: 50
  dependencies: []
keywords: {json.dumps(domain_keywords)}
tools:
  allowed: {json.dumps(recommended_tools)}
outputs:
  expected: ["output.md"]
policies: {{}}
"""
        skill = f"""---
name: {name}
description: "{description}"
keywords: {json.dumps(domain_keywords)}
---

# {name}

## Purpose

{description}

## Capabilities

1. **Analysis**: Analyze requirements and gather context
2. **Design**: Create structured design artifacts
3. **Validation**: Ensure output quality and completeness

## ReAct Workflow

### Phase 1: Context Gathering

#### Think 1: Analyze Requirements
Analyze the requirements and identify what information is needed.

#### Act 1: Gather Information
Use available tools to gather necessary context.

#### Observe 1: Collected Data
Review the gathered information for completeness.

### Phase 2: Design

#### Think 2: Design Strategy
Plan the structure and content of the output.

#### Act 2: Generate Output
Create the design artifacts.

#### Observe 2: Review Output
Validate the generated content.

## Output Artifacts

| File | Description |
|------|-------------|
| output.md | Primary output document |

## Tools Used

This expert uses the following tools:
{chr(10).join([f'- {t}' for t in recommended_tools])}
"""
        return {
            "success": True,
            "expert_id": expert_id,
            "profile": profile,
            "skill": skill,
            "template": f"# {name} Output Template\n\n## Generated Content\n\n<!-- Add your content here -->",
            "template_name": "output_template.md.j2",
            "script": "",
            "script_name": None,
            "tools_recommended": recommended_tools,
        }
    
    def create_expert(
        self,
        expert_id: str,
        name: str,
        description: str = "",
        use_llm: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Create a new expert with intelligent generation.
        
        Args:
            expert_id: Initial expert ID (will be cleaned to Kebab-case)
            name: Expert display name
            description: Expert description
            use_llm: Whether to use LLM for intelligent generation
            
        Returns:
            Expert metadata dict if successful, None otherwise
        """
        # Clean initial ID
        initial_id = self._clean_expert_id(expert_id)
        
        # Generate content
        if use_llm:
            result = self._generate_with_llm(name, description)
        else:
            result = {"success": False}
        
        if not result.get("success"):
            result = self._generate_fallback_content(initial_id, name, description)
        
        expert_id = result.get("expert_id", initial_id)
        
        # Ensure unique ID
        profile_path = self._resolve_expert_profile_path(expert_id)
        if profile_path.exists():
            expert_id = f"{expert_id}-{uuid.uuid4().hex[:4]}"
            profile_path = self._resolve_expert_profile_path(expert_id)
        
        # Create directory structure
        self.experts_dir.mkdir(parents=True, exist_ok=True)
        skill_dir = self.skills_dir / expert_id
        (skill_dir / "assets" / "templates").mkdir(parents=True, exist_ok=True)
        (skill_dir / "references").mkdir(parents=True, exist_ok=True)
        (skill_dir / "scripts").mkdir(parents=True, exist_ok=True)
        
        # Write files
        profile_content = result.get("profile", "")
        skill_content = result.get("skill", "")
        template_content = result.get("template", "")
        template_name = result.get("template_name", "output_template.md.j2")
        script_content = result.get("script", "")
        script_name = result.get("script_name")
        
        if profile_content:
            profile_path.write_text(profile_content, encoding="utf-8")
        if skill_content:
            (skill_dir / "SKILL.md").write_text(skill_content, encoding="utf-8")
        if template_content:
            (skill_dir / "assets" / "templates" / template_name).write_text(template_content, encoding="utf-8")
        if script_content and script_name:
            (skill_dir / "scripts" / script_name).write_text(script_content, encoding="utf-8")
        
        # Return expert metadata
        return {
            "id": expert_id,
            "name": name,
            "description": description,
            "profile_path": str(profile_path),
            "skill_path": str(skill_dir / "SKILL.md"),
            "tools_recommended": result.get("tools_recommended", []),
            "expertise": [],
        }


def create_expert(
    base_dir: Path,
    expert_id: str,
    name: str,
    description: str = "",
    use_llm: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Convenience function to create a new expert.
    
    Args:
        base_dir: Project base directory
        expert_id: Initial expert ID
        name: Expert display name
        description: Expert description
        use_llm: Whether to use LLM generation
        
    Returns:
        Expert metadata dict if successful, None otherwise
    """
    generator = ExpertGenerator(base_dir)
    return generator.create_expert(expert_id, name, description, use_llm)
