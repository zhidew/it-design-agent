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


@router.get("/agents")
async def list_agents():
    """List all available agents using AgentRegistry."""
    from registry.agent_registry import AgentRegistry
    
    try:
        registry = AgentRegistry.get_instance()
        manifests = registry.get_all_manifests()
        
        # Convert to API response format (compatible with existing UI)
        agents = []
        for m in manifests:
            agent_data = {
                "id": m.capability,
                "name": m.name,
                "description": m.description,
                "config_path": m.agent_yaml_path or "",
                "skills": [m.capability],  # Each agent has its corresponding skill
            }
            agents.append(agent_data)
        
        return agents
    except RuntimeError:
        # Fallback to original implementation if registry not initialized
        return orch.list_agents()


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Get a single agent's details."""
    from registry.agent_registry import AgentRegistry
    
    try:
        registry = AgentRegistry.get_instance()
        manifest = registry.get_manifest(agent_id)
        
        if manifest:
            return {
                "id": manifest.capability,
                "name": manifest.name,
                "description": manifest.description,
                "config_path": manifest.agent_yaml_path or "",
                "skills": [manifest.capability],
                "keywords": manifest.keywords,
                "required_inputs": manifest.required_inputs,
                "expected_outputs": manifest.expected_outputs,
            }
    except RuntimeError:
        pass
    
    # Fallback to original implementation
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
