from __future__ import annotations

from typing import Any


def build_anomaly_surprise_detector_summary(
    *,
    topic: str,
    research_state: dict[str, Any],
    claim_graph: dict[str, Any],
) -> dict[str, Any]:
    executor_runs = _items(research_state.get("executor_run_summary", {}).get("runs", [])) if isinstance(research_state.get("executor_run_summary", {}), dict) else []
    backprop = research_state.get("executor_belief_backpropagation_summary", {}) if isinstance(research_state.get("executor_belief_backpropagation_summary", {}), dict) else {}
    negative_results = _items(claim_graph.get("negative_results", []))
    theory = research_state.get("theory_prediction_compiler_summary", {}) if isinstance(research_state.get("theory_prediction_compiler_summary", {}), dict) else {}
    anomalies = []
    anomalies.extend(_executor_anomalies(executor_runs))
    anomalies.extend(_backprop_anomalies(backprop))
    anomalies.extend(_negative_result_anomalies(negative_results, theory))
    anomalies.extend(_literature_anomalies(research_state))
    anomalies = _rank(anomalies)
    return {
        "anomaly_surprise_detector_id": f"anomaly-surprise::{_slugify(topic)}",
        "topic": topic,
        "anomaly_count": len(anomalies),
        "surprise_level": _surprise_level(anomalies),
        "anomalies": anomalies[:80],
        "top_anomalies": anomalies[:8],
        "mechanism_reframing_triggers": [
            item for item in anomalies if item.get("recommended_action") in {"reframe_problem", "revise_mechanism_family"}
        ][:12],
        "scheduler_constraints": _scheduler_constraints(anomalies),
        "memory_updates": _memory_updates(topic, anomalies),
    }


def _executor_anomalies(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for run in runs:
        errors = _strings(run.get("errors", []))
        bundle = run.get("normalized_bundle", {}) if isinstance(run.get("normalized_bundle", {}), dict) else {}
        interpretation = bundle.get("interpretation_record", {}) if isinstance(bundle.get("interpretation_record", {}), dict) else {}
        qc = bundle.get("quality_control_review", {}) if isinstance(bundle.get("quality_control_review", {}), dict) else {}
        if errors:
            records.append(_record(run, "executor_error", "executor returned errors", 0.75, "inspect_executor_or_toolchain"))
        if interpretation.get("negative_result"):
            records.append(_record(run, "unexpected_negative_result", "interpretation marks result as negative", 0.8, "revise_mechanism_family"))
        if str(qc.get("quality_control_status", "")).lower() == "failed":
            records.append(_record(run, "quality_control_failure", "quality control failed", 0.7, "quarantine_result"))
        if run.get("execution_state") == "completed" and not run.get("provenance_fact_ids"):
            records.append(_record(run, "missing_provenance_after_execution", "completed run lacks provenance facts", 0.65, "repair_provenance"))
    return records


def _backprop_anomalies(backprop: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    for item in _items(backprop.get("hypothesis_updates", [])):
        if item.get("update_type") == "negative_or_null_result":
            records.append(_record(item, "belief_reversal_signal", "executor backpropagation challenges target hypotheses", 0.85, "reframe_problem"))
        if item.get("update_type") == "technical_failure":
            records.append(_record(item, "route_failure_signal", "technical failure should penalize route not hypothesis", 0.6, "avoid_repeat_route"))
    return records


def _negative_result_anomalies(negative_results: list[dict[str, Any]], theory: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    predicted_ids = {
        str(item.get("hypothesis_id", "")).strip()
        for item in _items(theory.get("prediction_table", []))
        if str(item.get("hypothesis_id", "")).strip()
    }
    for item in negative_results:
        affected = set(_strings(item.get("affected_hypothesis_ids", [])))
        severity = 0.75 if affected.intersection(predicted_ids) else 0.55
        records.append(_record(item, "negative_result_against_prediction", "negative result overlaps compiled theory predictions", severity, "revise_mechanism_family"))
    return records


def _literature_anomalies(research_state: dict[str, Any]) -> list[dict[str, Any]]:
    review_summary = research_state.get("systematic_review_summary", {})
    review = review_summary if isinstance(review_summary, dict) else {}
    return [
        {
            "anomaly_id": f"anomaly::literature-conflict::{index}",
            "anomaly_type": "unresolved_literature_conflict",
            "severity": 0.65,
            "description": str(item.get("question", "")),
            "recommended_action": "reframe_problem",
            "source_refs": _strings(item.get("affected_evidence_ids", [])),
        }
        for index, item in enumerate(_items(review.get("conflict_matrix", [])), start=1)
    ]


def _record(source: dict[str, Any], anomaly_type: str, description: str, severity: float, action: str) -> dict[str, Any]:
    ref = str(source.get("experiment_id", "") or source.get("package_id", "") or source.get("negative_result_id", "") or source.get("run_id", "")).strip()
    return {
        "anomaly_id": f"anomaly::{_slugify(anomaly_type)}::{_slugify(ref or description)}",
        "anomaly_type": anomaly_type,
        "severity": round(severity, 3),
        "description": description,
        "recommended_action": action,
        "source_refs": [ref] if ref else [],
    }


def _rank(anomalies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique = {str(item.get("anomaly_id", "")): item for item in anomalies if str(item.get("anomaly_id", "")).strip()}
    return sorted(unique.values(), key=lambda item: float(item.get("severity", 0)), reverse=True)


def _surprise_level(anomalies: list[dict[str, Any]]) -> str:
    if any(float(item.get("severity", 0)) >= 0.8 for item in anomalies):
        return "high"
    if anomalies:
        return "medium"
    return "low"


def _scheduler_constraints(anomalies: list[dict[str, Any]]) -> list[str]:
    return [f"address anomaly before promotion: {item.get('anomaly_type', '')}" for item in anomalies[:8]]


def _memory_updates(topic: str, anomalies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "title": f"Anomaly in {topic}: {item.get('anomaly_type', '')}",
            "summary": item.get("description", ""),
            "tags": ["anomaly", "surprise", item.get("recommended_action", "")],
            "source_refs": item.get("source_refs", []),
        }
        for item in anomalies[:12]
    ]


def _items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value).strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "anomaly"
