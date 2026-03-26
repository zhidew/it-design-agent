---
name: validator
description: Validate completeness and consistency of the generated design package and produce a validation report.
---

# Workflow
1. Scan generated artifacts under `artifacts/`.
2. Verify that required design outputs exist and are structurally valid.
3. Check cross-artifact consistency for names, APIs, data models, and traceability.
4. Use lightweight commands when needed to validate JSON, YAML, or other machine-readable outputs.
5. Produce `artifacts/validation-report.md`.
6. Record evidence in `evidence/validator.json`.

# Inputs
- `requirements`: path or text for the baseline requirement source.
- `existing_assets`: generated design artifacts.
- `output_root`: project design output root.

# Outputs
- `artifacts/validation-report.md`
- `evidence/validator.json`

# Tools
- list_files
- read_file_chunk
- grep_search
- extract_structure
- run_command

# Notes
- Validation should surface actionable issues without inventing missing evidence.
- Distinguish failures, warnings, and passes clearly in the report.
- Prefer deterministic checks for machine-readable artifacts.
- Boundary: validate and report only. Do not generate replacement design content or silently "fix" missing upstream decisions inside the validation report.
- Dependency handling: when a finding points to an upstream artifact, cite that artifact and explain the inconsistency scope instead of proposing an ungrounded redesign.
