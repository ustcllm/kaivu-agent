from __future__ import annotations

from typing import Any

from .models import KaggleExperimentCandidate, KaggleTaskAdapterInput, KaggleTaskAdapterOutput, SubmissionPlan, ValidationProtocol


class KaggleResearchDossierAdapter:
    def adapt(self, data: KaggleTaskAdapterInput | dict[str, Any]) -> KaggleTaskAdapterOutput:
        request = data if isinstance(data, KaggleTaskAdapterInput) else KaggleTaskAdapterInput(**data)
        dossier = request.dossier
        competition_info = _dict(dossier.get("competition_info", {}))
        inventory = _dict(dossier.get("data_inventory", {}))
        method_review = _dict(dossier.get("method_literature_review", {}))
        metric = request.metric or str(competition_info.get("metric", ""))
        task_type = _resolve_modeling_task_type(request.task_type, str(competition_info.get("task_type", "")))
        target_column = request.target_column or str(competition_info.get("target_column", ""))
        id_column = request.id_column or str(competition_info.get("id_column", ""))
        validation = _build_validation_protocol(
            competition_name=request.competition_name,
            task_type=task_type,
            metric=metric,
            metric_direction=str(competition_info.get("metric_direction", "")),
            inventory=inventory,
        )
        leakage_report = _build_leakage_report(
            inventory=inventory,
            target_column=target_column,
            id_column=id_column,
            validation=validation,
        )
        hypotheses = _build_modeling_hypotheses(
            task_type=task_type,
            metric=metric,
            method_review=method_review,
            leakage_report=leakage_report,
        )
        candidates = _build_experiment_candidates(
            competition_name=request.competition_name,
            hypotheses=hypotheses,
            validation=validation,
            leakage_report=leakage_report,
            work_dir=str(request.resolved_work_dir(".")),
        )
        submission = _build_submission_plan(
            competition_info=competition_info,
            leakage_report=leakage_report,
            constraints=request.constraints,
        )
        return KaggleTaskAdapterOutput(
            competition_spec={
                **competition_info,
                "adapter_state": "ready",
                "competition_name": request.competition_name,
                "competition_url": request.competition_url or competition_info.get("competition_url", ""),
            },
            dataset_profile={
                "profile_state": inventory.get("inventory_state", "draft"),
                "data_dir": inventory.get("data_dir", request.data_dir),
                "train_file": inventory.get("detected_train_file", ""),
                "test_file": inventory.get("detected_test_file", ""),
                "sample_submission_file": inventory.get("detected_sample_submission", ""),
                "target_column": target_column,
                "id_column": id_column,
                "task_type": task_type,
                "file_count": len(inventory.get("files", []) if isinstance(inventory.get("files", []), list) else []),
                "warnings": inventory.get("warnings", []),
            },
            leakage_report=leakage_report,
            validation_protocol=validation.to_dict(),
            modeling_hypotheses=hypotheses,
            experiment_candidates=[candidate.to_dict() for candidate in candidates],
            execution_plan=_build_execution_plan(candidates, request),
            submission_plan=submission.to_dict(),
            memory_items=_build_memory_items(request, leakage_report, validation, candidates),
            graph_facts=_build_graph_facts(request, target_column, candidates),
            learning_metadata={
                "task_adapter": "kaggle",
                "observation_only": True,
                "competition_name": request.competition_name,
                "candidate_count": len(candidates),
                "leakage_risk": leakage_report.get("overall_risk", "medium"),
                "submission_governance_enabled": True,
            },
        )


