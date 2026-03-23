import argparse
import json
from collections import defaultdict
from pathlib import Path


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def _load_jsonl(path: Path) -> list[dict]:
    entries: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            entries.append(json.loads(line))
    return entries


def _node_family(node_id: str) -> str:
    if node_id == "planner":
        return "planner"
    if node_id.endswith("-final"):
        return f"{node_id[:-6]}:final"
    if "-react-step-" in node_id:
        return f"{node_id.split('-react-step-')[0]}:react"
    return node_id


def _format_row(row: dict) -> str:
    return (
        f"{row['node_id']:<32} "
        f"sys={row['system_prompt_tokens_est']:>6} "
        f"user={row['user_prompt_tokens_est']:>6} "
        f"total={row['total_prompt_tokens_est']:>6} "
        f"chars={row['total_prompt_chars']:>7}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit stored LLM prompt sizes for a project version.")
    parser.add_argument("project_id", help="Project ID, for example: test2")
    parser.add_argument("version", help="Version ID, for example: v20260323001814")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]), help="Workspace root")
    parser.add_argument("--top", type=int, default=12, help="How many largest interactions to show")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    log_path = root / "projects" / args.project_id / args.version / "logs" / "llm_interactions.jsonl"

    if not log_path.exists():
        print(f"Missing prompt log: {log_path}")
        print("Prompt audit requires LLM interaction logging to be enabled for the project.")
        print("Set project debug config:")
        print('  {"llm_interaction_logging_enabled": true, "llm_full_payload_logging_enabled": true}')
        print("Then rerun the version and rerun this script.")
        return 1

    entries = _load_jsonl(log_path)
    if not entries:
        print(f"No entries found in {log_path}")
        return 1

    normalized: list[dict] = []
    for entry in entries:
        sizes = entry.get("sizes") or {}
        system_chars = int(sizes.get("system_prompt_chars") or 0)
        user_chars = int(sizes.get("user_prompt_chars") or 0)
        system_tokens = int(sizes.get("system_prompt_tokens_est") or _estimate_tokens(""))
        user_tokens = int(sizes.get("user_prompt_tokens_est") or _estimate_tokens(""))
        node_id = str(entry.get("node_id") or "unknown")
        normalized.append(
            {
                "timestamp": entry.get("timestamp"),
                "node_id": node_id,
                "family": _node_family(node_id),
                "system_prompt_chars": system_chars,
                "user_prompt_chars": user_chars,
                "total_prompt_chars": system_chars + user_chars,
                "system_prompt_tokens_est": system_tokens,
                "user_prompt_tokens_est": user_tokens,
                "total_prompt_tokens_est": system_tokens + user_tokens,
                "status": entry.get("status"),
                "provider": entry.get("provider"),
                "model": entry.get("model"),
            }
        )

    normalized.sort(key=lambda item: item["total_prompt_tokens_est"], reverse=True)

    print(f"Prompt Audit: {args.project_id}/{args.version}")
    print(f"Source: {log_path}")
    print(f"Interactions: {len(normalized)}")
    print("")
    print("Largest individual interactions:")
    for row in normalized[: args.top]:
        print(_format_row(row))

    print("")
    print("Aggregated by node family:")
    family_stats: dict[str, dict] = defaultdict(lambda: {"count": 0, "total_tokens": 0, "max_tokens": 0, "total_chars": 0})
    for row in normalized:
        stats = family_stats[row["family"]]
        stats["count"] += 1
        stats["total_tokens"] += row["total_prompt_tokens_est"]
        stats["max_tokens"] = max(stats["max_tokens"], row["total_prompt_tokens_est"])
        stats["total_chars"] += row["total_prompt_chars"]

    ranked_families = sorted(family_stats.items(), key=lambda item: item[1]["total_tokens"], reverse=True)
    for family, stats in ranked_families:
        print(
            f"{family:<28} calls={stats['count']:>3} "
            f"total_tokens={stats['total_tokens']:>6} "
            f"max_tokens={stats['max_tokens']:>6} "
            f"total_chars={stats['total_chars']:>7}"
        )

    print("")
    print("Focused nodes:")
    focused = [row for row in normalized if row["node_id"].startswith("design-assembler") or row["node_id"].startswith("validator")]
    if focused:
        for row in focused:
            print(_format_row(row))
    else:
        print("No design-assembler or validator interactions found.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
