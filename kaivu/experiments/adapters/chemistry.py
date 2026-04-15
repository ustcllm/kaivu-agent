from __future__ import annotations

from ..quality_control import QualityControlCheckDefinition, QualityControlChecklist


def chemistry_quality_control_checklist() -> QualityControlChecklist:
    return QualityControlChecklist(
        discipline="chemistry",
        checks=[
            QualityControlCheckDefinition(
                check_id="instrument_calibration",
                title="Instrument calibration verified",
                rationale="Spectra and quantitative measurements are unreliable when calibration is stale.",
                severity_if_failed="high",
            ),
            QualityControlCheckDefinition(
                check_id="reagent_batch_recorded",
                title="Reagent batch recorded",
                rationale="Reaction variability and contamination risk depend on the reagent batch.",
            ),
            QualityControlCheckDefinition(
                check_id="sample_contamination_check",
                title="Sample contamination reviewed",
                rationale="Contamination can create false peaks or suppress expected products.",
                severity_if_failed="high",
            ),
            QualityControlCheckDefinition(
                check_id="reaction_conditions_within_window",
                title="Reaction conditions remained in the planned window",
                rationale="Temperature, pressure, and time drift can invalidate mechanistic interpretation.",
                severity_if_failed="high",
            ),
            QualityControlCheckDefinition(
                check_id="signal_to_noise_reviewed",
                title="Signal-to-noise reviewed",
                rationale="Low signal quality can mimic a negative result.",
            ),
            QualityControlCheckDefinition(
                check_id="repeatability_checked",
                title="Repeatability checked",
                rationale="A one-off chemical result should not immediately drive a strong mechanistic update.",
                required=False,
            ),
        ],
    )


