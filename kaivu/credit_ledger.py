from __future__ import annotations

from typing import Any


def build_scientific_credit_responsibility_ledger_summary(
    *,
    topic: str,
    research_state: dict[str, Any],
    run_manifest: dict[str, Any],
) -> dict[str, Any]:
    records = []
    records.extend(_agent_records(research_state))
    records.extend(_model_records(run_manifest))
    records.extend(_artifact_records(run_manifest))
    records.extend(_decision_records(research_state))
    records.extend(_execution_responsibility_records(research_state))
    records.extend(_formal_review_records(research_state))
    records.extend(_debate_records(research_state))
    records = _dedupe_records(records)
    return {
        "scientific_credit_responsibility_ledger_id": f"credit-ledger::{_slugify(topic)}",
        "topic": topic,
        "record_count": len(records),
        "records": records[:200],
        "credit_by_actor": _sum_by(records, "actor", "credit_weight"),
        "responsibility_by_actor": _sum_by(records, "actor", "responsibility_weight"),
        "unassigned_responsibilities": [
            item for item in records if not str(item.get("actor", "")).strip()
        ][:20],
        "audit_rules": [
            "every promoted claim should have proposer, reviewer, and evidence curator responsibility",
            "every executed package should have run manager and quality-control responsibility",
            "every model-assisted decision should keep model metadata and human/agent reviewer responsibility",
            "formal dissent and standing objections should receive credit when later validated",
        ],
    }


def _agent_records(research_state: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    stance = research_state.get("agent_stance_continuity_summary", {}) if isinstance(research_state.get("agent_stance_continuity_summary", {}), dict) else {}
    for item in _items(stance.get("records", [])):
        actor = str(item.get("agent_name", "") or item.get("profile_name", "")).strip()
        records.append(
            _record(actor, "agent_stance", str(item.get("stance_label", "position")), 0.4, 0.5, _strings(item.get("evidence_refs", [])))
        )
    return records


def _model_records(run_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    for item in _items(run_manifest.get("models_used", [])):
        actor = str(item.get("profile_name", "") or item.get("model", "")).strip()
        records.append(_record(actor, "model_contribution", str(item.get("model", "model")), 0.2, 0.2, []))
    return records


def _artifact_records(run_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    for item in _items(run_manifest.get("artifacts", [])):
        actor = str(item.get("created_by", "") or item.get("producer", "") or "workflow").strip()
        records.append(_record(actor, "artifact_production", str(item.get("path", "") or item.get("artifact_id", "")), 0.3, 0.4, [str(item.get("path", "")).strip()]))
    return records


def _decision_records(research_state: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    decision = research_state.get("scientific_decision_summary", {}) if isinstance(research_state.get("scientific_decision_summary", {}), dict) else {}
    for item in _items(decision.get("decision_queue", [])):
        actor = str(item.get("owner_agent", "") or "decision_engine").strip()
        records.append(_record(actor, "scientific_decision", str(item.get("action", "")), 0.5, 0.7, _strings(item.get("source_refs", []))))
    return records


def _execution_responsibility_records(research_state: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    scheduler = research_state.get("experiment_execution_loop_summary", {}) if isinstance(research_state.get("experiment_execution_loop_summary", {}), dict) else {}
    for item in _items(scheduler.get("execution_queue", [])):
        experiment_id = str(item.get("experiment_id", "")).strip()
        if not experiment_id:
            continue
        records.append(_record("run_manager", "execution_responsibility", experiment_id, 0.3, 0.8, [experiment_id]))
        records.append(_record("quality_control_reviewer", "quality_control_responsibility", experiment_id, 0.3, 0.8, [experiment_id]))
    executor = research_state.get("executor_run_summary", {}) if isinstance(research_state.get("executor_run_summary", {}), dict) else {}
    for run in _items(executor.get("runs", [])):
        run_id = str(run.get("run_id", "") or run.get("experiment_id", "")).strip()
        if run_id:
            records.append(_record("run_manager", "executor_run_record", run_id, 0.4, 0.9, [run_id]))
    return records


def _formal_review_records(research_state: dict[str, Any]) -> list[dict[str, Any]]:
    formal = research_state.get("formal_review_record_summary", {}) if isinstance(research_state.get("formal_review_record_summary", {}), dict) else {}
    records: list[dict[str, Any]] = []
    if formal.get("screening_record_count") or formal.get("evidence_table_record_count"):
        records.append(
            _record(
                "literature_reviewer",
                "formal_review_screening",
                str(formal.get("review_protocol_version", "draft")),
                0.4,
                0.7,
                _strings(formal.get("screening_records", [])),
            )
        )
        records.append(
            _record(
                "evidence_curator",
                "formal_evidence_table",
                str(formal.get("review_protocol_version", "draft")),
                0.4,
                0.7,
                _strings(formal.get("evidence_table_records", [])),
            )
        )
    return records


def _debate_records(research_state: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    debate = research_state.get("scientific_debate_protocol_summary", {}) if isinstance(research_state.get("scientific_debate_protocol_summary", {}), dict) else {}
    for disagreement in _strings(debate.get("open_disagreements", [])):
        records.append(_record("skeptic", "formal_dissent", disagreement, 0.35, 0.5, [disagreement]))
    lab = research_state.get("lab_meeting_protocol_summary", {}) if isinstance(research_state.get("lab_meeting_protocol_summary", {}), dict) else {}
    for item in _items(lab.get("rounds", [])):
        role = str(item.get("speaker_role", "")).strip()
        round_id = str(item.get("round_id", "")).strip()
        if role and round_id:
            records.append(_record(role, "lab_meeting_review", round_id, 0.25, 0.4, [round_id]))
    return records


def _record(actor: str, contribution_type: str, description: str, credit: float, responsibility: float, refs: list[str]) -> dict[str, Any]:
    return {
        "record_id": f"credit::{_slugify(actor)}::{_slugify(contribution_type)}::{_slugify(description)[:60]}",
        "actor": actor,
        "contribution_type": contribution_type,
        "description": description,
        "credit_weight": round(credit, 3),
        "responsibility_weight": round(responsibility, 3),
        "source_refs": refs[:10],
    }


def _dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return list({str(item.get("record_id", "")): item for item in records if str(item.get("record_id", "")).strip()}.values())


def _sum_by(records: list[dict[str, Any]], key: str, value_key: str) -> dict[str, float]:
    totals: dict[str, float] = {}
    for item in records:
        bucket = str(item.get(key, "")).strip() or "unassigned"
        totals[bucket] = round(totals.get(bucket, 0.0) + float(item.get(value_key, 0) or 0), 3)
    return totals


def _items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value).strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "credit"
