from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .event_ledger import ResearchEvent
from .experiments import ExperimentRegistry


@dataclass(slots=True)
class ExperimentBackpropagationRecord:
    backpropagation_id: str
    bundle_id: str
    run_id: str
    experiment_id: str
    propagation_state: str
    saved_records: dict[str, list[str]] = field(default_factory=dict)
    negative_result_candidates: list[dict[str, Any]] = field(default_factory=list)
    claim_update_candidates: list[str] = field(default_factory=list)
    asset_lineage_updates: list[dict[str, Any]] = field(default_factory=list)
    memory_updates: list[dict[str, Any]] = field(default_factory=list)
    event_candidates: list[dict[str, Any]] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def persist_run_handoff_bundle(
    *,
    registry: ExperimentRegistry,
    bundle: dict[str, Any],
) -> dict[str, Any]:
    saved: dict[str, list[str]] = {
        "experiment_runs": [],
        "observation_records": [],
        "quality_control_reviews": [],
        "interpretation_records": [],
        "research_assets": [],
        "handoff_bundles": [],
    }
    bundle_id = str(bundle.get("bundle_id", "")).strip() or "run-handoff-bundle"
    registry.save_record("handoff_bundles", bundle_id, bundle)
    saved["handoff_bundles"].append(bundle_id)

    run = bundle.get("experiment_run", {}) if isinstance(bundle.get("experiment_run", {}), dict) else {}
    run_id = str(run.get("run_id", "")).strip()
    if run_id:
        registry.save_record("experiment_runs", run_id, run)
        saved["experiment_runs"].append(run_id)

    for item in bundle.get("observation_records", []) if isinstance(bundle.get("observation_records", []), list) else []:
        if not isinstance(item, dict):
            continue
        identifier = str(item.get("observation_id", "")).strip()
        if identifier:
            registry.save_record("observation_records", identifier, item)
            saved["observation_records"].append(identifier)

    qc = bundle.get("quality_control_review", {}) if isinstance(bundle.get("quality_control_review", {}), dict) else {}
    qc_id = str(qc.get("review_id", "")).strip()
    if qc_id:
        registry.save_record("quality_control_reviews", qc_id, qc)
        saved["quality_control_reviews"].append(qc_id)

    interpretation = bundle.get("interpretation_record", {}) if isinstance(bundle.get("interpretation_record", {}), dict) else {}
    interpretation_id = str(interpretation.get("interpretation_id", "")).strip()
    if interpretation_id:
        registry.save_record("interpretation_records", interpretation_id, interpretation)
        saved["interpretation_records"].append(interpretation_id)

    for item in bundle.get("research_asset_records", []) if isinstance(bundle.get("research_asset_records", []), list) else []:
        if not isinstance(item, dict):
            continue
        identifier = str(item.get("asset_id", "")).strip()
        if identifier:
            registry.save_record("research_assets", identifier, item)
            saved["research_assets"].append(identifier)

    summary = build_run_backpropagation_summary(bundle=bundle, saved_records=saved)
    registry.save_record("backpropagation_records", summary["backpropagation_id"], summary)
    return summary


