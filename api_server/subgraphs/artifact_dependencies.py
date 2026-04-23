"""Artifact dependency helpers for dynamic subagents."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from registry.expert_runtime_profile import ExpertRuntimeProfile


UPSTREAM_ARTIFACT_MAPPING_FALLBACK: dict[str, dict[str, list[str]]] = {
    "config-design": {
        "modular-design": ["architecture.md", "module-map.json"],
    },
    "data-design": {
        "modular-design": ["architecture.md", "module-map.json"],
    },
    "ddd-structure": {
        "data-design": ["schema.sql", "er.md", "migration-plan.md"],
    },
    "api-design": {
        "modular-design": ["architecture.md", "module-map.json"],
        "data-design": ["schema.sql", "er.md", "migration-plan.md"],
        "ddd-structure": ["class-diagram.md", "ddd-structure.md", "context-map.md"],
    },
    "flow-design": {
        "modular-design": ["architecture.md", "module-map.json"],
    },
    "integration-design": {
        "modular-design": ["architecture.md", "module-map.json"],
    },
    "ops-design": {
        "config-design": ["config-catalog.yaml", "config-matrix.md"],
    },
    "test-design": {
        "flow-design": ["sequence.md", "state.md"],
        "api-design": ["api-design.md", "errors-rfc9457.json"],
        "integration-design": ["integration.md", "asyncapi.yaml"],
        "ops-design": ["slo.yaml", "observability-spec.yaml", "deployment-runbook.md"],
    },
    "validator": {
        "design-assembler": ["detailed-design.md", "implementation-plan.json", "traceability.json", "review-checklist.md"],
    },
}


def get_upstream_artifact_mapping(
    profiles: dict[str, ExpertRuntimeProfile] | None = None,
) -> dict[str, dict[str, list[str]]]:
    merged: dict[str, dict[str, list[str]]] = {
        capability: dict(mapping)
        for capability, mapping in UPSTREAM_ARTIFACT_MAPPING_FALLBACK.items()
    }

    if profiles:
        for capability, profile in profiles.items():
            if profile.upstream_artifacts:
                merged[capability] = dict(profile.upstream_artifacts)
        if merged:
            return merged

    try:
        from registry.expert_registry import ExpertRegistry

        registry = ExpertRegistry.get_instance()
        result: dict[str, dict[str, list[str]]] = {}
        for manifest in registry.get_all_manifests():
            if manifest.upstream_artifacts:
                result[manifest.capability] = manifest.upstream_artifacts
        return {**merged, **result} if result else merged
    except RuntimeError:
        return merged


def discover_upstream_artifacts(
    capability: str,
    artifacts_dir: Path,
    mapping: dict[str, dict[str, list[str]]] | None = None,
) -> dict[str, list[str]]:
    upstream_map = (mapping or get_upstream_artifact_mapping()).get(capability, {})
    if not upstream_map or not artifacts_dir.exists():
        return {}

    existing_files = {item.name for item in artifacts_dir.iterdir() if item.is_file()}
    discovered: dict[str, list[str]] = {}
    for upstream_agent, expected_files in upstream_map.items():
        found = [file_name for file_name in expected_files if file_name in existing_files]
        if found:
            discovered[upstream_agent] = found
    return discovered

