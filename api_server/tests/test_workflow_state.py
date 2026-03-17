import asyncio
import datetime
import json
import sqlite3
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
import shutil
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
API_SERVER_ROOT = REPO_ROOT / "api_server"
if str(API_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(API_SERVER_ROOT))

langgraph_module = ModuleType("langgraph")
langgraph_graph_module = ModuleType("langgraph.graph")
langgraph_checkpoint_module = ModuleType("langgraph.checkpoint")
langgraph_checkpoint_memory_module = ModuleType("langgraph.checkpoint.memory")
langgraph_checkpoint_sqlite_module = ModuleType("langgraph.checkpoint.sqlite")
langgraph_checkpoint_sqlite_aio_module = ModuleType("langgraph.checkpoint.sqlite.aio")
scripts_module = ModuleType("scripts")
llm_generator_module = ModuleType("scripts.llm_generator")
yaml_module = ModuleType("yaml")
pydantic_module = ModuleType("pydantic")


class _FakeCompiledGraph:
    def get_state(self, config):
        return None

    def update_state(self, config, payload):
        return None

    async def astream(self, initial_state, config=None, stream_mode=None):
        if False:
            yield initial_state


class _FakeStateGraph:
    def __init__(self, state_type):
        self.state_type = state_type

    def add_node(self, name, node):
        return None

    def set_entry_point(self, name):
        return None

    def add_edge(self, source, target):
        return None

    def add_conditional_edges(self, source, router):
        return None

    def compile(self, checkpointer=None):
        return _FakeCompiledGraph()


class _FakeMemorySaver:
    pass


class _FakeSqliteSaver:
    def __init__(self, conn_string=None):
        self.conn_string = conn_string
        self.get_next_version = lambda current=None, channel=None: 1

    @classmethod
    def from_conn_string(cls, conn_string):
        return cls(conn_string=conn_string)


class _FakeAsyncSaverContextManager:
    def __init__(self, conn_string=None):
        self.saver = _FakeSqliteSaver(conn_string=conn_string)

    async def __aenter__(self):
        return self.saver

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeAsyncSqliteSaver:
    @classmethod
    def from_conn_string(cls, conn_string):
        return _FakeAsyncSaverContextManager(conn_string=conn_string)


class _FakeSubagentOutput:
    def __init__(self, reasoning="", artifacts=None):
        self.reasoning = reasoning
        self.artifacts = artifacts or {}


def _fake_generate_with_llm(system_prompt, user_prompt, requested_artifacts):
    return _FakeSubagentOutput(reasoning="stub", artifacts={"active_agents": "[]"})


class _FakeBaseModel:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    @classmethod
    def model_validate(cls, payload):
        return cls(**payload)

    @classmethod
    def parse_obj(cls, payload):
        return cls(**payload)

    def model_dump(self):
        return self.__dict__.copy()

    def dict(self):
        return self.__dict__.copy()


def _fake_field(default=None, **kwargs):
    return default


langgraph_graph_module.StateGraph = _FakeStateGraph
langgraph_graph_module.END = "END"
langgraph_checkpoint_memory_module.MemorySaver = _FakeMemorySaver
langgraph_checkpoint_sqlite_module.SqliteSaver = _FakeSqliteSaver
langgraph_checkpoint_sqlite_aio_module.AsyncSqliteSaver = _FakeAsyncSqliteSaver

sys.modules.setdefault("langgraph", langgraph_module)
sys.modules.setdefault("langgraph.graph", langgraph_graph_module)
sys.modules.setdefault("langgraph.checkpoint", langgraph_checkpoint_module)
sys.modules.setdefault("langgraph.checkpoint.memory", langgraph_checkpoint_memory_module)
sys.modules.setdefault("langgraph.checkpoint.sqlite", langgraph_checkpoint_sqlite_module)
sys.modules.setdefault("langgraph.checkpoint.sqlite.aio", langgraph_checkpoint_sqlite_aio_module)
llm_generator_module.generate_with_llm = _fake_generate_with_llm
llm_generator_module.SubagentOutput = _FakeSubagentOutput
sys.modules.setdefault("scripts", scripts_module)
sys.modules.setdefault("scripts.llm_generator", llm_generator_module)
yaml_module.safe_load = lambda content: {}
sys.modules.setdefault("yaml", yaml_module)
pydantic_module.BaseModel = _FakeBaseModel
pydantic_module.Field = _fake_field
sys.modules.setdefault("pydantic", pydantic_module)

from contextlib import contextmanager

from graphs.state import merge_artifacts, merge_task_queue
from graphs import nodes
from models.events import NodeStartedEvent, ToolEvent, validate_event_payload
from graphs.tools import execute_tool
from services import orchestrator_service as orch


