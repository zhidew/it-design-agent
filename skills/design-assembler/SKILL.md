---
name: design-assembler
description: Assemble all structured design artifacts into the final detailed design package and traceability outputs.
---

# Workflow
1. Read the baseline requirements and all subagent artifacts under `artifacts/`.
2. Merge architecture, domain, data, API, flow, integration, config, test, and ops decisions into a single narrative.
3. Produce `artifacts/detailed-design.md`.
4. Produce `artifacts/traceability.json`.
5. Produce `artifacts/review-checklist.md`.
6. Record evidence in `evidence/design-assembler.json`.

# Inputs
- `requirements`: path or text for the baseline requirement source.
- `existing_assets`: all generated design artifacts.
- `output_root`: project design output root.

# Outputs
- `artifacts/detailed-design.md`
- `artifacts/traceability.json`
- `artifacts/review-checklist.md`
- `evidence/design-assembler.json`

# Tool Usage Notes
- Follow the runtime-generated tool contract from the expert YAML. Do not assume a tool is available unless the controller prompt exposes it.
- Prefer reading and reconciling upstream artifacts first. Use write tools only to assemble owned deliverables or make bounded corrections under `artifacts/`.
- Do not use the assembler to bypass upstream ownership. If evidence is missing or conflicting, record the smallest grounded normalization instead of inventing new design scope.

# Notes
- Preserve cross-artifact consistency and terminology.
- The traceability output must map requirements to the generated design decisions.
- Use the templates under `assets/templates/` as style references.
- Boundary: assemble and align upstream artifacts only. Do not invent a brand-new detailed design that bypasses or overwrites upstream expert outputs.
- Dependency handling: when two upstream artifacts conflict, surface the conflict, choose the smallest necessary normalization, and keep the original source references traceable.
