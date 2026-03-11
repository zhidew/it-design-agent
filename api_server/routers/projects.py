from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import List
from models.project import ProjectCreateRequest, ProjectResponse, VersionRunRequest, JobResponse
import services.orchestrator_service as orch

router = APIRouter(
    prefix="/api/v1/projects",
    tags=["Projects"],
)

@router.get("", response_model=List[ProjectResponse])
async def get_projects():
    projects = orch.list_projects()
    return projects

@router.post("", response_model=ProjectResponse)
async def create_project(req: ProjectCreateRequest):
    # Use name as ID for simplicity in MVP
    project_id = req.name.strip().replace(" ", "-").lower()
    orch.create_project(project_id)
    return {"id": project_id, "name": req.name, "description": req.description}

@router.get("/{project_id}/versions", response_model=List[str])
async def get_project_versions(project_id: str):
    versions = orch.list_versions(project_id)
    return versions

@router.post("/{project_id}/versions/{version}/run", response_model=JobResponse)
async def run_design_orchestrator(project_id: str, version: str, req: VersionRunRequest):
    # This triggers the async task in the background
    job_id = orch.trigger_orchestrator(project_id, version, req.requirement_text)
    return {"job_id": job_id, "status": "running", "message": "Orchestrator job started."}

@router.get("/{project_id}/versions/{version}/artifacts")
async def get_artifacts(project_id: str, version: str):
    tree = orch.get_artifacts_tree(project_id, version)
    if not tree:
        raise HTTPException(status_code=404, detail="Artifacts not found or project/version does not exist.")
    return tree

@router.get("/{project_id}/versions/{version}/logs")
async def get_version_logs(project_id: str, version: str):
    logs = orch.get_version_logs(project_id, version)
    return {"logs": logs}
