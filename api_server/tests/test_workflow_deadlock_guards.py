import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType


API_SERVER_DIR = Path(__file__).resolve().parents[1]
if str(API_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(API_SERVER_DIR))


def _load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


graphs_package = ModuleType("graphs")
graphs_package.__path__ = [str(API_SERVER_DIR / "graphs")]
sys.modules["graphs"] = graphs_package

services_package = ModuleType("services")
services_package.__path__ = [str(API_SERVER_DIR / "services")]
sys.modules["services"] = services_package

models_package = ModuleType("models")
models_package.__path__ = [str(API_SERVER_DIR / "models")]
sys.modules["models"] = models_package

subgraphs_package = ModuleType("subgraphs")
subgraphs_package.__path__ = [str(API_SERVER_DIR / "subgraphs")]
sys.modules["subgraphs"] = subgraphs_package

yaml_module = ModuleType("yaml")
yaml_module.safe_load = lambda content: {}
sys.modules["yaml"] = yaml_module

llm_service_module = ModuleType("services.llm_service")
llm_service_module.SubagentOutput = object
llm_service_module.generate_with_llm = lambda *args, **kwargs: None
llm_service_module.resolve_runtime_llm_settings = lambda *args, **kwargs: None
sys.modules["services.llm_service"] = llm_service_module
setattr(services_package, "llm_service", llm_service_module)


class _StubMetadataDB:
    def list_repositories(self, project_id):
        return []

    def list_databases(self, project_id):
        return []

    def list_knowledge_bases(self, project_id):
        return []

    def get_workflow_run(self, project_id, version):
        return {}

    def list_workflow_tasks(self, project_id, version):
        return []

    def upsert_version(self, *args, **kwargs):
        return None

    def upsert_workflow_run(self, *args, **kwargs):
        return None

    def replace_workflow_tasks(self, *args, **kwargs):
        return None

    def upsert_workflow_task(self, *args, **kwargs):
        return None


db_service_module = ModuleType("services.db_service")
db_service_module.metadata_db = _StubMetadataDB()
sys.modules["services.db_service"] = db_service_module
setattr(services_package, "db_service", db_service_module)

log_service_module = ModuleType("services.log_service")
log_service_module.get_run_log = lambda *args, **kwargs: []
log_service_module.save_run_log = lambda *args, **kwargs: None
sys.modules["services.log_service"] = log_service_module
setattr(services_package, "log_service", log_service_module)

events_module = ModuleType("models.events")
events_module.dump_event = lambda *args, **kwargs: {}
events_module.validate_event_payload = lambda *args, **kwargs: True
sys.modules["models.events"] = events_module
setattr(models_package, "events", events_module)

dynamic_subagent_module = ModuleType("subgraphs.dynamic_subagent")


async def _stub_run_dynamic_subagent(*args, **kwargs):
    return {}


dynamic_subagent_module.run_dynamic_subagent = _stub_run_dynamic_subagent
sys.modules["subgraphs.dynamic_subagent"] = dynamic_subagent_module
setattr(subgraphs_package, "dynamic_subagent", dynamic_subagent_module)

tools_module = ModuleType("graphs.tools")
tools_module.execute_tool = lambda *args, **kwargs: {}
sys.modules["graphs.tools"] = tools_module
setattr(graphs_package, "tools", tools_module)

builder_module = ModuleType("graphs.builder")
builder_module.CHECKPOINT_DB_PATH = API_SERVER_DIR / "tests" / "dummy.sqlite"
builder_module.CHECKPOINTS_DIR = API_SERVER_DIR / "tests"
builder_module.create_design_graph = lambda *args, **kwargs: None
sys.modules["graphs.builder"] = builder_module
setattr(graphs_package, "builder", builder_module)

registry_package = ModuleType("registry")
sys.modules["registry"] = registry_package
agent_registry_module = ModuleType("registry.agent_registry")
expert_registry_module = ModuleType("registry.expert_registry")


class _StubRegistry:
    @staticmethod
    def get_instance():
        raise RuntimeError("registry not initialized in unit test")


agent_registry_module.AgentRegistry = _StubRegistry
expert_registry_module.ExpertRegistry = _StubRegistry
sys.modules["registry.agent_registry"] = agent_registry_module
sys.modules["registry.expert_registry"] = expert_registry_module
setattr(registry_package, "agent_registry", agent_registry_module)
setattr(registry_package, "expert_registry", expert_registry_module)

