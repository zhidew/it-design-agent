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

# Tools
- list_files
- read_file_chunk
- grep_search
- extract_structure
- write_file
- patch_file

# Notes
- Preserve cross-artifact consistency and terminology.
- The traceability output must map requirements to the generated design decisions.
- Use the templates under `assets/templates/` as style references.
