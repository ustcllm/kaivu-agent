from __future__ import annotations

from typing import Any


def build_ai_artifact_contract(
    *,
    project_id: str = "",
    evaluation_protocol: dict[str, Any],
    training_recipe: dict[str, Any],
) -> dict[str, Any]:
    return {
        "contract_state": "draft",
        "project_id": project_id,
        "required_artifacts": [
            {
                "artifact_type": "dataset_profile",
                "path_pattern": "profiles/dataset_profile.json",
                "required_for": ["evaluation_design", "contamination_review"],
            },
            {
                "artifact_type": "evaluation_protocol",
                "path_pattern": "profiles/evaluation_protocol.json",
                "required_for": ["baseline", "claim_support"],
            },
            {
                "artifact_type": "training_config",
                "path_pattern": "experiments/{experiment_id}/config.json",
                "required_for": ["reproducibility", "comparison"],
            },
            {
                "artifact_type": "metrics",
                "path_pattern": "experiments/{experiment_id}/metrics.json",
                "required_for": ["scheduler_feedback", "claim_support"],
            },
            {
                "artifact_type": "runtime_manifest",
                "path_pattern": "experiments/{experiment_id}/runtime_manifest.json",
                "required_for": ["audit", "replay"],
            },
            {
                "artifact_type": "predictions_or_outputs",
                "path_pattern": "experiments/{experiment_id}/predictions.*",
                "required_for": ["error_analysis", "ensemble_or_comparison"],
            },
        ],
        "metadata_required": [
            "model_family",
            "dataset_version",
            "split_id",
            "metric",
            "seed",
            "environment",
            "code_version_or_hash",
        ],
        "metric": evaluation_protocol.get("primary_metric", ""),
        "candidate_models": training_recipe.get("candidate_models", []),
    }


