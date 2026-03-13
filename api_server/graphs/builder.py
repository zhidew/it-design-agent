from pathlib import Path
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from .state import DesignState
from .nodes import supervisor, create_worker_node, init_node

# 全局内存存储
memory = MemorySaver()

def create_design_graph():
    workflow = StateGraph(DesignState)

    workflow.add_node("init", init_node)
    workflow.add_node("supervisor", supervisor)
    
    # 定义所有可用的 Agents
    agents = [
        "planner", 
        "architecture-mapping", "integration-design", 
        "data-design", "ddd-structure", 
        "flow-design", "api-design", "config-design", 
        "test-design", "ops-readiness", 
        "design-assembler", "validator"
    ]
    
    for agent in agents:
        workflow.add_node(agent, create_worker_node(agent))

    workflow.set_entry_point("init")
    workflow.add_edge("init", "supervisor")
    
    def route_supervisor(state: DesignState):
        decision = supervisor(state)
        next_step = decision["next"]
        
        if next_step == "END" or next_step == "human_review":
            return END
        elif next_step == "supervisor_advance":
            return "supervisor"
            
        return next_step

    workflow.add_conditional_edges(
        "supervisor",
        route_supervisor
    )

    for agent in agents:
        if agent != "planner": 
            workflow.add_edge(agent, "supervisor")

    return workflow.compile(checkpointer=memory)
