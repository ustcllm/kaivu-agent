from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .models import (
    DisciplineName,
    ExperimentRun,
    ObservationRecord,
    QualityControlReview,
)


@dataclass(slots=True)
class QualityControlCheckDefinition:
    check_id: str
    title: str
    rationale: str
    severity_if_failed: str = "medium"
    required: bool = True


@dataclass(slots=True)
class QualityControlChecklist:
    discipline: DisciplineName
    checks: list[QualityControlCheckDefinition] = field(default_factory=list)

    def check_ids(self) -> list[str]:
        return [item.check_id for item in self.checks]

    def required_check_ids(self) -> list[str]:
        return [item.check_id for item in self.checks if item.required]


def build_quality_control_review(
    *,
    review_id: str,
    run: ExperimentRun,
    checklist: QualityControlChecklist,
    checks_run: Iterable[str] | None = None,
    issues: list[str] | None = None,
    possible_artifacts: list[str] | None = None,
    protocol_deviations: list[str] | None = None,
    affected_outputs: list[str] | None = None,
    repeat_required: bool = False,
    usable_for_interpretation: bool = True,
    recommended_action: str = "",
    evidence_reliability: str = "medium",
) -> QualityControlReview:
    executed = list(dict.fromkeys(str(item) for item in (checks_run or []) if str(item).strip()))
    required = checklist.required_check_ids()
    missing = [item for item in required if item not in executed]
    issue_list = [str(item) for item in (issues or []) if str(item).strip()]
    artifact_list = [str(item) for item in (possible_artifacts or []) if str(item).strip()]
    deviation_list = [str(item) for item in (protocol_deviations or []) if str(item).strip()]

    quality_control_status = "passed"
    blocking_severity = "low"
    if missing or issue_list or artifact_list or deviation_list:
        quality_control_status = "warning"
        blocking_severity = "medium"
    if repeat_required or not usable_for_interpretation:
        quality_control_status = "failed"
        blocking_severity = "high"

    return QualityControlReview(
        review_id=review_id,
        run_id=run.run_id,
        quality_control_status=quality_control_status,
        issues=issue_list,
        possible_artifacts=artifact_list,
        protocol_deviations=deviation_list,
        quality_control_checks_run=executed,
        missing_quality_control_checks=missing,
        affected_outputs=[str(item) for item in (affected_outputs or []) if str(item).strip()],
        repeat_required=repeat_required,
        blocking_severity=blocking_severity,
        evidence_reliability=evidence_reliability,
        usable_for_interpretation=usable_for_interpretation,
        recommended_action=recommended_action,
        discipline_payload={"discipline": checklist.discipline},
    )


def summarize_quality_control_review(review: QualityControlReview) -> str:
    parts = [
        f"status={review.quality_control_status}",
        f"reliability={review.evidence_reliability}",
        f"repeat_required={review.repeat_required}",
    ]
    if review.issues:
        parts.append(f"issues={len(review.issues)}")
    if review.missing_quality_control_checks:
        parts.append(f"missing_checks={len(review.missing_quality_control_checks)}")
    return " | ".join(parts)


def collect_observation_file_references(
    observations: list[ObservationRecord],
) -> list[str]:
    files: list[str] = []
    for item in observations:
        files.extend(path for path in item.files if path)
    return list(dict.fromkeys(files))
