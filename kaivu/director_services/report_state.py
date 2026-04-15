from __future__ import annotations

from datetime import datetime, timezone
import platform
import sys
from pathlib import Path
from typing import Any


def collect_execution_records(steps: list[Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for step in steps:
        raw_records = step.state.scratchpad.get("execution_records", [])
        if not isinstance(raw_records, list):
            continue
        for record in raw_records:
            if isinstance(record, dict):
                tagged = dict(record)
                tagged.setdefault("profile_name", step.profile_name)
                tagged.setdefault("model_meta", step.model_meta)
                records.append(tagged)
    return records


def collect_usage_summary(steps: list[Any]) -> dict[str, Any]:
    by_profile: list[dict[str, Any]] = []
    total = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "estimated_cost_usd": 0.0,
        "rounds": 0,
    }
    for step in steps:
        usage_totals = step.state.scratchpad.get("model_usage_totals", {})
        if not isinstance(usage_totals, dict):
            continue
        profile_summary = {
            "profile_name": step.profile_name,
            "model": step.model_meta.get("model", "unknown"),
            "input_tokens": int(usage_totals.get("input_tokens", 0)),
            "output_tokens": int(usage_totals.get("output_tokens", 0)),
            "total_tokens": int(usage_totals.get("total_tokens", 0)),
            "estimated_cost_usd": round(float(usage_totals.get("estimated_cost_usd", 0.0)), 6),
            "rounds": int(usage_totals.get("rounds", 0)),
        }
        by_profile.append(profile_summary)
        total["input_tokens"] += profile_summary["input_tokens"]
        total["output_tokens"] += profile_summary["output_tokens"]
        total["total_tokens"] += profile_summary["total_tokens"]
        total["estimated_cost_usd"] = round(
            total["estimated_cost_usd"] + profile_summary["estimated_cost_usd"],
            6,
        )
        total["rounds"] += profile_summary["rounds"]
    return {"by_profile": by_profile, "total": total}


def build_run_manifest(
    *,
    topic: str,
    steps: list[Any],
    execution_records: list[dict[str, Any]],
    usage_summary: dict[str, Any],
    report_path: Path,
    cwd: Path,
    collaboration_context: dict[str, Any],
) -> dict[str, Any]:
    input_files: dict[str, dict[str, Any]] = {}
    artifacts: dict[str, dict[str, Any]] = {}
    seeds: list[int] = []
    tools_used: list[str] = []
    models_used: list[dict[str, Any]] = []

    for step in steps:
        models_used.append(
            {
                "profile_name": step.profile_name,
                **step.model_meta,
            }
        )

    for record in execution_records:
        tool_name = str(record.get("tool_name", "")).strip()
        if tool_name:
            tools_used.append(tool_name)
        inputs = record.get("inputs", {})
        if isinstance(inputs, dict):
            seed = inputs.get("seed")
            if isinstance(seed, int):
                seeds.append(seed)
            for item in inputs.get("file_inputs", []):
                if isinstance(item, dict) and item.get("path"):
                    input_files[str(item["path"])] = item
        for item in record.get("artifacts", []):
            if isinstance(item, dict) and item.get("path"):
                artifacts[str(item["path"])] = item

    report_artifact = {
        "path": str(report_path),
        "kind": "report",
        "exists": False,
        "scope": "artifact",
    }
    artifacts[str(report_path)] = report_artifact

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "topic": topic,
        "cwd": str(cwd),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "collaboration_context": collaboration_context,
        "tools_used": sorted(set(tools_used)),
        "models_used": models_used,
        "input_files": list(input_files.values()),
        "artifacts": list(artifacts.values()),
        "seeds": sorted(set(seeds)),
        "usage_summary": usage_summary,
    }


__all__ = [
    "build_run_manifest",
    "collect_execution_records",
    "collect_usage_summary",
]
