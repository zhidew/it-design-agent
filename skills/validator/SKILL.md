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

# Tool Usage Notes
- Follow the runtime-generated tool contract from the expert YAML. Do not assume a tool is available unless the controller prompt exposes it.
- Prefer read and evidence-gathering steps first. Use write tools only to persist the owned validation artifacts or make bounded corrections under `artifacts/`.
- Use execution or validation tools only when they are explicitly exposed for this run and they are needed to confirm machine-readable outputs. Do not invent ad-hoc external tools.

# Notes
- Validation should surface actionable issues without inventing missing evidence.
- Distinguish failures, warnings, and passes clearly in the report.
- Prefer deterministic checks for machine-readable artifacts.
- Boundary: validate and report only. Do not generate replacement design content or silently "fix" missing upstream decisions inside the validation report.
- Dependency handling: when a finding points to an upstream artifact, cite that artifact and explain the inconsistency scope instead of proposing an ungrounded redesign.
