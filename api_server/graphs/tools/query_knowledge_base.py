from pathlib import Path
from typing import Any, Dict, List

from services.db_service import metadata_db
from services.kb_indexer import (
    KnowledgeBaseError,
    get_feature_tree,
    get_related_designs,
    load_knowledge_base,
    search_design_docs,
    search_terms,
)

from .clone_repository import _resolve_project_id


def _resolve_kb_root(project_id: str, kb_config: Dict[str, Any]) -> Path:
    kb_type = kb_config.get("type")
    if kb_type != "local":
        raise KnowledgeBaseError(f"Unsupported knowledge base type: {kb_type}")

    path = kb_config.get("path")
    if not path:
        raise KnowledgeBaseError(f"Knowledge base '{kb_config['id']}' is missing path.")

    kb_root = Path(path)
    if not kb_root.is_absolute():
        kb_root = Path(__file__).resolve().parents[3] / "projects" / project_id / kb_root
    return kb_root.resolve()


def query_knowledge_base(root_dir: Path, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    query_type = tool_input.get("query_type")
    if not isinstance(query_type, str) or not query_type.strip():
        raise ValueError("`query_type` must be a non-empty string.")

    project_id = _resolve_project_id(root_dir, tool_input)
    kb_id = tool_input.get("kb_id")
    if kb_id:
        config = metadata_db.get_knowledge_base(project_id, kb_id)
        if config is None:
            raise ValueError(f"Knowledge base config not found for kb_id='{kb_id}'.")
        kb_configs: List[Dict[str, Any]] = [config]
    else:
        kb_configs = metadata_db.list_knowledge_bases(project_id)
        if not kb_configs:
            raise ValueError(f"No knowledge bases configured for project '{project_id}'.")

    aggregated = []
    keyword = tool_input.get("keyword")
    feature_id = tool_input.get("feature_id")

    for kb_config in kb_configs:
        kb_root = _resolve_kb_root(project_id, kb_config)
        index = load_knowledge_base(kb_root, includes=kb_config.get("includes"))
        if query_type == "search_terms":
            if not isinstance(keyword, str) or not keyword.strip():
                raise ValueError("`keyword` is required for search_terms.")
            payload = {"matches": search_terms(index, keyword)}
        elif query_type == "get_feature_tree":
            payload = {"feature_tree": get_feature_tree(index)}
        elif query_type == "search_design_docs":
            if not isinstance(keyword, str) or not keyword.strip():
                raise ValueError("`keyword` is required for search_design_docs.")
            payload = {"matches": search_design_docs(index, keyword)}
        elif query_type == "get_related_designs":
            if not isinstance(feature_id, str) or not feature_id.strip():
                raise ValueError("`feature_id` is required for get_related_designs.")
            payload = {"matches": get_related_designs(index, feature_id)}
        else:
            raise ValueError(f"Unsupported query_type: {query_type}")

        aggregated.append(
            {
                "kb_id": kb_config["id"],
                "kb_name": kb_config["name"],
                "kb_root": str(kb_root),
                **payload,
            }
        )

    return {
        "project_id": project_id,
        "query_type": query_type,
        "knowledge_bases": aggregated,
    }
