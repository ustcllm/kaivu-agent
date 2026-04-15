from __future__ import annotations

from typing import Any


def safe_float(value: Any) -> float:
    """Best-effort float conversion for heterogeneous model/runtime metadata."""
    try:
        return float(value)
    except Exception:
        return 0.0


def context_string(context: dict[str, Any], key: str) -> str:
    value = context.get(key)
    return str(value).strip() if value is not None else ""


def context_list(context: dict[str, Any], key: str) -> list[str]:
    value = context.get(key)
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def context_dict(context: dict[str, Any], key: str) -> dict[str, Any]:
    value = context.get(key)
    return value if isinstance(value, dict) else {}


def collect_research_state_inputs(steps: list[Any]) -> dict[str, Any]:
    stage_counts: dict[str, int] = {}
    blockers: list[str] = []
    open_questions: list[str] = []
    active_hypotheses: list[dict[str, Any]] = []
    negative_results: list[dict[str, Any]] = []
    evidence_strengths: list[str] = []
    evidence_quality_grades: list[str] = []
    conflict_groups: dict[str, list[dict[str, Any]]] = {}
    experiment_runs: list[dict[str, Any]] = []
    quality_control_reviews: list[dict[str, Any]] = []
    interpretation_records: list[dict[str, Any]] = []

    for step in steps:
        parsed = step.parsed_output
        stage = parsed.get("stage_assessment", {})
        if isinstance(stage, dict):
            current = str(stage.get("current_stage", "")).strip()
            if current:
                stage_counts[current] = stage_counts.get(current, 0) + 1
            for blocker in stage.get("stage_blockers", []) if isinstance(stage.get("stage_blockers", []), list) else []:
                if blocker:
                    blockers.append(str(blocker))
        for question in parsed.get("open_questions", []) if isinstance(parsed.get("open_questions", []), list) else []:
            if question:
                open_questions.append(str(question))
        for item in parsed.get("hypotheses", []) if isinstance(parsed.get("hypotheses", []), list) else []:
            if isinstance(item, dict):
                active_hypotheses.append(item)
        for item in parsed.get("negative_results", []) if isinstance(parsed.get("negative_results", []), list) else []:
            if isinstance(item, dict):
                negative_results.append(item)
        for evidence in parsed.get("evidence", []) if isinstance(parsed.get("evidence", []), list) else []:
            if isinstance(evidence, dict):
                strength = str(evidence.get("strength", "")).strip()
                if strength:
                    evidence_strengths.append(strength)
                quality_grade = str(evidence.get("quality_grade", "")).strip().lower()
                if quality_grade:
                    evidence_quality_grades.append(quality_grade)
                conflict_group = str(evidence.get("conflict_group", "")).strip()
                if conflict_group:
                    conflict_groups.setdefault(conflict_group, []).append(evidence)
        run_payload = parsed.get("experiment_run", {})
        if isinstance(run_payload, dict) and run_payload:
            experiment_runs.append(run_payload)
        quality_payload = parsed.get("quality_control_review", {})
        if isinstance(quality_payload, dict) and quality_payload:
            quality_control_reviews.append(quality_payload)
        interpretation_payload = parsed.get("interpretation_record", {})
        if isinstance(interpretation_payload, dict) and interpretation_payload:
            interpretation_records.append(interpretation_payload)

    return {
        "stage_counts": stage_counts,
        "blockers": blockers,
        "open_questions": open_questions,
        "active_hypotheses": active_hypotheses,
        "negative_results": negative_results,
        "evidence_strengths": evidence_strengths,
        "evidence_quality_grades": evidence_quality_grades,
        "conflict_groups": conflict_groups,
        "experiment_runs": experiment_runs,
        "quality_control_reviews": quality_control_reviews,
        "interpretation_records": interpretation_records,
    }


__all__ = [
    "collect_research_state_inputs",
    "context_dict",
    "context_list",
    "context_string",
    "safe_float",
]
