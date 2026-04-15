from __future__ import annotations

from ..quality_control import QualityControlCheckDefinition, QualityControlChecklist


def chemical_engineering_quality_control_checklist() -> QualityControlChecklist:
    return QualityControlChecklist(
        discipline="chemical_engineering",
        checks=[
            QualityControlCheckDefinition(
                check_id="process_conditions_stable",
                title="Process conditions remained stable",
                rationale="Small temperature or pressure excursions can dominate downstream performance.",
                severity_if_failed="high",
            ),
            QualityControlCheckDefinition(
                check_id="sensor_calibration_verified",
                title="Sensor calibration verified",
                rationale="Uncalibrated sensors can distort process control conclusions.",
                severity_if_failed="high",
            ),
            QualityControlCheckDefinition(
                check_id="feed_composition_verified",
                title="Feed composition verified",
                rationale="Feed variability can masquerade as process improvement or degradation.",
            ),
            QualityControlCheckDefinition(
                check_id="mass_balance_reviewed",
                title="Mass balance reviewed",
                rationale="A broken mass balance often indicates a run or measurement problem.",
                severity_if_failed="high",
            ),
            QualityControlCheckDefinition(
                check_id="steady_state_confirmed",
                title="Steady-state confirmed where applicable",
                rationale="Interpreting transient behavior as steady-state performance can mislead process conclusions.",
                required=False,
            ),
        ],
    )


