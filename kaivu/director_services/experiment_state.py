from __future__ import annotations

from typing import Any


def derive_execution_cycle_summary(
    *,
    experiment_runs: list[dict[str, Any]],
    quality_control_reviews: list[dict[str, Any]],
    interpretation_records: list[dict[str, Any]],
) -> dict[str, Any]:
    run_status_counts: dict[str, int] = {}
    quality_status_counts: dict[str, int] = {}
    repeat_required_count = 0
    unusable_count = 0
    negative_interpretation_count = 0
    next_decisions: list[str] = []

    for item in experiment_runs:
        status = str(item.get("status", "")).strip() or "unknown"
        run_status_counts[status] = run_status_counts.get(status, 0) + 1
    for item in quality_control_reviews:
        status = str(item.get("quality_control_status", "")).strip() or "unknown"
        quality_status_counts[status] = quality_status_counts.get(status, 0) + 1
        if bool(item.get("repeat_required", False)):
            repeat_required_count += 1
        if not bool(item.get("usable_for_interpretation", True)):
            unusable_count += 1
    for item in interpretation_records:
        if bool(item.get("negative_result", False)):
            negative_interpretation_count += 1
        decision = str(item.get("next_decision", "")).strip()
        if decision:
            next_decisions.append(decision)

    return {
        "experiment_run_count": len(experiment_runs),
        "quality_control_review_count": len(quality_control_reviews),
        "interpretation_record_count": len(interpretation_records),
        "run_status_counts": run_status_counts,
        "quality_control_status_counts": quality_status_counts,
        "quality_control_failed_count": int(quality_status_counts.get("failed", 0)),
        "quality_control_warning_count": int(quality_status_counts.get("warning", 0)),
        "quality_control_passed_count": int(quality_status_counts.get("passed", 0)),
        "repeat_required_count": repeat_required_count,
        "non_interpretable_review_count": unusable_count,
        "unusable_for_interpretation_count": unusable_count,
        "negative_interpretation_count": negative_interpretation_count,
        "next_decisions": list(dict.fromkeys(next_decisions))[:8],
    }


def derive_experiment_governance_summary(
    *,
    experiment_runs: list[dict[str, Any]],
    quality_control_reviews: list[dict[str, Any]],
    interpretation_records: list[dict[str, Any]],
    claim_graph: dict[str, Any],
) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    quarantine_runs: list[str] = []
    rerun_candidates: list[str] = []
    approval_gate_needed = False
    for item in experiment_runs:
        status = str(item.get("status", "")).strip().lower() or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1
        run_id = str(item.get("run_id", "")).strip()
        if status in {"planned", "approved"}:
            approval_gate_needed = True
        if status in {"quality_control_failed", "qc_failed"} and run_id:
            quarantine_runs.append(run_id)
    for item in quality_control_reviews:
        run_id = str(item.get("run_id", "")).strip()
        review_status = str(item.get("quality_control_status", "")).strip().lower()
        if bool(item.get("repeat_required", False)) and run_id:
            rerun_candidates.append(run_id)
        if review_status == "failed" and run_id:
            quarantine_runs.append(run_id)
    protocol_assets = [
        item
        for item in (
            claim_graph.get("asset_registry", [])
            if isinstance(claim_graph.get("asset_registry", []), list)
            else []
        )
        if isinstance(item, dict) and str(item.get("asset_type", "")).strip() == "experimental_protocol"
    ]
    interpreted_run_ids = {
        str(item.get("run_id", "")).strip()
        for item in interpretation_records
        if isinstance(item, dict) and str(item.get("run_id", "")).strip()
    }
    governance_risks: list[str] = []
    if approval_gate_needed:
        governance_risks.append("there are planned or approved runs that have not yet cleared execution governance")
    if quarantine_runs:
        governance_risks.append("some runs should be quarantined because quality control failed")
    if len(protocol_assets) > len({str(item.get("experiment_id", "")).strip() for item in experiment_runs if isinstance(item, dict)}):
        governance_risks.append("protocol lineage may be diverging from run lineage")
    return {
        "run_status_counts": status_counts,
        "approval_gate_needed": approval_gate_needed,
        "quarantine_runs": list(dict.fromkeys(quarantine_runs))[:10],
        "rerun_candidates": list(dict.fromkeys(rerun_candidates))[:10],
        "interpreted_run_count": len(interpreted_run_ids),
        "protocol_record_count": len(protocol_assets),
        "governance_risks": governance_risks[:8],
    }


