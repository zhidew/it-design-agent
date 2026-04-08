from typing import Dict, List, Set

from fastapi import APIRouter, HTTPException

from models.project_config import DatabaseConfig, DebugConfig, ExpertConfig, KnowledgeBaseConfig, LlmConfig, RepositoryConfig, ModelConfig, ModelConfigs

try:
    from api_server.services.db_service import metadata_db
    from api_server.services.llm_service import test_llm_connectivity
    from api_server.services.connectivity_service import (
        test_repository_connection,
        test_database_connection,
        test_knowledge_base_connection,
    )
    from api_server.services.orchestrator_service import get_expert as get_expert_metadata
    from api_server.services.orchestrator_service import get_phase_orchestration
except ModuleNotFoundError:
    from services.db_service import metadata_db
    from services.llm_service import test_llm_connectivity
    from services.connectivity_service import (
        test_repository_connection,
        test_database_connection,
        test_knowledge_base_connection,
    )
    from services.orchestrator_service import get_expert as get_expert_metadata
    from services.orchestrator_service import get_phase_orchestration


router = APIRouter(
    prefix="/api/v1/projects/{project_id}/config",
    tags=["Project Config"],
)

system_router = APIRouter(
    prefix="/api/v1/system",
    tags=["System Config"],
)


def _require_project(project_id: str):
    project = metadata_db.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found.")
    return project


def _get_expert_phase_assignment(expert_id: str) -> str:
    try:
        orchestration = get_phase_orchestration()
    except Exception:
        return ""

    for expert in orchestration.get("experts", []):
        if expert.get("id") == expert_id:
            return str(expert.get("phase") or "").strip().upper()
    return ""


def _ensure_phase_assignment_for_enabled_expert(project_id: str, payload: dict):
    if not payload.get("enabled", True):
        return

    existing = metadata_db.get_project_expert(project_id, payload["id"]) or {}
    if existing.get("enabled"):
        return

    if _get_expert_phase_assignment(payload["id"]):
        return

    expert_label = (
        payload.get("name_zh")
        or payload.get("name_en")
        or payload.get("name")
        or payload["id"]
    )
    raise HTTPException(
        status_code=422,
        detail=(
            f"Expert '{expert_label}' is not assigned to any phase yet. "
            "Configure it in Expert Center > System Tools > Phase Orchestration "
            "before enabling it for this project."
        ),
    )


def _get_expert_lifecycle_status(expert_id: str) -> str:
    try:
        expert = get_expert_metadata(expert_id)
    except Exception:
        expert = None
    if not expert:
        return "active"
    return str(expert.get("lifecycle_status") or "active").strip().lower() or "active"


def _ensure_active_lifecycle_for_enabled_expert(project_id: str, payload: dict):
    if not payload.get("enabled", True):
        return

    existing = metadata_db.get_project_expert(project_id, payload["id"]) or {}
    if existing.get("enabled"):
        return

    lifecycle_status = _get_expert_lifecycle_status(payload["id"])
    if lifecycle_status == "active":
        return

    expert_label = (
        payload.get("name_zh")
        or payload.get("name_en")
        or payload.get("name")
        or payload["id"]
    )
    raise HTTPException(
        status_code=422,
        detail=(
            f"Expert '{expert_label}' is currently in lifecycle status '{lifecycle_status}'. "
            "Promote it to Active in Expert Center > select the expert > Lifecycle Status "
            "before enabling it for this project."
        ),
    )


def _get_expert_label(expert: dict) -> str:
    return (
        expert.get("name_zh")
        or expert.get("name_en")
        or expert.get("name")
        or expert.get("id")
        or "unknown expert"
    )


def _get_project_expert_catalog(project_id: str) -> Dict[str, dict]:
    experts = metadata_db.list_project_experts(project_id)
    return {
        str(expert.get("id")).strip(): expert
        for expert in experts
        if str(expert.get("id") or "").strip()
    }


def _normalize_dependency_ids(raw_dependencies: List[str], available_ids: Set[str]) -> List[str]:
    dependencies: List[str] = []
    seen: Set[str] = set()
    for dependency_id in raw_dependencies or []:
        normalized = str(dependency_id or "").strip()
        if not normalized or normalized in seen or normalized not in available_ids:
            continue
        seen.add(normalized)
        dependencies.append(normalized)
    return dependencies


def _collect_transitive_dependencies(
    expert_id: str,
    dependency_map: Dict[str, List[str]],
    cache: Dict[str, Set[str]],
    trail: Set[str] | None = None,
) -> Set[str]:
    if expert_id in cache:
        return set(cache[expert_id])

    active_trail = set(trail or set())
    active_trail.add(expert_id)
    collected: Set[str] = set()

    for dependency_id in dependency_map.get(expert_id, []):
        if dependency_id == expert_id or dependency_id in active_trail:
            continue
        collected.add(dependency_id)
        collected.update(
            _collect_transitive_dependencies(
                dependency_id,
                dependency_map,
                cache,
                active_trail,
            )
        )

    cache[expert_id] = set(collected)
    return set(collected)


