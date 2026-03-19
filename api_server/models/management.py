from pydantic import BaseModel
from typing import List, Optional, Dict

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
