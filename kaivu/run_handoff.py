from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .experiments import (
    ExperimentRun,
    InterpretationRecord,
    ObservationRecord,
    QualityControlReview,
    ResearchAssetRecord,
)


@dataclass(slots=True)
class RunHandoffContract:
    contract_id: str
    package_id: str
    experiment_id: str
    adapter_id: str
    required_payload_fields: list[str] = field(default_factory=list)
    required_artifacts: list[str] = field(default_factory=list)
    required_quality_gates: list[str] = field(default_factory=list)
    return_record_types: list[str] = field(default_factory=list)
    validation_rules: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RunHandoffRecordBundle:
    bundle_id: str
    contract_id: str
    validation_state: str
    validation_errors: list[str] = field(default_factory=list)
    experiment_run: dict[str, Any] = field(default_factory=dict)
    observation_records: list[dict[str, Any]] = field(default_factory=list)
    quality_control_review: dict[str, Any] = field(default_factory=dict)
    interpretation_record: dict[str, Any] = field(default_factory=dict)
    research_asset_records: list[dict[str, Any]] = field(default_factory=list)
    backpropagation_targets: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_run_handoff_contract_summary(
    *,
    topic: str,
    project_id: str = "",
    execution_adapter_registry_summary: dict[str, Any],
) -> dict[str, Any]:
    packages = [
        item
        for item in execution_adapter_registry_summary.get("execution_packages", [])
        if isinstance(item, dict)
    ]
    contracts = [_contract_for_package(package) for package in packages[:20]]
    return {
        "handoff_contract_id": f"run-handoff-contract::{_slugify(project_id or 'workspace')}::{_slugify(topic)}",
        "topic": topic,
        "project_id": project_id,
        "contract_state": "ready" if contracts else "no_execution_packages",
        "contract_count": len(contracts),
        "contracts": [contract.to_dict() for contract in contracts],
        "return_contract": {
            "experiment_run": "required",
            "observation_records": "required",
            "quality_control_review": "required",
            "interpretation_record": "required_after_analysis",
            "research_asset_records": "required_for_files_or_outputs",
        },
        "normalization_function": "normalize_run_handoff_payload",
    }


