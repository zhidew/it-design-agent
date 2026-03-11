from pydantic import BaseModel
from typing import List, Optional

class ProjectCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None

class ProjectResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None

class VersionRunRequest(BaseModel):
    requirement_text: str

class JobResponse(BaseModel):
    job_id: str
    status: str
    message: str
