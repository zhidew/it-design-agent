---
name: ddd-structure
description: Build a grounded domain model, DDD structure description, and context map from the business requirements.
---

# Workflow
1. Read the baseline requirements and any available domain-model artifacts.
2. Extract aggregates, entities, value objects, repositories, commands, queries, and domain events.
3. Produce `artifacts/class-diagram.md` for the main domain class diagram.
4. Produce `artifacts/ddd-structure.md` for the DDD structure narrative.
5. Produce `artifacts/context-map.md` for bounded-context relationships.
6. Record evidence in `evidence/ddd-structure.json`.

# Inputs
- `requirements`: path or text for the baseline requirement source.
- `existing_assets`: optional domain dictionaries or historical DDD assets.
- `output_root`: project design output root.
- `domain_name`: optional label used inside the content, not in the filename.

# Outputs
- `artifacts/class-diagram.md`
- `artifacts/ddd-structure.md`
- `artifacts/context-map.md`
- `evidence/ddd-structure.json`

# Tools
- list_files
- read_file_chunk
- grep_search
- extract_structure
- write_file
- patch_file

# Notes
- Keep aggregate boundaries and invariants explicit.
- Use terminology consistent with requirements, schema, and API design.
- Use the templates under `assets/templates/` as style references.
- Boundary: own aggregates, entities, value objects, domain services, and context mapping only. Do not expand into full DDL, full request/response or event payload catalogs, deployment/runbook detail, or test plans.
- Dependency handling: consume upstream architecture and data artifacts as inputs. If an upstream artifact already settled a naming or ownership boundary, reference it instead of redefining it here.