def normalize_run_handoff_payload(
    *,
    contract: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    errors = _validate_payload(contract, payload)
    package_id = str(contract.get("package_id", "")).strip()
    experiment_id = str(contract.get("experiment_id", "")).strip()
    run_payload = payload.get("experiment_run", {}) if isinstance(payload.get("experiment_run", {}), dict) else {}
    run_id = str(run_payload.get("run_id", "")).strip() or f"run::{_slugify(package_id or experiment_id)}"
    protocol_id = str(run_payload.get("protocol_id", "")).strip() or f"protocol::{_slugify(experiment_id)}"
    run = ExperimentRun(
        run_id=run_id,
        experiment_id=str(run_payload.get("experiment_id", "")).strip() or experiment_id,
        protocol_id=protocol_id,
        status=_run_status(str(run_payload.get("status", "completed"))),
        operator=str(run_payload.get("operator", "")).strip(),
        started_at=str(run_payload.get("started_at", "")).strip(),
        ended_at=str(run_payload.get("ended_at", "")).strip(),
        configuration_snapshot=(
            run_payload.get("configuration_snapshot", {})
            if isinstance(run_payload.get("configuration_snapshot", {}), dict)
            else {}
        ),
        environment_snapshot=(
            run_payload.get("environment_snapshot", {})
            if isinstance(run_payload.get("environment_snapshot", {}), dict)
            else {}
        ),
        approval_status=str(run_payload.get("approval_status", "approved")).strip(),
        approved_by=str(run_payload.get("approved_by", "")).strip(),
        approval_note=str(run_payload.get("approval_note", "")).strip(),
        governance_stage=str(run_payload.get("governance_stage", "handoff_returned")).strip(),
        discipline_payload={
            "package_id": package_id,
            "adapter_id": contract.get("adapter_id", ""),
            **(
                run_payload.get("discipline_payload", {})
                if isinstance(run_payload.get("discipline_payload", {}), dict)
                else {}
            ),
        },
    )
    observations = _normalize_observations(payload, run_id)
    qc = _normalize_quality_control(payload, run_id, contract)
    interpretation = _normalize_interpretation(payload, run_id)
    assets = _normalize_assets(payload, run_id, experiment_id)
    bundle = RunHandoffRecordBundle(
        bundle_id=f"run-handoff-bundle::{_slugify(run_id)}",
        contract_id=str(contract.get("contract_id", "")).strip(),
        validation_state="valid" if not errors else "invalid",
        validation_errors=errors,
        experiment_run=run.to_dict(),
        observation_records=[item.to_dict() for item in observations],
        quality_control_review=qc.to_dict(),
        interpretation_record=interpretation.to_dict(),
        research_asset_records=[item.to_dict() for item in assets],
        backpropagation_targets=[
            "experiment_registry",
            "quality_control_memory",
            "artifact_provenance_graph",
            "belief_update",
            "failure_memory_if_negative_or_failed",
        ],
    )
    return bundle.to_dict()


def _contract_for_package(package: dict[str, Any]) -> RunHandoffContract:
    package_id = str(package.get("package_id", "")).strip()
    experiment_id = str(package.get("experiment_id", "")).strip()
    adapter_id = str(package.get("adapter_id", "")).strip()
    expected_artifacts = [
        str(item).strip()
        for item in package.get("expected_artifacts", [])
        if str(item).strip()
    ] if isinstance(package.get("expected_artifacts", []), list) else []
    quality_gates = [
        str(item).strip()
        for item in package.get("quality_gates", [])
        if str(item).strip()
    ] if isinstance(package.get("quality_gates", []), list) else []
    return RunHandoffContract(
        contract_id=f"run-contract::{_slugify(package_id or experiment_id)}",
        package_id=package_id,
        experiment_id=experiment_id,
        adapter_id=adapter_id,
        required_payload_fields=[
            "experiment_run",
            "observation_records",
            "quality_control_review",
        ],
        required_artifacts=expected_artifacts,
        required_quality_gates=quality_gates,
        return_record_types=[
            "ExperimentRun",
            "ObservationRecord",
            "QualityControlReview",
            "InterpretationRecord",
            "ResearchAssetRecord",
        ],
        validation_rules=[
            "run must reference the package experiment_id",
            "all produced files must become research_asset_records",
            "quality gates must be marked passed, warning, or failed",
            "negative or failed outcomes must include interpretation notes",
        ],
    )


def _validate_payload(contract: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field_name in contract.get("required_payload_fields", []):
        if field_name not in payload:
            errors.append(f"missing required payload field: {field_name}")
    run = payload.get("experiment_run", {}) if isinstance(payload.get("experiment_run", {}), dict) else {}
    contract_experiment_id = str(contract.get("experiment_id", "")).strip()
    run_experiment_id = str(run.get("experiment_id", "")).strip()
    if contract_experiment_id and run_experiment_id and contract_experiment_id != run_experiment_id:
        errors.append("experiment_run.experiment_id does not match contract")
    qc = payload.get("quality_control_review", {}) if isinstance(payload.get("quality_control_review", {}), dict) else {}
    if qc and str(qc.get("quality_control_status", "")).strip().lower() not in {"passed", "warning", "failed"}:
        errors.append("quality_control_review.quality_control_status must be passed, warning, or failed")
    return errors[:12]


def _normalize_observations(payload: dict[str, Any], run_id: str) -> list[ObservationRecord]:
    observations: list[ObservationRecord] = []
    for index, item in enumerate(payload.get("observation_records", []) if isinstance(payload.get("observation_records", []), list) else []):
        if not isinstance(item, dict):
            continue
        observations.append(
            ObservationRecord(
                observation_id=str(item.get("observation_id", "")).strip() or f"observation::{_slugify(run_id)}::{index + 1}",
                run_id=str(item.get("run_id", "")).strip() or run_id,
                observation_type=str(item.get("observation_type", "result")).strip(),
                raw_values=item.get("raw_values", {}) if isinstance(item.get("raw_values", {}), dict) else {},
                summary=str(item.get("summary", "")).strip(),
                files=[
                    str(path).strip()
                    for path in item.get("files", [])
                    if str(path).strip()
                ] if isinstance(item.get("files", []), list) else [],
                notes=[
                    str(note).strip()
                    for note in item.get("notes", [])
                    if str(note).strip()
                ] if isinstance(item.get("notes", []), list) else [],
                timestamp=str(item.get("timestamp", "")).strip(),
                discipline_payload=item.get("discipline_payload", {}) if isinstance(item.get("discipline_payload", {}), dict) else {},
            )
        )
    return observations


def _normalize_quality_control(payload: dict[str, Any], run_id: str, contract: dict[str, Any]) -> QualityControlReview:
    item = payload.get("quality_control_review", {}) if isinstance(payload.get("quality_control_review", {}), dict) else {}
    checks_run = [
        str(check).strip()
        for check in item.get("quality_control_checks_run", [])
        if str(check).strip()
    ] if isinstance(item.get("quality_control_checks_run", []), list) else []
    required = [
        str(check).strip()
        for check in contract.get("required_quality_gates", [])
        if str(check).strip()
    ] if isinstance(contract.get("required_quality_gates", []), list) else []
    missing = [
        check for check in required if check not in checks_run
    ]
    return QualityControlReview(
        review_id=str(item.get("review_id", "")).strip() or f"qc::{_slugify(run_id)}",
        run_id=str(item.get("run_id", "")).strip() or run_id,
        quality_control_status=_qc_status(str(item.get("quality_control_status", "warning" if missing else "passed"))),
        issues=[str(value).strip() for value in item.get("issues", []) if str(value).strip()] if isinstance(item.get("issues", []), list) else [],
        possible_artifacts=[str(value).strip() for value in item.get("possible_artifacts", []) if str(value).strip()] if isinstance(item.get("possible_artifacts", []), list) else [],
        protocol_deviations=[str(value).strip() for value in item.get("protocol_deviations", []) if str(value).strip()] if isinstance(item.get("protocol_deviations", []), list) else [],
        quality_control_checks_run=checks_run,
        missing_quality_control_checks=missing,
        affected_outputs=[str(value).strip() for value in item.get("affected_outputs", []) if str(value).strip()] if isinstance(item.get("affected_outputs", []), list) else [],
        repeat_required=bool(item.get("repeat_required", False)),
        blocking_severity=str(item.get("blocking_severity", "medium" if missing else "low")).strip(),
        evidence_reliability=str(item.get("evidence_reliability", "medium")).strip(),
        usable_for_interpretation=bool(item.get("usable_for_interpretation", not missing)),
        recommended_action=str(item.get("recommended_action", "")).strip() or (
            "complete missing quality gates before interpretation" if missing else "interpret results"
        ),
        discipline_payload=item.get("discipline_payload", {}) if isinstance(item.get("discipline_payload", {}), dict) else {},
    )


def _normalize_interpretation(payload: dict[str, Any], run_id: str) -> InterpretationRecord:
    item = payload.get("interpretation_record", {}) if isinstance(payload.get("interpretation_record", {}), dict) else {}
    return InterpretationRecord(
        interpretation_id=str(item.get("interpretation_id", "")).strip() or f"interpretation::{_slugify(run_id)}",
        run_id=str(item.get("run_id", "")).strip() or run_id,
        supported_hypothesis_ids=_string_list(item.get("supported_hypothesis_ids", [])),
        weakened_hypothesis_ids=_string_list(item.get("weakened_hypothesis_ids", [])),
        inconclusive_hypothesis_ids=_string_list(item.get("inconclusive_hypothesis_ids", [])),
        negative_result=bool(item.get("negative_result", False)),
        claim_updates=_string_list(item.get("claim_updates", [])),
        confidence=str(item.get("confidence", "medium")).strip(),
        next_decision=str(item.get("next_decision", "")).strip(),
        discipline_payload=item.get("discipline_payload", {}) if isinstance(item.get("discipline_payload", {}), dict) else {},
    )


def _normalize_assets(payload: dict[str, Any], run_id: str, experiment_id: str) -> list[ResearchAssetRecord]:
    assets: list[ResearchAssetRecord] = []
    for index, item in enumerate(payload.get("research_asset_records", []) if isinstance(payload.get("research_asset_records", []), list) else []):
        if not isinstance(item, dict):
            continue
        assets.append(
            ResearchAssetRecord(
                asset_id=str(item.get("asset_id", "")).strip() or f"asset::{_slugify(run_id)}::{index + 1}",
                asset_type=str(item.get("asset_type", "artifact")).strip(),
                label=str(item.get("label", "")).strip() or f"artifact {index + 1}",
                path_or_reference=str(item.get("path_or_reference", "")).strip(),
                role=str(item.get("role", "run_output")).strip(),
                experiment_id=str(item.get("experiment_id", "")).strip() or experiment_id,
                run_id=str(item.get("run_id", "")).strip() or run_id,
                discipline=str(item.get("discipline", "")).strip(),
                parent_asset_id=str(item.get("parent_asset_id", "")).strip(),
                derived_from_asset_ids=_string_list(item.get("derived_from_asset_ids", [])),
                governance_status=str(item.get("governance_status", "returned_by_handoff")).strip(),
                lineage_note=str(item.get("lineage_note", "")).strip(),
                is_frozen=bool(item.get("is_frozen", False)),
                metadata=item.get("metadata", {}) if isinstance(item.get("metadata", {}), dict) else {},
            )
        )
    return assets


def _run_status(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"planned", "approved", "running", "completed", "quality_control_failed", "analyzed", "archived"}:
        return normalized
    return "completed"


def _qc_status(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"passed", "warning", "failed"}:
        return normalized
    return "warning"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "handoff"


