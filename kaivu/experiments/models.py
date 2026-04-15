from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


DisciplineName = Literal[
    "chemistry",
    "chemical_engineering",
    "physics",
    "artificial_intelligence",
    "mathematics",
]
DecisionType = Literal["discriminate", "validate", "optimize", "reproduce", "falsify"]
ExperimentRunStatus = Literal[
    "planned",
    "approved",
    "running",
    "completed",
    "quality_control_failed",
    "analyzed",
    "archived",
]
QualityControlStatus = Literal["passed", "warning", "failed"]


@dataclass(slots=True)
class ExperimentSpecification:
    experiment_id: str
    title: str
    discipline: DisciplineName
    project_id: str
    hypothesis_ids: list[str] = field(default_factory=list)
    research_question: str = ""
    goal: str = ""
    decision_type: DecisionType = "validate"
    success_criteria: list[str] = field(default_factory=list)
    failure_criteria: list[str] = field(default_factory=list)
    priority: str = "medium"
    status: str = "planned"
    lineage_parent_experiment_id: str = ""
    lineage_note: str = ""
    economics_summary: dict[str, Any] = field(default_factory=dict)
    adjudication_context: dict[str, Any] = field(default_factory=dict)
    discipline_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExperimentalProtocol:
    protocol_id: str
    experiment_id: str
    version: str
    inputs: list[str] = field(default_factory=list)
    controls: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    measurement_plan: list[str] = field(default_factory=list)
    expected_outputs: list[str] = field(default_factory=list)
    risk_points: list[str] = field(default_factory=list)
    quality_control_checks: list[str] = field(default_factory=list)
    lineage_parent_protocol_id: str = ""
    amendment_reason: str = ""
    governance_checks: list[str] = field(default_factory=list)
    approval_requirements: list[str] = field(default_factory=list)
    defer_reasons: list[str] = field(default_factory=list)
    adjudication_questions: list[str] = field(default_factory=list)
    discipline_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExperimentRun:
    run_id: str
    experiment_id: str
    protocol_id: str
    status: ExperimentRunStatus = "planned"
    operator: str = ""
    started_at: str = ""
    ended_at: str = ""
    configuration_snapshot: dict[str, Any] = field(default_factory=dict)
    environment_snapshot: dict[str, Any] = field(default_factory=dict)
    seed: int | None = None
    approval_status: str = "pending"
    approved_by: str = ""
    approval_note: str = ""
    supersedes_run_id: str = ""
    governance_stage: str = ""
    paused_reason: str = ""
    cost_pressure: str = ""
    adjudication_status: str = ""
    discipline_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ObservationRecord:
    observation_id: str
    run_id: str
    observation_type: str
    raw_values: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    files: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    timestamp: str = ""
    discipline_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class QualityControlReview:
    review_id: str
    run_id: str
    quality_control_status: QualityControlStatus
    issues: list[str] = field(default_factory=list)
    possible_artifacts: list[str] = field(default_factory=list)
    protocol_deviations: list[str] = field(default_factory=list)
    quality_control_checks_run: list[str] = field(default_factory=list)
    missing_quality_control_checks: list[str] = field(default_factory=list)
    affected_outputs: list[str] = field(default_factory=list)
    repeat_required: bool = False
    blocking_severity: str = "low"
    evidence_reliability: str = "medium"
    usable_for_interpretation: bool = True
    recommended_action: str = ""
    discipline_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class InterpretationRecord:
    interpretation_id: str
    run_id: str
    supported_hypothesis_ids: list[str] = field(default_factory=list)
    weakened_hypothesis_ids: list[str] = field(default_factory=list)
    inconclusive_hypothesis_ids: list[str] = field(default_factory=list)
    negative_result: bool = False
    claim_updates: list[str] = field(default_factory=list)
    confidence: str = "medium"
    next_decision: str = ""
    discipline_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ResearchAssetRecord:
    asset_id: str
    asset_type: str
    label: str
    path_or_reference: str
    role: str
    experiment_id: str = ""
    run_id: str = ""
    discipline: str = ""
    parent_asset_id: str = ""
    derived_from_asset_ids: list[str] = field(default_factory=list)
    governance_status: str = ""
    lineage_note: str = ""
    is_frozen: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


