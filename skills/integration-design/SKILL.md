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

# Tool Usage Notes
- Follow the runtime-generated tool contract from the expert YAML. Do not assume a tool is available unless the controller prompt exposes it.
- Prefer read and grounding steps first. Use write tools only to persist owned integration artifacts or make bounded corrections under `artifacts/`.
- Use execution-oriented tools only when explicitly exposed and when they materially improve confidence in structured outputs.

# Notes
- Make idempotency keys, retry policy, timeout policy, circuit breaking, and compensation flow explicit.
- Keep every statement grounded in the requirement text or upstream artifacts.
- Use the templates under `assets/templates/` as style references.
- Boundary: own cross-service/external integration contracts, async events, retries, idempotency, timeout, and compensation only. Do not duplicate full REST schema catalogs, full DDL/index design, config matrices, ops runbooks, or test plans.
- Dependency handling: treat upstream architecture and API/data outputs as constraints. Reuse their names and boundaries; if they are insufficient, record a targeted assumption instead of redefining their artifacts here.
