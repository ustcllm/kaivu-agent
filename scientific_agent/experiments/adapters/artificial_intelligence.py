from __future__ import annotations

from ..quality_control import QualityControlCheckDefinition, QualityControlChecklist


def artificial_intelligence_quality_control_checklist() -> QualityControlChecklist:
    return QualityControlChecklist(
        discipline="artificial_intelligence",
        checks=[
            QualityControlCheckDefinition(
                check_id="dataset_split_verified",
                title="Dataset split verified",
                rationale="Leakage between train, validation, and test data invalidates most performance claims.",
                severity_if_failed="high",
            ),
            QualityControlCheckDefinition(
                check_id="configuration_snapshot_saved",
                title="Configuration snapshot saved",
                rationale="Without a configuration snapshot, the run cannot be reproduced or audited.",
                severity_if_failed="high",
            ),
            QualityControlCheckDefinition(
                check_id="seed_recorded",
                title="Random seed recorded",
                rationale="Seed instability can hide whether a result is robust.",
            ),
            QualityControlCheckDefinition(
                check_id="training_convergence_reviewed",
                title="Training convergence reviewed",
                rationale="A non-converged model can generate misleading comparisons.",
                severity_if_failed="high",
            ),
            QualityControlCheckDefinition(
                check_id="baseline_comparison_checked",
                title="Baseline comparison checked",
                rationale="Without a stable baseline, an apparent gain may be meaningless.",
            ),
            QualityControlCheckDefinition(
                check_id="repeated_runs_reviewed",
                title="Repeated runs reviewed",
                rationale="Large variance across seeds weakens confidence in the result.",
                required=False,
            ),
        ],
    )