def _ensure_dependency_closure_for_project_expert(project_id: str, payload: dict):
    existing = metadata_db.get_project_expert(project_id, payload["id"]) or {}
    was_enabled = bool(existing.get("enabled"))
    will_be_enabled = bool(payload.get("enabled", True))
    if was_enabled == will_be_enabled:
        return

    experts_by_id = _get_project_expert_catalog(project_id)
    stored_expert = experts_by_id.get(payload["id"], {})
    current_expert = {**stored_expert, **payload}
    if not payload.get("dependencies") and stored_expert.get("dependencies"):
        current_expert["dependencies"] = stored_expert.get("dependencies") or []
    experts_by_id[payload["id"]] = current_expert
    available_ids = set(experts_by_id.keys())
    dependency_map = {
        expert_id: _normalize_dependency_ids(expert.get("dependencies") or [], available_ids)
        for expert_id, expert in experts_by_id.items()
    }
    enabled_ids = {
        expert_id
        for expert_id, expert in experts_by_id.items()
        if bool(expert.get("enabled"))
    }
    closure_cache: Dict[str, Set[str]] = {}

    if will_be_enabled:
        desired_enabled_ids = set(enabled_ids)
        desired_enabled_ids.add(payload["id"])
        required_ids = _collect_transitive_dependencies(payload["id"], dependency_map, closure_cache)
        missing_ids = sorted(
            required_ids - desired_enabled_ids,
            key=lambda item: _get_expert_label(experts_by_id[item]).lower(),
        )
        if not missing_ids:
            return

        missing_labels = ", ".join(f"'{_get_expert_label(experts_by_id[item])}'" for item in missing_ids)
        raise HTTPException(
            status_code=422,
            detail=(
                f"Expert '{_get_expert_label(current_expert)}' depends on {missing_labels}. "
                "Enable those upstream experts in Project Config > Expert Enablement "
                "before enabling it for this project."
            ),
        )

    desired_enabled_ids = set(enabled_ids)
    desired_enabled_ids.discard(payload["id"])
    blocking_ids = sorted(
        [
            expert_id
            for expert_id in desired_enabled_ids
            if payload["id"] in _collect_transitive_dependencies(expert_id, dependency_map, closure_cache)
        ],
        key=lambda item: _get_expert_label(experts_by_id[item]).lower(),
    )
    if not blocking_ids:
        return

    blocking_labels = ", ".join(f"'{_get_expert_label(experts_by_id[item])}'" for item in blocking_ids)
    raise HTTPException(
        status_code=422,
        detail=(
            f"Expert '{_get_expert_label(current_expert)}' is still required by enabled experts {blocking_labels}. "
            "Disable those downstream experts in Project Config > Expert Enablement "
            "before disabling it for this project."
        ),
    )

@router.post("/repositories")
async def create_repository_config(project_id: str, req: RepositoryConfig):
    _require_project(project_id)
    payload = req.model_dump() if hasattr(req, "model_dump") else req.dict()
    return metadata_db.upsert_repository(project_id, payload)


@router.get("/repositories")
async def list_repository_configs(project_id: str):
    _require_project(project_id)
    return {"repositories": metadata_db.list_repositories(project_id)}


