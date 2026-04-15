from __future__ import annotations

from pathlib import Path
from typing import Any

from .data_inventory import scan_kaggle_data_dir
from .models import (
    CompetitionInfo,
    CompetitionResearchDossier,
    KaggleCommunityResearch,
    KaggleMethodLiteratureReview,
)


def build_competition_research_dossier(
    *,
    competition_name: str,
    data_dir: str,
    competition_url: str = "",
    target_column: str = "",
    id_column: str = "",
    metric: str = "",
    task_type: str = "",
    context_pack: dict[str, Any] | None = None,
    prior_memory: dict[str, Any] | None = None,
    constraints: dict[str, Any] | None = None,
) -> CompetitionResearchDossier:
    inventory = scan_kaggle_data_dir(data_dir)
    local_description = _read_local_description(Path(data_dir).resolve())
    resolved_target = target_column or inventory.inferred_target_column
    resolved_id = id_column or inventory.inferred_id_column
    resolved_task = _resolve_modeling_task_type(task_type, inventory.inferred_task_type)
    resolved_metric = metric or _default_metric(resolved_task)
    competition_info = CompetitionInfo(
        competition_name=competition_name,
        competition_url=competition_url,
        overview=local_description[:3000],
        metric=resolved_metric,
        metric_direction=_metric_direction(resolved_metric),
        task_type=resolved_task,
        target_column=resolved_target,
        id_column=resolved_id,
        submission_format=_submission_format(inventory, id_column=resolved_id, target_column=resolved_target),
        rules_summary={
            "source": "user_or_local_inference",
            "internet_allowed": bool((constraints or {}).get("internet_allowed", False)),
            "external_data_allowed": bool((constraints or {}).get("external_data_allowed", False)),
            "submission_budget": int((constraints or {}).get("submission_budget", 3) or 3),
        },
        confidence="medium" if inventory.inventory_state == "scanned" else "low",
    )
    method_review = _method_review_for_task(resolved_task, metric=resolved_metric)
    community = _community_research_from_context(context_pack or {})
    open_questions = _open_questions(competition_info, inventory)
    return CompetitionResearchDossier(
        competition_info=competition_info,
        data_inventory=inventory,
        community_research=community,
        method_literature_review=method_review,
        prior_kaggle_memory=prior_memory or {},
        context_pack=context_pack or {},
        open_questions=open_questions,
        confidence="medium" if not open_questions else "medium_with_open_questions",
    )


def _read_local_description(data_dir: Path) -> str:
    for name in ["competition.md", "README.md", "description.md"]:
        path = data_dir / name
        if path.exists():
            try:
                return path.read_text(encoding="utf-8")
            except Exception:
                return ""
    return ""


def _default_metric(task_type: str) -> str:
    lowered = task_type.lower()
    if "classification" in lowered:
        return "accuracy"
    if "regression" in lowered:
        return "rmse"
    if "ranking" in lowered:
        return "map@k"
    return "competition_metric_unspecified"


def _resolve_modeling_task_type(route_task_type: str, inferred_task_type: str) -> str:
    route = route_task_type.strip()
    if route.lower() in {"", "kaggle_competition", "kaggle", "competition"}:
        return inferred_task_type or "tabular_supervised"
    return route


def _metric_direction(metric: str) -> str:
    lowered = metric.lower()
    if lowered in {"rmse", "mse", "mae", "logloss", "loss"}:
        return "minimize"
    return "maximize"


def _submission_format(inventory: Any, *, id_column: str, target_column: str) -> dict[str, Any]:
    sample = next(
        (
            item
            for item in inventory.files
            if str(item.get("path", "")) == inventory.detected_sample_submission
        ),
        {},
    )
    columns = sample.get("columns", []) if isinstance(sample.get("columns", []), list) else []
    return {
        "sample_submission_file": inventory.detected_sample_submission,
        "columns": columns or [id_column, target_column],
        "id_column": id_column,
        "prediction_column": target_column,
    }


def _method_review_for_task(task_type: str, *, metric: str) -> KaggleMethodLiteratureReview:
    lowered = task_type.lower()
    if "tabular" in lowered:
        methods = [
            {"method": "sklearn_linear_or_tree_baseline", "reason": "fast sanity-check pipeline"},
            {"method": "LightGBM_or_HistGradientBoosting", "reason": "strong default for tabular supervised data"},
            {"method": "CatBoost", "reason": "useful when high-cardinality categoricals are present"},
        ]
        risks = [
            {"method": "target_encoding", "risk": "must be fold-aware to avoid leakage"},
            {"method": "public_leaderboard_tuning", "risk": "can overfit public leaderboard"},
        ]
    else:
        methods = [{"method": "simple_baseline_first", "reason": "validate end-to-end metric and submission"}]
        risks = [{"method": "complex_model_first", "risk": "can hide data, metric, or submission bugs"}]
    return KaggleMethodLiteratureReview(
        recommended_methods=methods,
        method_risks=risks,
        transferable_principles=[
            "Establish trustworthy local validation before optimizing leaderboard score",
            f"Optimize the official metric `{metric}` with a frozen validation protocol",
            "Record every failed attempt as reusable negative knowledge",
            "Use OOF predictions before stacking or blending",
        ],
    )


def _community_research_from_context(context_pack: dict[str, Any]) -> KaggleCommunityResearch:
    memory_items = context_pack.get("memory_items", []) if isinstance(context_pack.get("memory_items", []), list) else []
    literature_items = context_pack.get("literature_items", []) if isinstance(context_pack.get("literature_items", []), list) else []
    failed = context_pack.get("failed_attempt_items", []) if isinstance(context_pack.get("failed_attempt_items", []), list) else []
    return KaggleCommunityResearch(
        discussion_findings=[
            {"claim": str(item.get("summary", "")), "source": str(item.get("source_path", "")), "confidence": "medium"}
            for item in memory_items[:5]
            if isinstance(item, dict)
        ],
        notebook_patterns=[
            {"pattern": str(item.get("summary", "")), "source": str(item.get("source_path", ""))}
            for item in literature_items[:5]
            if isinstance(item, dict)
        ],
        anti_patterns=[
            {"pattern": str(item.get("summary", "")), "reason": "prior failed attempt"}
            for item in failed[:5]
            if isinstance(item, dict)
        ],
        source_refs=[
            str(item.get("source_path", ""))
            for item in [*memory_items, *literature_items, *failed]
            if isinstance(item, dict) and str(item.get("source_path", "")).strip()
        ],
    )


def _open_questions(info: CompetitionInfo, inventory: Any) -> list[str]:
    questions: list[str] = []
    if not info.metric or info.metric == "competition_metric_unspecified":
        questions.append("Official metric is not confirmed")
    if not info.target_column:
        questions.append("Target column is not confirmed")
    if not info.id_column:
        questions.append("Submission id column is not confirmed")
    if not inventory.detected_sample_submission:
        questions.append("Sample submission file is missing")
    return questions


