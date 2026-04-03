# IT Design Agent

IT Design Agent is a multi-expert detailed design platform for enterprise software projects. It combines FastAPI, React, LangGraph, and YAML-defined experts to turn requirements plus project assets into structured design deliverables.

## What It Does

- Generates design artifacts through a planner plus multiple domain experts
- Uses backend expert YAML as the single source of truth for expert metadata
- Supports project-level configuration for repositories, databases, knowledge bases, models, and enabled experts
- Streams workflow progress to the UI through SSE
- Stores project metadata and workflow state locally under `projects/.orchestrator/`

## Core Stack

- Backend: FastAPI
- Frontend: React + Vite
- Orchestration: LangGraph
- Expert registry: YAML manifests in `experts/`
- Expert skills: prompt/templates/assets in `skills/`
- Metadata store: SQLite

## Repository Layout

```text
it-design-agent/
|-- api_server/              # FastAPI backend and orchestration runtime
|-- admin-ui/                # React frontend
|-- config/                  # Phase orchestration config
|-- experts/                 # Expert YAML manifests
|-- skills/                  # Expert skill packages
|-- projects/                # Generated project data and local metadata
|-- start-backend.bat        # Windows backend bootstrap
|-- start-frontend.bat       # Windows frontend bootstrap
|-- start-all.bat            # Windows all-in-one bootstrap
|-- .env.example             # Backend/system environment example
`-- README.md
```

## Expert Source Of Truth

Expert names, IDs, descriptions, dependencies, and expected outputs are defined in backend YAML manifests under `experts/`.

Examples:

- `experts/modular-design.expert.yaml`
- `experts/api-design.expert.yaml`

Frontend i18n files are not the source of expert metadata.

## Built-in Experts

| Expert ID | Display Name | Primary Outputs |
|---|---|---|
| `modular-design` | 模块化设计专家 / Modular Design Expert | `architecture.md`, `module-map.json` |
| `data-design` | 数据设计专家 / Data Design Expert | `schema.sql`, `er.md`, `migration-plan.md` |
| `ddd-structure` | 领域建模专家 / DDD Structure Expert | `ddd-structure.md`, `class-diagram.md`, `context-map.md` |
| `api-design` | API 设计专家 / API Design Expert | `api-design.md`, `errors-rfc9457.json` |
| `integration-design` | 集成设计专家 / Integration Design Expert | `integration.md`, `asyncapi.yaml` |
| `flow-design` | 流程设计专家 / Flow Design Expert | `sequence.md`, `state.md` |
| `config-design` | 配置设计专家 / Configuration Design Expert | `config-catalog.yaml`, `config-matrix.md` |
| `ops-design` | 运维设计专家 / Ops Design Expert | `slo.yaml`, `observability-spec.yaml`, `deployment-runbook.md` |
| `test-design` | 测试设计专家 / Test Design Expert | `test-inputs.md`, `coverage-map.json` |
| `design-assembler` | 设计组装专家 / Design Assembler | `detailed-design.md`, `traceability.json`, `review-checklist.md` |
| `validator` | 校验专家 / Validator | validation findings and workflow validation output |

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Windows batch scripts are provided, but manual startup also works cross-platform

### 1. Install Backend Dependencies

```bash
python -m venv venv
venv\Scripts\activate
pip install -r api_server/requirements.txt
```

### 2. Configure Backend Environment

```bash
copy .env.example .env
```

Edit `.env` and at minimum set:

- `LLM_PROVIDER`
- `OPENAI_API_KEY`
- `OPENAI_MODEL_NAME`

### 3. Install Frontend Dependencies

```bash
cd admin-ui
npm install
```

### 4. Configure Frontend API Address

```bash
copy admin-ui\.env.example admin-ui\.env.development
```

The frontend reads `VITE_API_BASE_URL` from `admin-ui/.env.development`.

### 5. Start Services

Windows:

```bash
start-all.bat
```

Or separately:

```bash
start-backend.bat
start-frontend.bat
```

Manual startup:

```bash
cd api_server
python main.py
```

```bash
cd admin-ui
npm run dev
```

### 6. Open the App

- Frontend: [http://localhost:5173](http://localhost:5173)
- Backend API: [http://localhost:8000](http://localhost:8000)
- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)

## Environment Variables

### Backend/System `.env`

The backend loads the root `.env` file from the repository root.

| Variable | Default | Required | Description |
|---|---|---|---|
| `LLM_PROVIDER` | `openai` | Yes | Current documented provider selector |
| `OPENAI_API_KEY` | empty | Yes | API key for OpenAI-compatible gateways |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | No | Base URL for OpenAI-compatible APIs |
| `OPENAI_MODEL_NAME` | `gpt-4o` | Yes | Model name for OpenAI-compatible APIs |
| `IT_DESIGN_AGENT_METADATA_KEY` | auto-generated if absent | No | Encrypts secrets stored in metadata SQLite |
| `LLM_MIN_CALL_INTERVAL_SECONDS` | `0` | No | Minimum delay between LLM request starts |
| `LLM_REQUEST_TIMEOUT_SECONDS` | `600` | No | Per-request timeout for expert generation and other synchronous LLM calls; set `0` to disable |
| `USE_DYNAMIC_SUBAGENT` | `true` | No | Enables dynamic expert execution path |
| `USE_MARKDOWN_UPSERT_TOOL` | `true` | No | Enables markdown upsert behavior in dynamic subagent finalization |
| `ORCHESTRATOR_MAX_PARALLEL` | `2` | No | Max parallel executable tasks in orchestration |
| `ORCHESTRATOR_STALE_TIMEOUT_SECONDS` | `180` | No | Timeout for stale running workflow detection |
| `AGENT_MAX_REACT_STEPS` | `99` | No | Max ReAct steps per expert |
| `AGENT_MAX_ACTIONS_PER_STEP` | `2` | No | Max read-only actions per ReAct step |
| `AGENT_MAX_FINALIZATION_STEPS` | `16` | No | Max finalization refinement steps |
| `AGENT_REACT_PLATEAU_WINDOW` | `4` | No | Plateau detection window for expert iteration |
| `AGENT_REACT_MIN_STEPS_BEFORE_PLATEAU` | `8` | No | Minimum steps before plateau detection activates |
| `AGENT_PATH_NOT_FOUND_REPEAT_LIMIT` | `2` | No | Repeat limit for missing-path tool errors |

### `AGENT_*` Parameter Definitions

These parameters control how each expert iterates during dynamic execution.

| Variable | What It Controls | Practical Effect |
|---|---|---|
| `AGENT_MAX_REACT_STEPS` | Upper bound of ReAct loop iterations for one expert | Increase it when experts stop too early on complex projects; decrease it to cap runtime and token cost |
| `AGENT_MAX_ACTIONS_PER_STEP` | Max number of batched read-only actions in one step | Higher values improve evidence gathering speed, but can make each step noisier and less focused |
| `AGENT_MAX_FINALIZATION_STEPS` | Max number of artifact refinement/finalization rounds | Increase it if outputs often need multiple polish passes before stabilizing |
| `AGENT_REACT_PLATEAU_WINDOW` | Number of recent steps inspected for “no progress” detection | Smaller values make plateau detection more aggressive; larger values make it more tolerant |
| `AGENT_REACT_MIN_STEPS_BEFORE_PLATEAU` | Minimum loop count before plateau detection can trigger | Prevents early termination on tasks that need several exploratory steps up front |
| `AGENT_PATH_NOT_FOUND_REPEAT_LIMIT` | How many repeated missing-path failures are tolerated | Prevents the same bad file/path lookup from being retried indefinitely |

Recommended tuning guidance:

- Keep defaults unless you have observed repeated early stops or excessive runtime.
- Raise `AGENT_MAX_REACT_STEPS` and `AGENT_MAX_FINALIZATION_STEPS` for larger, messier codebases.
- Lower `AGENT_MAX_ACTIONS_PER_STEP` if expert behavior becomes too broad or unstable.
- Lower `AGENT_PATH_NOT_FOUND_REPEAT_LIMIT` if runs waste time on repeated nonexistent paths.

### Frontend `admin-ui/.env.development`

| Variable | Default | Required | Description |
|---|---|---|---|
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000/api/v1` | No | Frontend API base URL |

## Configuration Notes

- Backend metadata database: `projects/.orchestrator/metadata.sqlite`
- LangGraph checkpoints: `projects/.orchestrator/langgraph-checkpoints.sqlite`
- Backend currently starts on `0.0.0.0:8000` in `api_server/main.py`
- Frontend Vite dev server defaults to port `5173`
- Expert creation in Expert Center uses the system-level LLM env settings from `.env`, not a specific project's saved model selection

## Expert Development

To add a new expert:

1. Add a YAML manifest under `experts/`
2. Add a matching skill package under `skills/<expert-id>/`
3. Define expected outputs, dependencies, and boundary contract in YAML
4. Reload experts from the backend management API or restart the backend

New expert manifests should follow the same pattern as `experts/modular-design.expert.yaml`.

## Common Commands

Backend syntax check:

```bash
python -m py_compile api_server\\main.py
```

Frontend build:

```bash
cd admin-ui
npm run build
```

Search expert references:

```bash
rg -n "modular-design|api-design|data-design" .
```

## Notes

- Project-level expert enablement is stored in the local metadata database
- Historical project data lives under `projects/`
- `.env` is ignored by git; use `.env.example` as the shared template