class WorkflowStateTests(unittest.TestCase):
    def setUp(self):
        orch.runtime_registry.clear()
        orch.jobs.clear()

    def make_temp_root(self, name: str) -> Path:
        root = REPO_ROOT / "api_server" / "tests" / ".tmp" / name
        if root.exists():
            shutil.rmtree(root)
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def test_merge_artifacts_preserves_parallel_updates(self):
        merged = merge_artifacts(
            {"architecture.md": "old architecture"},
            {"api-public.yaml": "new api"},
        )

        self.assertEqual(merged["architecture.md"], "old architecture")
        self.assertEqual(merged["api-public.yaml"], "new api")

    def test_merge_task_queue_preserves_distinct_task_updates(self):
        merged = merge_task_queue(
            [
                {"id": "1", "agent_type": "architecture-mapping", "status": "todo"},
                {"id": "2", "agent_type": "api-design", "status": "todo"},
            ],
            [
                {"id": "1", "status": "success"},
                {"id": "2", "status": "failed"},
            ],
        )

        self.assertEqual(
            merged,
            [
                {"id": "1", "agent_type": "architecture-mapping", "status": "success"},
                {"id": "2", "agent_type": "api-design", "status": "failed"},
            ],
        )

    def test_supervisor_dispatches_multiple_ready_tasks_up_to_parallel_limit(self):
        decision = nodes.supervisor(
            {
                "workflow_phase": "ARCHITECTURE",
                "design_context": {"orchestrator": {"max_parallel_tasks": 2}},
                "task_queue": [
                    {"id": "0", "agent_type": "planner", "status": "success", "dependencies": [], "priority": 100},
                    {"id": "1", "agent_type": "architecture-mapping", "status": "todo", "dependencies": ["0"], "priority": 90},
                    {"id": "3", "agent_type": "data-design", "status": "todo", "dependencies": ["0"], "priority": 80},
                    {"id": "5", "agent_type": "api-design", "status": "todo", "dependencies": ["0"], "priority": 70},
                    {"id": "10", "agent_type": "design-assembler", "status": "todo", "dependencies": ["1", "3", "5"], "priority": 20},
                ],
            }
        )

        self.assertEqual(decision["next"], ["architecture-mapping", "data-design"])
        self.assertEqual(
            decision["dispatched_tasks"],
            [
                {"id": "1", "agent_type": "architecture-mapping"},
                {"id": "3", "agent_type": "data-design"},
            ],
        )
        statuses = {task["agent_type"]: task["status"] for task in decision["task_queue"]}
        self.assertEqual(statuses["architecture-mapping"], "running")
        self.assertEqual(statuses["data-design"], "running")
        self.assertEqual(statuses["api-design"], "todo")
        self.assertEqual(statuses["design-assembler"], "todo")

    def test_supervisor_can_fall_back_to_serial_mode(self):
        decision = nodes.supervisor(
            {
                "workflow_phase": "ARCHITECTURE",
                "design_context": {"orchestrator": {"max_parallel_tasks": 1}},
                "task_queue": [
                    {"id": "0", "agent_type": "planner", "status": "success", "dependencies": [], "priority": 100},
                    {"id": "1", "agent_type": "architecture-mapping", "status": "todo", "dependencies": ["0"], "priority": 90},
                    {"id": "3", "agent_type": "data-design", "status": "todo", "dependencies": ["0"], "priority": 80},
                ],
            }
        )

        self.assertEqual(decision["next"], "architecture-mapping")
        statuses = {task["agent_type"]: task["status"] for task in decision["task_queue"]}
        self.assertEqual(statuses["architecture-mapping"], "running")
        self.assertEqual(statuses["data-design"], "todo")

    def test_supervisor_parallel_dispatch_emits_multiple_node_started_events(self):
        temp_root = self.make_temp_root("parallel-node-events")
        orch._ensure_job("run-1")
        payload = {
            "next": ["architecture-mapping", "api-design"],
            "dispatched_tasks": [
                {"id": "1", "agent_type": "architecture-mapping"},
                {"id": "5", "agent_type": "api-design"},
            ],
            "task_queue": [
                {"id": "1", "agent_type": "architecture-mapping", "status": "running"},
                {"id": "5", "agent_type": "api-design", "status": "running"},
            ],
            "history": [],
        }

        with patch.object(orch, "PROJECTS_DIR", temp_root / "projects"), patch.object(orch, "_load_artifacts_from_disk", return_value={}):
            orch._handle_structured_graph_event("run-1", "demo", "v1", "supervisor", payload, {})

        node_started_events = [event for event in orch.get_job_events("run-1") if event["event_type"] == "node_started"]
        self.assertEqual(len(node_started_events), 2)
        self.assertEqual({event["node_type"] for event in node_started_events}, {"architecture-mapping", "api-design"})

    def test_normalize_state_returns_explicit_runtime_fields(self):
        temp_projects = self.make_temp_root("normalize") / "projects"
        (temp_projects / "demo" / "v1" / "artifacts").mkdir(parents=True, exist_ok=True)
        (temp_projects / "demo" / "v1" / "artifacts" / "architecture.md").write_text("arch", encoding="utf-8")

        with patch.object(orch, "PROJECTS_DIR", temp_projects):
            state = orch._normalize_state(
                "demo",
                "v1",
                {
                    "workflow_phase": "ARCHITECTURE",
                    "task_queue": [
                        {"id": "1", "agent_type": "architecture-mapping", "status": "running"},
                        {"id": "2", "agent_type": "api-design", "status": "todo"},
                    ],
                    "history": ["started"],
                },
            )

        self.assertEqual(state["run_status"], "running")
        self.assertEqual(state["current_node"], "architecture-mapping")
        self.assertFalse(state["can_resume"])
        self.assertIsNone(state["waiting_reason"])
        self.assertIn("updated_at", state)
        self.assertEqual(state["artifacts"]["architecture.md"], "arch")

    def test_get_workflow_state_keeps_failed_legacy_versions_resumable(self):
        temp_root = self.make_temp_root("legacy")
        temp_projects = temp_root / "projects"
        version_root = temp_projects / "demo" / "v1"
        (version_root / "logs").mkdir(parents=True, exist_ok=True)
        (version_root / "baseline").mkdir(parents=True, exist_ok=True)
        (version_root / "logs" / "validator.log").write_text("[ERROR] failed", encoding="utf-8")

        @contextmanager
        def fake_graph():
            class _Graph:
                def get_state(self, config):
                    return None

            yield _Graph()

        with patch.object(orch, "PROJECTS_DIR", temp_projects), patch.object(orch, "BASE_DIR", temp_root), patch.object(orch, "_graph_for_state", fake_graph):
            state = orch.get_workflow_state("demo", "v1")

        self.assertEqual(state["run_status"], "failed")
        self.assertTrue(state["can_resume"])
        self.assertIn("updated_at", state)

    def test_normalize_state_restores_waiting_metadata_without_runtime_cache(self):
        orch.runtime_registry.clear()

        state = orch._normalize_state(
            "demo",
            "v1",
            {
                "run_id": "run-42",
                "workflow_phase": "ARCHITECTURE",
                "task_queue": [
                    {"id": "0", "agent_type": "planner", "status": "success"},
                    {"id": "1", "agent_type": "architecture-mapping", "status": "todo"},
                ],
                "history": ["planner finished"],
                "run_status": "waiting_human",
                "waiting_reason": "Please clarify payment channels before planning continues.",
                "last_worker": "planner",
                "human_intervention_required": True,
            },
        )

        self.assertEqual(state["run_id"], "run-42")
        self.assertEqual(state["run_status"], "waiting_human")
        self.assertEqual(state["current_node"], "planner")
        self.assertTrue(state["can_resume"])
        self.assertEqual(state["waiting_reason"], "Please clarify payment channels before planning continues.")

    def test_normalize_state_does_not_mark_planner_pause_as_success(self):
        orch.runtime_registry.clear()

        state = orch._normalize_state(
            "demo",
            "v1",
            {
                "workflow_phase": "ARCHITECTURE",
                "task_queue": [
                    {"id": "0", "agent_type": "planner", "status": "success"},
                    {"id": "1", "agent_type": "architecture-mapping", "status": "todo"},
                ],
                "history": ["planner finished"],
                "run_status": "success",
                "human_intervention_required": True,
                "waiting_reason": "Please clarify payment channels before planning continues.",
                "last_worker": "planner",
                "current_node": "bootstrap",
            },
        )

        self.assertEqual(state["run_status"], "waiting_human")
        self.assertEqual(state["current_node"], "planner")
        self.assertTrue(state["can_resume"])

    def test_normalize_state_can_ignore_stale_runtime_when_all_tasks_succeed(self):
        state = orch._normalize_state(
            "demo",
            "v1",
            {
                "workflow_phase": "DONE",
                "task_queue": [
                    {"id": "0", "agent_type": "planner", "status": "success"},
                    {"id": "1", "agent_type": "architecture-mapping", "status": "success"},
                    {"id": "10", "agent_type": "design-assembler", "status": "success"},
                    {"id": "11", "agent_type": "validator", "status": "success"},
                ],
                "last_worker": "validator",
                "current_node": "supervisor",
            },
            runtime={},
        )

        self.assertEqual(state["run_status"], "success")
        self.assertEqual(state["current_node"], "supervisor")
        self.assertFalse(state["can_resume"])

    def test_normalize_state_marks_orphaned_running_node_as_failed_for_manual_recovery(self):
        stale_timestamp = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=10)).isoformat()

        state = orch._normalize_state(
            "demo",
            "v1",
            {
                "workflow_phase": "ARCHITECTURE",
                "task_queue": [
                    {"id": "0", "agent_type": "planner", "status": "success"},
                    {"id": "1", "agent_type": "architecture-mapping", "status": "running"},
                    {"id": "10", "agent_type": "design-assembler", "status": "todo"},
                ],
                "current_node": "architecture-mapping",
                "updated_at": stale_timestamp,
            },
            runtime={},
        )

        self.assertEqual(state["run_status"], "failed")
        self.assertTrue(state["can_resume"])
        self.assertTrue(state["stale_execution_detected"])
        self.assertEqual(state["current_node"], "architecture-mapping")
        failed_task = next(task for task in state["task_queue"] if task["agent_type"] == "architecture-mapping")
        self.assertEqual(failed_task["status"], "failed")
        self.assertIn("Execution appears stalled", state["waiting_reason"])

    def test_normalize_state_marks_stale_running_runtime_without_active_task_as_failed(self):
        stale_timestamp = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=10)).isoformat()

        state = orch._normalize_state(
            "demo",
            "v1",
            {
                "workflow_phase": "INTERFACE",
                "task_queue": [
                    {"id": "0", "agent_type": "planner", "status": "success"},
                    {"id": "7", "agent_type": "flow-design", "status": "running"},
                ],
                "current_node": "flow-design",
                "updated_at": stale_timestamp,
            },
            runtime={
                "job_id": "run-stale",
                "run_status": "running",
                "current_node": "flow-design",
                "updated_at": stale_timestamp,
            },
        )

        self.assertEqual(state["run_status"], "failed")
        self.assertTrue(state["can_resume"])
        self.assertTrue(state["stale_execution_detected"])
        failed_task = next(task for task in state["task_queue"] if task["agent_type"] == "flow-design")
        self.assertEqual(failed_task["status"], "failed")
        self.assertIn("Execution appears stalled", state["waiting_reason"])

    def test_normalize_state_rebuilds_task_queue_for_legacy_state_without_tasks(self):
        temp_root = self.make_temp_root("rebuild-legacy")
        temp_projects = temp_root / "projects"
        version_root = temp_projects / "demo" / "v1"
        (version_root / "artifacts").mkdir(parents=True, exist_ok=True)
        (version_root / "artifacts" / "architecture.md").write_text("arch", encoding="utf-8")
        (version_root / "baseline").mkdir(parents=True, exist_ok=True)
        (version_root / "baseline" / "requirements.json").write_text(
            '{"active_agents":["architecture-mapping","design-assembler","validator"]}',
            encoding="utf-8",
        )

        with patch.object(orch, "PROJECTS_DIR", temp_projects):
            state = orch._normalize_state(
                "demo",
                "v1",
                {
                    "workflow_phase": "ARCHIVED",
                    "task_queue": [],
                    "history": ["done"],
                },
            )

        self.assertGreater(len(state["task_queue"]), 0)
        self.assertEqual(state["task_queue"][0]["agent_type"], "planner")

    def test_normalize_state_marks_legacy_release_artifacts_as_success(self):
        temp_root = self.make_temp_root("legacy-success")
        temp_projects = temp_root / "projects"
        version_root = temp_projects / "demo" / "v1"
        (version_root / "artifacts").mkdir(parents=True, exist_ok=True)
        (version_root / "release").mkdir(parents=True, exist_ok=True)
        (version_root / "logs").mkdir(parents=True, exist_ok=True)
        (version_root / "artifacts" / "architecture.md").write_text("arch", encoding="utf-8")
        (version_root / "release" / "detailed-design.md").write_text("design", encoding="utf-8")
        (version_root / "logs" / "validator.log").write_text("[SUCCESS] All M2 Gates Passed!", encoding="utf-8")
        (version_root / "baseline").mkdir(parents=True, exist_ok=True)
        (version_root / "baseline" / "requirements.json").write_text(
            '{"active_agents":["architecture-mapping","design-assembler","validator"]}',
            encoding="utf-8",
        )

        with patch.object(orch, "PROJECTS_DIR", temp_projects):
            state = orch._normalize_state(
                "demo",
                "v1",
                {
                    "workflow_phase": "ARCHIVED",
                    "task_queue": [],
                    "history": ["done"],
                },
            )

        statuses = {task["agent_type"]: task["status"] for task in state["task_queue"]}
        self.assertEqual(statuses["planner"], "success")
        self.assertEqual(statuses["architecture-mapping"], "success")
        self.assertEqual(statuses["design-assembler"], "success")
        self.assertEqual(statuses["validator"], "success")
        self.assertEqual(state["run_status"], "success")
        self.assertFalse(state["can_resume"])

    def test_record_graph_event_tolerates_none_output(self):
        orch.runtime_registry.clear()

        payload = orch._record_graph_event("demo", "v1", "supervisor", None, job_id="job-1")

        self.assertEqual(payload, {})
        runtime = orch.runtime_registry["demo_v1"]
        self.assertEqual(runtime["run_status"], "running")
        self.assertEqual(runtime["current_node"], "supervisor")
        self.assertIsNone(runtime["waiting_reason"])

    def test_structured_event_contract_validates_payload(self):
        event = validate_event_payload(
            {
                "event_id": "evt-1",
                "event_type": "node_started",
                "run_id": "run-1",
                "node_id": "0",
                "node_type": "planner",
                "timestamp": "2026-03-15T00:00:00+00:00",
            }
        )

        self.assertIsInstance(event, NodeStartedEvent)
        self.assertEqual(event.node_type, "planner")

    def test_tool_event_contract_validates_payload(self):
        event = validate_event_payload(
            {
                "event_id": "evt-tool-1",
                "event_type": "tool_event",
                "run_id": "run-1",
                "node_id": "0",
                "node_type": "planner",
                "tool_name": "list_files",
                "status": "success",
                "error_code": "OK",
                "duration_ms": 8,
                "tool_input": {"root_dir": "D:/tmp/project"},
                "tool_output": {"files": [{"path": "baseline/spec.md", "name": "spec.md"}]},
                "timestamp": "2026-03-15T00:00:00+00:00",
            }
        )

        self.assertIsInstance(event, ToolEvent)
        self.assertEqual(event.tool_name, "list_files")

    def test_publish_event_stores_structured_payload(self):
        orch.jobs.clear()

        stored = orch._publish_event(
            "run-1",
            {
                "event_id": "evt-2",
                "event_type": "run_completed",
                "run_id": "run-1",
                "status": "success",
                "timestamp": "2026-03-15T00:00:00+00:00",
            },
        )

        self.assertEqual(stored["event_type"], "run_completed")
        self.assertEqual(orch.get_job_events("run-1")[0]["status"], "success")

    def test_handle_structured_graph_event_emits_tool_events(self):
        orch.jobs.clear()
        temp_root = self.make_temp_root("tool-events")
        with patch.object(orch, "PROJECTS_DIR", temp_root / "projects"):
            orch._handle_structured_graph_event(
                "run-1",
                "demo",
                "v1",
                "planner",
                {
                    "task_queue": [{"id": "0", "agent_type": "planner", "status": "success"}],
                    "tool_results": [
                        {
                            "tool_name": "list_files",
                            "status": "success",
                            "error_code": "OK",
                            "duration_ms": 3,
                            "input": {"root_dir": "D:/tmp/project"},
                            "output": {"files": [{"path": "baseline/spec.md", "name": "spec.md"}]},
                        }
                    ],
                },
                previous_artifacts={},
            )

        tool_events = [event for event in orch.get_job_events("run-1") if event["event_type"] == "tool_event"]
        self.assertEqual(len(tool_events), 1)
        self.assertEqual(tool_events[0]["tool_name"], "list_files")
        self.assertEqual(tool_events[0]["status"], "success")

    def test_bootstrap_initializes_planner_as_running(self):
        temp_root = self.make_temp_root("bootstrap")
        with patch.object(nodes, "BASE_DIR", temp_root):
            state = self.async_run(
                nodes.bootstrap_node(
                    {
                        "project_id": "demo",
                        "version": "v1",
                        "requirement": "Need payment design",
                    }
                )
            )

        self.assertEqual(state["workflow_phase"], "ANALYSIS")
        self.assertEqual(state["task_queue"][0]["agent_type"], "planner")
        self.assertEqual(state["task_queue"][0]["status"], "running")
        self.assertIn("[SYSTEM] Planner started.", state["history"])

    def test_planner_promotes_itself_to_success_and_generates_requirements(self):
        temp_root = self.make_temp_root("planner")
        baseline_dir = temp_root / "projects" / "demo" / "v1" / "baseline"
        logs_dir = temp_root / "projects" / "demo" / "v1" / "logs"
        baseline_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        (baseline_dir / "original-requirements.md").write_text("Need payment design", encoding="utf-8")

        fake_llm_output = _FakeSubagentOutput(
            reasoning="Selected api and data design",
            artifacts={"active_agents": '["api-design","data-design"]'},
        )

        with patch.object(nodes, "BASE_DIR", temp_root), patch.object(nodes, "generate_with_llm", return_value=fake_llm_output):
            state = self.async_run(
                nodes.planner_node(
                    {
                        "project_id": "demo",
                        "version": "v1",
                        "requirement": "Need payment design",
                        "task_queue": [
                            {"id": "0", "agent_type": "planner", "status": "running", "dependencies": [], "priority": 100}
                        ],
                    }
                )
            )

        planner_task = next(task for task in state["task_queue"] if task["agent_type"] == "planner")
        api_task = next(task for task in state["task_queue"] if task["agent_type"] == "api-design")
        self.assertEqual(planner_task["status"], "success")
        self.assertEqual(api_task["status"], "todo")
        self.assertEqual(api_task["dependencies"], ["1"])
        self.assertIn("[SYSTEM] Planner finished.", state["history"])
        self.assertFalse(state["human_intervention_required"])
        self.assertEqual(state["run_status"], "running")
        self.assertIsNone(state["waiting_reason"])
        self.assertIsNone(state.get("pending_interrupt"))
        self.assertTrue((baseline_dir / "requirements.json").exists())

        requirements_payload = json.loads((baseline_dir / "requirements.json").read_text(encoding="utf-8"))
        self.assertIn("tool_context", requirements_payload)
        self.assertIn("list_files", requirements_payload["tool_context"])
        self.assertIn("extract_structure", requirements_payload["tool_context"])

    def test_planner_triggers_ask_human_when_information_is_insufficient(self):
        temp_root = self.make_temp_root("planner-ask-human")
        baseline_dir = temp_root / "projects" / "demo" / "v1" / "baseline"
        logs_dir = temp_root / "projects" / "demo" / "v1" / "logs"
        baseline_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        (baseline_dir / "original-requirements.md").write_text("Need payment design", encoding="utf-8")

        fake_llm_output = _FakeSubagentOutput(
            reasoning="Need merchant channel and deployment region before planning.",
            artifacts={
                "active_agents": json.dumps(
                    {
                        "needs_human": True,
                        "question": "请补充商户类型、支付渠道范围和部署区域。",
                        "context": {
                            "missing_information": ["merchant_type", "payment_channels", "deployment_region"],
                            "why_needed": "这些信息会影响 API、数据模型和合规设计。",
                            "options": [
                                {
                                    "value": "cn_wallets_only",
                                    "label": "CN wallets only",
                                    "description": "Alipay and WeChat in mainland China.",
                                },
                                "global_cards",
                            ],
                        },
                    },
                    ensure_ascii=False,
                )
            },
        )

        with patch.object(nodes, "BASE_DIR", temp_root), patch.object(nodes, "generate_with_llm", return_value=fake_llm_output):
            state = self.async_run(
                nodes.planner_node(
                    {
                        "project_id": "demo",
                        "version": "v1",
                        "requirement": "Need payment design",
                        "task_queue": [
                            {"id": "0", "agent_type": "planner", "status": "running", "dependencies": [], "priority": 100}
                        ],
                    }
                )
            )

        self.assertTrue(state["human_intervention_required"])
        self.assertEqual(state["run_status"], "waiting_human")
        self.assertIn("pending_interrupt", state)
        self.assertEqual(state["pending_interrupt"]["node_id"], "planner")
        self.assertEqual(state["pending_interrupt"]["resume_target"], "planner")
        self.assertIn("payment_channels", state["pending_interrupt"]["context"]["missing_information"])
        self.assertEqual(state["pending_interrupt"]["context"]["options"][0]["value"], "cn_wallets_only")
        self.assertEqual(state["pending_interrupt"]["context"]["options"][1]["label"], "global_cards")
        self.assertTrue(state["pending_interrupt"]["context"]["allow_free_text"])

    def test_planner_prompt_requires_material_sufficiency_assessment_before_asking_human(self):
        temp_root = self.make_temp_root("planner-prompt-contract")
        baseline_dir = temp_root / "projects" / "demo" / "v1" / "baseline"
        logs_dir = temp_root / "projects" / "demo" / "v1" / "logs"
        baseline_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        (baseline_dir / "original-requirements.md").write_text("Need payment design", encoding="utf-8")

        captured_prompts = {}

        def fake_generate(system_prompt, user_prompt, required_artifacts):
            captured_prompts["system_prompt"] = system_prompt
            captured_prompts["user_prompt"] = user_prompt
            return _FakeSubagentOutput(
                reasoning="Materials are sufficient.",
                artifacts={"active_agents": '["api-design","data-design"]'},
            )

        with patch.object(nodes, "BASE_DIR", temp_root), patch.object(nodes, "generate_with_llm", side_effect=fake_generate):
            self.async_run(
                nodes.planner_node(
                    {
                        "project_id": "demo",
                        "version": "v1",
                        "requirement": "Need payment design",
                        "task_queue": [
                            {"id": "0", "agent_type": "planner", "status": "running", "dependencies": [], "priority": 100}
                        ],
                    }
                )
            )

        self.assertIn("material sufficiency assessment", captured_prompts["system_prompt"])
        self.assertIn("If the existing materials are already sufficient", captured_prompts["system_prompt"])
        self.assertIn("ask only one focused clarification question at a time", captured_prompts["system_prompt"])
        self.assertIn("Evaluate whether the existing materials already provide enough information", captured_prompts["user_prompt"])

    def test_planner_includes_human_answer_summary_in_baseline_payload(self):
        temp_root = self.make_temp_root("planner-human-summary")
        baseline_dir = temp_root / "projects" / "demo" / "v1" / "baseline"
        logs_dir = temp_root / "projects" / "demo" / "v1" / "logs"
        baseline_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        (baseline_dir / "original-requirements.md").write_text("Need payment design", encoding="utf-8")

        fake_llm_output = _FakeSubagentOutput(
            reasoning="Selected api and data design with human clarifications.",
            artifacts={"active_agents": '["api-design","data-design"]'},
        )

        with patch.object(nodes, "BASE_DIR", temp_root), patch.object(nodes, "generate_with_llm", return_value=fake_llm_output):
            self.async_run(
                nodes.planner_node(
                    {
                        "project_id": "demo",
                        "version": "v1",
                        "requirement": "Need payment design",
                        "human_answers": {
                            "planner": [
                                {
                                    "interrupt_id": "int-1",
                                    "answer": "商户类型以直营网关商户为主，首期支持支付宝和微信，部署在境内华东区。",
                                    "summary": "补充了商户范围、渠道范围和部署区域。",
                                }
                            ]
                        },
                        "task_queue": [
                            {"id": "0", "agent_type": "planner", "status": "running", "dependencies": [], "priority": 100}
                        ],
                    }
                )
            )

        requirements_payload = json.loads((baseline_dir / "requirements.json").read_text(encoding="utf-8"))
        self.assertIn("human_inputs", requirements_payload)
        self.assertIn("summary", requirements_payload["human_inputs"])
        self.assertIn("支付宝", requirements_payload["human_inputs"]["summary"])
        self.assertEqual(requirements_payload["human_inputs"]["answers"][0]["interrupt_id"], "int-1")

    def test_planner_uses_tools_to_capture_uploaded_file_structure_without_full_text(self):
        temp_root = self.make_temp_root("planner-tools")
        baseline_dir = temp_root / "projects" / "demo" / "v1" / "baseline"
        logs_dir = temp_root / "projects" / "demo" / "v1" / "logs"
        baseline_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        file_body = "# Payment API\n## Scope\nNeed async settlement support\n## Constraints\nNo PII replication"
        (baseline_dir / "spec.md").write_text(file_body, encoding="utf-8")
        (baseline_dir / "config.json").write_text('{"service": {"name": "billing", "retries": 3}}', encoding="utf-8")

        fake_llm_output = _FakeSubagentOutput(
            reasoning="Selected api design from file structure",
            artifacts={"active_agents": '["api-design"]'},
        )

        with patch.object(nodes, "BASE_DIR", temp_root), patch.object(nodes, "generate_with_llm", return_value=fake_llm_output):
            state = self.async_run(
                nodes.planner_node(
                    {
                        "project_id": "demo",
                        "version": "v1",
                        "requirement": "Need payment design",
                        "task_queue": [
                            {"id": "0", "agent_type": "planner", "status": "running", "dependencies": [], "priority": 100}
                        ],
                    }
                )
            )

        requirements_payload = json.loads((baseline_dir / "requirements.json").read_text(encoding="utf-8"))
        listed_names = [item["name"] for item in requirements_payload["tool_context"]["list_files"]["files"]]
        self.assertEqual(sorted(listed_names), ["config.json", "spec.md"])

        structure_entries = requirements_payload["tool_context"]["extract_structure"]["files"]
        spec_summary = next(item for item in structure_entries if item["path"] == "spec.md")
        self.assertEqual(spec_summary["headings"], ["Payment API", "Scope", "Constraints"])
        self.assertNotIn("content", spec_summary)
        self.assertNotIn(file_body, json.dumps(spec_summary, ensure_ascii=False))
        self.assertEqual(len(state["tool_results"]), 2)

    def test_execute_tool_extract_structure_returns_summary_not_full_text(self):
        temp_root = self.make_temp_root("extract-structure")
        baseline_dir = temp_root / "baseline"
        baseline_dir.mkdir(parents=True, exist_ok=True)
        file_body = "# Overview\n## Goals\nKeep summary concise"
        (baseline_dir / "readme.md").write_text(file_body, encoding="utf-8")

        result = execute_tool(
            "extract_structure",
            {"root_dir": str(baseline_dir), "files": ["readme.md"]},
        )

        self.assertEqual(result["status"], "success")
        summary = result["output"]["files"][0]
        self.assertEqual(summary["headings"], ["Overview", "Goals"])
        self.assertNotIn("content", summary)
        self.assertNotIn(file_body, json.dumps(summary, ensure_ascii=False))

    def test_execute_tool_grep_search_returns_matching_lines(self):
        temp_root = self.make_temp_root("grep-search")
        baseline_dir = temp_root / "baseline"
        baseline_dir.mkdir(parents=True, exist_ok=True)
        (baseline_dir / "requirements.md").write_text(
            "payment order table\nrefund order table\ncustomer profile\n",
            encoding="utf-8",
        )

        result = execute_tool(
            "grep_search",
            {"root_dir": str(baseline_dir), "pattern": "order"},
        )

        self.assertEqual(result["status"], "success")
        matches = result["output"]["matches"]
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0]["line_number"], 1)
        self.assertIn("payment order table", matches[0]["line"])

    def test_execute_tool_read_file_chunk_returns_requested_line_range(self):
        temp_root = self.make_temp_root("read-file-chunk")
        baseline_dir = temp_root / "baseline"
        baseline_dir.mkdir(parents=True, exist_ok=True)
        (baseline_dir / "requirements.md").write_text(
            "line1\nline2\nline3\nline4\n",
            encoding="utf-8",
        )

        result = execute_tool(
            "read_file_chunk",
            {"root_dir": str(baseline_dir), "path": "requirements.md", "start_line": 2, "end_line": 3},
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["output"]["content"], "line2\nline3")
        self.assertEqual(result["output"]["start_line"], 2)
        self.assertEqual(result["output"]["end_line"], 3)

    def test_execute_tool_extract_lookup_values_reads_enum_dictionary(self):
        temp_root = self.make_temp_root("lookup-values")
        baseline_dir = temp_root / "baseline"
        baseline_dir.mkdir(parents=True, exist_ok=True)
        (baseline_dir / "payment_lookup.json").write_text(
            json.dumps({"payment_channel": ["ALIPAY", "WECHAT", "UNIONPAY"]}, ensure_ascii=False),
            encoding="utf-8",
        )

        result = execute_tool(
            "extract_lookup_values",
            {"root_dir": str(baseline_dir)},
        )

        self.assertEqual(result["status"], "success")
        entries = result["output"]["entries"]
        self.assertEqual(entries[0]["name"], "payment_channel")
        self.assertEqual(entries[0]["values"], ["ALIPAY", "WECHAT", "UNIONPAY"])

    def test_data_design_runs_in_process_with_multistep_react_observability(self):
        temp_root = self.make_temp_root("data-design-react")
        project_root = temp_root / "projects" / "demo" / "v1"
        baseline_dir = project_root / "baseline"
        baseline_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "project_name": "demo",
            "project_id": "demo",
            "version": "v1",
            "requirement": "Need payment trade order schema",
            "uploaded_files": ["original-requirements.md"],
            "active_agents": ["data-design", "design-assembler", "validator"],
        }
        (baseline_dir / "requirements.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        (baseline_dir / "original-requirements.md").write_text(
            "Create payment_order table with merchant_id, out_trade_no, amount, status.\n"
            "Need refund_order table with payment_order_id and refund_amount.\n",
            encoding="utf-8",
        )

        llm_outputs = [
            _FakeSubagentOutput(
                reasoning="Step 1: search for payment order requirements.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "Search for payment_order and related fields first.",
                            "tool_name": "grep_search",
                            "tool_input": {"pattern": "payment_order"},
                            "evidence_note": "Locate primary order requirement lines.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Step 2: read the payment order chunk in detail.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "Read the chunk around the payment_order match.",
                            "tool_name": "read_file_chunk",
                            "tool_input": {"path": "original-requirements.md", "start_line": 1, "end_line": 8},
                            "evidence_note": "Capture payment_order fields and constraints.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Step 3: search for refund requirements.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "Search for refund_order references.",
                            "tool_name": "grep_search",
                            "tool_input": {"pattern": "refund_order"},
                            "evidence_note": "Locate refund table relationships.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Step 4: read the refund chunk.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "Read the chunk around the refund_order match.",
                            "tool_name": "read_file_chunk",
                            "tool_input": {"path": "original-requirements.md", "start_line": 2, "end_line": 8},
                            "evidence_note": "Capture refund fields and relation to payment_order.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Enough evidence collected to draft the schema.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": True,
                            "thought": "Enough grounded evidence has been collected.",
                            "tool_name": "none",
                            "tool_input": {},
                            "evidence_note": "Move to final artifact generation.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Used multi-step grep_search and read_file_chunk observations to ground order fields.",
                artifacts={
                    "schema.sql": (
                        "CREATE TABLE payment_order (\n"
                        "  merchant_id BIGINT,\n"
                        "  out_trade_no VARCHAR(64),\n"
                        "  amount BIGINT,\n"
                        "  status VARCHAR(32)\n"
                        ");\n"
                        "CREATE TABLE refund_order (\n"
                        "  payment_order_id BIGINT,\n"
                        "  refund_amount BIGINT\n"
                        ");\n"
                    ),
                    "er.md": "```mermaid\nerDiagram\npayment_order ||--o{ refund_order : settles\n```",
                    "migration-plan.md": "Up: create payment_order and refund_order\nDown: drop refund_order; drop payment_order",
                },
            ),
        ]

        worker = nodes.create_worker_node("data-design")
        state_input = {
            "project_id": "demo",
            "version": "v1",
            "task_queue": [
                {"id": "0", "agent_type": "planner", "status": "success", "dependencies": [], "priority": 100},
                {"id": "3", "agent_type": "data-design", "status": "running", "dependencies": ["0"], "priority": 80},
            ],
        }

        with patch.object(nodes, "BASE_DIR", temp_root), patch.object(nodes, "generate_with_llm", side_effect=llm_outputs), patch.object(nodes.subprocess, "run", side_effect=AssertionError("subprocess should not be used for data-design")):
            result = self.async_run(worker(state_input))

        self.assertEqual(next(task for task in result["task_queue"] if task["agent_type"] == "data-design")["status"], "success")
        self.assertTrue((project_root / "artifacts" / "schema.sql").exists())
        self.assertTrue((project_root / "artifacts" / "er.md").exists())
        self.assertTrue((project_root / "artifacts" / "migration-plan.md").exists())
        self.assertTrue((project_root / "logs" / "data-design-reasoning.md").exists())
        evidence = json.loads((project_root / "evidence" / "data-design.json").read_text(encoding="utf-8"))
        self.assertIn("mapping", evidence)
        self.assertIn("payment_order", json.dumps(evidence["mapping"], ensure_ascii=False))
        self.assertEqual(
            [item["tool_name"] for item in result["tool_results"]],
            ["grep_search", "read_file_chunk", "grep_search", "read_file_chunk"],
        )
        self.assertEqual(evidence["mode"], "in_process_react")
        self.assertGreaterEqual(len(evidence["react_trace"]), 5)
        self.assertTrue(any("search keyword" in entry.lower() for entry in result["history"]))
        self.assertTrue(any("read file chunk" in entry.lower() for entry in result["history"]))
        self.assertTrue(any("react step 4" in entry.lower() for entry in result["history"]))

    def test_architecture_mapping_runs_in_process_with_multistep_react_and_generates_grounded_artifacts(self):
        temp_root = self.make_temp_root("architecture-react")
        project_root = temp_root / "projects" / "demo" / "v1"
        baseline_dir = project_root / "baseline"
        baseline_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "project_name": "demo",
            "project_id": "demo",
            "version": "v1",
            "domain_name": "PaymentDomain",
            "aggregate_root": "PaymentOrder",
            "provider": "LedgerPlatform",
            "consumer": "MerchantPortal",
            "requirement": "Build a payment platform with API gateway, application service, MySQL, Redis, and MQ integration.",
            "uploaded_files": ["original-requirements.md", "context.md"],
            "active_agents": ["architecture-mapping", "design-assembler", "validator"],
        }
        (baseline_dir / "requirements.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        (baseline_dir / "original-requirements.md").write_text(
            "# Payment Platform\n"
            "The system exposes APIs through an API gateway.\n"
            "Core business logic runs in an application service.\n"
            "Data is stored in MySQL and cached in Redis.\n"
            "Events are published to MQ for downstream consumers.\n",
            encoding="utf-8",
        )
        (baseline_dir / "context.md").write_text(
            "## Context\n"
            "- Provider: LedgerPlatform\n"
            "- Consumer: MerchantPortal\n"
            "- Aggregate: PaymentOrder\n",
            encoding="utf-8",
        )

        llm_outputs = [
            _FakeSubagentOutput(
                reasoning="Step 1: list files to see what requirement material exists.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "List files before extracting architectural signals.",
                            "tool_name": "list_files",
                            "tool_input": {},
                            "evidence_note": "Identify requirement and context files.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Step 2: extract document structure to locate the context section.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "Extract document structure to find architecture-relevant sections.",
                            "tool_name": "extract_structure",
                            "tool_input": {"files": ["original-requirements.md", "context.md"]},
                            "evidence_note": "Locate sections mentioning components and boundaries.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Step 3: search for gateway mentions.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "Search for gateway and storage keywords to ground containers.",
                            "tool_name": "grep_search",
                            "tool_input": {"pattern": "gateway"},
                            "evidence_note": "Confirm the inbound entry point and edge boundary.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Step 4: read the requirement lines around the architecture stack.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "Read the core requirement lines to verify gateway, service, MySQL, Redis, and MQ.",
                            "tool_name": "read_file_chunk",
                            "tool_input": {"path": "original-requirements.md", "start_line": 1, "end_line": 6},
                            "evidence_note": "Capture grounded container and integration details.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Enough evidence collected to draft the architecture artifacts.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": True,
                            "thought": "The core boundaries and containers are grounded.",
                            "tool_name": "none",
                            "tool_input": {},
                            "evidence_note": "Generate architecture artifacts.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Generated C4 context/container views from grounded requirement evidence.",
                artifacts={
                    "architecture.md": (
                        "# Architecture\n\n"
                        "```mermaid\n"
                        "C4Context\n"
                        "Rel(user, api, \"Uses\", \"HTTPS\")\n"
                        "```\n\n"
                        "```mermaid\n"
                        "C4Container\n"
                        "Container(api, \"API Gateway\", \"Kong\")\n"
                        "Container(app, \"Application Service\", \"Python\")\n"
                        "ContainerDb(db, \"MySQL\", \"MySQL\")\n"
                        "ContainerDb(cache, \"Redis\", \"Redis\")\n"
                        "Container(queue, \"MQ\", \"Kafka\")\n"
                        "```\n"
                    ),
                    "module-map.json": json.dumps(
                        {
                            "project_name": "demo",
                            "modules": [
                                {"name": "interfaces", "allowed_dependencies": ["application", "domain"]},
                                {"name": "application", "allowed_dependencies": ["domain"]},
                                {"name": "domain", "allowed_dependencies": []},
                                {"name": "infrastructure", "allowed_dependencies": ["application", "domain"]},
                            ],
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                },
            ),
        ]

        worker = nodes.create_worker_node("architecture-mapping")
        state_input = {
            "project_id": "demo",
            "version": "v1",
            "task_queue": [
                {"id": "0", "agent_type": "planner", "status": "success", "dependencies": [], "priority": 100},
                {"id": "1", "agent_type": "architecture-mapping", "status": "running", "dependencies": ["0"], "priority": 90},
            ],
        }

        with patch.object(nodes, "BASE_DIR", temp_root), patch.object(nodes, "generate_with_llm", side_effect=llm_outputs), patch.object(nodes.subprocess, "run", side_effect=AssertionError("subprocess should not be used for architecture-mapping")):
            result = self.async_run(worker(state_input))

        self.assertEqual(next(task for task in result["task_queue"] if task["agent_type"] == "architecture-mapping")["status"], "success")
        self.assertTrue((project_root / "artifacts" / "architecture.md").exists())
        self.assertTrue((project_root / "artifacts" / "module-map.json").exists())
        self.assertTrue((project_root / "logs" / "architecture-mapping-reasoning.md").exists())
        self.assertEqual(
            [item["tool_name"] for item in result["tool_results"]],
            ["list_files", "extract_structure", "grep_search", "read_file_chunk"],
        )
        evidence = json.loads((project_root / "evidence" / "architecture-mapping.json").read_text(encoding="utf-8"))
        self.assertEqual(evidence["mode"], "in_process_react")
        self.assertGreaterEqual(len(evidence["react_trace"]), 5)
        self.assertIn("module_mapping", evidence)
        self.assertIn("interfaces", json.dumps(evidence["module_mapping"], ensure_ascii=False))
        self.assertTrue(any("listed files" in entry.lower() for entry in result["history"]))
        self.assertTrue(any("react step 4" in entry.lower() for entry in result["history"]))

    def test_config_design_runs_in_process_with_multistep_react_and_generates_grounded_artifacts(self):
        temp_root = self.make_temp_root("config-react")
        project_root = temp_root / "projects" / "demo" / "v1"
        baseline_dir = project_root / "baseline"
        baseline_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "project_name": "demo",
            "project_id": "demo",
            "version": "v1",
            "provider": "ledger",
            "scenario_name": "payment_switch",
            "dependencies": "MySQL, Redis, Kafka",
            "requirement": "The system uses MySQL, Redis, Kafka and needs a payment switch feature flag with provider timeout settings.",
            "uploaded_files": ["original-requirements.md", "env-spec.json"],
            "active_agents": ["config-design", "design-assembler", "validator"],
        }
        (baseline_dir / "requirements.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        (baseline_dir / "original-requirements.md").write_text(
            "# Config\n"
            "Database uses MySQL.\n"
            "Cache uses Redis.\n"
            "Messaging uses Kafka.\n"
            "Need feature flag payment_switch.enabled.\n"
            "Provider ledger timeout should be configurable.\n",
            encoding="utf-8",
        )
        (baseline_dir / "env-spec.json").write_text(
            json.dumps(
                {
                    "envs": ["dev", "test", "prod"],
                    "config_keys": ["spring.datasource.url", "spring.redis.host", "integration.ledger.timeout_ms"],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        llm_outputs = [
            _FakeSubagentOutput(
                reasoning="Step 1: list files to find config sources.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "List files before locating config-specific evidence.",
                            "tool_name": "list_files",
                            "tool_input": {},
                            "evidence_note": "Identify requirement and environment spec files.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Step 2: extract structure from config-related files.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "Extract structure to find keys and headings quickly.",
                            "tool_name": "extract_structure",
                            "tool_input": {"files": ["original-requirements.md", "env-spec.json"]},
                            "evidence_note": "Locate config domains and known keys.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Step 3: search for feature flag references.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "Search for feature flag mentions to ground dynamic config.",
                            "tool_name": "grep_search",
                            "tool_input": {"pattern": "feature flag"},
                            "evidence_note": "Confirm business toggle requirements.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Step 4: read the detailed config requirement chunk.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "Read the relevant lines to verify MySQL, Redis, Kafka, and timeout settings.",
                            "tool_name": "read_file_chunk",
                            "tool_input": {"path": "original-requirements.md", "start_line": 1, "end_line": 8},
                            "evidence_note": "Capture grounded config keys and environment concerns.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Enough evidence collected to draft configuration artifacts.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": True,
                            "thought": "The core config keys and environments are grounded.",
                            "tool_name": "none",
                            "tool_input": {},
                            "evidence_note": "Generate config artifacts.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Generated config catalog and matrix from grounded config requirements.",
                artifacts={
                    "config-catalog.yaml": (
                        "service: demo\n"
                        "properties:\n"
                        "  - key: spring.datasource.url\n"
                        "    type: string\n"
                        "  - key: spring.redis.host\n"
                        "    type: string\n"
                        "  - key: integration.ledger.timeout_ms\n"
                        "    type: integer\n"
                        "  - key: features.payment_switch.enabled\n"
                        "    type: boolean\n"
                    ),
                    "config-matrix.md": (
                        "# Config Matrix\n\n"
                        "| Config Key | DEV | TEST | PROD |\n"
                        "| :--- | :--- | :--- | :--- |\n"
                        "| `spring.datasource.url` | `jdbc:mysql://dev` | `jdbc:mysql://test` | `jdbc:mysql://prod` |\n"
                        "| `integration.ledger.timeout_ms` | `5000` | `3000` | `2000` |\n"
                        "| `features.payment_switch.enabled` | `true` | `true` | `false` |\n"
                    ),
                },
            ),
        ]

        worker = nodes.create_worker_node("config-design")
        state_input = {
            "project_id": "demo",
            "version": "v1",
            "task_queue": [
                {"id": "0", "agent_type": "planner", "status": "success", "dependencies": [], "priority": 100},
                {"id": "6", "agent_type": "config-design", "status": "running", "dependencies": ["1"], "priority": 65},
            ],
        }

        with patch.object(nodes, "BASE_DIR", temp_root), patch.object(nodes, "generate_with_llm", side_effect=llm_outputs), patch.object(nodes.subprocess, "run", side_effect=AssertionError("subprocess should not be used for config-design")):
            result = self.async_run(worker(state_input))

        self.assertEqual(next(task for task in result["task_queue"] if task["agent_type"] == "config-design")["status"], "success")
        self.assertTrue((project_root / "artifacts" / "config-catalog.yaml").exists())
        self.assertTrue((project_root / "artifacts" / "config-matrix.md").exists())
        self.assertTrue((project_root / "logs" / "config-design-reasoning.md").exists())
        self.assertEqual(
            [item["tool_name"] for item in result["tool_results"]],
            ["list_files", "extract_structure", "grep_search", "read_file_chunk"],
        )
        evidence = json.loads((project_root / "evidence" / "config-design.json").read_text(encoding="utf-8"))
        self.assertEqual(evidence["mode"], "in_process_react")
        self.assertGreaterEqual(len(evidence["react_trace"]), 5)
        self.assertIn("config_mapping", evidence)
        self.assertIn("spring.datasource.url", json.dumps(evidence["config_mapping"], ensure_ascii=False))
        self.assertTrue(any("listed files" in entry.lower() for entry in result["history"]))
        self.assertTrue(any("react step 4" in entry.lower() for entry in result["history"]))

    def test_flow_design_runs_in_process_with_multistep_react_and_generates_grounded_artifacts(self):
        temp_root = self.make_temp_root("flow-react")
        project_root = temp_root / "projects" / "demo" / "v1"
        baseline_dir = project_root / "baseline"
        baseline_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "project_name": "demo",
            "project_id": "demo",
            "version": "v1",
            "scenario_name": "PaymentOrderCreation",
            "scenario_desc": "User submits a payment order and the system reserves funds before publishing an event.",
            "entity_name": "PaymentOrder",
            "aggregate_root": "PaymentOrder",
            "requirement": "Payment order creation goes through API gateway, application service, domain validation, repository persistence, and Kafka event publishing.",
            "uploaded_files": ["original-requirements.md", "state-rules.md"],
            "active_agents": ["flow-design", "design-assembler", "validator"],
        }
        (baseline_dir / "requirements.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        (baseline_dir / "original-requirements.md").write_text(
            "# Payment Order Creation\n"
            "Request enters through API gateway.\n"
            "Application service validates command and loads PaymentOrder.\n"
            "Domain layer reserves funds and changes status from CREATED to RESERVED.\n"
            "Repository persists the aggregate.\n"
            "Kafka event is published after commit.\n",
            encoding="utf-8",
        )
        (baseline_dir / "state-rules.md").write_text(
            "## State Rules\n"
            "- CREATED -> RESERVED when funds are successfully reserved\n"
            "- RESERVED -> CONFIRMED after payment callback\n"
            "- RESERVED -> CANCELLED when timeout occurs\n",
            encoding="utf-8",
        )

        llm_outputs = [
            _FakeSubagentOutput(
                reasoning="Step 1: list files to find flow-related inputs.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "List files before grounding sequence and state transitions.",
                            "tool_name": "list_files",
                            "tool_input": {},
                            "evidence_note": "Identify requirement and state rule files.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Step 2: extract structure from flow-related files.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "Extract structure to locate sequence and state sections.",
                            "tool_name": "extract_structure",
                            "tool_input": {"files": ["original-requirements.md", "state-rules.md"]},
                            "evidence_note": "Find headings for flow and state rule content.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Step 3: search for reserve and Kafka keywords.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "Search for key flow actions to ground sequence steps.",
                            "tool_name": "grep_search",
                            "tool_input": {"pattern": "reserved"},
                            "evidence_note": "Confirm status transitions and reserve behavior.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Step 4: read the requirement chunk that describes the main flow.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "Read the detailed lines to verify participants and post-commit publishing.",
                            "tool_name": "read_file_chunk",
                            "tool_input": {"path": "original-requirements.md", "start_line": 1, "end_line": 8},
                            "evidence_note": "Capture grounded sequence actors and transitions.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Enough evidence collected to generate flow artifacts.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": True,
                            "thought": "The sequence participants and state transitions are grounded.",
                            "tool_name": "none",
                            "tool_input": {},
                            "evidence_note": "Generate sequence and state diagrams.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Generated grounded sequence and state diagrams for payment order creation.",
                artifacts={
                    "sequence-paymentordercreation.md": (
                        "# Sequence\n\n"
                        "```mermaid\n"
                        "sequenceDiagram\n"
                        "Client->>Gateway: Create payment order\n"
                        "Gateway->>Application: Forward request\n"
                        "Application->>Domain: Reserve funds\n"
                        "Application->>Repository: Save aggregate\n"
                        "Application->>Kafka: Publish event\n"
                        "```\n"
                    ),
                    "state-paymentorder.md": (
                        "# State\n\n"
                        "```mermaid\n"
                        "stateDiagram\n"
                        "[*] --> CREATED\n"
                        "CREATED --> RESERVED\n"
                        "RESERVED --> CONFIRMED\n"
                        "RESERVED --> CANCELLED\n"
                        "```\n"
                    ),
                },
            ),
        ]

        worker = nodes.create_worker_node("flow-design")
        state_input = {
            "project_id": "demo",
            "version": "v1",
            "task_queue": [
                {"id": "0", "agent_type": "planner", "status": "success", "dependencies": [], "priority": 100},
                {"id": "7", "agent_type": "flow-design", "status": "running", "dependencies": ["1"], "priority": 60},
            ],
        }

        with patch.object(nodes, "BASE_DIR", temp_root), patch.object(nodes, "generate_with_llm", side_effect=llm_outputs), patch.object(nodes.subprocess, "run", side_effect=AssertionError("subprocess should not be used for flow-design")):
            result = self.async_run(worker(state_input))

        self.assertEqual(next(task for task in result["task_queue"] if task["agent_type"] == "flow-design")["status"], "success")
        self.assertTrue((project_root / "artifacts" / "sequence-paymentordercreation.md").exists())
        self.assertTrue((project_root / "artifacts" / "state-paymentorder.md").exists())
        self.assertTrue((project_root / "logs" / "flow-design-reasoning.md").exists())
        self.assertEqual(
            [item["tool_name"] for item in result["tool_results"]],
            ["list_files", "extract_structure", "grep_search", "read_file_chunk"],
        )
        evidence = json.loads((project_root / "evidence" / "flow-design.json").read_text(encoding="utf-8"))
        self.assertEqual(evidence["mode"], "in_process_react")
        self.assertGreaterEqual(len(evidence["react_trace"]), 5)
        self.assertIn("flow_mapping", evidence)
        self.assertIn("RESERVED", json.dumps(evidence["flow_mapping"], ensure_ascii=False))
        self.assertTrue(any("listed files" in entry.lower() for entry in result["history"]))
        self.assertTrue(any("react step 4" in entry.lower() for entry in result["history"]))

    def test_integration_design_runs_in_process_with_multistep_react_and_generates_grounded_artifacts(self):
        temp_root = self.make_temp_root("integration-react")
        project_root = temp_root / "projects" / "demo" / "v1"
        baseline_dir = project_root / "baseline"
        baseline_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "project_name": "demo",
            "project_id": "demo",
            "version": "v1",
            "integration_scenario": "PaymentNotification",
            "scenario_desc": "Notify downstream ledger platform after payment success and support retry compensation.",
            "consumer": "PaymentCore",
            "provider": "LedgerPlatform",
            "requirement": "Payment success should publish a Kafka event and call ledger platform with idempotency key, retry, circuit breaker, and outbox compensation.",
            "uploaded_files": ["original-requirements.md", "event-contract.md"],
            "active_agents": ["integration-design", "design-assembler", "validator"],
        }
        (baseline_dir / "requirements.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        (baseline_dir / "original-requirements.md").write_text(
            "# Payment Notification\n"
            "PaymentCore calls LedgerPlatform after payment success.\n"
            "The integration must carry x-request-id for idempotency.\n"
            "Kafka event payment.succeeded is published.\n"
            "Failed delivery is retried and compensated through outbox.\n",
            encoding="utf-8",
        )
        (baseline_dir / "event-contract.md").write_text(
            "## Domain Events\n"
            "- payment.succeeded includes tradeNo, amount, status\n"
            "- ledger.notify.request includes requestId and merchantId\n",
            encoding="utf-8",
        )

        llm_outputs = [
            _FakeSubagentOutput(
                reasoning="Step 1: list files to find integration evidence.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "List files before grounding integration contracts and compensation.",
                            "tool_name": "list_files",
                            "tool_input": {},
                            "evidence_note": "Identify requirement and event contract files.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Step 2: extract structure from integration files.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "Extract structure to locate event and integration sections quickly.",
                            "tool_name": "extract_structure",
                            "tool_input": {"files": ["original-requirements.md", "event-contract.md"]},
                            "evidence_note": "Find headings and keys related to async integration.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Step 3: search for idempotency evidence.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "Search for idempotency and retry terms to ground compensation design.",
                            "tool_name": "grep_search",
                            "tool_input": {"pattern": "idempotency"},
                            "evidence_note": "Confirm request deduplication and retry strategy.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Step 4: read the detailed integration requirement chunk.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "Read the key lines to verify Kafka, outbox, and downstream invocation.",
                            "tool_name": "read_file_chunk",
                            "tool_input": {"path": "original-requirements.md", "start_line": 1, "end_line": 8},
                            "evidence_note": "Capture grounded integration flow and event payload hints.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Enough evidence collected to generate integration artifacts.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": True,
                            "thought": "The downstream call, event, and compensation details are grounded.",
                            "tool_name": "none",
                            "tool_input": {},
                            "evidence_note": "Generate integration design artifacts.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Generated grounded integration design and AsyncAPI artifacts.",
                artifacts={
                    "integration-ledgerplatform.md": (
                        "# Integration Design\n\n"
                        "- Consumer: PaymentCore\n"
                        "- Provider: LedgerPlatform\n"
                        "- Idempotency: x-request-id\n"
                        "- Retry: exponential backoff\n"
                        "- Compensation: outbox relay\n"
                    ),
                    "asyncapi.yaml": (
                        "asyncapi: 3.0.0\n"
                        "channels:\n"
                        "  paymentSucceeded:\n"
                        "    address: payment.succeeded\n"
                        "operations:\n"
                        "  publishPaymentSucceeded:\n"
                        "    action: send\n"
                    ),
                },
            ),
        ]

        worker = nodes.create_worker_node("integration-design")
        state_input = {
            "project_id": "demo",
            "version": "v1",
            "task_queue": [
                {"id": "0", "agent_type": "planner", "status": "success", "dependencies": [], "priority": 100},
                {"id": "2", "agent_type": "integration-design", "status": "running", "dependencies": ["1"], "priority": 85},
            ],
        }

        with patch.object(nodes, "BASE_DIR", temp_root), patch.object(nodes, "generate_with_llm", side_effect=llm_outputs), patch.object(nodes.subprocess, "run", side_effect=AssertionError("subprocess should not be used for integration-design")):
            result = self.async_run(worker(state_input))

        self.assertEqual(next(task for task in result["task_queue"] if task["agent_type"] == "integration-design")["status"], "success")
        self.assertTrue((project_root / "artifacts" / "integration-ledgerplatform.md").exists())
        self.assertTrue((project_root / "artifacts" / "asyncapi.yaml").exists())
        self.assertTrue((project_root / "logs" / "integration-design-reasoning.md").exists())
        self.assertEqual(
            [item["tool_name"] for item in result["tool_results"]],
            ["list_files", "extract_structure", "grep_search", "read_file_chunk"],
        )
        evidence = json.loads((project_root / "evidence" / "integration-design.json").read_text(encoding="utf-8"))
        self.assertEqual(evidence["mode"], "in_process_react")
        self.assertGreaterEqual(len(evidence["react_trace"]), 5)
        self.assertIn("integration_mapping", evidence)
        self.assertIn("payment.succeeded", json.dumps(evidence["integration_mapping"], ensure_ascii=False))
        self.assertTrue(any("listed files" in entry.lower() for entry in result["history"]))
        self.assertTrue(any("react step 4" in entry.lower() for entry in result["history"]))

    def test_ddd_structure_runs_in_process_with_multistep_react_and_generates_grounded_artifacts(self):
        temp_root = self.make_temp_root("ddd-react")
        project_root = temp_root / "projects" / "demo" / "v1"
        baseline_dir = project_root / "baseline"
        baseline_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "project_name": "demo",
            "project_id": "demo",
            "version": "v1",
            "domain_name": "Payment",
            "aggregate_root": "PaymentOrder",
            "requirement": "Payment domain includes PaymentOrder aggregate, RefundRecord entity, Money value object, and events for order created and payment succeeded.",
            "uploaded_files": ["original-requirements.md", "domain-notes.md"],
            "active_agents": ["ddd-structure", "design-assembler", "validator"],
        }
        (baseline_dir / "requirements.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        (baseline_dir / "original-requirements.md").write_text(
            "# Payment Domain\n"
            "PaymentOrder is the aggregate root.\n"
            "RefundRecord belongs to the payment lifecycle.\n"
            "Money is a value object with amount and currency.\n"
            "PaymentOrderCreatedEvent and PaymentSucceededEvent are emitted.\n",
            encoding="utf-8",
        )
        (baseline_dir / "domain-notes.md").write_text(
            "## Domain Notes\n"
            "- Repository: PaymentOrderRepository\n"
            "- Command: CreatePaymentOrderCommand\n"
            "- Query: GetPaymentOrderDetailQuery\n",
            encoding="utf-8",
        )

        llm_outputs = [
            _FakeSubagentOutput(
                reasoning="Step 1: list files to locate domain materials.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "List files before grounding aggregates and value objects.",
                            "tool_name": "list_files",
                            "tool_input": {},
                            "evidence_note": "Identify requirement and domain note files.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Step 2: extract structure from domain files.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "Extract structure to locate domain sections and command/query hints.",
                            "tool_name": "extract_structure",
                            "tool_input": {"files": ["original-requirements.md", "domain-notes.md"]},
                            "evidence_note": "Find headings and keys related to aggregates and events.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Step 3: search for aggregate root mentions.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "Search for PaymentOrder and related domain terms to ground the model.",
                            "tool_name": "grep_search",
                            "tool_input": {"pattern": "PaymentOrder"},
                            "evidence_note": "Confirm aggregate root and domain event vocabulary.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Step 4: read the detailed domain requirement chunk.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "Read the key lines to verify entity, value object, repository, and commands.",
                            "tool_name": "read_file_chunk",
                            "tool_input": {"path": "original-requirements.md", "start_line": 1, "end_line": 8},
                            "evidence_note": "Capture grounded DDD concepts and relationships.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Enough evidence collected to generate DDD artifacts.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": True,
                            "thought": "The aggregate, entities, value objects, and events are grounded.",
                            "tool_name": "none",
                            "tool_input": {},
                            "evidence_note": "Generate DDD class and structure artifacts.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Generated grounded DDD model and package structure artifacts.",
                artifacts={
                    "class-payment.md": (
                        "# Class Diagram\n\n"
                        "```mermaid\n"
                        "classDiagram\n"
                        "class PaymentOrder\n"
                        "class RefundRecord\n"
                        "class Money\n"
                        "PaymentOrder --> RefundRecord\n"
                        "PaymentOrder --> Money\n"
                        "```\n"
                    ),
                    "ddd-structure.md": (
                        "# DDD Structure\n\n"
                        "- AggregateRoot: PaymentOrder\n"
                        "- Repository: PaymentOrderRepository\n"
                        "- Command: CreatePaymentOrderCommand\n"
                        "- Query: GetPaymentOrderDetailQuery\n"
                        "- Event: PaymentSucceededEvent\n"
                    ),
                },
            ),
        ]

        worker = nodes.create_worker_node("ddd-structure")
        state_input = {
            "project_id": "demo",
            "version": "v1",
            "task_queue": [
                {"id": "0", "agent_type": "planner", "status": "success", "dependencies": [], "priority": 100},
                {"id": "4", "agent_type": "ddd-structure", "status": "running", "dependencies": ["3"], "priority": 75},
            ],
        }

        with patch.object(nodes, "BASE_DIR", temp_root), patch.object(nodes, "generate_with_llm", side_effect=llm_outputs), patch.object(nodes.subprocess, "run", side_effect=AssertionError("subprocess should not be used for ddd-structure")):
            result = self.async_run(worker(state_input))

        self.assertEqual(next(task for task in result["task_queue"] if task["agent_type"] == "ddd-structure")["status"], "success")
        self.assertTrue((project_root / "artifacts" / "class-payment.md").exists())
        self.assertTrue((project_root / "artifacts" / "ddd-structure.md").exists())
        self.assertTrue((project_root / "logs" / "ddd-structure-reasoning.md").exists())
        self.assertEqual(
            [item["tool_name"] for item in result["tool_results"]],
            ["list_files", "extract_structure", "grep_search", "read_file_chunk"],
        )
        evidence = json.loads((project_root / "evidence" / "ddd-structure.json").read_text(encoding="utf-8"))
        self.assertEqual(evidence["mode"], "in_process_react")
        self.assertGreaterEqual(len(evidence["react_trace"]), 5)
        self.assertIn("domain_mapping", evidence)
        self.assertIn("PaymentOrder", json.dumps(evidence["domain_mapping"], ensure_ascii=False))
        self.assertTrue(any("listed files" in entry.lower() for entry in result["history"]))
        self.assertTrue(any("react step 4" in entry.lower() for entry in result["history"]))

    def test_ops_readiness_runs_in_process_with_multistep_react_and_generates_grounded_artifacts(self):
        temp_root = self.make_temp_root("ops-react")
        project_root = temp_root / "projects" / "demo" / "v1"
        baseline_dir = project_root / "baseline"
        baseline_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "project_name": "demo",
            "project_id": "demo",
            "version": "v1",
            "scenario_name": "PaymentOrderCreation",
            "entity_name": "PaymentOrder",
            "provider": "LedgerPlatform",
            "dependencies": "MySQL, Redis, Kafka",
            "requirement": "Payment order creation requires 99.99% availability, p99 latency below 200ms, Kafka event observability, and rollback when downstream ledger latency spikes.",
            "uploaded_files": ["original-requirements.md", "ops-notes.md"],
            "active_agents": ["ops-readiness", "design-assembler", "validator"],
        }
        (baseline_dir / "requirements.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        (baseline_dir / "original-requirements.md").write_text(
            "# Ops Requirements\n"
            "Availability target is 99.99%.\n"
            "P99 latency should stay below 200ms.\n"
            "Kafka publishing and LedgerPlatform calls must be observable.\n"
            "Rollback if downstream ledger latency exceeds 2000ms.\n",
            encoding="utf-8",
        )
        (baseline_dir / "ops-notes.md").write_text(
            "## Alerts\n"
            "- Error rate above 5% for 3 minutes triggers rollback\n"
            "- Trace external_api_call span for LedgerPlatform\n"
            "- Track Kafka publish success ratio\n",
            encoding="utf-8",
        )

        llm_outputs = [
            _FakeSubagentOutput(
                reasoning="Step 1: list files to find operations evidence.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "List files before grounding SLOs and runbook actions.",
                            "tool_name": "list_files",
                            "tool_input": {},
                            "evidence_note": "Identify requirement and ops note files.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Step 2: extract structure from ops files.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "Extract structure to locate SLO and alert sections.",
                            "tool_name": "extract_structure",
                            "tool_input": {"files": ["original-requirements.md", "ops-notes.md"]},
                            "evidence_note": "Find headings related to observability and rollback.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Step 3: search for latency requirements.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "Search for latency and rollback thresholds to ground alerting.",
                            "tool_name": "grep_search",
                            "tool_input": {"pattern": "latency"},
                            "evidence_note": "Confirm quantitative thresholds for SLOs and rollback.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Step 4: read the detailed ops requirement chunk.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "Read the key lines to verify availability, latency, observability, and rollback conditions.",
                            "tool_name": "read_file_chunk",
                            "tool_input": {"path": "original-requirements.md", "start_line": 1, "end_line": 8},
                            "evidence_note": "Capture grounded SLO and runbook constraints.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Enough evidence collected to generate ops readiness artifacts.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": True,
                            "thought": "The quantitative SLOs, alerts, and rollback triggers are grounded.",
                            "tool_name": "none",
                            "tool_input": {},
                            "evidence_note": "Generate SLO, observability, and runbook artifacts.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Generated grounded ops readiness artifacts.",
                artifacts={
                    "slo.yaml": (
                        "service: demo\n"
                        "slos:\n"
                        "  - sli_name: api_success_rate\n"
                        "    target: 99.99\n"
                        "  - sli_name: api_latency_p99\n"
                        "    target: \"< 200ms\"\n"
                    ),
                    "observability-spec.yaml": (
                        "service: demo\n"
                        "tracing:\n"
                        "  critical_spans:\n"
                        "    - name: external_api_call\n"
                        "alerts:\n"
                        "  - name: LedgerLatencySpike\n"
                        "    condition: ledger_p99_latency > 2000ms\n"
                    ),
                    "deployment-runbook.md": (
                        "# Deployment Runbook\n\n"
                        "- Check Kafka and LedgerPlatform health\n"
                        "- Roll back when error rate > 5% for 3 minutes\n"
                        "- Roll back when ledger latency exceeds 2000ms\n"
                    ),
                },
            ),
        ]

        worker = nodes.create_worker_node("ops-readiness")
        state_input = {
            "project_id": "demo",
            "version": "v1",
            "task_queue": [
                {"id": "0", "agent_type": "planner", "status": "success", "dependencies": [], "priority": 100},
                {"id": "9", "agent_type": "ops-readiness", "status": "running", "dependencies": ["1"], "priority": 45},
            ],
        }

        with patch.object(nodes, "BASE_DIR", temp_root), patch.object(nodes, "generate_with_llm", side_effect=llm_outputs), patch.object(nodes.subprocess, "run", side_effect=AssertionError("subprocess should not be used for ops-readiness")):
            result = self.async_run(worker(state_input))

        self.assertEqual(next(task for task in result["task_queue"] if task["agent_type"] == "ops-readiness")["status"], "success")
        self.assertTrue((project_root / "artifacts" / "slo.yaml").exists())
        self.assertTrue((project_root / "artifacts" / "observability-spec.yaml").exists())
        self.assertTrue((project_root / "artifacts" / "deployment-runbook.md").exists())
        self.assertTrue((project_root / "logs" / "ops-readiness-reasoning.md").exists())
        self.assertEqual(
            [item["tool_name"] for item in result["tool_results"]],
            ["list_files", "extract_structure", "grep_search", "read_file_chunk"],
        )
        evidence = json.loads((project_root / "evidence" / "ops-readiness.json").read_text(encoding="utf-8"))
        self.assertEqual(evidence["mode"], "in_process_react")
        self.assertGreaterEqual(len(evidence["react_trace"]), 5)
        self.assertIn("ops_mapping", evidence)
        self.assertIn("2000ms", json.dumps(evidence["ops_mapping"], ensure_ascii=False))
        self.assertTrue(any("listed files" in entry.lower() for entry in result["history"]))
        self.assertTrue(any("react step 4" in entry.lower() for entry in result["history"]))

    def test_test_design_runs_in_process_with_multistep_react_and_generates_grounded_artifacts(self):
        temp_root = self.make_temp_root("test-design-react")
        project_root = temp_root / "projects" / "demo" / "v1"
        baseline_dir = project_root / "baseline"
        baseline_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "project_name": "demo",
            "project_id": "demo",
            "version": "v1",
            "scenario_name": "PaymentOrderCreation",
            "entity_name": "PaymentOrder",
            "provider": "LedgerPlatform",
            "dependencies": "MySQL, Redis, Kafka",
            "requirement": "Payment order creation needs boundary tests for amount and channel, idempotency tests for callback, chaos tests for ledger timeout, and concurrency tests for duplicate submission.",
            "uploaded_files": ["original-requirements.md", "test-notes.md"],
            "active_agents": ["test-design", "design-assembler", "validator"],
        }
        (baseline_dir / "requirements.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        (baseline_dir / "original-requirements.md").write_text(
            "# Test Requirements\n"
            "Amount must be a positive integer in fen.\n"
            "Channel supports ALIPAY, WECHAT, UNIONPAY, BANK_CARD.\n"
            "Callback processing must be idempotent.\n"
            "LedgerPlatform timeout and Kafka publish failures need chaos tests.\n"
            "Duplicate submission requires concurrency testing.\n",
            encoding="utf-8",
        )
        (baseline_dir / "test-notes.md").write_text(
            "## Coverage Notes\n"
            "- API create and callback endpoints require integration coverage\n"
            "- State transition CREATED -> SUCCESS must be covered\n"
            "- Retry and circuit breaker scenarios require fault injection\n",
            encoding="utf-8",
        )

        llm_outputs = [
            _FakeSubagentOutput(
                reasoning="Step 1: list files to find test design evidence.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "List files before grounding test boundaries and coverage.",
                            "tool_name": "list_files",
                            "tool_input": {},
                            "evidence_note": "Identify requirement and test note files.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Step 2: extract structure from test-related files.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "Extract structure to locate testing sections and coverage hints.",
                            "tool_name": "extract_structure",
                            "tool_input": {"files": ["original-requirements.md", "test-notes.md"]},
                            "evidence_note": "Find headings related to boundaries, chaos, and coverage.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Step 3: search for idempotency requirements.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "Search for idempotent callback and concurrency requirements.",
                            "tool_name": "grep_search",
                            "tool_input": {"pattern": "idempotent"},
                            "evidence_note": "Confirm callback deduplication and concurrency expectations.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Step 4: read the detailed testing requirement chunk.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "Read the key lines to verify field boundaries, chaos tests, and concurrency tests.",
                            "tool_name": "read_file_chunk",
                            "tool_input": {"path": "original-requirements.md", "start_line": 1, "end_line": 8},
                            "evidence_note": "Capture grounded test design constraints.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Enough evidence collected to generate test design artifacts.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": True,
                            "thought": "The boundary, chaos, and concurrency requirements are grounded.",
                            "tool_name": "none",
                            "tool_input": {},
                            "evidence_note": "Generate test design artifacts.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Generated grounded test inputs and coverage map artifacts.",
                artifacts={
                    "test-inputs.md": (
                        "# Test Inputs\n\n"
                        "- amount: valid positive integer, invalid zero and negative\n"
                        "- channel: ALIPAY/WECHAT/UNIONPAY/BANK_CARD\n"
                        "- callback: duplicate notification idempotency case\n"
                        "- chaos: LedgerPlatform timeout and Kafka publish failure\n"
                        "- concurrency: duplicate submission under load\n"
                    ),
                    "coverage-map.json": json.dumps(
                        {
                            "coverage_rules": [
                                {
                                    "design_module": "API create/callback",
                                    "coverage_requirement": "create and callback endpoints need automated coverage",
                                },
                                {
                                    "design_module": "State transition",
                                    "coverage_requirement": "CREATED to SUCCESS must be covered",
                                },
                            ],
                            "mapped_test_cases": [
                                {
                                    "scenario": "callback idempotency",
                                    "design_ref": "notify flow",
                                    "test_type": "Integration",
                                }
                            ],
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                },
            ),
        ]

        worker = nodes.create_worker_node("test-design")
        state_input = {
            "project_id": "demo",
            "version": "v1",
            "task_queue": [
                {"id": "0", "agent_type": "planner", "status": "success", "dependencies": [], "priority": 100},
                {"id": "8", "agent_type": "test-design", "status": "running", "dependencies": ["7"], "priority": 50},
            ],
        }

        with patch.object(nodes, "BASE_DIR", temp_root), patch.object(nodes, "generate_with_llm", side_effect=llm_outputs), patch.object(nodes.subprocess, "run", side_effect=AssertionError("subprocess should not be used for test-design")):
            result = self.async_run(worker(state_input))

        self.assertEqual(next(task for task in result["task_queue"] if task["agent_type"] == "test-design")["status"], "success")
        self.assertTrue((project_root / "artifacts" / "test-inputs.md").exists())
        self.assertTrue((project_root / "artifacts" / "coverage-map.json").exists())
        self.assertTrue((project_root / "logs" / "test-design-reasoning.md").exists())
        self.assertEqual(
            [item["tool_name"] for item in result["tool_results"]],
            ["list_files", "extract_structure", "grep_search", "read_file_chunk"],
        )
        evidence = json.loads((project_root / "evidence" / "test-design.json").read_text(encoding="utf-8"))
        self.assertEqual(evidence["mode"], "in_process_react")
        self.assertGreaterEqual(len(evidence["react_trace"]), 5)
        self.assertIn("test_mapping", evidence)
        self.assertIn("callback idempotency", json.dumps(evidence["test_mapping"], ensure_ascii=False))
        self.assertTrue(any("listed files" in entry.lower() for entry in result["history"]))
        self.assertTrue(any("react step 4" in entry.lower() for entry in result["history"]))

    def test_api_design_runs_in_process_with_multistep_react_and_grounds_enums_in_lookup_files(self):
        temp_root = self.make_temp_root("api-design-react")
        project_root = temp_root / "projects" / "demo" / "v1"
        baseline_dir = project_root / "baseline"
        baseline_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "project_name": "demo",
            "project_id": "demo",
            "version": "v1",
            "server_url": "https://internal.demo.local",
            "owner": "demo-team",
            "audience": "both",
            "scenario_desc": "Support payment order creation",
            "requirement": "Create payment order API with payment channel enum from lookup file.",
            "uploaded_files": ["original-requirements.md", "payment_lookup.json"],
            "active_agents": ["api-design", "design-assembler", "validator"],
        }
        (baseline_dir / "requirements.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        (baseline_dir / "original-requirements.md").write_text(
            "Create payment order API and expose payment_channel in request.\n",
            encoding="utf-8",
        )
        (baseline_dir / "payment_lookup.json").write_text(
            json.dumps({"payment_channel": ["ALIPAY", "WECHAT", "UNIONPAY"]}, ensure_ascii=False),
            encoding="utf-8",
        )

        llm_outputs = [
            _FakeSubagentOutput(
                reasoning="Step 1: inspect uploaded files first.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "List uploaded files to find lookup materials.",
                            "tool_name": "list_files",
                            "tool_input": {},
                            "evidence_note": "Identify candidate lookup and requirement files.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Step 2: extract lookup values for payment_channel.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "Read lookup dictionaries to capture enum values.",
                            "tool_name": "extract_lookup_values",
                            "tool_input": {},
                            "evidence_note": "Collect enum values from uploaded lookup files.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Step 3: read the requirement chunk mentioning payment_channel.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": False,
                            "thought": "Read the requirement lines around payment_channel usage.",
                            "tool_name": "read_file_chunk",
                            "tool_input": {"path": "original-requirements.md", "start_line": 1, "end_line": 6},
                            "evidence_note": "Confirm where the enum is used in request payloads.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Enough evidence collected to draft OpenAPI.",
                artifacts={
                    "decision": json.dumps(
                        {
                            "done": True,
                            "thought": "Lookup values and usage context are sufficient.",
                            "tool_name": "none",
                            "tool_input": {},
                            "evidence_note": "Generate final API artifacts.",
                        },
                        ensure_ascii=False,
                    )
                },
            ),
            _FakeSubagentOutput(
                reasoning="Used multi-step lookup and chunk reading to align payment_channel enum.",
                artifacts={
                    "api-design.md": "Payment API design summary",
                    "api-internal.yaml": "paymentChannel:\n  type: string\n  enum: [ALIPAY, WECHAT, UNIONPAY]\n",
                    "api-public.yaml": "paymentChannel:\n  type: string\n  enum: [ALIPAY, WECHAT, UNIONPAY]\n",
                    "errors-rfc9457.json": '{"errors":[{"errorCode":"PAY-400"}]}',
                },
            ),
        ]

        worker = nodes.create_worker_node("api-design")
        state_input = {
            "project_id": "demo",
            "version": "v1",
            "task_queue": [
                {"id": "0", "agent_type": "planner", "status": "success", "dependencies": [], "priority": 100},
                {"id": "5", "agent_type": "api-design", "status": "running", "dependencies": ["0"], "priority": 70},
            ],
        }

        with patch.object(nodes, "BASE_DIR", temp_root), patch.object(nodes, "generate_with_llm", side_effect=llm_outputs), patch.object(nodes.subprocess, "run", side_effect=AssertionError("subprocess should not be used for api-design")):
            result = self.async_run(worker(state_input))

        self.assertEqual(next(task for task in result["task_queue"] if task["agent_type"] == "api-design")["status"], "success")
        api_public = (project_root / "artifacts" / "api-public.yaml").read_text(encoding="utf-8")
        self.assertIn("ALIPAY", api_public)
        self.assertIn("UNIONPAY", api_public)
        self.assertEqual([item["tool_name"] for item in result["tool_results"]], ["list_files", "extract_lookup_values", "read_file_chunk"])
        evidence = json.loads((project_root / "evidence" / "api-design.json").read_text(encoding="utf-8"))
        self.assertEqual(evidence["lookup_entries"][0]["values"], ["ALIPAY", "WECHAT", "UNIONPAY"])
        self.assertEqual(evidence["enum_mapping"][0]["enum_values"], ["ALIPAY", "WECHAT", "UNIONPAY"])
        self.assertEqual(evidence["mode"], "in_process_react")
        self.assertGreaterEqual(len(evidence["react_trace"]), 4)
        self.assertTrue(any("react step 3" in entry.lower() for entry in result["history"]))

    def test_api_design_degrades_with_clear_message_when_lookup_missing(self):
        temp_root = self.make_temp_root("api-design-no-lookup")
        project_root = temp_root / "projects" / "demo" / "v1"
        baseline_dir = project_root / "baseline"
        baseline_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "project_name": "demo",
            "project_id": "demo",
            "version": "v1",
            "server_url": "https://internal.demo.local",
            "owner": "demo-team",
            "audience": "external",
            "scenario_desc": "Support payment order creation",
            "requirement": "Create payment order API.",
            "uploaded_files": ["original-requirements.md"],
            "active_agents": ["api-design", "design-assembler", "validator"],
        }
        (baseline_dir / "requirements.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        (baseline_dir / "original-requirements.md").write_text("Create payment order API.\n", encoding="utf-8")

        def fake_llm(system_prompt, user_prompt, expected_files):
            if expected_files == ["decision"]:
                return _FakeSubagentOutput(reasoning="Mock decision fallback", artifacts={"decision": ""})
            return _FakeSubagentOutput(
                reasoning="Proceed without lookup file and leave enum note.",
                artifacts={
                    "api-design.md": "No lookup uploaded; enums require confirmation.",
                    "api-public.yaml": "paymentChannel:\n  type: string\n  description: Lookup file not provided.\n",
                    "errors-rfc9457.json": '{"errors":[{"errorCode":"PAY-400"}]}',
                },
            )

        worker = nodes.create_worker_node("api-design")
        state_input = {
            "project_id": "demo",
            "version": "v1",
            "task_queue": [
                {"id": "0", "agent_type": "planner", "status": "success", "dependencies": [], "priority": 100},
                {"id": "5", "agent_type": "api-design", "status": "running", "dependencies": ["0"], "priority": 70},
            ],
        }

        with patch.object(nodes, "BASE_DIR", temp_root), patch.object(nodes, "generate_with_llm", side_effect=fake_llm):
            result = self.async_run(worker(state_input))

        self.assertEqual(next(task for task in result["task_queue"] if task["agent_type"] == "api-design")["status"], "success")
        self.assertTrue(any("lookup file" in entry.lower() for entry in result["history"]))

    def test_planner_normalizes_agent_aliases_into_supported_queue(self):
        temp_root = self.make_temp_root("planner-aliases")
        baseline_dir = temp_root / "projects" / "demo" / "v1" / "baseline"
        logs_dir = temp_root / "projects" / "demo" / "v1" / "logs"
        baseline_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        (baseline_dir / "original-requirements.md").write_text("Need payment design", encoding="utf-8")

        fake_llm_output = _FakeSubagentOutput(
            reasoning="Selected aliases",
            artifacts={"active_agents": '["architect-map","readiness","tests"]'},
        )

        with patch.object(nodes, "BASE_DIR", temp_root), patch.object(nodes, "generate_with_llm", return_value=fake_llm_output):
            state = self.async_run(
                nodes.planner_node(
                    {
                        "project_id": "demo",
                        "version": "v1",
                        "requirement": "Need payment design",
                        "task_queue": [
                            {"id": "0", "agent_type": "planner", "status": "running", "dependencies": [], "priority": 100}
                        ],
                    }
                )
            )

        queued_agents = {task["agent_type"] for task in state["task_queue"]}
        self.assertIn("architecture-mapping", queued_agents)
        self.assertIn("ops-readiness", queued_agents)
        self.assertIn("test-design", queued_agents)
        self.assertNotIn("architect-map", queued_agents)
        self.assertNotIn("readiness", queued_agents)
        self.assertNotIn("tests", queued_agents)

    def test_resume_workflow_reuses_existing_run_id_for_approve(self):
        saved_tasks = []

        async def fake_run(job_id, project_id, version, requirement_text, *, resume_action=None, feedback=None, persisted_state_override=None):
            saved_tasks.append(
                {
                    "job_id": job_id,
                    "project_id": project_id,
                    "version": version,
                    "requirement_text": requirement_text,
                    "resume_action": resume_action,
                    "feedback": feedback,
                    "persisted_state_override": persisted_state_override,
                }
            )

        with patch.object(
            orch,
            "get_workflow_state",
            return_value={
                "run_id": "run-existing",
                "requirement": "Need payment design",
                "run_status": "waiting_human",
                "current_node": "planner",
                "can_resume": True,
            },
        ), patch.object(orch, "run_orchestrator_task", side_effect=fake_run), patch.object(orch, "_delete_checkpoint_state") as delete_checkpoint_state:
            success = self.async_run(orch.resume_workflow("demo", "v1", {"action": "approve", "feedback": ""}))
            self.async_run(asyncio.sleep(0))

        self.assertTrue(success)
        delete_checkpoint_state.assert_called_once_with("demo", "v1")
        self.assertEqual(len(saved_tasks), 1)
        self.assertEqual(saved_tasks[0]["job_id"], "run-existing")
        self.assertEqual(saved_tasks[0]["resume_action"], "approve")
        self.assertEqual(saved_tasks[0]["persisted_state_override"]["run_id"], "run-existing")

    def test_resume_workflow_routes_answer_to_precise_interrupt_target(self):
        saved_tasks = []

        async def fake_run(job_id, project_id, version, requirement_text, *, resume_action=None, feedback=None, persisted_state_override=None):
            saved_tasks.append(
                {
                    "job_id": job_id,
                    "resume_action": resume_action,
                    "feedback": feedback,
                    "persisted_state_override": persisted_state_override,
                }
            )

        waiting_state = {
            "run_id": "run-existing",
            "requirement": "Need payment design",
            "run_status": "waiting_human",
            "current_node": "planner",
            "can_resume": True,
            "task_queue": [
                {"id": "0", "agent_type": "planner", "status": "success", "dependencies": [], "priority": 100}
            ],
            "pending_interrupt": {
                "node_id": "planner",
                "node_type": "planner",
                "interrupt_id": "interrupt-1",
                "question": "请补充支付渠道范围",
                "context": {"missing_information": ["payment_channels"]},
                "resume_target": "planner",
            },
        }

        with patch.object(orch, "get_workflow_state", return_value=waiting_state), patch.object(orch, "run_orchestrator_task", side_effect=fake_run), patch.object(orch, "_delete_checkpoint_state") as delete_checkpoint_state:
            success = self.async_run(
                orch.resume_workflow(
                    "demo",
                    "v1",
                    {
                        "action": "answer",
                        "node_id": "planner",
                        "interrupt_id": "interrupt-1",
                        "selected_option": "wallets_only",
                        "answer": "首期支持支付宝、微信和银联。",
                    },
                )
            )
            self.async_run(asyncio.sleep(0))

        self.assertTrue(success)
        delete_checkpoint_state.assert_called_once_with("demo", "v1")
        self.assertEqual(saved_tasks[0]["resume_action"], "answer")
        resumed_state = saved_tasks[0]["persisted_state_override"]
        self.assertEqual(resumed_state["resume_target_node"], "planner")
        self.assertIsNone(resumed_state["pending_interrupt"])
        self.assertEqual(resumed_state["human_answers"]["planner"][0]["answer"], "首期支持支付宝、微信和银联。")
        self.assertEqual(resumed_state["human_answers"]["planner"][0]["selected_option"], "wallets_only")
        self.assertIn("Selected option: wallets_only", resumed_state["human_answers"]["planner"][0]["summary"])

    def test_resume_workflow_reuses_existing_run_id_for_revise(self):
        saved_tasks = []

        async def fake_run(job_id, project_id, version, requirement_text, *, resume_action=None, feedback=None, persisted_state_override=None):
            saved_tasks.append(
                {
                    "job_id": job_id,
                    "project_id": project_id,
                    "version": version,
                    "requirement_text": requirement_text,
                    "resume_action": resume_action,
                    "feedback": feedback,
                    "persisted_state_override": persisted_state_override,
                }
            )

        with patch.object(
            orch,
            "get_workflow_state",
            return_value={
                "run_id": "run-existing",
                "requirement": "Need payment design",
                "run_status": "waiting_human",
                "current_node": "planner",
                "can_resume": True,
            },
        ), patch.object(orch, "run_orchestrator_task", side_effect=fake_run), patch.object(orch, "_delete_checkpoint_state") as delete_checkpoint_state:
            success = self.async_run(
                orch.resume_workflow("demo", "v1", {"action": "revise", "feedback": "Please focus on async API design"})
            )
            self.async_run(asyncio.sleep(0))

        self.assertTrue(success)
        delete_checkpoint_state.assert_called_once_with("demo", "v1")
        self.assertEqual(len(saved_tasks), 1)
        self.assertEqual(saved_tasks[0]["job_id"], "run-existing")
        self.assertEqual(saved_tasks[0]["resume_action"], "revise")
        self.assertEqual(saved_tasks[0]["feedback"], "Please focus on async API design")
        self.assertEqual(saved_tasks[0]["persisted_state_override"]["run_id"], "run-existing")

    def test_resume_workflow_does_not_create_new_run_when_state_missing(self):
        with patch.object(orch, "get_workflow_state", return_value=None):
            success = self.async_run(orch.resume_workflow("demo", "v1", {"action": "approve", "feedback": ""}))

        self.assertFalse(success)

    def test_waiting_human_event_includes_interrupt_context(self):
        orch._ensure_job("run-ctx")
        payload = {
            "human_intervention_required": True,
            "waiting_reason": "请补充支付渠道范围",
            "pending_interrupt": {
                "node_id": "planner",
                "node_type": "planner",
                "interrupt_id": "interrupt-ctx",
                "question": "请补充支付渠道范围",
                "context": {"missing_information": ["payment_channels"]},
                "resume_target": "planner",
            },
            "task_queue": [{"id": "0", "agent_type": "planner", "status": "success"}],
        }

        with patch.object(orch, "_load_artifacts_from_disk", return_value={}):
            orch._handle_structured_graph_event("run-ctx", "demo", "v1", "planner", payload, {})

        waiting_event = next(event for event in orch.get_job_events("run-ctx") if event["event_type"] == "waiting_human")
        self.assertEqual(waiting_event["node_id"], "0")
        self.assertEqual(waiting_event["interrupt_id"], "interrupt-ctx")
        self.assertEqual(waiting_event["context"]["missing_information"], ["payment_channels"])

    def test_load_artifacts_from_disk_includes_logs_and_baseline_files_for_frontend(self):
        temp_root = self.make_temp_root("artifact-sources")
        temp_projects = temp_root / "projects"
        version_root = temp_projects / "demo" / "v1"
        (version_root / "artifacts").mkdir(parents=True, exist_ok=True)
        (version_root / "logs").mkdir(parents=True, exist_ok=True)
        (version_root / "baseline").mkdir(parents=True, exist_ok=True)
        (version_root / "evidence").mkdir(parents=True, exist_ok=True)
        (version_root / "release").mkdir(parents=True, exist_ok=True)

        (version_root / "artifacts" / "architecture.md").write_text("architecture-body", encoding="utf-8")
        (version_root / "logs" / "architecture-mapping-reasoning.md").write_text("reasoning-body", encoding="utf-8")
        (version_root / "baseline" / "requirements.json").write_text('{"k":"v"}', encoding="utf-8")
        (version_root / "evidence" / "architecture-mapping.json").write_text('{"mode":"react"}', encoding="utf-8")
        (version_root / "release" / "detailed-design.md").write_text("release-body", encoding="utf-8")

        with patch.object(orch, "PROJECTS_DIR", temp_projects):
            artifacts = orch._load_artifacts_from_disk("demo", "v1")

        self.assertEqual(artifacts["architecture.md"], "architecture-body")
        self.assertEqual(artifacts["architecture-mapping-reasoning.md"], "reasoning-body")
        self.assertEqual(artifacts["requirements.json"], '{"k":"v"}')
        self.assertEqual(artifacts["architecture-mapping.json"], '{"mode":"react"}')
        self.assertEqual(artifacts["detailed-design.md"], "release-body")

    def test_delete_version_removes_project_files_and_checkpoint_rows(self):
        temp_root = self.make_temp_root("delete-version")
        temp_projects = temp_root / "projects"
        version_root = temp_projects / "demo" / "v1"
        (version_root / "artifacts").mkdir(parents=True, exist_ok=True)
        (version_root / "artifacts" / "architecture.md").write_text("arch", encoding="utf-8")

        checkpoint_db = temp_root / "langgraph.sqlite"
        conn = sqlite3.connect(checkpoint_db)
        conn.execute(
            "CREATE TABLE checkpoints (thread_id TEXT, checkpoint_ns TEXT, checkpoint_id TEXT, parent_checkpoint_id TEXT, type TEXT, checkpoint BLOB, metadata BLOB)"
        )
        conn.execute(
            "CREATE TABLE writes (thread_id TEXT, checkpoint_ns TEXT, checkpoint_id TEXT, task_id TEXT, idx INTEGER, channel TEXT, type TEXT, value BLOB)"
        )
        conn.execute("INSERT INTO checkpoints(thread_id, checkpoint_ns, checkpoint_id) VALUES (?, ?, ?)", ("demo_v1", "", "cp1"))
        conn.execute("INSERT INTO writes(thread_id, checkpoint_ns, checkpoint_id, task_id, idx) VALUES (?, ?, ?, ?, ?)", ("demo_v1", "", "cp1", "task", 0))
        conn.execute("INSERT INTO checkpoints(thread_id, checkpoint_ns, checkpoint_id) VALUES (?, ?, ?)", ("demo_v2", "", "cp2"))
        conn.commit()
        conn.close()

        with patch.object(orch, "PROJECTS_DIR", temp_projects), patch.object(orch, "CHECKPOINT_DB_PATH", checkpoint_db):
            deleted = orch.delete_version("demo", "v1")

        self.assertTrue(deleted)
        self.assertFalse(version_root.exists())

        conn = sqlite3.connect(checkpoint_db)
        remaining_threads = [row[0] for row in conn.execute("SELECT thread_id FROM checkpoints ORDER BY thread_id").fetchall()]
        conn.close()
        self.assertEqual(remaining_threads, ["demo_v2"])

    def test_delete_version_rejects_running_version(self):
        with patch.object(
            orch,
            "get_workflow_state",
            return_value={"run_status": "running", "run_id": "run-1"},
        ):
            deleted = orch.delete_version("demo", "v1")

        self.assertFalse(deleted)

    def test_record_graph_event_marks_human_pause_as_waiting(self):
        orch.runtime_registry.clear()

        payload = orch._record_graph_event(
            "demo",
            "v1",
            "planner",
            {"human_intervention_required": True, "waiting_reason": "Need approval"},
            job_id="run-1",
        )

        self.assertTrue(payload["human_intervention_required"])
        runtime = orch.runtime_registry["demo_v1"]
        self.assertEqual(runtime["run_status"], "waiting_human")
        self.assertEqual(runtime["current_node"], "planner")
        self.assertEqual(runtime["waiting_reason"], "Need approval")

    def test_reset_retry_branch_only_resets_target_and_downstream_nodes(self):
        queue = [
            {"id": "0", "agent_type": "planner", "status": "success", "dependencies": []},
            {"id": "1", "agent_type": "architecture-mapping", "status": "success", "dependencies": ["0"]},
            {"id": "5", "agent_type": "api-design", "status": "failed", "dependencies": ["1"]},
            {"id": "7", "agent_type": "flow-design", "status": "success", "dependencies": ["1"]},
            {"id": "10", "agent_type": "design-assembler", "status": "todo", "dependencies": ["1", "5", "7"]},
            {"id": "11", "agent_type": "validator", "status": "todo", "dependencies": ["10"]},
        ]

        reset_queue = orch._reset_retry_branch(queue, "api-design")
        statuses = {task["agent_type"]: task["status"] for task in reset_queue}

        self.assertEqual(statuses["planner"], "success")
        self.assertEqual(statuses["architecture-mapping"], "success")
        self.assertEqual(statuses["flow-design"], "success")
        self.assertEqual(statuses["api-design"], "todo")
        self.assertEqual(statuses["design-assembler"], "todo")
        self.assertEqual(statuses["validator"], "todo")

    def test_retry_workflow_node_reuses_run_and_resets_branch(self):
        saved_tasks = []
        current_state = {
            "run_id": "run-existing",
            "requirement": "Need payment design",
            "run_status": "failed",
            "task_queue": [
                {"id": "0", "agent_type": "planner", "status": "success", "dependencies": []},
                {"id": "1", "agent_type": "architecture-mapping", "status": "success", "dependencies": ["0"]},
                {"id": "5", "agent_type": "api-design", "status": "failed", "dependencies": ["1"]},
                {"id": "10", "agent_type": "design-assembler", "status": "todo", "dependencies": ["1", "5"]},
            ],
        }

        async def fake_run(job_id, project_id, version, requirement_text, *, resume_action=None, feedback=None, persisted_state_override=None):
            saved_tasks.append(
                {
                    "job_id": job_id,
                    "resume_action": resume_action,
                    "persisted_state_override": persisted_state_override,
                }
            )

        with patch.object(orch, "get_workflow_state", return_value=current_state), patch.object(orch, "run_orchestrator_task", side_effect=fake_run), patch.object(orch, "_delete_checkpoint_state") as delete_checkpoint_state:
            success = self.async_run(orch.retry_workflow_node("demo", "v1", "api-design"))
            self.async_run(asyncio.sleep(0))

        self.assertTrue(success)
        delete_checkpoint_state.assert_called_once_with("demo", "v1")
        self.assertEqual(saved_tasks[0]["job_id"], "run-existing")
        self.assertEqual(saved_tasks[0]["resume_action"], "approve")
        retried_queue = saved_tasks[0]["persisted_state_override"]["task_queue"]
        retried_statuses = {task["agent_type"]: task["status"] for task in retried_queue}
        self.assertEqual(saved_tasks[0]["persisted_state_override"]["resume_target_node"], "api-design")
        self.assertEqual(retried_statuses["api-design"], "running")

    def test_continue_workflow_reuses_run_for_queued_state(self):
        saved_tasks = []
        current_state = {
            "run_id": "run-existing",
            "requirement": "Need payment design",
            "run_status": "queued",
            "can_resume": False,
            "task_queue": [
                {"id": "0", "agent_type": "planner", "status": "success", "dependencies": []},
                {"id": "1", "agent_type": "architecture-mapping", "status": "success", "dependencies": ["0"]},
                {"id": "10", "agent_type": "design-assembler", "status": "todo", "dependencies": ["1"]},
            ],
        }

        async def fake_run(job_id, project_id, version, requirement_text, *, resume_action=None, feedback=None, persisted_state_override=None):
            saved_tasks.append(
                {
                    "job_id": job_id,
                    "resume_action": resume_action,
                    "persisted_state_override": persisted_state_override,
                }
            )

        with patch.object(orch, "get_workflow_state", return_value=current_state), patch.object(orch, "run_orchestrator_task", side_effect=fake_run), patch.object(orch, "_delete_checkpoint_state") as delete_checkpoint_state:
            success = self.async_run(orch.continue_workflow("demo", "v1"))
            self.async_run(asyncio.sleep(0))

        self.assertTrue(success)
        delete_checkpoint_state.assert_called_once_with("demo", "v1")
        self.assertEqual(saved_tasks[0]["job_id"], "run-existing")
        self.assertEqual(saved_tasks[0]["resume_action"], "approve")
        self.assertEqual(saved_tasks[0]["persisted_state_override"]["run_status"], "running")

    def test_continue_workflow_rejects_when_workflow_is_waiting_human(self):
        current_state = {
            "run_id": "run-existing",
            "run_status": "waiting_human",
            "can_resume": True,
            "task_queue": [
                {"id": "0", "agent_type": "planner", "status": "success", "dependencies": []},
                {"id": "1", "agent_type": "architecture-mapping", "status": "todo", "dependencies": ["0"]},
            ],
        }

        with patch.object(orch, "get_workflow_state", return_value=current_state):
            success = self.async_run(orch.continue_workflow("demo", "v1"))

        self.assertFalse(success)

    def async_run(self, awaitable):
        import asyncio

        return asyncio.run(awaitable)


if __name__ == "__main__":
    unittest.main()
