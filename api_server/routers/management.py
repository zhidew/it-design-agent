from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List

import services.orchestrator_service as orch
from models.management import (
    ExpertDependencyValidationResponse,
    ExpertCenterFileNode,
    ExpertMetadata,
    FileContentResponse,
    SkillMetadata,
    TemplateMetadata,
)
from registry.expert_registry import ExpertRegistry


management_router = APIRouter(
    prefix="/api/v1/management",
    tags=["Management"],
)

expert_center_router = APIRouter(
    prefix="/api/v1/expert-center",
    tags=["Expert Center"],
)


class TemplateUpdateRequest(BaseModel):
    content: str


class AgentUpdateRequest(BaseModel):
    config_yaml: str


class ExpertUpdateRequest(BaseModel):
    profile_yaml: str


class ExpertCreateRequest(BaseModel):
    expert_id: str
    name: str
    description: str = ""


class FileContentUpdateRequest(BaseModel):
    content: str


@management_router.get("/agents")
async def list_agents():
    return orch.list_agents()


@management_router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    agent = orch.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@management_router.post("/agents/{agent_id}")
async def update_agent(agent_id: str, req: AgentUpdateRequest):
    success = orch.update_agent(agent_id, req.config_yaml)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to update agent")
    return {"status": "success", "message": f"Agent {agent_id} updated."}


@management_router.get("/skills", response_model=List[SkillMetadata])
async def list_skills():
    return orch.list_skills()


@management_router.get("/skills/{skill_id}/templates/{template_name}", response_model=TemplateMetadata)
async def get_template(skill_id: str, template_name: str):
    template = orch.get_template(skill_id, template_name)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@management_router.post("/skills/{skill_id}/templates/{template_name}")
async def update_template(skill_id: str, template_name: str, req: TemplateUpdateRequest):
    success = orch.update_template(skill_id, template_name, req.content)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update template")
    return {"status": "success", "message": f"Template {template_name} updated."}


@expert_center_router.get("/experts", response_model=List[ExpertMetadata])
async def list_experts():
    return orch.list_experts()


@expert_center_router.get("/experts/validate-dependencies", response_model=ExpertDependencyValidationResponse)
async def validate_expert_dependencies():
    return orch.validate_expert_dependencies()


@expert_center_router.post("/experts", response_model=ExpertMetadata)
async def create_expert(req: ExpertCreateRequest):
    expert = orch.create_expert(req.expert_id, req.name, req.description)
    if not expert:
        raise HTTPException(status_code=400, detail="Failed to create expert")
    return expert


@expert_center_router.get("/experts/{expert_id}", response_model=ExpertMetadata)
async def get_expert(expert_id: str):
    expert = orch.get_expert(expert_id)
    if not expert:
        raise HTTPException(status_code=404, detail="Expert not found")
    return expert


@expert_center_router.put("/experts/{expert_id}")
async def update_expert(expert_id: str, req: ExpertUpdateRequest):
    success = orch.update_expert(expert_id, req.profile_yaml)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to update expert profile")
    return {"status": "success", "message": f"Expert {expert_id} updated."}


@expert_center_router.delete("/experts/{expert_id}")
async def delete_expert(expert_id: str):
    success = orch.delete_expert(expert_id)
    if not success:
        raise HTTPException(status_code=404, detail="Expert not found")
    return {"status": "success", "message": f"Expert {expert_id} deleted."}


@expert_center_router.get("/file-tree", response_model=List[ExpertCenterFileNode])
async def get_file_tree():
    return orch.get_expert_center_tree()


@expert_center_router.get("/files/{path:path}/content", response_model=FileContentResponse)
async def get_file_content(path: str):
    payload = orch.get_file_content(path)
    if not payload:
        raise HTTPException(status_code=404, detail="File not found")
    return payload


@expert_center_router.put("/files/{path:path}/content")
async def update_file_content(path: str, req: FileContentUpdateRequest):
    success = orch.update_file_content(path, req.content)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to update file content")
    return {"status": "success", "message": f"File {path} updated."}


@expert_center_router.delete("/files/{path:path}")
async def delete_file(path: str):
    """Delete a file from the expert center.
    
    Only allows deleting files in templates, references, and scripts directories.
    Profile and SKILL.md files cannot be deleted.
    """
    success = orch.delete_file(path)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to delete file. File may be protected or not found.")
    return {"status": "success", "message": f"File {path} deleted."}


@expert_center_router.post("/reload")
async def reload_experts():
    """Hot-reload all experts from the experts/ directory.
    
    This enables adding new experts without restarting the server:
    1. Add new *.expert.yaml file to experts/ directory
    2. Call POST /api/v1/expert-center/reload
    3. New expert is automatically available in the workflow
    """
    try:
        registry = ExpertRegistry.get_instance()
        registry.reload()
        stats = registry.get_stats()
        return {
            "status": "success",
            "message": f"Reloaded {stats['total_experts']} experts",
            "experts": stats['capabilities'],
            "errors": stats['load_errors'],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reload experts: {e}")


@expert_center_router.get("/tools")
async def list_tools():
    """List all system built-in tools."""
    tools = orch.list_system_tools()
    return tools


@expert_center_router.get("/tools/{tool_name}/code")
async def get_tool_code(tool_name: str):
    """Get the implementation code of a specific tool."""
    code = orch.get_tool_code(tool_name)
    if code is None:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")
    return {"tool_name": tool_name, "code": code}


router = management_router
