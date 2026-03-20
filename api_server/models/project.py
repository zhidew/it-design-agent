from pydantic import BaseModel
from typing import List, Optional

class ProjectCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None

class ProjectResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    total_versions: int = 0
    enabled_experts_count: int = 0
    running_versions: int = 0
    has_versions: bool = False
    is_active: bool = False
    status: str = 'empty'

class VersionRunRequest(BaseModel):
    requirement_text: str

class JobResponse(BaseModel):
    job_id: str
    status: str
    message: str


class ResumeRequest(BaseModel):
    action: str
    node_id: Optional[str] = None
    interrupt_id: Optional[str] = None
    selected_option: Optional[str] = None
    answer: Optional[str] = None
    feedback: Optional[str] = None


class NodeRetryRequest(BaseModel):
    node_type: str
