from pathlib import Path

from langgraph.graph import END, StateGraph

from .nodes import bootstrap_node, create_worker_node, planner_node, supervisor
from .state import DesignState

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CHECKPOINTS_DIR = BASE_DIR / "projects" / ".orchestrator"
CHECKPOINT_DB_PATH = CHECKPOINTS_DIR / "langgraph-checkpoints.sqlite"


def _get_agents_from_registry() -> list[str]:
    """Dynamically get agent list from ExpertRegistry.
    
    This enables hot-pluggable experts - new experts are automatically
    included in the workflow without code changes.
    """
    builtin_agents = {"validator", "design-assembler"}
    
    try:
        from registry.expert_registry import ExpertRegistry
        registry = ExpertRegistry.get_instance()
        return list(set(registry.get_capabilities()) | builtin_agents)
    except RuntimeError:
        # Fallback for when registry is not initialized (e.g., during tests)
        return list(builtin_agents)


def create_design_graph(checkpointer=None):
    workflow = StateGraph(DesignState)

    workflow.add_node("bootstrap", bootstrap_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("supervisor", supervisor)

    # Dynamically get agents from registry (hot-pluggable)
    agents = _get_agents_from_registry()

    for agent in agents:
        workflow.add_node(agent, create_worker_node(agent))

    workflow.set_entry_point("bootstrap")

    def route_bootstrap(state: DesignState):
        if state.get("resume_target_node"):
            return state["resume_target_node"]
        if state.get("resume_action") == "approve":
            return "supervisor"
        return "planner"

    def route_planner(state: DesignState):
        if state.get("human_intervention_required"):
            return END
        return "supervisor"

    def route_supervisor(state: DesignState):
        decision = supervisor(state)
        next_step = decision["next"]

        if isinstance(next_step, list):
            return next_step if next_step else END
        if next_step in {"END", "human_review"}:
            return END
        if next_step == "supervisor_advance":
            return "supervisor"
        return next_step

    workflow.add_conditional_edges("bootstrap", route_bootstrap)
    workflow.add_conditional_edges("planner", route_planner)
    workflow.add_conditional_edges("supervisor", route_supervisor)

    for agent in agents:
        workflow.add_edge(agent, "supervisor")

    return workflow.compile(checkpointer=checkpointer)
