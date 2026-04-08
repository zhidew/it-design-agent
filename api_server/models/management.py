from pydantic import BaseModel, Field
from typing import Any, List, Optional, Dict

class AgentVersion(BaseModel):
    version_id: str
    timestamp: str
    content: str # YAML content
    author: Optional[str] = "System"

class AgentMetadata(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    config_path: str
    current_config: str # Current YAML content
    versions: List[AgentVersion] = []
    skills: List[str] = []

class SkillMetadata(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    path: str
    templates: List[str]

class TemplateVersion(BaseModel):
    version_id: str
    timestamp: str
    content: str
    author: Optional[str] = "System"

class TemplateMetadata(BaseModel):
    id: str
    name: str
    skill_id: str
    current_content: str
    versions: List[TemplateVersion] = []


class ExpertVersion(BaseModel):
    version_id: str
    timestamp: str
    content: str
    author: Optional[str] = "System"


class ExpertMetadata(BaseModel):
    id: str
    name: str
    name_zh: Optional[str] = None
    name_en: Optional[str] = None
    description: Optional[str] = None
    expertise: List[str] = []
    lifecycle_status: str = "active"
    profile_path: str
    skill_path: Optional[str] = None
    current_profile: str
    versions: List[ExpertVersion] = []


class ExpertCenterFileNode(BaseModel):
    id: str
    name: str
    path: str
    node_type: str
    expert_id: Optional[str] = None
    children: List["ExpertCenterFileNode"] = []


class FileContentVersion(BaseModel):
    version_id: str
    timestamp: str
    content: str
    author: Optional[str] = "System"


class FileContentResponse(BaseModel):
    path: str
    name: str
    content: str
    versions: List[FileContentVersion] = []


class ExpertDependencyFinding(BaseModel):
    severity: str
    code: str
    message: str
    expert_id: Optional[str] = None
    related_expert_id: Optional[str] = None
    details: Dict[str, Any] = {}


class ExpertImpactOverlap(BaseModel):
    related_expert_id: str
    shared_outputs: List[str] = Field(default_factory=list)
    shared_boundary_owns: List[str] = Field(default_factory=list)


class ExpertReverseImpact(BaseModel):
    expert_id: str
    direct_downstream_expert_ids: List[str] = Field(default_factory=list)
    all_downstream_expert_ids: List[str] = Field(default_factory=list)
    artifact_consumer_expert_ids: List[str] = Field(default_factory=list)
    output_overlap: List[ExpertImpactOverlap] = Field(default_factory=list)
    boundary_overlap: List[ExpertImpactOverlap] = Field(default_factory=list)
    review_required: bool = False


class ExpertDependencyValidationResponse(BaseModel):
    ok: bool
    expert_count: int
    dependency_edges: int
    summary: Dict[str, int]
    expert_impacts: List[ExpertReverseImpact] = Field(default_factory=list)
    findings: List[ExpertDependencyFinding] = Field(default_factory=list)


class PhaseExpertOption(BaseModel):
    id: str
    name: str
    name_zh: Optional[str] = None
    name_en: Optional[str] = None
    description: Optional[str] = None
    phase: str = ""


class PhaseOrchestrationItem(BaseModel):
    id: str
    label: str
    label_zh: str
    label_en: str
    executable: bool
    order: int
    experts: List[str] = []


class PhaseOrchestrationResponse(BaseModel):
    phases: List[PhaseOrchestrationItem] = []
    experts: List[PhaseExpertOption] = []
    validation_errors: List[str] = []


ExpertCenterFileNode.model_rebuild()


class VersionMetadata(BaseModel):
    version_id: str
    project_id: str
    requirement: str
    run_status: str
    created_at: str
    updated_at: str


class ProjectMetadata(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    created_at: str
    updated_at: str


class VersionListResponse(BaseModel):
    versions: List[VersionMetadata]
    total: int
    page: int
    page_size: int
