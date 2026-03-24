---
name: integration-design
description: Design service-to-service and external integration contracts, including idempotency, retry, compensation, and AsyncAPI event definitions.
---

# Workflow
1. Read the baseline requirements and any upstream integration-relevant artifacts.
2. Extract downstream calls, callbacks, asynchronous events, retry rules, and compensation signals.
3. Produce `artifacts/integration.md` with grounded integration design decisions.
4. Produce `artifacts/asyncapi.yaml` for the event contract.
5. Record evidence in `evidence/integration-design.json`.

# Inputs
- `requirements`: path or text for the baseline requirement source.
- `existing_assets`: optional upstream API or integration artifacts.
- `output_root`: project design output root.
- `provider`: optional provider label used inside the document content, not in the filename.

# Outputs
- `artifacts/integration.md`
- `artifacts/asyncapi.yaml`
- `evidence/integration-design.json`

# Tools
- list_files
- read_file_chunk
- grep_search
- extract_structure
- write_file
- patch_file

# Notes
- Make idempotency keys, retry policy, timeout policy, circuit breaking, and compensation flow explicit.
- Keep every statement grounded in the requirement text or upstream artifacts.
- Use the templates under `assets/templates/` as style references.
