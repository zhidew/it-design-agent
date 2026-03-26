---
name: flow-design
description: Generate grounded sequence and state-flow artifacts for the core business process and its exception paths.
---

# Workflow
1. Read the baseline requirements and any existing flow-related artifacts.
2. Extract participants, ordered interactions, callbacks, state transitions, and exception branches.
3. Produce `artifacts/sequence.md` as the main sequence diagram.
4. Produce `artifacts/state.md` as the main state machine or lifecycle view.
5. Record evidence in `evidence/flow-design.json`.

# Inputs
- `requirements`: path or text for the baseline requirement source.
- `existing_assets`: optional flow, BPMN, or state-related assets.
- `output_root`: project design output root.

# Outputs
- `artifacts/sequence.md`
- `artifacts/state.md`
- `evidence/flow-design.json`

# Tools
- list_files
- read_file_chunk
- grep_search
- extract_structure
- write_file
- patch_file

# Notes
- Cover both mainline and exception behavior.
- Keep participant naming consistent with architecture and API artifacts.
- Use Mermaid output compatible with the flow templates under `assets/templates/`.
- Boundary: own sequence and lifecycle/state views only. Do not restate full API schemas, AsyncAPI payload details, DDL/index design, config matrices, ops runbooks, or test inventories.
- Dependency handling: use upstream architecture/API/integration naming directly. When an interaction depends on another expert's detailed contract, reference the artifact and keep only the flow-level abstraction here.
