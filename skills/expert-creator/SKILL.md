---
name: Expert Creator
description: Intelligently generate new design experts with complete profiles, skill guides, templates, and scripts based on domain requirements.
keywords:
  - expert generation
  - agent creation
  - domain modeling
  - capability definition
  - tool recommendation
---

# Expert Creator

## Purpose

The Expert Creator is a system-level expert responsible for intelligently generating new design experts. It analyzes domain requirements, designs expert capabilities, recommends appropriate tools, and produces complete expert configurations including profiles, skill guides, templates, and auxiliary scripts.

## Capabilities

1. **Domain Analysis**: Understand user requirements and map them to expert capabilities
2. **ID Generation**: Create professional Kebab-case identifiers (e.g., `api-design`, `security-audit`)
3. **Tool Recommendation**: Analyze requirements and recommend appropriate tool combinations from the system tool registry
4. **Profile Design**: Generate complete expert YAML configurations
5. **Skill Guide Creation**: Design detailed ReAct workflow guides
6. **Template Generation**: Create domain-specific asset templates
7. **Script Tooling**: Implement auxiliary Python scripts when needed

---

## LLM Instructions

When creating a new expert, follow this structured process:

### Step 1: Parse User Intent

Analyze the user-provided information:
- Expert name (Chinese/English)
- Domain description
- Expected outputs

### Step 2: Generate Expert Metadata

Create a JSON object with the following structure:

```json
{
  "expert_id": "professional-kebab-case-id",
  "name_zh": "中文名称",
  "name_en": "English Name",
  "description": "Expert description in Chinese",
  "tools_allowed": ["tool1", "tool2"],
  "needed_script_tool": "optional_script.py",
  "core_template_name": "output_template.md.j2"
}
```

**Rules for expert_id:**
- Must be professional English in Kebab-case (e.g., `api-design`, `security-audit`, `performance-analysis`)
- No Chinese characters
- Use hyphens to separate words
- Keep it concise and descriptive

**Tool recommendation rules:**
- Always include: `write_file`, `read_file_chunk`
- Add `query_database` if the expert works with data models or databases
- Add `query_knowledge_base` if the expert needs business context or terminology
- Add `clone_repository` if the expert analyzes code
- Add `grep_search` if the expert searches for patterns
- Add `patch_file` if the expert updates existing documents

### Step 3: Generate Expert Profile (profile.yaml)

Generate a YAML configuration with this structure:

```yaml
name: {name_en}
capability: {expert_id}
description: "{description}"
version: 0.1.0
skills:
  - {expert_id}
scheduling:
  priority: {50-100}
  dependencies: {list of expert-ids}
keywords:
  - {keyword1}
  - {keyword2}
tools:
  allowed: {tools_allowed}
outputs:
  expected: {list of output files}
policies:
  asset_baseline_required: true
  evidence_required: true
  output_must_be_structured: true
```

### Step 4: Generate Skill Guide (SKILL.md)

Generate a comprehensive skill guide with ReAct workflow using the template at:
`skills/expert-creator/assets/templates/skill_template.md.j2`

The SKILL.md must include:
1. **Frontmatter** with name, description, keywords
2. **Purpose** section explaining the expert's goal
3. **Capabilities** section listing what the expert can do
4. **ReAct Workflow** with at least 3 phases, each containing:
   - Think: What to analyze
   - Act: What action to take
   - Observe: What to expect
5. **Output Artifacts** table
6. **Tools Used** section

### Step 5: Generate Templates

Create Jinja2 templates for the expert's outputs. Place in:
`skills/{expert_id}/assets/templates/`

Template naming conventions:
- `{expert_id}_spec.md.j2` for specification templates
- `{expert_id}_report.md.j2` for report templates
- `{expert_id}_design.md.j2` for design templates

### Step 6: Generate Scripts (Optional)

If `needed_script_tool` is specified, create a Python script in:
`skills/{expert_id}/scripts/{script_name}`

Script structure:
```python
"""
Script Description

Usage:
    python {script_name} --arg1 value1
"""

import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    # Add arguments
    args = parser.parse_args()
    
    # Implementation
    pass

if __name__ == "__main__":
    main()
```

---

## Tool Registry Reference

Available tools in the system (see `skills/expert-creator/assets/TOOL_REGISTRY.yaml`):

### File Operations
- `write_file`: Create or overwrite files
- `patch_file`: Update files using diff algorithm
- `read_file_chunk`: Read specific line ranges
- `list_files`: List directory contents
- `grep_search`: Search with regex

### Database
- `query_database`: Query database metadata or execute read-only SQL

### Knowledge Base
- `query_knowledge_base`: Search business terminology, feature trees, design docs

### Repository
- `clone_repository`: Clone or update Git repositories

### Analysis
- `extract_structure`: Extract code structure
- `extract_lookup_values`: Extract enums and dictionaries

### Execution
- `run_command`: Execute shell commands

---

## ReAct Workflow Example

### Phase 1: Requirement Analysis

#### Think 1: Analyze User Requirements
Analyze the expert name and description to understand the domain.

#### Act 1: Read Tool Registry
```yaml
Action: read_file_chunk
Input:
  file_path: "skills/expert-creator/assets/TOOL_REGISTRY.yaml"
```

#### Observe 1: Available Tools
Tool registry loaded. Available tools identified for recommendation.

### Phase 2: Tool Recommendation

#### Think 2: Select Appropriate Tools
Based on domain keywords, recommend tools that match the expert's needs.

#### Act 2: Generate Expert Metadata
Create expert metadata with recommended tools.

#### Observe 2: Metadata Generated
Expert ID, name, and tool configuration decided.

### Phase 3: File Generation

#### Think 3: Create Expert Structure
Plan the directory structure and file contents.

#### Act 3: Write Expert Files
```yaml
Action: write_file
Input:
  file_path: "experts/{expert_id}.expert.yaml"
  content: "{profile_content}"
```

#### Observe 3: Files Created
Expert profile, skill guide, and templates successfully generated.

---

## Output Artifacts

| File | Path | Description |
|------|------|-------------|
| Profile | `experts/{expert-id}.expert.yaml` | Expert configuration |
| Skill Guide | `skills/{expert-id}/SKILL.md` | ReAct workflow guide |
| Templates | `skills/{expert-id}/assets/templates/*.j2` | Output templates |
| Scripts | `skills/{expert-id}/scripts/*.py` | Optional auxiliary scripts |

## Notes

- This expert is a **system expert** and cannot be deleted through the UI
- Generated experts follow the same structural conventions as built-in experts
- Tool recommendations are based on domain analysis
- All generated content uses professional naming conventions
- Templates ensure consistent output structure