@router.delete("/repositories/{repo_id}")
async def delete_repository_config(project_id: str, repo_id: str):
    _require_project(project_id)
    deleted = metadata_db.delete_repository(project_id, repo_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Repository config '{repo_id}' not found.")
    return {"success": True, "project_id": project_id, "repo_id": repo_id}


@router.post("/databases")
async def create_database_config(project_id: str, req: DatabaseConfig):
    _require_project(project_id)
    payload = req.model_dump() if hasattr(req, "model_dump") else req.dict()
    return metadata_db.upsert_database(project_id, payload)


@router.get("/databases")
async def list_database_configs(project_id: str):
    _require_project(project_id)
    return {"databases": metadata_db.list_databases(project_id)}


@router.delete("/databases/{db_id}")
async def delete_database_config(project_id: str, db_id: str):
    _require_project(project_id)
    deleted = metadata_db.delete_database(project_id, db_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Database config '{db_id}' not found.")
    return {"success": True, "project_id": project_id, "db_id": db_id}


@router.post("/knowledge-bases")
async def create_knowledge_base_config(project_id: str, req: KnowledgeBaseConfig):
    _require_project(project_id)
    payload = req.model_dump() if hasattr(req, "model_dump") else req.dict()
    return metadata_db.upsert_knowledge_base(project_id, payload)


@router.get("/knowledge-bases")
async def list_knowledge_base_configs(project_id: str):
    _require_project(project_id)
    return {"knowledge_bases": metadata_db.list_knowledge_bases(project_id)}


@router.delete("/knowledge-bases/{kb_id}")
async def delete_knowledge_base_config(project_id: str, kb_id: str):
    _require_project(project_id)
    deleted = metadata_db.delete_knowledge_base(project_id, kb_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Knowledge base config '{kb_id}' not found.")
    return {"success": True, "project_id": project_id, "kb_id": kb_id}


@router.post("/experts")
async def save_project_expert_config(project_id: str, req: ExpertConfig):
    _require_project(project_id)
    payload = req.model_dump() if hasattr(req, "model_dump") else req.dict()
    _ensure_phase_assignment_for_enabled_expert(project_id, payload)
    _ensure_active_lifecycle_for_enabled_expert(project_id, payload)
    _ensure_dependency_closure_for_project_expert(project_id, payload)
    return metadata_db.upsert_project_expert(project_id, payload)


@router.get("/experts")
async def list_project_expert_configs(project_id: str):
    _require_project(project_id)
    return {"experts": metadata_db.list_project_experts(project_id)}


@router.get("/llm")
async def get_project_llm_config(project_id: str):
    _require_project(project_id)
    return metadata_db.get_project_llm_config(project_id, include_secrets=False, merge_defaults=True)


@router.post("/llm")
async def save_project_llm_config(project_id: str, req: LlmConfig):
    _require_project(project_id)
    payload = req.model_dump() if hasattr(req, "model_dump") else req.dict()
    return metadata_db.upsert_project_llm_config(project_id, payload)


@router.get("/debug")
async def get_project_debug_config(project_id: str):
    _require_project(project_id)
    return metadata_db.get_project_debug_config(project_id)


@router.post("/debug")
async def save_project_debug_config(project_id: str, req: DebugConfig):
    _require_project(project_id)
    payload = req.model_dump() if hasattr(req, "model_dump") else req.dict()
    return metadata_db.upsert_project_debug_config(project_id, payload)


@router.get("/models")
async def list_project_models(project_id: str):
    _require_project(project_id)
    return {"models": metadata_db.list_project_models(project_id)}


@router.post("/models")
async def save_project_model_config(project_id: str, req: ModelConfig):
    _require_project(project_id)
    payload = req.model_dump() if hasattr(req, "model_dump") else req.dict()
    return metadata_db.upsert_project_model(project_id, payload)


@router.delete("/models/{model_id}")
async def delete_project_model_config(project_id: str, model_id: str):
    _require_project(project_id)
    deleted = metadata_db.delete_project_model(project_id, model_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Model config '{model_id}' not found.")
    return {"success": True, "project_id": project_id, "model_id": model_id}


@router.post("/repositories/test")
async def test_repository_config(project_id: str, req: RepositoryConfig):
    _require_project(project_id)
    payload = req.model_dump() if hasattr(req, "model_dump") else req.dict()
    # If token is None but we have an existing one in DB, fetch it
    if payload.get("token") is None and payload.get("id"):
        existing = metadata_db.get_repository(project_id, payload["id"], include_secrets=True)
        if existing:
            payload["token"] = existing.get("token")
    result = test_repository_connection(payload)
    return result.to_dict()


@router.post("/databases/test")
async def test_database_config(project_id: str, req: DatabaseConfig):
    _require_project(project_id)
    payload = req.model_dump() if hasattr(req, "model_dump") else req.dict()
    # If password is None but we have an existing one in DB, fetch it
    if payload.get("password") is None and payload.get("id"):
        existing = metadata_db.get_database(project_id, payload["id"], include_secrets=True)
        if existing:
            payload["password"] = existing.get("password")
    result = test_database_connection(payload)
    return result.to_dict()


@router.post("/knowledge-bases/test")
async def test_knowledge_base_config(project_id: str, req: KnowledgeBaseConfig):
    _require_project(project_id)
    payload = req.model_dump() if hasattr(req, "model_dump") else req.dict()
    result = test_knowledge_base_connection(payload)
    return result.to_dict()


@router.post("/llm/test")
async def test_llm_config(project_id: str, req: ModelConfig):
    _require_project(project_id)
    # If API key is None but we have an existing one in DB, fetch it. 
    # If it is empty string "", it means the user explicitly wants to test with no key.
    payload = req.model_dump() if hasattr(req, "model_dump") else req.dict()
    if (payload.get("api_key") is None or payload.get("headers") is None) and payload.get("id"):
        existing = metadata_db.get_project_model(project_id, payload["id"], include_secrets=True)
        if existing:
            if payload.get("api_key") is None:
                payload["api_key"] = existing.get("api_key")
            if payload.get("headers") is None:
                payload["headers"] = existing.get("headers")
    
    return test_llm_connectivity(payload)


@system_router.get("/llm-config")
async def get_system_llm_defaults():
    return metadata_db.get_system_llm_defaults(include_secrets=False)
