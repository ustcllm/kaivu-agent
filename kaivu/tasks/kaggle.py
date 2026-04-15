from __future__ import annotations

from typing import Any

from ..ai_research.kaggle import KaggleResearchDossierAdapter
from ..ai_research.kaggle import KaggleTaskAdapterInput
from .base import ScientificTask, TaskAdapterResult


class KaggleTaskAdapter:
    """Normalize Kaggle competitions into the shared scientific task contract."""

    task_type = "kaggle_competition"
    discipline = "artificial_intelligence"

    def __init__(self, dossier_adapter: KaggleResearchDossierAdapter | None = None) -> None:
        self.dossier_adapter = dossier_adapter or KaggleResearchDossierAdapter()

    def adapt(self, data: KaggleTaskAdapterInput | dict[str, Any]) -> TaskAdapterResult:
        request = data if isinstance(data, KaggleTaskAdapterInput) else KaggleTaskAdapterInput(**data)
        adapted = self.dossier_adapter.adapt(request)
        task = ScientificTask(
            task_id=f"kaggle::{request.competition_name or 'competition'}",
            task_type=self.task_type,
            topic=request.competition_name or request.competition_url or "Kaggle competition",
            discipline=self.discipline,
            problem_statement=str(adapted.competition_spec.get("objective", "")).strip()
            or request.competition_name
            or "Kaggle competition modeling task",
            constraints=request.constraints,
            inputs={
                "competition_name": request.competition_name,
                "competition_url": request.competition_url,
                "data_dir": request.data_dir,
                "target_column": adapted.dataset_profile.get("target_column", ""),
                "id_column": adapted.dataset_profile.get("id_column", ""),
                "metric": request.metric or adapted.competition_spec.get("metric", ""),
                "dataset_profile": adapted.dataset_profile,
                "validation_protocol": adapted.validation_protocol,
                "leakage_report": adapted.leakage_report,
            },
            expected_outputs={
                "experiment_candidates": adapted.experiment_candidates,
                "submission_plan": adapted.submission_plan,
                "execution_plan": adapted.execution_plan,
            },
            environment={
                "kind": "kaggle",
                "executor": adapted.execution_plan.get("executor_kind", "kaggle_training_executor_scaffold"),
                "work_dir": adapted.execution_plan.get("work_dir", ""),
                "requires_approval_before_submission": adapted.execution_plan.get(
                    "requires_approval_before_submission",
                    True,
                ),
            },
            metadata={
                "adapter": "kaggle",
                "learning_metadata": adapted.learning_metadata,
                "competition_spec": adapted.competition_spec,
            },
        )
        return TaskAdapterResult(
            task=task,
            memory_items=adapted.memory_items,
            graph_facts=adapted.graph_facts,
            quality_gates=[
                {"name": "sample_submission_schema_validity", "stage": "quality_review"},
                {"name": "leaderboard_overfit_guard", "stage": "decision"},
                {"name": "rule_compliance_check", "stage": "execution_planning"},
            ],
            capability_requirements={
                "execution_planning": ["kaggle_submission_dry_run", "ai_training_execution", "executor_handoff"],
                "quality_review": ["kaggle_submission_dry_run"],
            },
            adapter_metadata=adapted.to_dict(),
        )