def _build_validation_protocol(
    *,
    competition_name: str,
    task_type: str,
    metric: str,
    metric_direction: str,
    inventory: dict[str, Any],
) -> ValidationProtocol:
    lowered = task_type.lower()
    columns = _train_columns(inventory)
    time_column = next((column for column in columns if any(token in column.lower() for token in ["date", "time", "timestamp"])), "")
    group_column = next((column for column in columns if "group" in column.lower()), "")
    if time_column:
        split = "time_series_split"
        rationale = "Detected time-like column; prefer leakage-safe chronological validation."
    elif group_column:
        split = "group_k_fold"
        rationale = "Detected group-like column; prevent group leakage across folds."
    elif "classification" in lowered:
        split = "stratified_k_fold"
        rationale = "Classification task should preserve target distribution across folds."
    else:
        split = "k_fold"
        rationale = "Default tabular validation protocol for supervised competition."
    return ValidationProtocol(
        protocol_id=f"kaggle-validation::{_slugify(competition_name)}",
        split_strategy=split,
        folds=5,
        metric=metric,
        metric_direction=metric_direction,
        group_column=group_column,
        time_column=time_column,
        leakage_guards=[
            "fit preprocessing inside each fold",
            "never tune using public leaderboard as validation",
            "keep OOF predictions for ensemble and diagnostics",
            "validate submission format before submitting",
        ],
        rationale=rationale,
    )


def _build_leakage_report(
    *,
    inventory: dict[str, Any],
    target_column: str,
    id_column: str,
    validation: ValidationProtocol,
) -> dict[str, Any]:
    columns = _train_columns(inventory)
    suspicious = [
        column
        for column in columns
        if column != target_column
        and any(token in column.lower() for token in ["target", "label", "leak", "future", "fold", "prediction"])
    ]
    if id_column and id_column in columns:
        suspicious.append(id_column)
    risk = "high" if any("future" in column.lower() or "leak" in column.lower() for column in suspicious) else "medium" if suspicious else "low"
    return {
        "report_state": "draft_static_audit",
        "overall_risk": risk,
        "suspicious_columns": sorted(set(suspicious)),
        "validation_split_risk": "low" if validation.split_strategy in {"time_series_split", "group_k_fold", "stratified_k_fold"} else "medium",
        "public_leaderboard_overfit_risk": "medium",
        "required_checks": [
            "train-test column parity check",
            "duplicate row and id leakage check",
            "adversarial validation if train/test shift is suspected",
            "fold-aware encoding for target/statistical encoders",
        ],
    }


def _build_modeling_hypotheses(
    *,
    task_type: str,
    metric: str,
    method_review: dict[str, Any],
    leakage_report: dict[str, Any],
) -> list[dict[str, Any]]:
    methods = method_review.get("recommended_methods", []) if isinstance(method_review.get("recommended_methods", []), list) else []
    hypotheses = [
        {
            "hypothesis_id": "kaggle-hyp-baseline-valid-pipeline",
            "statement": "A simple baseline can establish a valid metric, split, and submission pipeline.",
            "test": "Run a fast baseline and verify CV plus submission format.",
            "risk": "low",
        }
    ]
    for index, method in enumerate(methods[:4], start=1):
        if not isinstance(method, dict):
            continue
        name = str(method.get("method", f"method-{index}"))
        hypotheses.append(
            {
                "hypothesis_id": f"kaggle-hyp-{_slugify(name)}",
                "statement": f"{name} improves `{metric}` for task `{task_type}`.",
                "test": f"Compare {name} against the frozen baseline using the same validation protocol.",
                "risk": leakage_report.get("overall_risk", "medium") if "encoding" in name.lower() else "medium",
            }
        )
    return hypotheses


def _build_experiment_candidates(
    *,
    competition_name: str,
    hypotheses: list[dict[str, Any]],
    validation: ValidationProtocol,
    leakage_report: dict[str, Any],
    work_dir: str,
) -> list[KaggleExperimentCandidate]:
    candidates: list[KaggleExperimentCandidate] = []
    for index, hypothesis in enumerate(hypotheses, start=1):
        model_family = "sklearn_baseline" if index == 1 else _model_from_hypothesis(str(hypothesis.get("statement", "")))
        candidates.append(
            KaggleExperimentCandidate(
                experiment_id=f"kaggle-{_slugify(competition_name)}-exp-{index:03d}",
                title=str(hypothesis.get("statement", ""))[:120],
                hypothesis=str(hypothesis.get("statement", "")),
                model_family=model_family,
                priority="high" if index == 1 else "medium",
                expected_cv_gain=0.0 if index == 1 else 0.02,
                estimated_cost=1.0 if index == 1 else 2.0,
                leakage_risk=str(leakage_report.get("overall_risk", "medium")),
                leaderboard_overfit_risk=str(leakage_report.get("public_leaderboard_overfit_risk", "medium")),
                search_space={
                    "validation_protocol": validation.to_dict(),
                    "artifact_root": work_dir,
                    "seed": 42,
                    "model_family": model_family,
                },
                success_criteria=[
                    "CV metric is computed with frozen split",
                    "OOF or validation predictions are saved when applicable",
                    "submission format validates against sample submission",
                ],
                failure_criteria=[
                    "leakage is detected",
                    "CV cannot be reproduced",
                    "submission columns or row count are invalid",
                ],
            )
        )
    return candidates