state_module = _load_module("graphs.state", API_SERVER_DIR / "graphs" / "state.py")
setattr(graphs_package, "state", state_module)
nodes_module = _load_module("graphs.nodes", API_SERVER_DIR / "graphs" / "nodes.py")
setattr(graphs_package, "nodes", nodes_module)
orchestrator_service_module = _load_module(
    "services.orchestrator_service",
    API_SERVER_DIR / "services" / "orchestrator_service.py",
)
setattr(services_package, "orchestrator_service", orchestrator_service_module)

supervisor = nodes_module.supervisor
_normalize_state = orchestrator_service_module._normalize_state
RUN_STATUS_RUNNING = orchestrator_service_module.RUN_STATUS_RUNNING
RUN_STATUS_QUEUED = orchestrator_service_module.RUN_STATUS_QUEUED


class SupervisorGuardTests(unittest.TestCase):
    def test_supervisor_dispatches_later_ready_phase_instead_of_ending(self) -> None:
        state = {
            "workflow_phase": "ARCHITECTURE",
            "task_queue": [
                {"id": "0", "agent_type": "planner", "status": "success", "dependencies": [], "priority": 100},
                {"id": "1", "agent_type": "architecture-mapping", "status": "success", "dependencies": ["0"], "priority": 90, "phase": "ARCHITECTURE"},
                {"id": "2", "agent_type": "integration-design", "status": "todo", "dependencies": ["0", "5"], "priority": 85, "phase": "ARCHITECTURE"},
                {"id": "5", "agent_type": "api-design", "status": "todo", "dependencies": ["0"], "priority": 70, "phase": "INTERFACE"},
            ],
            "design_context": {"orchestrator": {"max_parallel_tasks": 1}},
        }

        decision = supervisor(state)

        self.assertEqual(decision["next"], "api-design")
        self.assertEqual(decision["workflow_phase"], "INTERFACE")
        self.assertEqual(decision["current_task_id"], "5")


class NormalizeStateGuardTests(unittest.TestCase):
    def test_missing_runtime_prefers_queued_projection_over_stale_running_row(self) -> None:
        original_metadata_db = orchestrator_service_module.metadata_db
        original_load_artifacts = orchestrator_service_module._load_artifacts_from_disk
        original_build_legacy = orchestrator_service_module._build_legacy_task_queue
        original_runtime_registry = dict(orchestrator_service_module.runtime_registry)
        original_runtime_tasks = dict(orchestrator_service_module.runtime_tasks)
        try:
            class _ProjectionMetadataDB:
                def get_workflow_run(self, project_id, version):
                    return {
                        "status": RUN_STATUS_RUNNING,
                        "current_node": "supervisor",
                        "waiting_reason": None,
                        "run_id": "run-1",
                        "current_phase": "ARCHITECTURE",
                        "updated_at": "2026-03-24T13:42:23.307451+00:00",
                    }

                def list_workflow_tasks(self, project_id, version):
                    return [
                        {"id": "0", "agent_type": "planner", "status": "success", "dependencies": [], "priority": 100},
                        {"id": "1", "agent_type": "architecture-mapping", "status": "success", "dependencies": ["0"], "priority": 90},
                        {"id": "2", "agent_type": "integration-design", "status": "todo", "dependencies": ["0"], "priority": 85},
                    ]

            orchestrator_service_module.metadata_db = _ProjectionMetadataDB()
            orchestrator_service_module._load_artifacts_from_disk = lambda *args, **kwargs: {}
            orchestrator_service_module._build_legacy_task_queue = lambda *args, **kwargs: []
            orchestrator_service_module.runtime_registry.clear()
            orchestrator_service_module.runtime_tasks.clear()

            normalized = _normalize_state("test4", "vdeadlock", {"current_node": "supervisor"})

            self.assertEqual(normalized["run_status"], RUN_STATUS_QUEUED)
            self.assertFalse(normalized["stale_execution_detected"])
        finally:
            orchestrator_service_module.metadata_db = original_metadata_db
            orchestrator_service_module._load_artifacts_from_disk = original_load_artifacts
            orchestrator_service_module._build_legacy_task_queue = original_build_legacy
            orchestrator_service_module.runtime_registry.clear()
            orchestrator_service_module.runtime_registry.update(original_runtime_registry)
            orchestrator_service_module.runtime_tasks.clear()
            orchestrator_service_module.runtime_tasks.update(original_runtime_tasks)


if __name__ == "__main__":
    unittest.main()
