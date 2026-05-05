from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from services import artifact_dependency_service
from services.db_service import metadata_db


IMPACT_STATUSES = {"no_impact", "needs_revalidation", "needs_regeneration", "blocked_pending_decision"}


def _infer_change_type(source_artifact: Dict[str, Any], revision_delta: Optional[Dict[str, Any]]) -> str:
    if revision_delta:
        explicit = str(revision_delta.get("change_type") or "").strip()
        if explicit:
            return explicit
    artifact_type = str(source_artifact.get("artifact_type") or "").lower()
    file_name = str(source_artifact.get("file_name") or "").lower()
    if artifact_type == "sql" or file_name.endswith(".sql"):
        return "schema_change"
    if "api" in file_name or source_artifact.get("expert_id") == "api-design":
        return "api_contract_change"
    return "artifact_revision"


def _status_for_downstream(change_type: str, downstream: Dict[str, Any], has_blocking_conflict: bool) -> str:
    if has_blocking_conflict:
        return "blocked_pending_decision"
    expert_id = str(downstream.get("expert_id") or "")
    if change_type == "schema_change" and expert_id in {"api-design", "test-design", "design-assembler"}:
        return "needs_regeneration" if expert_id == "design-assembler" else "needs_revalidation"
    if change_type == "api_contract_change" and expert_id in {"integration-design", "test-design", "design-assembler"}:
        return "needs_regeneration"
    return "needs_revalidation"


def analyze_revision_impact(
    source_artifact_id: str,
    revision_delta: Optional[Dict[str, Any]] = None,
    *,
    trigger_type: str = "revision",
    trigger_ref_id: Optional[str] = None,
    has_blocking_conflict: bool = False,
) -> Dict[str, Any]:
    source = metadata_db.get_design_artifact(source_artifact_id)
    if not source:
        raise ValueError("Source artifact not found.")
    downstream_artifacts = artifact_dependency_service.find_downstream_artifacts(source_artifact_id)
    change_type = _infer_change_type(source, revision_delta)
    records: List[Dict[str, Any]] = []

    for downstream in downstream_artifacts:
        impact_status = _status_for_downstream(change_type, downstream, has_blocking_conflict)
        reason = (
            "Upstream has unresolved blocking conflict."
            if impact_status == "blocked_pending_decision"
            else f"Conservative downstream impact from {change_type}."
        )
        record = metadata_db.create_artifact_impact_record(
            impact_id=str(uuid.uuid4()),
            project_id=source["project_id"],
            version_id=source["version_id"],
            source_artifact_id=source_artifact_id,
            impacted_artifact_id=downstream["artifact_id"],
            impact_status=impact_status,
            trigger_type=trigger_type,
            trigger_ref_id=trigger_ref_id,
            reason=reason,
            evidence={
                "change_type": change_type,
                "source_artifact_version": source.get("artifact_version"),
                "downstream_expert": downstream.get("expert_id"),
                "dependency_edge": downstream.get("dependency_edge"),
                "revision_delta": revision_delta or {},
            },
        )
        records.append(record)
        if impact_status != "no_impact":
            metadata_db.update_design_artifact(downstream["artifact_id"], status=impact_status)

    return {
        "source_artifact_id": source_artifact_id,
        "change_type": change_type,
        "impact_records": records,
    }


def mark_downstream_artifact_status(impact_id: str, status: str) -> Dict[str, Any]:
    if status not in IMPACT_STATUSES:
        raise ValueError("Unsupported impact status.")
    record = metadata_db.get_artifact_impact_record(impact_id)
    if not record:
        raise ValueError("Impact record not found.")
    updated = metadata_db.create_artifact_impact_record(
        impact_id=impact_id,
        project_id=record["project_id"],
        version_id=record["version_id"],
        source_artifact_id=record["source_artifact_id"],
        impacted_artifact_id=record["impacted_artifact_id"],
        impact_status=status,
        trigger_type=record["trigger_type"],
        trigger_ref_id=record.get("trigger_ref_id"),
        reason=f"Manually marked as {status}.",
        evidence=record.get("evidence") or {},
    )
    if status != "no_impact":
        metadata_db.update_design_artifact(record["impacted_artifact_id"], status=status)
    return updated


def list_impact_records(
    project_id: str,
    version_id: str,
    *,
    source_artifact_id: Optional[str] = None,
    impacted_artifact_id: Optional[str] = None,
    impact_status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    return metadata_db.list_artifact_impact_records(
        project_id=project_id,
        version_id=version_id,
        source_artifact_id=source_artifact_id,
        impacted_artifact_id=impacted_artifact_id,
        impact_status=impact_status,
    )