def _build_submission_plan(
    *,
    competition_info: dict[str, Any],
    leakage_report: dict[str, Any],
    constraints: dict[str, Any],
) -> SubmissionPlan:
    risk = str(leakage_report.get("public_leaderboard_overfit_risk", "medium"))
    budget = int(constraints.get("submission_budget", competition_info.get("rules_summary", {}).get("submission_budget", 3)) or 3)
    return SubmissionPlan(
        should_submit=budget > 0,
        max_submissions_this_cycle=min(1, budget),
        public_leaderboard_overfit_risk=risk,
        rationale="Submit only after local CV and submission format checks pass.",
    )


def _build_execution_plan(candidates: list[KaggleExperimentCandidate], request: KaggleTaskAdapterInput) -> dict[str, Any]:
    return {
        "execution_state": "planned",
        "work_dir": str(request.resolved_work_dir(".")),
        "data_dir": request.data_dir,
        "candidate_count": len(candidates),
        "first_action": candidates[0].action if candidates else "inspect_data",
        "executor_kind": "kaggle_training_executor_scaffold",
        "requires_approval_before_submission": True,
    }


def _build_memory_items(
    request: KaggleTaskAdapterInput,
    leakage_report: dict[str, Any],
    validation: ValidationProtocol,
    candidates: list[KaggleExperimentCandidate],
) -> list[dict[str, Any]]:
    return [
        {
            "title": f"Kaggle competition setup: {request.competition_name}",
            "summary": f"metric={request.metric or 'inferred'}; validation={validation.split_strategy}; candidates={len(candidates)}",
            "memory_type": "decision",
            "scope": "project",
            "content": f"Competition `{request.competition_name}` is configured for Kaggle workflow with validation `{validation.split_strategy}`.",
            "tags": ["kaggle", "competition-setup", "validation"],
        },
        {
            "title": f"Kaggle leakage audit: {request.competition_name}",
            "summary": f"overall_risk={leakage_report.get('overall_risk', 'medium')}",
            "memory_type": "warning",
            "scope": "project",
            "content": str(leakage_report),
            "tags": ["kaggle", "leakage", "quality-control"],
        },
    ]


def _build_graph_facts(request: KaggleTaskAdapterInput, target_column: str, candidates: list[KaggleExperimentCandidate]) -> list[dict[str, Any]]:
    facts = [
        {
            "subject": f"competition::{request.competition_name}",
            "predicate": "has_target",
            "object": target_column,
        }
    ]
    for candidate in candidates:
        facts.append(
            {
                "subject": f"competition::{request.competition_name}",
                "predicate": "has_experiment_candidate",
                "object": candidate.experiment_id,
            }
        )
    return facts


def _train_columns(inventory: dict[str, Any]) -> list[str]:
    train_file = str(inventory.get("detected_train_file", ""))
    for item in inventory.get("files", []) if isinstance(inventory.get("files", []), list) else []:
        if isinstance(item, dict) and str(item.get("path", "")) == train_file:
            columns = item.get("columns", [])
            return [str(column) for column in columns] if isinstance(columns, list) else []
    return []


def _model_from_hypothesis(statement: str) -> str:
    lowered = statement.lower()
    if "catboost" in lowered:
        return "catboost"
    if "lightgbm" in lowered or "gradient" in lowered:
        return "gradient_boosting"
    return "sklearn_baseline"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _resolve_modeling_task_type(route_task_type: str, dossier_task_type: str) -> str:
    route = route_task_type.strip()
    if route.lower() in {"", "kaggle_competition", "kaggle", "competition"}:
        return dossier_task_type
    return route


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value).strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "kaggle"