def derive_failure_intelligence_summary(
    *,
    steps: list[Any],
    claim_graph: dict[str, Any],
    execution_cycle_summary: dict[str, Any],
) -> dict[str, Any]:
    technical_failures: list[str] = []
    theoretical_failures: list[str] = []
    evidence_failures: list[str] = []
    avoid_repeat_routes: list[str] = []
    for step in steps:
        parsed = step.parsed_output
        for item in parsed.get("negative_results", []) if isinstance(parsed.get("negative_results", []), list) else []:
            if not isinstance(item, dict):
                continue
            result = str(item.get("result", "")).strip()
            why = str(item.get("why_it_failed_or_did_not_support", "")).strip().lower()
            implication = str(item.get("implication", "")).strip().lower()
            if any(token in why for token in ["instrument", "calibration", "noise", "quality", "protocol", "execution", "data leakage"]):
                technical_failures.append(result or why)
            elif any(token in implication for token in ["hypothesis", "mechanism", "theory", "assumption", "causal"]):
                theoretical_failures.append(result or implication)
            else:
                evidence_failures.append(result or implication or why)
            for hypothesis_id in (
                item.get("affected_hypothesis_ids", [])
                if isinstance(item.get("affected_hypothesis_ids", []), list)
                else []
            ):
                if str(hypothesis_id).strip():
                    avoid_repeat_routes.append(str(hypothesis_id).strip())
    for item in claim_graph.get("hypotheses", []) if isinstance(claim_graph.get("hypotheses", []), list) else []:
        if not isinstance(item, dict):
            continue
        if str(item.get("status", "")).strip().lower() in {"deprecated", "rejected"}:
            hypothesis_id = str(item.get("global_hypothesis_id", "")).strip()
            if hypothesis_id:
                avoid_repeat_routes.append(hypothesis_id)
    dominant_failure_class = "mixed"
    if len(technical_failures) > max(len(theoretical_failures), len(evidence_failures)):
        dominant_failure_class = "technical"
    elif len(theoretical_failures) > max(len(technical_failures), len(evidence_failures)):
        dominant_failure_class = "theoretical"
    elif len(evidence_failures) > max(len(technical_failures), len(theoretical_failures)):
        dominant_failure_class = "evidentiary"
    return {
        "technical_failures": list(dict.fromkeys(technical_failures))[:8],
        "theoretical_failures": list(dict.fromkeys(theoretical_failures))[:8],
        "evidence_failures": list(dict.fromkeys(evidence_failures))[:8],
        "avoid_repeat_routes": list(dict.fromkeys(avoid_repeat_routes))[:10],
        "dominant_failure_class": dominant_failure_class,
        "negative_interpretation_count": int(
            execution_cycle_summary.get("negative_interpretation_count", 0) or 0
        ),
    }


def derive_experiment_economics_summary(
    *,
    topic: str,
    steps: list[Any],
    research_plan_summary: dict[str, Any],
    discipline_adaptation_summary: dict[str, Any],
    execution_cycle_summary: dict[str, Any],
    failure_intelligence_summary: dict[str, Any],
) -> dict[str, Any]:
    specialist_payload = next(
        (
            step.parsed_output.get("experiment_economics", {})
            for step in steps
            if step.profile_name == "experiment_economist"
            and isinstance(step.parsed_output.get("experiment_economics", {}), dict)
            and step.parsed_output.get("experiment_economics", {})
        ),
        {},
    )
    primary_discipline = str(
        discipline_adaptation_summary.get("primary_discipline", "general_science")
    ).strip()
    next_cycle_count = len(research_plan_summary.get("next_cycle_experiments", []))
    repeat_count = int(execution_cycle_summary.get("repeat_required_count", 0) or 0)
    failed_quality = int(execution_cycle_summary.get("quality_control_failed_count", 0) or 0)
    cost_pressure = "medium"
    time_pressure = "medium"
    if primary_discipline in {"chemistry", "chemical_engineering", "physics"} or repeat_count >= 2:
        cost_pressure = "high"
    if primary_discipline == "artificial_intelligence" and "benchmark" in topic.lower():
        cost_pressure = "medium"
    if next_cycle_count >= 3 or failed_quality >= 2:
        time_pressure = "high"
    cheapest_actions = list(
        dict.fromkeys(
            research_plan_summary.get("decision_gates", [])[:2]
            + research_plan_summary.get("information_gain_priorities", [])[:3]
        )
    )[:5]
    if not cheapest_actions:
        cheapest_actions = ["run the smallest discriminative next-step experiment first"]
    return {
        "primary_discipline": primary_discipline,
        "cost_pressure": str(specialist_payload.get("cost_pressure", "")).strip() or cost_pressure,
        "time_pressure": str(specialist_payload.get("time_pressure", "")).strip() or time_pressure,
        "repeat_burden": repeat_count,
        "quality_failure_burden": failed_quality,
        "information_gain_pressure": (
            str(specialist_payload.get("information_gain_pressure", "")).strip()
            or (
                "high" if next_cycle_count or failure_intelligence_summary.get("avoid_repeat_routes") else "medium"
            )
        ),
        "cheapest_discriminative_actions": (
            [
                str(item)
                for item in specialist_payload.get("cheapest_discriminative_actions", [])
                if str(item).strip()
            ]
            or cheapest_actions
        )[:6],
        "resource_risks": [
            str(item)
            for item in specialist_payload.get("resource_risks", [])
            if str(item).strip()
        ][:6],
        "defer_candidates": [
            str(item)
            for item in specialist_payload.get("defer_candidates", [])
            if str(item).strip()
        ][:6],
        "expected_information_gain": [
            str(item)
            for item in specialist_payload.get("expected_information_gain", [])
            if str(item).strip()
        ][:6],
    }


__all__ = [
    "derive_execution_cycle_summary",
    "derive_experiment_economics_summary",
    "derive_experiment_governance_summary",
    "derive_failure_intelligence_summary",
]
