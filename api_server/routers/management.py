from fastapi import APIRouter, HTTPException
from typing import List
from models.management import AgentMetadata, SkillMetadata, TemplateMetadata, TemplateVersion
import services.orchestrator_service as orch
from pydantic import BaseModel

router = APIRouter(
    prefix="/api/v1/management",
    tags=["Management"],
)

class TemplateUpdateRequest(BaseModel):
    content: str

class AgentUpdateRequest(BaseModel):
    config_yaml: str

@router.get("/agents", response_model=List[AgentMetadata])
async def list_agents():
    return orch.list_agents()

@router.get("/agents/{agent_id}", response_model=AgentMetadata)
async def get_agent(agent_id: str):
    agent = orch.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent

@router.post("/agents/{agent_id}")
async def update_agent(agent_id: str, req: AgentUpdateRequest):
    success = orch.update_agent(agent_id, req.config_yaml)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to update agent (invalid YAML or ID)")
    return {"status": "success", "message": f"Agent {agent_id} updated and versioned."}

@router.get("/skills", response_model=List[SkillMetadata])
async def list_skills():
    return orch.list_skills()

@router.get("/skills/{skill_id}/templates/{template_name}", response_model=TemplateMetadata)
async def get_template(skill_id: str, template_name: str):
    tpl = orch.get_template(skill_id, template_name)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    return tpl

@router.post("/skills/{skill_id}/templates/{template_name}")
async def update_template(skill_id: str, template_name: str, req: TemplateUpdateRequest):
    success = orch.update_template(skill_id, template_name, req.content)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update template")
    return {"status": "success", "message": f"Template {template_name} updated and versioned."}
