from pathlib import Path
from typing import Dict, List, Optional

import yaml


class KnowledgeBaseError(RuntimeError):
    pass


def _load_yaml_file(path: Path):
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_knowledge_base(root_path: Path, includes: Optional[List[str]] = None) -> Dict[str, object]:
    if not root_path.exists():
        raise KnowledgeBaseError(f"Knowledge base path not found: {root_path}")

    include_paths = [root_path / name for name in (includes or [])]
    terminology_path = next((path for path in include_paths if "terminology" in path.name), root_path / "terminology.yaml")
    feature_tree_path = next((path for path in include_paths if "feature-tree" in path.name), root_path / "feature-tree.yaml")

    design_docs = []
    for path in root_path.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".md", ".markdown", ".yaml", ".yml", ".json", ".txt"}:
            continue
        if path.name in {terminology_path.name, feature_tree_path.name}:
            continue
        design_docs.append(path)

    return {
        "root_path": root_path,
        "terminology": _load_yaml_file(terminology_path) if terminology_path.exists() else {},
        "feature_tree": _load_yaml_file(feature_tree_path) if feature_tree_path.exists() else {},
        "design_docs": design_docs,
    }


def search_terms(index: Dict[str, object], keyword: str) -> List[Dict[str, object]]:
    terminology = index.get("terminology") or {}
    entries = terminology.get("terms") if isinstance(terminology, dict) else terminology
    entries = entries if isinstance(entries, list) else []
    keyword_lower = keyword.lower()
    matches = []
    for entry in entries:
        name = str(entry.get("term") or entry.get("name") or "")
        definition = str(entry.get("definition") or entry.get("description") or "")
        if keyword_lower in name.lower() or keyword_lower in definition.lower():
            matches.append(entry)
    return matches


def get_feature_tree(index: Dict[str, object]) -> Dict[str, object]:
    return index.get("feature_tree") or {}


def search_design_docs(index: Dict[str, object], keyword: str) -> List[Dict[str, object]]:
    keyword_lower = keyword.lower()
    matches: List[Dict[str, object]] = []
    for path in index.get("design_docs", []):
        content = Path(path).read_text(encoding="utf-8", errors="replace")
        lowered = content.lower()
        if keyword_lower not in lowered:
            continue
        line_hits = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            if keyword_lower in line.lower():
                line_hits.append({"line_number": line_number, "line": line.strip()})
            if len(line_hits) >= 5:
                break
        matches.append({"path": str(Path(path)), "matches": line_hits})
    return matches


def get_related_designs(index: Dict[str, object], feature_id: str) -> List[Dict[str, object]]:
    return search_design_docs(index, feature_id)
