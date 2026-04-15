from __future__ import annotations

from typing import Any


def build_training_recipe(
    *,
    dataset_profile: dict[str, Any],
    evaluation_protocol: dict[str, Any],
    available_compute: str = "local_cpu",
    candidate_models: list[str] | None = None,
) -> dict[str, Any]:
    task = str(evaluation_protocol.get("task_type", "unspecified_ai_task"))
    models = candidate_models or _default_models(task=task, dataset_profile=dataset_profile, compute=available_compute)
    return {
        "recipe_state": "draft",
        "task_type": task,
        "available_compute": available_compute,
        "candidate_models": models,
        "baseline_recipe": _baseline_recipe(task=task, models=models),
        "training_controls": [
            "fixed random seed for initial baseline",
            "configuration snapshot for every run",
            "same split and preprocessing for comparable experiments",
            "persist out-of-fold predictions when supervised",
        ],
        "resource_policy": {
            "first_pass_budget": "small",
            "increase_budget_when": [
                "baseline is reproduced",
                "validation is trusted",
                "candidate has positive expected value",
            ],
            "stop_conditions": [
                "metric does not improve over baseline",
                "training is unstable",
                "quality-control gate fails",
            ],
        },
    }


def _default_models(*, task: str, dataset_profile: dict[str, Any], compute: str) -> list[str]:
    counts = dataset_profile.get("column_type_counts", {})
    has_tabular = bool(counts.get("numeric") or counts.get("categorical_or_text") or counts.get("high_cardinality_categorical_or_text"))
    if "llm" in task or "generation" in task:
        return ["prompt_baseline", "small_finetune", "retrieval_augmented_baseline"]
    if "classification" in task or "regression" in task:
        if has_tabular:
            return ["sklearn_baseline", "lightgbm", "catboost"]
        return ["sklearn_baseline", "small_mlp"]
    if "ranking" in task:
        return ["bm25_or_feature_baseline", "lightgbm_ranker"]
    return ["simple_baseline", "stronger_model_candidate"]


def _baseline_recipe(*, task: str, models: list[str]) -> dict[str, Any]:
    baseline = models[0] if models else "simple_baseline"
    return {
        "model": baseline,
        "feature_policy": "minimal clean features before feature search",
        "preprocessing": [
            "impute missing values",
            "encode categorical features fold-safely when needed",
            "standardize numeric features only for models that require it",
        ],
        "seed_policy": [42],
        "expected_outputs": ["metrics.json", "config.json", "runtime_manifest.json"],
    }