def build_run_backpropagation_summary(
    *,
    bundle: dict[str, Any],
    saved_records: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    run = bundle.get("experiment_run", {}) if isinstance(bundle.get("experiment_run", {}), dict) else {}
    qc = bundle.get("quality_control_review", {}) if isinstance(bundle.get("quality_control_review", {}), dict) else {}
    interpretation = bundle.get("interpretation_record", {}) if isinstance(bundle.get("interpretation_record", {}), dict) else {}
    run_id = str(run.get("run_id", "")).strip()
    experiment_id = str(run.get("experiment_id", "")).strip()
    validation_errors = [
        str(item).strip()
        for item in bundle.get("validation_errors", [])
        if str(item).strip()
    ] if isinstance(bundle.get("validation_errors", []), list) else []
    negative_candidates = _negative_result_candidates(
        run=run,
        qc=qc,
        interpretation=interpretation,
    )
    assets = [
        item
        for item in bundle.get("research_asset_records", [])
        if isinstance(item, dict)
    ] if isinstance(bundle.get("research_asset_records", []), list) else []
    propagation_state = "ready_to_backpropagate"
    if validation_errors:
        propagation_state = "blocked_by_invalid_handoff"
    elif qc.get("quality_control_status") == "failed":
        propagation_state = "quality_failed_backpropagation_required"
    elif interpretation.get("negative_result"):
        propagation_state = "negative_result_backpropagation_required"
    record = ExperimentBackpropagationRecord(
        backpropagation_id=f"backpropagation::{_slugify(run_id or experiment_id or bundle.get('bundle_id', 'run'))}",
        bundle_id=str(bundle.get("bundle_id", "")).strip(),
        run_id=run_id,
        experiment_id=experiment_id,
        propagation_state=propagation_state,
        saved_records=saved_records or {},
        negative_result_candidates=negative_candidates,
        claim_update_candidates=[
            str(item).strip()
            for item in interpretation.get("claim_updates", [])
            if str(item).strip()
        ] if isinstance(interpretation.get("claim_updates", []), list) else [],
        asset_lineage_updates=[
            {
                "asset_id": str(item.get("asset_id", "")).strip(),
                "run_id": str(item.get("run_id", "")).strip() or run_id,
                "experiment_id": str(item.get("experiment_id", "")).strip() or experiment_id,
                "path_or_reference": str(item.get("path_or_reference", "")).strip(),
                "governance_status": str(item.get("governance_status", "")).strip(),
            }
            for item in assets
            if str(item.get("asset_id", "")).strip()
        ][:50],
        memory_updates=_memory_updates(
            run=run,
            qc=qc,
            interpretation=interpretation,
            negative_candidates=negative_candidates,
        ),
        event_candidates=_event_candidates(
            run=run,
            qc=qc,
            interpretation=interpretation,
            negative_candidates=negative_candidates,
        ),
        validation_errors=validation_errors,
    )
    return record.to_dict()


def load_experiment_backpropagation_summary(
    *,
    registry_root: str | Path,
) -> dict[str, Any]:
    registry = ExperimentRegistry(registry_root)
    runs = registry.load_collection("experiment_runs")
    qc_reviews = registry.load_collection("quality_control_reviews")
    interpretations = registry.load_collection("interpretation_records")
    assets = registry.load_collection("research_assets")
    backprops = registry.load_collection("backpropagation_records")
    return {
        "registry_root": str(Path(registry_root).resolve()),
        "experiment_run_count": len(runs),
        "quality_control_review_count": len(qc_reviews),
        "interpretation_record_count": len(interpretations),
        "research_asset_count": len(assets),
        "backpropagation_record_count": len(backprops),
        "negative_result_candidate_count": sum(
            len(item.get("negative_result_candidates", []))
            for item in backprops
            if isinstance(item.get("negative_result_candidates", []), list)
        ),
        "latest_backpropagation_id": str(backprops[-1].get("backpropagation_id", "")) if backprops else "",
    }


def apply_backpropagation_to_claim_graph(
    *,
    claim_graph: dict[str, Any],
    backpropagation_record: dict[str, Any],
) -> dict[str, Any]:
    updated = dict(claim_graph)
    negative_results = list(
        updated.get("negative_results", [])
        if isinstance(updated.get("negative_results", []), list)
        else []
    )
    negative_links = list(
        updated.get("negative_result_links", [])
        if isinstance(updated.get("negative_result_links", []), list)
        else []
    )
    asset_registry = list(
        updated.get("asset_registry", [])
        if isinstance(updated.get("asset_registry", []), list)
        else []
    )
    existing_negative_ids = {
        str(item.get("negative_result_id", "") or item.get("global_negative_result_id", "")).strip()
        for item in negative_results
        if isinstance(item, dict)
    }
    for item in backpropagation_record.get("negative_result_candidates", []) if isinstance(backpropagation_record.get("negative_result_candidates", []), list) else []:
        if not isinstance(item, dict):
            continue
        negative_id = str(item.get("negative_result_id", "")).strip()
        if not negative_id or negative_id in existing_negative_ids:
            continue
        node = {
            **item,
            "global_negative_result_id": negative_id,
            "profile_name": "run_handoff_backpropagation",
            "stage": "execute",
            "status": "candidate",
        }
        negative_results.append(node)
        existing_negative_ids.add(negative_id)
        for hypothesis_id in item.get("affected_hypothesis_ids", []) if isinstance(item.get("affected_hypothesis_ids", []), list) else []:
            if str(hypothesis_id).strip():
                negative_links.append(
                    {
                        "negative_result_id": negative_id,
                        "hypothesis_id": str(hypothesis_id).strip(),
                        "relation": "challenges",
                        "source": "run_handoff_backpropagation",
                    }
                )
    existing_assets = {
        str(item.get("asset_id", "")).strip()
        for item in asset_registry
        if isinstance(item, dict)
    }
    for item in backpropagation_record.get("asset_lineage_updates", []) if isinstance(backpropagation_record.get("asset_lineage_updates", []), list) else []:
        if not isinstance(item, dict):
            continue
        asset_id = str(item.get("asset_id", "")).strip()
        if not asset_id or asset_id in existing_assets:
            continue
        asset_registry.append(
            {
                "asset_id": asset_id,
                "asset_type": "run_artifact",
                "label": asset_id,
                "path_or_reference": str(item.get("path_or_reference", "")).strip(),
                "role": "backpropagated_run_output",
                "experiment_id": str(item.get("experiment_id", "")).strip(),
                "run_id": str(item.get("run_id", "")).strip(),
                "governance_status": str(item.get("governance_status", "")).strip(),
                "source": "run_handoff_backpropagation",
            }
        )
        existing_assets.add(asset_id)
    updated["negative_results"] = negative_results
    updated["negative_result_links"] = negative_links
    updated["asset_registry"] = asset_registry
    updated["backpropagation_updates"] = list(
        updated.get("backpropagation_updates", [])
        if isinstance(updated.get("backpropagation_updates", []), list)
        else []
    ) + [backpropagation_record]
    return updated


def build_executor_belief_backpropagation_summary(
    *,
    topic: str,
    executor_run_summary: dict[str, Any],
    claim_graph: dict[str, Any],
    research_state: dict[str, Any],
) -> dict[str, Any]:
    runs = [
        item
        for item in executor_run_summary.get("runs", [])
        if isinstance(item, dict)
    ] if isinstance(executor_run_summary.get("runs", []), list) else []
    hypotheses = [
        item
        for item in claim_graph.get("hypotheses", [])
        if isinstance(item, dict)
    ] if isinstance(claim_graph.get("hypotheses", []), list) else []
    candidates = [
        item
        for item in research_state.get("experiment_execution_loop_summary", {}).get("candidate_experiments", [])
        if isinstance(item, dict)
    ] if isinstance(research_state.get("experiment_execution_loop_summary", {}).get("candidate_experiments", []), list) else []
    hypothesis_ids = [
        str(item.get("hypothesis_id", "") or item.get("id", "")).strip()
        for item in hypotheses
        if str(item.get("hypothesis_id", "") or item.get("id", "")).strip()
    ]
    candidate_by_experiment = {
        str(item.get("experiment_id", "")).strip(): item
        for item in candidates
        if str(item.get("experiment_id", "")).strip()
    }
    updates: list[dict[str, Any]] = []
    mechanism_updates: list[dict[str, Any]] = []
    scheduler_feedback: list[dict[str, Any]] = []
    for run in runs:
        experiment_id = str(run.get("experiment_id", "")).strip()
        package_id = str(run.get("package_id", "")).strip()
        state = str(run.get("execution_state", "")).strip() or "unknown"
        errors = _strings(run.get("errors", []))
        bundle = run.get("normalized_bundle", {}) if isinstance(run.get("normalized_bundle", {}), dict) else {}
        qc = bundle.get("quality_control_review", {}) if isinstance(bundle.get("quality_control_review", {}), dict) else {}
        interpretation = bundle.get("interpretation_record", {}) if isinstance(bundle.get("interpretation_record", {}), dict) else {}
        target_ids = _strings(
            candidate_by_experiment.get(experiment_id, {}).get("hypothesis_ids", [])
            or candidate_by_experiment.get(experiment_id, {}).get("target_hypothesis_ids", [])
            or candidate_by_experiment.get(experiment_id, {}).get("target_ids", [])
        )
        if not target_ids:
            target_ids = hypothesis_ids[:3]
        qc_passed = str(qc.get("quality_control_status", "")).strip().lower() in {"passed", "pass"}
        negative = bool(interpretation.get("negative_result")) or bool(errors)
        if errors:
            update_type = "technical_failure"
            belief_delta = "downgrade_experiment_route_not_hypothesis"
        elif negative:
            update_type = "negative_or_null_result"
            belief_delta = "challenge_target_hypotheses"
        elif qc_passed or state == "completed":
            update_type = "usable_observation"
            belief_delta = "ready_for_interpretation"
        else:
            update_type = "ambiguous_result"
            belief_delta = "hold_confidence_until_quality_review"
        updates.append(
            {
                "run_id": str(bundle.get("experiment_run", {}).get("run_id", "")).strip() if isinstance(bundle.get("experiment_run", {}), dict) else "",
                "package_id": package_id,
                "experiment_id": experiment_id,
                "execution_state": state,
                "affected_hypothesis_ids": target_ids[:10],
                "update_type": update_type,
                "belief_delta": belief_delta,
                "quality_control_status": str(qc.get("quality_control_status", "")).strip(),
                "interpretation_confidence": str(interpretation.get("confidence", "")).strip(),
                "provenance_fact_ids": _strings(run.get("provenance_fact_ids", []))[:20],
                "errors": errors[:10],
            }
        )
        scheduler_feedback.append(
            {
                "experiment_id": experiment_id,
                "package_id": package_id,
                "feedback_type": update_type,
                "scheduler_action": (
                    "penalize_route"
                    if update_type == "technical_failure"
                    else "prioritize_discriminating_follow_up"
                    if update_type == "negative_or_null_result"
                    else "promote_real_executor_or_replication"
                ),
                "reason": errors[0] if errors else str(interpretation.get("next_decision", "")).strip(),
            }
        )
        if target_ids:
            mechanism_updates.append(
                {
                    "experiment_id": experiment_id,
                    "hypothesis_ids": target_ids[:10],
                    "mechanism_state": (
                        "challenged"
                        if update_type == "negative_or_null_result"
                        else "execution_route_failed"
                        if update_type == "technical_failure"
                        else "awaiting_interpretation"
                    ),
                    "source": "executor_belief_backpropagation",
                }
            )
    challenged = sorted(
        {
            hypothesis_id
            for update in updates
            if update.get("update_type") in {"negative_or_null_result", "technical_failure"}
            for hypothesis_id in _strings(update.get("affected_hypothesis_ids", []))
        }
    )
    return {
        "executor_belief_backpropagation_id": f"executor-belief-backpropagation::{_slugify(topic)}",
        "topic": topic,
        "run_count": len(runs),
        "update_count": len(updates),
        "challenged_hypothesis_ids": challenged[:20],
        "hypothesis_updates": updates[:50],
        "mechanism_updates": mechanism_updates[:50],
        "scheduler_feedback": scheduler_feedback[:50],
        "closed_loop_state": (
            "ready"
            if updates
            else "waiting_for_executor_results"
        ),
        "next_actions": _dedupe(
            [
                item.get("scheduler_action", "")
                for item in scheduler_feedback
                if str(item.get("scheduler_action", "")).strip()
            ]
        )[:10],
    }


def build_backpropagation_memory_items(
    *,
    backpropagation_record: dict[str, Any],
    topic: str,
    project_id: str = "",
    user_id: str = "",
    group_id: str = "",
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for update in backpropagation_record.get("memory_updates", []) if isinstance(backpropagation_record.get("memory_updates", []), list) else []:
        if not isinstance(update, dict):
            continue
        filename = str(update.get("filename", "")).strip() or "experiment-backpropagation.md"
        kind = str(update.get("kind", "reference")).strip()
        items.append(
            {
                "title": f"Experiment backpropagation: {backpropagation_record.get('run_id', '')}",
                "summary": str(update.get("summary", "")).strip() or "Experiment backpropagation update",
                "kind": "warning" if kind in {"negative_result", "warning"} else kind,
                "scope": "project",
                "content": _memory_content(backpropagation_record, update),
                "filename": filename,
                "source_refs": [
                    str(backpropagation_record.get("run_id", "")).strip(),
                    str(backpropagation_record.get("experiment_id", "")).strip(),
                ],
                "evidence_level": "high" if kind == "negative_result" else "medium",
                "confidence": "medium",
                "status": "active",
                "owner_agent": "run_manager",
                "user_id": user_id,
                "project_id": project_id,
                "group_id": group_id,
                "visibility": "project",
                "promotion_status": "project",
                "tags": [
                    "experiment-backpropagation",
                    kind,
                    "run-handoff",
                    topic,
                ],
                "validated_by": ["workflow:experiment-backpropagation"],
            }
        )
    return items[:30]


def build_backpropagation_events(
    *,
    topic: str,
    project_id: str = "",
    user_id: str = "",
    group_id: str = "",
    backpropagation_record: dict[str, Any],
) -> list[ResearchEvent]:
    base = {
        "topic": topic,
        "project_id": project_id,
        "user_id": user_id,
        "group_id": group_id,
    }
    events: list[ResearchEvent] = [
        ResearchEvent(
            **base,
            event_id=f"experiment_backpropagated::{_slugify(str(backpropagation_record.get('backpropagation_id', '')))}",
            event_type="experiment_backpropagated",
            actor="experiment_backpropagation",
            asset_type="experiment_backpropagation",
            asset_id=str(backpropagation_record.get("backpropagation_id", "")),
            action=str(backpropagation_record.get("propagation_state", "")),
            summary=(
                f"run={backpropagation_record.get('run_id', '')}; "
                f"negative_candidates={len(backpropagation_record.get('negative_result_candidates', []))}"
            ),
            source_refs=[
                str(backpropagation_record.get("run_id", "")).strip(),
                str(backpropagation_record.get("experiment_id", "")).strip(),
            ],
            metadata=backpropagation_record,
        )
    ]
    for item in backpropagation_record.get("event_candidates", []) if isinstance(backpropagation_record.get("event_candidates", []), list) else []:
        if not isinstance(item, dict):
            continue
        asset_id = str(item.get("asset_id", "")).strip()
        event_type = str(item.get("event_type", "experiment_backpropagation_event")).strip()
        events.append(
            ResearchEvent(
                **base,
                event_id=f"{event_type}::{_slugify(asset_id or backpropagation_record.get('run_id', 'run'))}",
                event_type=event_type,
                actor="experiment_backpropagation",
                asset_type=str(item.get("asset_type", "experiment")).strip(),
                asset_id=asset_id,
                action=str(item.get("action", "")).strip(),
                summary=f"generated from {backpropagation_record.get('backpropagation_id', '')}",
                source_refs=[str(backpropagation_record.get("run_id", "")).strip()],
                metadata=item,
            )
        )
    return events[:50]


def _negative_result_candidates(
    *,
    run: dict[str, Any],
    qc: dict[str, Any],
    interpretation: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    run_id = str(run.get("run_id", "")).strip()
    experiment_id = str(run.get("experiment_id", "")).strip()
    affected_values: list[str] = []
    if isinstance(interpretation.get("weakened_hypothesis_ids", []), list):
        affected_values.extend(
            str(item).strip()
            for item in interpretation.get("weakened_hypothesis_ids", [])
            if str(item).strip()
        )
    if isinstance(interpretation.get("inconclusive_hypothesis_ids", []), list):
        affected_values.extend(
            str(item).strip()
            for item in interpretation.get("inconclusive_hypothesis_ids", [])
            if str(item).strip()
        )
    affected = _dedupe(affected_values)
    if bool(interpretation.get("negative_result", False)):
        candidates.append(
            {
                "negative_result_id": f"negative-result::{_slugify(run_id or experiment_id)}",
                "result": "Run returned a negative or hypothesis-weakening result.",
                "why_it_failed_or_did_not_support": str(interpretation.get("next_decision", "")).strip()
                or "interpretation marked negative_result=true",
                "implication": "Update hypothesis status, failure memory, and future scheduling constraints.",
                "affected_hypothesis_ids": affected,
                "source_run_id": run_id,
                "source_experiment_id": experiment_id,
                "source": "run_handoff_backpropagation",
            }
        )
    if str(qc.get("quality_control_status", "")).strip().lower() == "failed":
        candidates.append(
            {
                "negative_result_id": f"quality-failure::{_slugify(run_id or experiment_id)}",
                "result": "Run failed quality control.",
                "why_it_failed_or_did_not_support": _quality_failure_reason(qc)
                or "quality_control_status=failed",
                "implication": "Quarantine run outputs and schedule reproducibility or protocol repair.",
                "affected_hypothesis_ids": affected,
                "source_run_id": run_id,
                "source_experiment_id": experiment_id,
                "source": "quality_control_backpropagation",
            }
        )
    return candidates


def _memory_content(backpropagation_record: dict[str, Any], update: dict[str, Any]) -> str:
    lines = [
        f"Backpropagation id: {backpropagation_record.get('backpropagation_id', '')}",
        f"Run id: {backpropagation_record.get('run_id', '')}",
        f"Experiment id: {backpropagation_record.get('experiment_id', '')}",
        f"Propagation state: {backpropagation_record.get('propagation_state', '')}",
        f"Summary: {update.get('summary', '')}",
        "",
        "Negative result candidates:",
    ]
    lines.extend(
        f"- {item.get('negative_result_id', '')}: {item.get('result', '')}"
        for item in backpropagation_record.get("negative_result_candidates", [])
        if isinstance(item, dict)
    )
    lines.extend(["", "Claim update candidates:"])
    lines.extend(
        f"- {item}"
        for item in backpropagation_record.get("claim_update_candidates", [])
        if str(item).strip()
    )
    return "\n".join(lines).strip()


def _memory_updates(
    *,
    run: dict[str, Any],
    qc: dict[str, Any],
    interpretation: dict[str, Any],
    negative_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    updates = [
        {
            "filename": f"experiment-run-{_slugify(str(run.get('run_id', 'run')))}.md",
            "kind": "experiment",
            "summary": f"Run {run.get('run_id', '')} status={run.get('status', '')}",
        },
        {
            "filename": f"quality-control-{_slugify(str(qc.get('review_id', 'qc')))}.md",
            "kind": "warning" if qc.get("quality_control_status") != "passed" else "reference",
            "summary": f"Quality control status={qc.get('quality_control_status', '')}",
        },
    ]
    if interpretation:
        updates.append(
            {
                "filename": f"interpretation-{_slugify(str(interpretation.get('interpretation_id', 'interpretation')))}.md",
                "kind": "decision",
                "summary": f"Negative result={interpretation.get('negative_result', False)}",
            }
        )
    for item in negative_candidates:
        updates.append(
            {
                "filename": f"{_slugify(str(item.get('negative_result_id', 'negative-result')))}.md",
                "kind": "negative_result",
                "summary": str(item.get("result", "")),
            }
        )
    return updates[:20]


def _event_candidates(
    *,
    run: dict[str, Any],
    qc: dict[str, Any],
    interpretation: dict[str, Any],
    negative_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    run_id = str(run.get("run_id", "")).strip()
    events = [
        {
            "event_type": "experiment_run_persisted",
            "asset_type": "experiment_run",
            "asset_id": run_id,
            "action": str(run.get("status", "")),
        },
        {
            "event_type": "quality_control_persisted",
            "asset_type": "quality_control_review",
            "asset_id": str(qc.get("review_id", "")).strip(),
            "action": str(qc.get("quality_control_status", "")),
        },
    ]
    if interpretation:
        events.append(
            {
                "event_type": "interpretation_persisted",
                "asset_type": "interpretation_record",
                "asset_id": str(interpretation.get("interpretation_id", "")).strip(),
                "action": "negative_result" if interpretation.get("negative_result") else "interpreted",
            }
        )
    for item in negative_candidates:
        events.append(
            {
                "event_type": "negative_result_candidate_created",
                "asset_type": "negative_result",
                "asset_id": str(item.get("negative_result_id", "")).strip(),
                "action": "candidate_created",
            }
        )
    return events[:20]


def _quality_failure_reason(qc: dict[str, Any]) -> str:
    reasons: list[str] = []
    if isinstance(qc.get("issues", []), list):
        reasons.extend(str(item).strip() for item in qc.get("issues", []) if str(item).strip())
    if isinstance(qc.get("missing_quality_control_checks", []), list):
        reasons.extend(
            f"missing check: {item}"
            for item in qc.get("missing_quality_control_checks", [])
            if str(item).strip()
        )
    return "; ".join(reasons)


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys([str(item).strip() for item in values if str(item).strip()]))


def _strings(value: Any) -> list[str]:
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "backpropagation"


