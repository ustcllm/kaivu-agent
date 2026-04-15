from __future__ import annotations

from ..quality_control import QualityControlCheckDefinition, QualityControlChecklist


def physics_quality_control_checklist() -> QualityControlChecklist:
    return QualityControlChecklist(
        discipline="physics",
        checks=[
            QualityControlCheckDefinition(
                check_id="instrument_alignment_verified",
                title="Instrument alignment verified",
                rationale="Misalignment can produce systematic error and false physical effects.",
                severity_if_failed="high",
            ),
            QualityControlCheckDefinition(
                check_id="background_noise_characterized",
                title="Background noise characterized",
                rationale="Unexpected background structure can contaminate weak signals.",
            ),
            QualityControlCheckDefinition(
                check_id="calibration_reference_checked",
                title="Calibration reference checked",
                rationale="Incorrect calibration can shift quantitative measurements and derived constants.",
                severity_if_failed="high",
            ),
            QualityControlCheckDefinition(
                check_id="environmental_drift_checked",
                title="Environmental drift checked",
                rationale="Thermal or electromagnetic drift can dominate precision experiments.",
            ),
            QualityControlCheckDefinition(
                check_id="replicate_consistency_reviewed",
                title="Replicate consistency reviewed",
                rationale="A physical effect should survive basic repeat measurements.",
                required=False,
            ),
        ],
    )


