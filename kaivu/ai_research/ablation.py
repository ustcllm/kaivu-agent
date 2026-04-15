from __future__ import annotations

from typing import Any


def build_ablation_plan(
    *,
    training_recipe: dict[str, Any],
    evaluation_protocol: dict[str, Any],
) -> dict[str, Any]:
    candidates = list(training_recipe.get("candidate_models", []))
    baseline = str(training_recipe.get("baseline_recipe", {}).get("model", candidates[0] if candidates else "baseline"))
    experiments: list[dict[str, Any]] = [
        {
            "ablation_id": "abl_000_baseline",
            "change": "none",
            "model": baseline,
            "purpose": "establish reproducible baseline",
            "control_rule": "all future experiments compare against this frozen baseline",
        }
    ]
    for index, model in enumerate(candidates[1:4], start=1):
        experiments.append(
            {
                "ablation_id": f"abl_{index:03d}_model_family",
                "change": f"switch model family to {model}",
                "model": model,
                "purpose": "test whether model family explains performance gain",
                "control_rule": "keep split, features, metric, and budget fixed",
            }
        )
    experiments.extend(
        [
            {
                "ablation_id": "abl_feature_minimal_vs_engineered",
                "change": "add engineered feature set",
                "purpose": "measure feature contribution independently of model family",
                "control_rule": "use same model and split as baseline",
            },
            {
                "ablation_id": "abl_seed_variance",
                "change": "repeat best candidate across seeds",
                "purpose": "estimate robustness and avoid single-seed overclaiming",
                "control_rule": "only run after a candidate beats baseline",
            },
        ]
    )
    return {
        "plan_state": "draft",
        "primary_metric": evaluation_protocol.get("primary_metric", ""),
        "ablation_count": len(experiments),
        "experiments": experiments,
        "interpretation_rules": [
            "do not attribute gain when more than one factor changed",
            "small gains require seed variance review",
            "failed ablations enter failed-attempt memory with tested condition",
        ],
    }


