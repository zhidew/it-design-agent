from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File
import shutil
from typing import List
from models.project import ProjectCreateRequest, ProjectResponse, VersionRunRequest, JobResponse, ResumeRequest, NodeRetryRequest, ContinueRequest, CancelRequest
from models.management import VersionListResponse
import services.orchestrator_service as orch

router = APIRouter(
    prefix="/api/v1/projects",
    tags=["Projects"],
)

@router.post("/{project_id}/versions/{version}/upload")
async def upload_baseline_files(
    project_id: str, 
    version: str, 
    files: List[UploadFile] = File(...)
):
    """上传基线输入文件（需求、模型、字典等）"""
    project_path = orch.PROJECTS_DIR / project_id / version
    baseline_dir = project_path / "baseline"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    
    saved_files = []
    for file in files:
        file_path = baseline_dir / file.filename
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        saved_files.append(file.filename)
        
    return {"status": "success", "files": saved_files}

@router.get("", response_model=List[ProjectResponse])
async def get_projects():
    projects = orch.list_projects()
    return projects

@router.post("", response_model=ProjectResponse)
async def create_project(req: ProjectCreateRequest):
    project_id = req.name.strip().replace(" ", "-").lower()
    orch.create_project(project_id)
    return {"id": project_id, "name": req.name, "description": req.description}

@router.get("/{project_id}/assets-summary")
async def get_project_assets_summary(project_id: str):
    summary = orch.get_project_assets_summary(project_id)
    return summary

@router.delete("/{project_id}")
async def delete_project(project_id: str):
    success = orch.delete_project(project_id)
    if not success:
        raise HTTPException(status_code=409, detail="Project cannot be deleted while it has running versions.")
    return {"success": True, "project_id": project_id}

@router.get("/{project_id}/versions", response_model=VersionListResponse)
async def get_project_versions(project_id: str, page: int = 1, page_size: int = 10):
    versions_data = orch.list_versions(project_id, page, page_size)
    return versions_data

@router.delete("/{project_id}/versions/{version}")
async def delete_project_version(project_id: str, version: str):
    deleted = orch.delete_version(project_id, version)
    if not deleted:
        raise HTTPException(status_code=409, detail="Version cannot be deleted while it is running, or it does not exist.")
    return {"success": True, "project_id": project_id, "version": version}

@router.post("/{project_id}/versions/{version}/run", response_model=JobResponse)
async def run_design_orchestrator(project_id: str, version: str, req: VersionRunRequest):
    job_id = orch.trigger_orchestrator(
        project_id,
        version,
        req.requirement_text,
        req.model,
        req.effort_level,
    )
    return {"job_id": job_id, "status": "queued", "message": "Orchestrator job queued."}

@router.get("/{project_id}/versions/{version}/artifacts")
async def get_artifacts(project_id: str, version: str):
    tree = orch.get_artifacts_tree(project_id, version)
    return tree

@router.get("/{project_id}/versions/{version}/state")
async def get_workflow_state(project_id: str, version: str):
    state = orch.get_workflow_state(project_id, version)
    if not state:
        # Fallback to a very minimal state instead of 404
        return {
            "project_id": project_id,
            "version": version,
            "run_status": "failed",
            "task_queue": [],
            "history": ["Error: Workflow state not found on server."],
            "artifacts": {},
        }
    return state

@router.post("/{project_id}/versions/{version}/resume")
async def resume_workflow(project_id: str, version: str, req: ResumeRequest):
    payload = req.model_dump() if hasattr(req, "model_dump") else req.dict()
    success = await orch.resume_workflow(project_id, version, payload)
    if not success:
        raise HTTPException(status_code=409, detail="Workflow is not waiting for human input.")
    return {"success": True, "status": "queued", "action": req.action}

@router.post("/{project_id}/versions/{version}/retry-node")
async def retry_workflow_node(project_id: str, version: str, req: NodeRetryRequest):
    payload = req.model_dump() if hasattr(req, "model_dump") else req.dict()
    success = await orch.retry_workflow_node(
        project_id,
        version,
        payload["node_type"],
        payload.get("model"),
        payload.get("effort_level"),
    )
    if not success:
        raise HTTPException(status_code=409, detail="Node cannot be retried in the current workflow state.")
    return {"success": True, "status": "queued", "node_type": payload["node_type"]}

@router.post("/{project_id}/versions/{version}/continue")
async def continue_workflow(project_id: str, version: str, req: ContinueRequest):
    payload = req.model_dump() if hasattr(req, "model_dump") else req.dict()
    success = await orch.continue_workflow(
        project_id,
        version,
        payload.get("model"),
        payload.get("effort_level"),
    )
    if not success:
        raise HTTPException(status_code=409, detail="Workflow cannot be continued in the current state.")
    return {"success": True, "status": "queued"}


@router.post("/{project_id}/versions/{version}/cancel")
async def cancel_workflow(project_id: str, version: str, req: CancelRequest):
    payload = req.model_dump() if hasattr(req, "model_dump") else req.dict()
    success = await orch.cancel_workflow(
        project_id,
        version,
        payload.get("reason"),
    )
    if not success:
        raise HTTPException(status_code=409, detail="Workflow cannot be cancelled in the current state.")
    return {"success": True, "status": "cancelled"}


@router.get("/{project_id}/versions/{version}/logs")
async def get_version_logs(project_id: str, version: str):
    logs = orch.get_version_logs(project_id, version)
    return {"logs": logs}
