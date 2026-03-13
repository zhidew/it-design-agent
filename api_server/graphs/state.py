from typing import TypedDict, List, Dict, Any, Optional
from typing_extensions import Annotated
import operator

class Task(TypedDict):
    id: str
    agent_type: str  # e.g., 'api-design', 'data-design'
    priority: int
    input_keys: List[str]
    status: str  # 'todo', 'running', 'success', 'failed', 'blocked'
    dependencies: List[str]
    metadata: Dict[str, Any]

class DesignState(TypedDict):
    # design_context: assets pool (Markdown/YAML/JSON)
    design_context: Dict[str, Any]
    
    # task_queue: structured list of tasks
    # We use Annotated with operator.add or similar if we want to merge updates, 
    # but for a simple queue, we'll manage it in the nodes.
    task_queue: List[Task]
    
    # workflow_phase: INIT -> CORE -> MODEL -> LOGIC -> API -> QUALITY -> DONE
    workflow_phase: str
    
    # history: steps audit and reasoning logs
    history: Annotated[List[str], operator.add]
    
    # human_intervention: for interrupts
    human_intervention_required: bool
    last_worker: Optional[str]
    
    # project metadata
    project_id: str
    version: str
    requirement: str
