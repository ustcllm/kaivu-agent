from __future__ import annotations

from typing import Any


def build_evaluation_protocol(
    *,
    research_question: str,
    dataset_profile: dict[str, Any],
    contamination_risk_report: dict[str, Any],
    task_type: str = "",
    metric: str = "",
    metric_direction: str = "",
) -> dict[str, Any]:
    task = _infer_task_type(task_type=task_type, dataset_profile=dataset_profile)
    metric_name, direction = _infer_metric(task=task, metric=metric, metric_direction=metric_direction)
    split = _split_strategy(dataset_profile=dataset_profile, contamination_risk_report=contamination_risk_report, task=task)
    return {
        "protocol_state": "draft",
        "research_question": research_question,
        "task_type": task,
        "primary_metric": metric_name,
        "metric_direction": direction,
        "split_strategy": split,
        "baseline_requirements": [
            "simple reproducible baseline before advanced modeling",
            "frozen validation split before optimization",
            "same preprocessing path for baseline and candidate models",
        ],
        "statistical_checks": [
            "multi-seed replication for stochastic methods",
            "confidence interval or paired comparison when feasible",
            "report variance before claiming small gains",
        ],
        "claim_rules": [
            "exploratory validation can prioritize candidates but cannot finalize a claim",
            "confirmatory holdout or locked benchmark is required for strong claims",
            "quality-control failure blocks metric-based belief upgrade",
        ],
    }


def _infer_task_type(*, task_type: str, dataset_profile: dict[str, Any]) -> str:
    if task_type:
        return task_type
    target = str(dataset_profile.get("target_column", "")).strip()
    for item in dataset_profile.get("columns", []):
        if not isinstance(item, dict) or item.get("name") != target:
            continue
        unique_count = int(item.get("unique_count_sample", 0))
        if 2 <= unique_count <= 20:
            return "classification"
        return "regression"
    return "unspecified_ai_task"


def _infer_metric(*, task: str, metric: str, metric_direction: str) -> tuple[str, str]:
    if metric:
        return metric, metric_direction or _default_direction(metric)
    if "classification" in task:
        return "log_loss_or_auc", "minimize_or_maximize_by_metric_definition"
    if "regression" in task:
        return "rmse", "minimize"
    if "ranking" in task:
        return "ndcg_or_map", "maximize"
    if "generation" in task or "llm" in task:
        return "task_specific_eval_score", "maximize"
    return "primary_task_metric", "maximize"


def _default_direction(metric: str) -> str:
    lowered = metric.lower()
    if any(token in lowered for token in ("loss", "error", "rmse", "mae", "mse", "wer")):
        return "minimize"
    return "maximize"


def _split_strategy(
    *,
    dataset_profile: dict[str, Any],
    contamination_risk_report: dict[str, Any],
    task: str,
) -> dict[str, Any]:
    names = [str(item.get("name", "")).lower() for item in dataset_profile.get("columns", []) if isinstance(item, dict)]
    if any(any(token in name for token in ("date", "time", "timestamp")) for name in names):
        method = "time_series_split_or_forward_validation"
        rationale = "time-like columns suggest future leakage risk"
    elif any(risk.get("risk_type") in {"duplicate_leakage", "identifier_leakage"} for risk in contamination_risk_report.get("risks", [])):
        method = "group_kfold_or_group_holdout"
        rationale = "identifier or duplicate risk suggests entity-level grouping"
    elif "classification" in task:
        method = "stratified_kfold"
        rationale = "classification target should preserve label distribution"
    else:
        method = "kfold_with_locked_holdout"
        rationale = "default reproducible split for AI experiments"
    return {
        "method": method,
        "folds": 5,
        "locked_holdout_required": True,
        "rationale": rationale,
    }


