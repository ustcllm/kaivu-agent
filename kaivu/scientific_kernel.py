from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .graph import ResearchGraphRegistry


@dataclass(slots=True)
class ScientificObject:
    object_id: str
    object_type: str
    label: str
    status: str = "active"
    confidence: str = "medium"
    source_system: str = ""
    provenance_refs: list[str] = field(default_factory=list)
    related_object_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_research_operating_system_summary(
    *,
    topic: str,
    project_id: str = "",
    research_state: dict[str, Any],
    claim_graph: dict[str, Any],
    run_manifest: dict[str, Any],
) -> dict[str, Any]:
    """Compile the main scientific-agent control surfaces into one operating view."""
    objective = _research_objective_contract(topic=topic, research_state=research_state, claim_graph=claim_graph)
    hypothesis_lifecycle = _hypothesis_lifecycle_map(research_state=research_state, claim_graph=claim_graph)
    evidence_map = _evidence_map(research_state=research_state, claim_graph=claim_graph)
    resource_model = _resource_economics_model(research_state=research_state)
    autonomy = _autonomy_control_ladder(research_state=research_state)
    provenance = _provenance_source_policy(research_state=research_state, claim_graph=claim_graph, run_manifest=run_manifest)
    lab_meeting = _lab_meeting_governance_model(research_state=research_state, claim_graph=claim_graph)
    evaluation = _scientific_capability_evaluation_view(research_state=research_state)
    control_actions = _operating_system_control_actions(
        objective=objective,
        hypothesis_lifecycle=hypothesis_lifecycle,
        evidence_map=evidence_map,
        resource_model=resource_model,
        autonomy=autonomy,
        provenance=provenance,
        lab_meeting=lab_meeting,
        evaluation=evaluation,
    )
    return {
        "research_operating_system_id": f"research-os::{_slugify(project_id or 'workspace')}::{_slugify(topic)}",
        "topic": topic,
        "project_id": project_id,
        "operating_state": "blocked" if any(item.get("severity") == "blocking" for item in control_actions) else "active",
        "objective_contract": objective,
        "hypothesis_lifecycle": hypothesis_lifecycle,
        "evidence_map": evidence_map,
        "resource_economics": resource_model,
        "autonomy_control": autonomy,
        "provenance_source_policy": provenance,
        "lab_meeting_governance": lab_meeting,
        "capability_evaluation": evaluation,
        "control_actions": control_actions,
        "next_control_focus": control_actions[0]["action"] if control_actions else "continue_current_research_cycle",
    }


def build_scientific_object_store_summary(
    *,
    topic: str,
    project_id: str = "",
    claim_graph: dict[str, Any],
    research_state: dict[str, Any],
    run_manifest: dict[str, Any],
) -> dict[str, Any]:
    objects: dict[str, ScientificObject] = {}

    def add(obj: ScientificObject) -> None:
        if not obj.object_id:
            return
        existing = objects.get(obj.object_id)
        if existing is None:
            objects[obj.object_id] = obj
            return
        existing.provenance_refs = _dedupe(existing.provenance_refs + obj.provenance_refs)
        existing.related_object_ids = _dedupe(existing.related_object_ids + obj.related_object_ids)
        existing.metadata = {**existing.metadata, **obj.metadata}

    for item in _items(claim_graph.get("claims", [])):
        claim_id = str(item.get("claim_id", "") or item.get("id", "") or item.get("statement", "")[:80]).strip()
        add(
            ScientificObject(
                object_id=f"claim::{_slugify(claim_id)}",
                object_type="claim",
                label=str(item.get("statement", "") or item.get("claim", "") or claim_id).strip(),
                status=str(item.get("status", "active")).strip() or "active",
                confidence=str(item.get("confidence", "medium")).strip() or "medium",
                source_system="claim_graph",
                provenance_refs=_strings(item.get("evidence_refs", [])),
                metadata=item,
            )
        )

    for item in _items(claim_graph.get("hypotheses", [])):
        hypothesis_id = str(item.get("global_hypothesis_id", "") or item.get("hypothesis_id", "")).strip()
        add(
            ScientificObject(
                object_id=hypothesis_id,
                object_type="hypothesis",
                label=str(item.get("name", "")).strip() or hypothesis_id,
                status=str(item.get("status", "active")).strip() or "active",
                confidence=str(item.get("confidence", "medium")).strip() or "medium",
                source_system="claim_graph",
                provenance_refs=_strings(item.get("evidence_refs", [])),
                metadata=item,
            )
        )

    for item in _items(claim_graph.get("negative_results", [])):
        negative_id = str(item.get("negative_result_id", "")).strip()
        add(
            ScientificObject(
                object_id=negative_id,
                object_type="failed_attempt",
                label=str(item.get("result", "")).strip()[:160] or negative_id,
                status="active",
                confidence=str(item.get("confidence", "medium")).strip() or "medium",
                source_system="negative_result_memory",
                related_object_ids=_strings(item.get("affected_hypothesis_ids", [])),
                metadata=item,
            )
        )

    for item in _items(research_state.get("hypothesis_validation_summary", {}).get("records", [])):
        hypothesis_id = str(item.get("hypothesis_id", "")).strip()
        add(
            ScientificObject(
                object_id=f"hypothesis-validation::{_slugify(hypothesis_id)}",
                object_type="hypothesis_validation",
                label=f"validation {hypothesis_id}",
                status=str(item.get("overall_recommendation", "observe")).strip() or "observe",
                source_system="hypothesis_validators",
                related_object_ids=[hypothesis_id] if hypothesis_id else [],
                metadata=item,
            )
        )

    for item in _items(research_state.get("experiment_execution_loop_summary", {}).get("candidate_experiments", [])):
        experiment_id = str(item.get("experiment_id", "")).strip()
        add(
            ScientificObject(
                object_id=experiment_id,
                object_type="experiment_candidate",
                label=str(item.get("title", "")).strip() or experiment_id,
                status=str(item.get("gate_state", "candidate")).strip() or "candidate",
                source_system="experiment_scheduler",
                related_object_ids=_strings(item.get("target_ids", [])),
                provenance_refs=_strings(item.get("provenance_refs", [])),
                metadata=item,
            )
        )

    for item in _items(research_state.get("scientific_decision_summary", {}).get("decision_queue", [])):
        decision_id = str(item.get("decision_id", "")).strip()
        target_id = str(item.get("target_id", "")).strip()
        add(
            ScientificObject(
                object_id=decision_id,
                object_type="scientific_decision",
                label=str(item.get("action", "")).strip() or decision_id,
                status=str(item.get("priority", "medium")).strip() or "medium",
                source_system="decision_engine",
                related_object_ids=[target_id] if target_id else [],
                metadata=item,
            )
        )

    for item in _items(run_manifest.get("artifacts", [])):
        path = str(item.get("path", "") or item.get("artifact_id", "")).strip()
        if not path:
            continue
        add(
            ScientificObject(
                object_id=f"artifact::{_slugify(path)}",
                object_type="artifact",
                label=str(item.get("kind", "artifact")).strip() or "artifact",
                status="exists" if item.get("exists") else "planned",
                source_system="run_manifest",
                provenance_refs=[path],
                metadata=item,
            )
        )

    type_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for obj in objects.values():
        type_counts[obj.object_type] = type_counts.get(obj.object_type, 0) + 1
        status_counts[obj.status] = status_counts.get(obj.status, 0) + 1
    return {
        "object_store_id": f"scientific-object-store::{_slugify(project_id or 'workspace')}::{_slugify(topic)}",
        "topic": topic,
        "project_id": project_id,
        "object_count": len(objects),
        "object_type_counts": type_counts,
        "status_counts": status_counts,
        "objects": [obj.to_dict() for obj in objects.values()][:200],
    }


def build_research_state_machine_summary(
    *,
    topic: str,
    research_state: dict[str, Any],
    object_store_summary: dict[str, Any],
) -> dict[str, Any]:
    scheduler = research_state.get("experiment_execution_loop_summary", {})
    evidence_review = research_state.get("evidence_review_summary", {})
    hypothesis_gate = research_state.get("hypothesis_gate_summary", {})
    evaluation = research_state.get("kaivu_evaluation_harness_summary", {})
    release_gate = research_state.get("scientific_release_gate_summary", {})
    risk_permission = research_state.get("experiment_risk_permission_summary", {})
    current = str(research_state.get("current_stage", "")).strip() or "question_formulation"
    blockers = _strings(research_state.get("blockers", []))
    if str(release_gate.get("release_state", "")).lower() == "release_ready":
        canonical = "publishable"
    elif str(risk_permission.get("permission_state", "")).lower() in {"blocked", "requires_human_approval"}:
        canonical = "human_governance"
        blockers.extend(_strings(risk_permission.get("required_approvals", [])))
    elif str(hypothesis_gate.get("gate_state", "")).lower() in {"blocked", "revision_required"}:
        canonical = "hypothesis_validation"
    elif str(scheduler.get("scheduler_state", "")).lower() in {"ready_to_schedule", "needs_protocol", "needs_human_approval"}:
        canonical = "experiment_design"
    elif str(evidence_review.get("review_readiness", "")).lower() in {"decision_ready", "ready"}:
        canonical = "decision"
    elif str(evaluation.get("release_state", "")).lower() in {"release_ready", "publishable"}:
        canonical = "publishable"
    else:
        canonical = _canonical_stage(current)
    legal_next = _legal_next_states(canonical)
    if blockers:
        legal_next = _dedupe(["paused"] + legal_next)
    return {
        "state_machine_id": f"research-state-machine::{_slugify(topic)}",
        "topic": topic,
        "current_state": canonical,
        "workflow_stage": current,
        "legal_next_states": legal_next,
        "recommended_next_state": legal_next[0] if legal_next else "report",
        "blockers": blockers[:12],
        "object_count": object_store_summary.get("object_count", 0),
        "transition_guards": _transition_guards(research_state),
    }


def build_uncertainty_ledger_summary(
    *,
    topic: str,
    research_state: dict[str, Any],
    claim_graph: dict[str, Any],
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for index, item in enumerate(_strings(research_state.get("open_questions", [])), start=1):
        entries.append(_uncertainty_entry(topic, index, "open_question", item, "medium", "literature_or_experiment"))
    for index, item in enumerate(_strings(research_state.get("blockers", [])), start=1):
        entries.append(_uncertainty_entry(topic, index, "blocker", item, "high", "human_or_protocol_resolution"))
    for index, item in enumerate(_strings(research_state.get("systematic_review_summary", {}).get("review_protocol_gaps", [])), start=1):
        entries.append(_uncertainty_entry(topic, index, "review_protocol_gap", item, "high", "systematic_review_update"))
    for index, item in enumerate(_strings(research_state.get("systematic_review_summary", {}).get("bias_hotspots", [])), start=1):
        entries.append(_uncertainty_entry(topic, index, "bias_hotspot", item, "high", "bias_risk_assessment"))
    for item in _items(claim_graph.get("negative_results", [])):
        result = str(item.get("result", "")).strip()
        if result:
            entries.append(
                _uncertainty_entry(
                    topic,
                    len(entries) + 1,
                    "failed_attempt",
                    result,
                    "medium",
                    "failure_mode_resolution",
                    related_ids=_strings(item.get("affected_hypothesis_ids", [])),
                )
            )
    severity_counts: dict[str, int] = {}
    for item in entries:
        severity = str(item.get("severity", "medium"))
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
    return {
        "uncertainty_ledger_id": f"uncertainty-ledger::{_slugify(topic)}",
        "topic": topic,
        "entry_count": len(entries),
        "severity_counts": severity_counts,
        "decision_blocking_count": sum(1 for item in entries if item.get("decision_blocking")),
        "entries": entries[:100],
    }


def build_value_of_information_summary(
    *,
    topic: str,
    experiment_execution_loop_summary: dict[str, Any],
    uncertainty_ledger_summary: dict[str, Any],
) -> dict[str, Any]:
    high_uncertainty = int(uncertainty_ledger_summary.get("severity_counts", {}).get("high", 0) or 0)
    scored: list[dict[str, Any]] = []
    for item in _items(experiment_execution_loop_summary.get("candidate_experiments", [])):
        information = _float(item.get("information_gain_score", item.get("expected_information_gain", 0)))
        discrimination = _float(item.get("discrimination_score", 0))
        failure_gain = _float(item.get("failure_knowledge_gain", 0))
        cost = _float(item.get("cost_score", item.get("estimated_cost", 0)))
        risk = _float(item.get("risk_score", 0)) + _float(item.get("validator_penalty", 0))
        voi = round(information * 2.0 + discrimination + failure_gain + min(high_uncertainty, 5) * 0.25 - cost - risk, 3)
        scored.append(
            {
                "experiment_id": str(item.get("experiment_id", "")),
                "title": str(item.get("title", "")),
                "value_of_information": voi,
                "information_gain_score": information,
                "cost_score": cost,
                "risk_score": risk,
                "decision_impact": "high" if voi >= 5 else "medium" if voi >= 2 else "low",
                "uncertainty_targets": [entry.get("uncertainty_id") for entry in uncertainty_ledger_summary.get("entries", [])[:5]],
            }
        )
    scored.sort(key=lambda item: float(item.get("value_of_information", 0)), reverse=True)
    return {
        "value_of_information_id": f"value-of-information::{_slugify(topic)}",
        "topic": topic,
        "candidate_count": len(scored),
        "top_candidate_id": scored[0]["experiment_id"] if scored else "",
        "top_value_of_information": scored[0]["value_of_information"] if scored else 0,
        "items": scored[:50],
    }


def build_counterfactual_experiment_summary(
    *,
    topic: str,
    claim_graph: dict[str, Any],
    uncertainty_ledger_summary: dict[str, Any],
) -> dict[str, Any]:
    hypotheses = _items(claim_graph.get("hypotheses", []))
    designs: list[dict[str, Any]] = []
    for index, hypothesis in enumerate(hypotheses[:20], start=1):
        hypothesis_id = str(hypothesis.get("global_hypothesis_id", "") or hypothesis.get("hypothesis_id", "")).strip()
        name = str(hypothesis.get("name", "")).strip() or hypothesis_id
        prediction = str(hypothesis.get("prediction", "")).strip()
        mechanism = str(hypothesis.get("mechanism", "")).strip()
        designs.append(
            {
                "counterfactual_design_id": f"counterfactual::{_slugify(hypothesis_id or str(index))}",
                "hypothesis_id": hypothesis_id,
                "question": f"What observation would distinguish whether {name} is true versus a rival explanation?",
                "if_hypothesis_true": prediction or f"observable pattern consistent with {name}",
                "if_hypothesis_false": "prediction fails, reverses, or appears only under confounded boundary conditions",
                "rival_explanation": "measurement artifact, confounding variable, or alternative mechanism",
                "discriminative_experiment": f"Run a controlled comparison that perturbs the proposed mechanism: {mechanism or 'mechanism unspecified'}",
                "required_controls": ["negative control", "positive control", "boundary-condition control"],
                "failure_value": "a negative result should update failed-attempt memory and narrow mechanism family scope",
                "uncertainty_refs": [entry.get("uncertainty_id") for entry in uncertainty_ledger_summary.get("entries", [])[:3]],
            }
        )
    return {
        "counterfactual_experiment_id": f"counterfactual-experiments::{_slugify(topic)}",
        "topic": topic,
        "design_count": len(designs),
        "designs": designs,
    }


def build_reproducibility_kernel_summary(
    *,
    topic: str,
    run_manifest: dict[str, Any],
    research_state: dict[str, Any],
) -> dict[str, Any]:
    artifacts = _items(run_manifest.get("artifacts", []))
    execution_records = _items(run_manifest.get("execution_records", []))
    execution_cycle = research_state.get("execution_cycle_summary", {})
    required_fields = {
        "code_or_tool_trace": bool(run_manifest.get("tools_used") or execution_records),
        "model_trace": bool(run_manifest.get("models_used") or run_manifest.get("usage_summary")),
        "artifact_manifest": bool(artifacts),
        "quality_control": bool(execution_cycle.get("quality_control_review_count", 0)),
        "interpretation_record": bool(execution_cycle.get("interpretation_record_count", 0)),
        "raw_or_report_output": any(item.get("kind") in {"report", "raw_data", "dataset", "notebook"} for item in artifacts),
    }
    missing = [name for name, present in required_fields.items() if not present]
    return {
        "reproducibility_kernel_id": f"reproducibility-kernel::{_slugify(topic)}",
        "topic": topic,
        "readiness": "high" if not missing else "medium" if len(missing) <= 2 else "low",
        "required_fields": required_fields,
        "missing_fields": missing,
        "artifact_count": len(artifacts),
        "execution_record_count": len(execution_records),
        "replay_contract": {
            "requires_code_version": "code_or_tool_trace" in missing,
            "requires_data_version": not any(item.get("kind") in {"raw_data", "dataset"} for item in artifacts),
            "requires_environment_capture": True,
            "requires_seed_capture": True,
            "requires_protocol_version": not bool(research_state.get("run_handoff_contract_summary", {})),
        },
        "artifacts": artifacts[:50],
    }


def build_scientific_debate_protocol_summary(
    *,
    topic: str,
    research_state: dict[str, Any],
    claim_graph: dict[str, Any],
) -> dict[str, Any]:
    consensus = research_state.get("lab_meeting_consensus_summary", {})
    conflicts = _strings(research_state.get("conflict_attribution", {}).get("conflict_groups", []))
    blockers = _strings(research_state.get("blockers", []))
    claims = _items(claim_graph.get("claims", []))
    hypotheses = _items(claim_graph.get("hypotheses", []))
    agenda = _strings(consensus.get("agenda_items", [])) or [
        "review strongest claim",
        "challenge weakest hypothesis",
        "decide next discriminative experiment",
    ]
    roles = [
        {"role": "proposer", "responsibility": "state the claim or hypothesis and its expected mechanism"},
        {"role": "supporter", "responsibility": "compile supporting evidence and boundary conditions"},
        {"role": "skeptic", "responsibility": "identify counterexamples, failed attempts, and confounders"},
        {"role": "methodologist", "responsibility": "check design, controls, and reproducibility"},
        {"role": "statistician", "responsibility": "check uncertainty, effect size, and inference risks"},
        {"role": "chair", "responsibility": "record consensus level, unresolved disagreement, and next action"},
    ]
    consensus_state = str(consensus.get("consensus_state", "") or consensus.get("consensus_status", "")).strip()
    if blockers or conflicts:
        level = "contested"
    elif consensus_state:
        level = consensus_state
    else:
        level = "rough_consensus" if claims or hypotheses else "forming"
    return {
        "scientific_debate_protocol_id": f"scientific-debate::{_slugify(topic)}",
        "topic": topic,
        "consensus_level": level,
        "agenda_items": agenda[:10],
        "roles": roles,
        "open_disagreements": (conflicts + blockers)[:12],
        "formal_record_required": bool(blockers or conflicts or hypotheses),
        "decision_rule": "advance only when proposer/supporter claims survive skeptic and methodologist objections",
    }


def build_failure_reuse_engine_summary(
    *,
    topic: str,
    claim_graph: dict[str, Any],
    experiment_execution_loop_summary: dict[str, Any],
) -> dict[str, Any]:
    failures = _items(claim_graph.get("negative_results", []))
    candidates = _items(experiment_execution_loop_summary.get("candidate_experiments", []))
    recommendations: list[dict[str, Any]] = []
    for candidate in candidates[:50]:
        target_ids = set(_strings(candidate.get("target_ids", [])))
        matched = [
            failure
            for failure in failures
            if target_ids.intersection(set(_strings(failure.get("affected_hypothesis_ids", []))))
        ]
        if not matched:
            continue
        recommendations.append(
            {
                "experiment_id": str(candidate.get("experiment_id", "")),
                "matched_failure_count": len(matched),
                "matched_failure_ids": [str(item.get("negative_result_id", "")) for item in matched[:10]],
                "reuse_action": "require_sanity_check_before_repeat",
                "scheduler_constraint": "do_not_repeat_failed_route_without_changed_conditions",
                "condition_change_required": True,
            }
        )
    return {
        "failure_reuse_engine_id": f"failure-reuse::{_slugify(topic)}",
        "topic": topic,
        "failure_count": len(failures),
        "candidate_count": len(candidates),
        "recommendation_count": len(recommendations),
        "recommendations": recommendations,
        "memory_query": "retrieve failed attempts with overlapping hypothesis, mechanism, conditions, and measurement target",
    }


def build_literature_claim_compiler_summary(
    *,
    topic: str,
    claim_graph: dict[str, Any],
    systematic_review_summary: dict[str, Any],
) -> dict[str, Any]:
    compiled: dict[str, dict[str, Any]] = {}
    for item in _items(claim_graph.get("claims", [])):
        statement = str(item.get("statement", "") or item.get("claim", "")).strip()
        if not statement:
            continue
        key = _slugify(statement[:120])
        record = compiled.setdefault(
            key,
            {
                "compiled_claim_id": f"compiled-claim::{key}",
                "statement": statement,
                "supporting_evidence_refs": [],
                "challenging_evidence_refs": [],
                "source_claim_ids": [],
                "status": "unresolved",
            },
        )
        record["source_claim_ids"].extend(_strings([item.get("claim_id", item.get("id", ""))]))
        record["supporting_evidence_refs"].extend(_strings(item.get("evidence_refs", [])))
    contested = _strings(systematic_review_summary.get("bias_hotspots", [])) + _strings(
        systematic_review_summary.get("evidence_balance", [])
    )
    for record in compiled.values():
        if contested:
            record["challenging_evidence_refs"].extend(contested[:5])
        support_count = len(record["supporting_evidence_refs"])
        challenge_count = len(record["challenging_evidence_refs"])
        record["status"] = "supported" if support_count > challenge_count else "contested" if challenge_count else "under_evidenced"
        record["source_claim_ids"] = _dedupe(record["source_claim_ids"])
        record["supporting_evidence_refs"] = _dedupe(record["supporting_evidence_refs"])
        record["challenging_evidence_refs"] = _dedupe(record["challenging_evidence_refs"])
    records = list(compiled.values())
    return {
        "literature_claim_compiler_id": f"literature-claim-compiler::{_slugify(topic)}",
        "topic": topic,
        "compiled_claim_count": len(records),
        "status_counts": _count_by(records, "status"),
        "records": records[:100],
        "systematic_review_refs": {
            "screened_evidence_count": systematic_review_summary.get("screened_evidence_count", 0),
            "review_protocol_version": systematic_review_summary.get("review_protocol_version", ""),
        },
    }


def build_model_reliability_layer_summary(
    *,
    topic: str,
    run_manifest: dict[str, Any],
    research_state: dict[str, Any],
) -> dict[str, Any]:
    usage = run_manifest.get("usage_summary", {})
    by_profile = usage.get("by_profile", []) if isinstance(usage, dict) else []
    records = []
    for item in by_profile if isinstance(by_profile, list) else []:
        if not isinstance(item, dict):
            continue
        total_tokens = _float(item.get("total_tokens", 0))
        cost = _float(item.get("estimated_cost_usd", 0))
        profile = str(item.get("profile_name", "")).strip()
        model = str(item.get("model", "unknown")).strip() or "unknown"
        reliability_flags: list[str] = []
        if total_tokens == 0:
            reliability_flags.append("missing_usage_trace")
        if profile in {"literature_reviewer", "hypothesis_generator", "critic"} and model == "unknown":
            reliability_flags.append("unknown_model_for_high_impact_agent")
        records.append(
            {
                "profile_name": profile,
                "model": model,
                "total_tokens": total_tokens,
                "estimated_cost_usd": cost,
                "reliability_state": "needs_review" if reliability_flags else "tracked",
                "reliability_flags": reliability_flags,
            }
        )
    evaluation = research_state.get("kaivu_evaluation_harness_summary", {})
    return {
        "model_reliability_layer_id": f"model-reliability::{_slugify(topic)}",
        "topic": topic,
        "model_record_count": len(records),
        "models_used": _dedupe([str(item.get("model", "")) for item in records]),
        "needs_review_count": sum(1 for item in records if item.get("reliability_state") == "needs_review"),
        "evaluation_release_state": evaluation.get("release_state", ""),
        "routing_policy": {
            "literature_reviewer": "prefer retrieval-capable high-context model",
            "hypothesis_generator": "prefer high-reasoning model with validator fallback",
            "critic": "prefer independent model from proposer when possible",
            "data_analyst": "prefer code/tool-reliable model",
        },
        "records": records,
    }


def build_benchmark_case_suite_summary(
    *,
    topic: str,
    research_state: dict[str, Any],
    claim_graph: dict[str, Any],
    run_manifest: dict[str, Any],
) -> dict[str, Any]:
    provenance_replay = research_state.get("provenance_replay_summary", {})
    if not isinstance(provenance_replay, dict):
        provenance_replay = {}
    if not provenance_replay:
        provenance_graph = claim_graph.get("provenance_claim_graph", {})
        if isinstance(provenance_graph, dict):
            provenance_replay = provenance_graph.get("replay_summary", {}) if isinstance(provenance_graph.get("replay_summary", {}), dict) else {}
    fact_count = int(provenance_replay.get("fact_count", 0) or 0)
    replay_claim_count = int(provenance_replay.get("claim_count", 0) or 0)
    replay_hypothesis_count = int(provenance_replay.get("hypothesis_count", 0) or 0)
    replay_evidence_count = int(provenance_replay.get("evidence_count", 0) or 0)
    replay_experiment_count = int(provenance_replay.get("experiment_count", 0) or 0)
    context = {
        "claim_graph": claim_graph,
        "research_state": research_state,
        "run_manifest": run_manifest,
        **research_state,
    }
    replay_cases = run_benchmark_replay_cases(context=context)
    dataset_summary = build_benchmark_dataset_summary()
    regression_suite = build_benchmark_regression_suite(
        context=context,
        baseline=research_state.get("benchmark_regression_baseline", {})
        if isinstance(research_state.get("benchmark_regression_baseline", {}), dict)
        else {},
    )
    replay_by_id = {
        str(case.get("case_id", "")).strip(): case
        for case in replay_cases
        if str(case.get("case_id", "")).strip()
    }
    cases = [
        _benchmark_case(
            "literature_claim_extraction",
            "Extract and normalize scientific claims from literature evidence.",
            _items(claim_graph.get("claims", [])),
            ["claim_graph contains claim objects", "compiled literature claims exist"],
            bool(_items(claim_graph.get("claims", [])))
            or bool(research_state.get("literature_claim_compiler_summary", {}).get("compiled_claim_count", 0)),
        ),
        _benchmark_case(
            "hypothesis_validator",
            "Reject or revise weak, non-falsifiable, or under-evidenced hypotheses.",
            _items(research_state.get("hypothesis_validation_summary", {}).get("records", [])),
            ["validator records exist", "gate summary exists", "weak hypotheses are flagged"],
            bool(research_state.get("hypothesis_validation_summary", {}).get("validation_count", 0))
            and bool(research_state.get("hypothesis_gate_summary", {})),
        ),
        _benchmark_case(
            "experiment_design_controls",
            "Check that scheduled experiments have controls, quality gates, and handoff contracts.",
            _items(research_state.get("experiment_execution_loop_summary", {}).get("candidate_experiments", [])),
            ["execution candidates exist", "quality gates exist", "handoff contract exists"],
            bool(research_state.get("experiment_execution_loop_summary", {}).get("candidate_count", 0))
            and bool(research_state.get("run_handoff_contract_summary", {}).get("contract_count", 0)),
        ),
        _benchmark_case(
            "failure_backpropagation",
            "Use failed attempts to alter future scheduling and memory.",
            _items(claim_graph.get("negative_results", [])),
            ["negative results exist", "failure reuse recommendations exist", "memory updates exist"],
            bool(claim_graph.get("negative_results"))
            and bool(research_state.get("failure_reuse_engine_summary", {}).get("recommendation_count", 0)),
        ),
        _benchmark_case(
            "provenance_replay",
            "Replay fact-backed claims, hypotheses, evidence, experiments, decisions, artifacts, model usage, and runtime outputs.",
            _items(run_manifest.get("artifacts", [])),
            [
                "provenance facts exist",
                "provenance replay reconstructs claims or hypotheses",
                "provenance replay reconstructs evidence or experiments",
                "runtime/usage trace exists",
            ],
            fact_count > 0
            and (replay_claim_count > 0 or replay_hypothesis_count > 0)
            and (replay_evidence_count > 0 or replay_experiment_count > 0)
            and bool(run_manifest.get("usage_summary", {}) or research_state.get("typed_research_graph_summary", {})),
        ),
    ]
    merged_cases: list[dict[str, Any]] = []
    seen_case_ids: set[str] = set()
    for case in cases:
        case_id = str(case.get("case_id", "")).strip()
        replay_case = replay_by_id.get(case_id, {})
        if replay_case:
            case = {
                **case,
                "replay_status": replay_case.get("status", ""),
                "replay_missing_outputs": replay_case.get("missing_outputs", []),
                "replay_present_outputs": replay_case.get("present_outputs", []),
                "replay_evidence": replay_case.get("evidence", []),
                "replay_path": replay_case.get("path", ""),
                "dataset_category": replay_case.get("category", ""),
                "dataset_split": replay_case.get("split", ""),
                "dataset_tags": replay_case.get("tags", []),
                "case_score": replay_case.get("score", 0),
                "quality_score": replay_case.get("quality_score", replay_case.get("score", 0)),
                "quality_status": replay_case.get("quality_status", ""),
                "quality_findings": replay_case.get("quality_findings", []),
            }
            if replay_case.get("status") != "passed":
                case["status"] = "failed"
                case["failure_mode"] = (
                    str(case.get("failure_mode", "")).strip()
                    or f"{case_id} replay expected outputs are missing"
                )
        merged_cases.append(case)
        seen_case_ids.add(case_id)
    for case_id, replay_case in replay_by_id.items():
        if case_id in seen_case_ids:
            continue
        merged_cases.append(
            {
                "case_id": case_id,
                "description": replay_case.get("task", ""),
                "priority": replay_case.get("priority", "P1"),
                "status": replay_case.get("status", "failed"),
                "rubric": replay_case.get("rubric", []),
                "evidence_object_count": len(replay_case.get("present_outputs", []) if isinstance(replay_case.get("present_outputs", []), list) else []),
                "failure_mode": "" if replay_case.get("status") == "passed" else f"{case_id} replay expected outputs are missing",
                "replay_status": replay_case.get("status", ""),
                "replay_missing_outputs": replay_case.get("missing_outputs", []),
                "replay_present_outputs": replay_case.get("present_outputs", []),
                  "replay_evidence": replay_case.get("evidence", []),
                  "replay_path": replay_case.get("path", ""),
                  "dataset_category": replay_case.get("category", ""),
                  "dataset_split": replay_case.get("split", ""),
                  "dataset_tags": replay_case.get("tags", []),
                  "case_score": replay_case.get("score", 0),
                  "quality_score": replay_case.get("quality_score", replay_case.get("score", 0)),
                  "quality_status": replay_case.get("quality_status", ""),
                  "quality_findings": replay_case.get("quality_findings", []),
              }
          )
    cases = merged_cases
    passed = [case for case in cases if case["status"] == "passed"]
    failed = [case for case in cases if case["status"] != "passed"]
    quality_scores = [
        _float(case.get("quality_score", case.get("case_score", 1.0 if case.get("status") == "passed" else 0.0)))
        for case in cases
    ]
    average_quality_score = round(sum(quality_scores) / max(1, len(quality_scores)), 3)
    low_quality_cases = [
        str(case.get("case_id", "")).strip()
        for case in cases
        if _float(case.get("quality_score", case.get("case_score", 0.0))) < 0.7
    ]
    readiness = "high" if len(passed) == len(cases) else "medium" if len(passed) >= 3 else "low"
    benchmark_gaps = [case["failure_mode"] for case in failed if str(case.get("failure_mode", "")).strip()]
    regression_checks = [
        f"case:{case['case_id']} must remain {case['status']}"
        for case in cases
    ]
    fail_fast_cases = [case["case_id"] for case in failed if case["priority"] == "P0"]
    return {
        "benchmark_case_suite_id": f"benchmark-case-suite::{_slugify(topic)}",
        "topic": topic,
        "case_count": len(cases),
        "passed_count": len(passed),
        "failed_count": len(failed),
        "benchmark_readiness": readiness,
        "benchmark_ready": readiness in {"medium", "high"},
        "release_readiness": readiness,
          "average_quality_score": average_quality_score,
          "quality_gate_state": "passed" if average_quality_score >= 0.75 and not low_quality_cases else "needs_quality_review",
          "low_quality_cases": low_quality_cases[:20],
          "benchmark_gaps": benchmark_gaps,
          "cases": cases,
          "benchmark_dataset": dataset_summary,
          "benchmark_replay_runner": {
              "runner": "builtin_yaml_expected_output_replay",
              "case_file_count": len(replay_cases),
            "passed_count": len([case for case in replay_cases if case.get("status") == "passed"]),
            "failed_count": len([case for case in replay_cases if case.get("status") != "passed"]),
              "cases": replay_cases,
          },
          "benchmark_regression_suite": regression_suite,
          "provenance_replay_summary": provenance_replay,
        "fact_backed_replay_ready": fact_count > 0
        and (replay_claim_count > 0 or replay_hypothesis_count > 0)
        and (replay_evidence_count > 0 or replay_experiment_count > 0),
          "regression_matrix": [
              {
                  "case_id": case["case_id"],
                  "status": case["status"],
                  "must_not_regress": True,
                  "minimum_expected_status": "passed",
                  "dataset_category": case.get("dataset_category", ""),
                  "dataset_split": case.get("dataset_split", ""),
                  "case_score": case.get("case_score", 1.0 if case.get("status") == "passed" else 0.0),
                  "quality_score": case.get("quality_score", case.get("case_score", 0.0)),
              }
              for case in cases
          ],
          "regression_checks": _dedupe(
              regression_checks
              + [
                  str(item)
                  for item in regression_suite.get("regression_checks", [])
                  if str(item).strip()
              ]
              + [
                  f"case:{case_id} must keep quality_score>=0.70"
                  for case_id in low_quality_cases
              ]
          ),
          "fail_fast_checks": [
              f"fail-fast benchmark case must pass: {case_id}"
              for case_id in fail_fast_cases
          ]
          + [
              str(item)
              for item in regression_suite.get("fail_fast_checks", [])
              if str(item).strip()
          ],
          "fail_fast_cases": fail_fast_cases,
      }


def build_scientific_evaluation_benchmark_summary(
    *,
    topic: str,
    research_state: dict[str, Any],
    claim_graph: dict[str, Any],
) -> dict[str, Any]:
    tasks = [
        _benchmark_task(
            "literature_systematicity",
            "Can the agent produce protocolized systematic review artifacts?",
            research_state.get("systematic_review_summary", {}).get("synthesis_state")
            in {"synthesis_ready", "needs_stratified_synthesis"},
        ),
        _benchmark_task(
            "problem_reframing",
            "Can the agent detect when the scientific question needs reframing?",
            bool(research_state.get("scientific_problem_reframer_summary", {}).get("candidate_frames")),
        ),
        _benchmark_task(
            "theory_prediction",
            "Can the agent compile hypotheses into predictions and discriminating tests?",
            research_state.get("theory_prediction_compiler_summary", {}).get("formalization_readiness")
            in {"medium", "high"},
        ),
        _benchmark_task(
            "anomaly_response",
            "Can the agent detect and route anomalies or surprises?",
            bool(research_state.get("anomaly_surprise_detector_summary", {})),
        ),
        _benchmark_task(
            "credit_responsibility",
            "Can the agent assign credit and responsibility for collaborative research work?",
            bool(research_state.get("scientific_credit_responsibility_ledger_summary", {}).get("record_count", 0)),
        ),
        _benchmark_task(
            "closed_loop_execution",
            "Can executor results feed back into beliefs and scheduler constraints?",
            bool(research_state.get("executor_belief_backpropagation_summary", {}).get("closed_loop_state")),
        ),
    ]
    for task in tasks:
        task["quality_score"] = _benchmark_quality_score(task, research_state, claim_graph)
        task["status"] = "passed" if task["passed"] and task["quality_score"] >= 0.65 else "needs_repair"
    passed = len([item for item in tasks if item["status"] == "passed"])
    avg_quality = round(sum(item["quality_score"] for item in tasks) / max(1, len(tasks)), 3)
    return {
        "scientific_evaluation_benchmark_id": f"scientific-evaluation-benchmark::{_slugify(topic)}",
        "topic": topic,
        "benchmark_version": "current",
        "task_count": len(tasks),
        "passed_count": passed,
        "failed_count": len(tasks) - passed,
        "average_quality_score": avg_quality,
        "benchmark_state": "strong" if passed == len(tasks) and avg_quality >= 0.8 else "usable" if passed >= 4 else "needs_repairs",
        "tasks": tasks,
        "regression_checks": [f"scientific benchmark task must pass: {item['task_id']}" for item in tasks],
        "failure_modes": [item["task_id"] for item in tasks if item["status"] != "passed"],
    }


def build_benchmark_dataset_summary(root: str | Path | None = None) -> dict[str, Any]:
    dataset = load_builtin_benchmark_dataset(root)
    cases = dataset.get("cases", []) if isinstance(dataset.get("cases", []), list) else []
    category_counts: dict[str, int] = {}
    split_counts: dict[str, int] = {}
    priority_counts: dict[str, int] = {}
    tag_counts: dict[str, int] = {}
    for case in cases:
        if not isinstance(case, dict):
            continue
        category = str(case.get("category", "uncategorized")).strip() or "uncategorized"
        split = str(case.get("split", "regression")).strip() or "regression"
        priority = str(case.get("priority", "P1")).strip() or "P1"
        category_counts[category] = category_counts.get(category, 0) + 1
        split_counts[split] = split_counts.get(split, 0) + 1
        priority_counts[priority] = priority_counts.get(priority, 0) + 1
        for tag in _strings(case.get("tags", [])):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    manifest = dataset.get("manifest", {}) if isinstance(dataset.get("manifest", {}), dict) else {}
    return {
        "dataset_id": str(manifest.get("dataset_id", "kaivu-benchmark")).strip(),
        "version": str(manifest.get("version", "0.1.0")).strip(),
        "task_family": str(manifest.get("task_family", "kaivu_kernel")).strip(),
        "case_count": len(cases),
        "case_ids": [str(case.get("case_id", "")).strip() for case in cases if isinstance(case, dict)],
        "category_counts": category_counts,
        "split_counts": split_counts,
        "priority_counts": priority_counts,
        "tag_counts": tag_counts,
        "metrics": _strings(manifest.get("metrics", [])),
        "governance": {
            "cases_are_versioned_files": True,
            "baseline_comparison_supported": True,
            "registry_replay_supported": True,
            "trajectory_replay_supported": True,
        },
    }


def build_benchmark_regression_suite(
    *,
    context: dict[str, Any],
    baseline: dict[str, Any] | None = None,
    root: str | Path | None = None,
) -> dict[str, Any]:
    baseline = baseline or {}
    cases = run_benchmark_replay_cases(context=context, root=root)
    baseline_cases = _baseline_cases_by_id(baseline)
    regressions: list[dict[str, Any]] = []
    improvements: list[dict[str, Any]] = []
    for case in cases:
        case_id = str(case.get("case_id", "")).strip()
        prior = baseline_cases.get(case_id, {})
        prior_status = str(prior.get("status", "")).strip()
        prior_score = _float(prior.get("score", 1.0 if prior_status == "passed" else 0.0))
        current_status = str(case.get("status", "")).strip()
        current_score = _float(case.get("score", 1.0 if current_status == "passed" else 0.0))
        prior_quality = _float(prior.get("quality_score", prior_score))
        current_quality = _float(case.get("quality_score", current_score))
        if prior_status == "passed" and current_status != "passed":
            regressions.append(
                {
                    "case_id": case_id,
                    "regression_type": "status_regression",
                    "previous_status": prior_status,
                    "current_status": current_status,
                    "missing_outputs": case.get("missing_outputs", []),
                }
            )
        elif prior_quality and current_quality + 0.001 < prior_quality:
            regressions.append(
                {
                    "case_id": case_id,
                    "regression_type": "quality_score_drop",
                    "previous_quality_score": prior_quality,
                    "current_quality_score": current_quality,
                    "quality_findings": case.get("quality_findings", []),
                }
            )
        elif current_score + 0.001 < prior_score:
            regressions.append(
                {
                    "case_id": case_id,
                    "regression_type": "score_drop",
                    "previous_score": prior_score,
                    "current_score": current_score,
                    "missing_outputs": case.get("missing_outputs", []),
                }
            )
        elif prior_status and prior_status != "passed" and current_status == "passed":
            improvements.append(
                {
                    "case_id": case_id,
                    "improvement_type": "newly_passing",
                    "previous_status": prior_status,
                    "current_status": current_status,
                }
            )
    category_matrix: dict[str, dict[str, int]] = {}
    split_matrix: dict[str, dict[str, int]] = {}
    for case in cases:
        category = str(case.get("category", "uncategorized")).strip() or "uncategorized"
        split = str(case.get("split", "regression")).strip() or "regression"
        status = str(case.get("status", "failed")).strip() or "failed"
        category_matrix.setdefault(category, {"passed": 0, "failed": 0})
        split_matrix.setdefault(split, {"passed": 0, "failed": 0})
        category_matrix[category]["passed" if status == "passed" else "failed"] += 1
        split_matrix[split]["passed" if status == "passed" else "failed"] += 1
    passed_count = len([case for case in cases if case.get("status") == "passed"])
    failed_count = len(cases) - passed_count
    return {
        "regression_suite_id": "benchmark-regression-suite::builtin",
        "runner": "dataset_manifest_expected_output_regression",
        "case_count": len(cases),
        "passed_count": passed_count,
        "failed_count": failed_count,
        "regression_count": len(regressions),
        "improvement_count": len(improvements),
        "release_state": "blocked" if regressions else "passing" if failed_count == 0 else "needs_repairs",
        "category_matrix": category_matrix,
        "split_matrix": split_matrix,
        "regressions": regressions,
        "improvements": improvements,
        "cases": cases,
        "regression_checks": [
            f"dataset case {case.get('case_id', '')} must keep status={case.get('status', '')}"
            for case in cases
        ],
        "fail_fast_checks": [
            f"P0 dataset case must pass: {case.get('case_id', '')}"
            for case in cases
            if str(case.get("priority", "")).strip() == "P0" and case.get("status") != "passed"
        ],
    }


def build_benchmark_regression_suite_from_trajectory(
    *,
    trajectory: dict[str, Any],
    baseline: dict[str, Any] | None = None,
    root: str | Path | None = None,
) -> dict[str, Any]:
    evaluation = trajectory.get("evaluation_summary", {}) if isinstance(trajectory.get("evaluation_summary", {}), dict) else {}
    context = {
        "trajectory": trajectory,
        "evaluation_summary": evaluation,
        "kaivu_evaluation_harness_summary": evaluation,
        "run_manifest": {
            "usage_summary": trajectory.get("usage_summary", {})
            if isinstance(trajectory.get("usage_summary", {}), dict)
            else {},
        },
        "research_state": {
            "kaivu_evaluation_harness_summary": evaluation,
            "runtime_harness_summary": {
                "event_count": len(trajectory.get("events", []) if isinstance(trajectory.get("events", []), list) else []),
            },
        },
        "claim_graph": {},
    }
    return build_benchmark_regression_suite(context=context, baseline=baseline, root=root)


def load_builtin_benchmark_dataset(root: str | Path | None = None) -> dict[str, Any]:
    base = Path(root) if root else Path(__file__).resolve().parent / "benchmarks"
    manifest_path = base / "dataset.yaml"
    manifest = (
        _parse_benchmark_case_yaml(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.exists()
        else {
            "dataset_id": "kaivu-benchmark",
            "version": "0.1.0",
            "task_family": "kaivu_kernel",
            "metrics": ["case_pass_rate", "p0_pass_rate", "regression_count"],
        }
    )
    cases = []
    for case_file in load_builtin_benchmark_case_files(base / "cases"):
        case = _parse_benchmark_case_yaml(str(case_file.get("content", "")))
        case["case_id"] = str(case.get("case_id", "") or case_file.get("case_id", "")).strip()
        case["path"] = str(case_file.get("path", ""))
        cases.append(case)
    return {"manifest": manifest, "cases": cases}


def run_benchmark_replay_cases(
    *,
    context: dict[str, Any],
    root: str | Path | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for case_file in load_builtin_benchmark_case_files(root):
        case = _parse_benchmark_case_yaml(str(case_file.get("content", "")))
        case_id = str(case.get("case_id", "") or case_file.get("case_id", "")).strip()
        expected_outputs = _strings(case.get("expected_outputs", []))
        expected_values = case.get("expected_values", {})
        expected_values = expected_values if isinstance(expected_values, dict) else {}
        present: list[str] = []
        missing: list[str] = []
        evidence: list[dict[str, Any]] = []
        for path in expected_outputs:
            resolved = _resolve_context_path(context, path)
            if _path_value_present(resolved):
                present.append(path)
                evidence.append(
                    {
                        "path": path,
                        "kind": type(resolved).__name__,
                        "size": len(resolved) if isinstance(resolved, (list, dict, str)) else 1,
                    }
                )
            else:
                missing.append(path)
        value_results = _benchmark_expected_value_results(
            expected_values=expected_values,
            context=context,
        )
        failed_values = [
            item for item in value_results if item.get("status") != "passed"
        ]
        score = round(len(present) / max(1, len(expected_outputs)), 3)
        rubric_results = _benchmark_rubric_results(case=case, context=context, evidence=evidence)
        rubric_pass_rate = sum(1 for item in rubric_results if item.get("status") == "passed") / max(1, len(rubric_results))
        value_pass_rate = sum(1 for item in value_results if item.get("status") == "passed") / max(1, len(value_results) or 1)
        quality_score = round((score * 0.45) + (rubric_pass_rate * 0.35) + (value_pass_rate * 0.20), 3)
        status = "passed" if expected_outputs and not missing and not failed_values else "failed"
        results.append(
            {
                "case_id": case_id,
                "path": str(case_file.get("path", "")),
                "priority": str(case.get("priority", "P1")).strip() or "P1",
                "category": str(case.get("category", "uncategorized")).strip() or "uncategorized",
                "split": str(case.get("split", "regression")).strip() or "regression",
                "tags": _strings(case.get("tags", [])),
                "task": str(case.get("task", "")).strip(),
                "expected_outputs": expected_outputs,
                "present_outputs": present,
                "missing_outputs": missing,
                "status": status,
                "score": score,
                "quality_score": quality_score,
                "quality_status": "passed" if status == "passed" and quality_score >= 0.7 else "needs_review",
                "rubric_results": rubric_results,
                "quality_findings": [
                    str(item.get("finding", "")).strip()
                    for item in rubric_results
                    if item.get("status") != "passed" and str(item.get("finding", "")).strip()
                ]
                + [
                    str(item.get("finding", "")).strip()
                    for item in value_results
                    if item.get("status") != "passed" and str(item.get("finding", "")).strip()
                ],
                "rubric": _strings(case.get("rubric", [])),
                "expected_values": expected_values,
                "expected_value_results": value_results,
                "inputs": case.get("inputs", {}),
                "evidence": evidence,
            }
        )
    return results


def run_benchmark_replay_from_registry(
    *,
    registry: ResearchGraphRegistry,
    project_id: str = "",
    topic: str = "",
    snapshot_id: str = "",
    root: str | Path | None = None,
) -> dict[str, Any]:
    replay = registry.replay_facts(project_id=project_id, topic=topic)
    snapshots = registry.load_snapshots(project_id=project_id, topic=topic)
    if snapshot_id:
        snapshots = [
            snapshot
            for snapshot in snapshots
            if str(snapshot.get("snapshot_id", "")).strip() == snapshot_id
        ]
    selected_snapshot = snapshots[-1] if snapshots else {}
    claim_graph = _claim_graph_context_from_replay(replay)
    research_state = _research_state_context_from_replay(replay, selected_snapshot)
    run_manifest = _run_manifest_context_from_replay(replay, selected_snapshot)
    context = {
        "claim_graph": claim_graph,
        "research_state": research_state,
        "run_manifest": run_manifest,
        **research_state,
    }
    cases = run_benchmark_replay_cases(context=context, root=root)
    regression_suite = build_benchmark_regression_suite(context=context, root=root)
    return {
        "runner": "registry_provenance_fact_replay",
        "project_id": project_id,
        "topic": topic,
        "snapshot_id": str(selected_snapshot.get("snapshot_id", "")),
        "fact_count": replay.get("fact_count", 0),
        "case_count": len(cases),
        "passed_count": len([case for case in cases if case.get("status") == "passed"]),
        "failed_count": len([case for case in cases if case.get("status") != "passed"]),
        "cases": cases,
        "benchmark_dataset": build_benchmark_dataset_summary(root=root),
        "benchmark_regression_suite": regression_suite,
        "replay_summary": {
            "fact_count": replay.get("fact_count", 0),
            "claim_count": replay.get("claim_count", 0),
            "hypothesis_count": replay.get("hypothesis_count", 0),
            "evidence_count": replay.get("evidence_count", 0),
            "experiment_count": replay.get("experiment_count", 0),
            "artifact_count": replay.get("artifact_count", 0),
            "relation_count": len(replay.get("relations", []) if isinstance(replay.get("relations", []), list) else []),
        },
        "reconstructed_context_summary": {
            "claim_count": len(claim_graph.get("claims", [])),
            "evidence_count": len(claim_graph.get("evidence", [])),
            "hypothesis_count": len(claim_graph.get("hypotheses", [])),
            "experiment_queue_count": len(
                research_state.get("experiment_execution_loop_summary", {}).get("execution_queue", [])
                if isinstance(research_state.get("experiment_execution_loop_summary", {}).get("execution_queue", []), list)
                else []
            ),
            "artifact_count": len(run_manifest.get("artifacts", []) if isinstance(run_manifest.get("artifacts", []), list) else []),
        },
    }


def build_memory_governance_loop_summary(
    *,
    topic: str,
    research_state: dict[str, Any],
    claim_graph: dict[str, Any],
    object_store_summary: dict[str, Any],
) -> dict[str, Any]:
    proposed_actions: list[dict[str, Any]] = []
    for item in _items(claim_graph.get("memory_updates", [])):
        proposed_actions.append(
            {
                "memory_action_id": f"memory-action::{_slugify(str(item.get('filename', 'memory')))}",
                "source": "claim_graph_memory_update",
                "target_scope": "project",
                "action": "commit_or_refresh",
                "risk_level": "low",
                "reason": str(item.get("updated_by", "workflow memory sync")),
                "object_refs": _strings([item.get("hypothesis_id", "")]),
            }
        )
    for item in _items(claim_graph.get("negative_results", [])):
        negative_id = str(item.get("negative_result_id", "")).strip()
        proposed_actions.append(
            {
                "memory_action_id": f"memory-action::failed-attempt::{_slugify(negative_id)}",
                "source": "negative_result",
                "target_scope": "project",
                "action": "commit_failed_attempt",
                "risk_level": "medium",
                "reason": "failed attempts should be reusable by scheduler and validators",
                "object_refs": [negative_id, *_strings(item.get("affected_hypothesis_ids", []))],
            }
        )
    distill = research_state.get("project_distill", {})
    if isinstance(distill, dict) and distill.get("current_consensus"):
        proposed_actions.append(
            {
                "memory_action_id": f"memory-action::project-distill::{_slugify(topic)}",
                "source": "project_distill",
                "target_scope": "project",
                "action": "commit_project_distill",
                "risk_level": "low",
                "reason": "project consensus should refresh project memory",
                "object_refs": [],
            }
        )
    debate = research_state.get("scientific_debate_protocol_summary", {})
    if isinstance(debate, dict) and debate.get("formal_record_required"):
        proposed_actions.append(
            {
                "memory_action_id": f"memory-action::group-debate::{_slugify(topic)}",
                "source": "scientific_debate_protocol",
                "target_scope": "group",
                "action": "propose_group_memory",
                "risk_level": "medium",
                "reason": "contested or formal lab-meeting decisions require group memory review",
                "object_refs": _strings(debate.get("open_disagreements", [])),
            }
        )
    for obj in _items(object_store_summary.get("objects", [])):
        if obj.get("object_type") in {"scientific_decision", "hypothesis_validation"} and obj.get("status") in {"blocked", "reject", "revise"}:
            proposed_actions.append(
                {
                    "memory_action_id": f"memory-action::review::{_slugify(str(obj.get('object_id', 'object')))}",
                    "source": "scientific_object_store",
                    "target_scope": "project",
                    "action": "mark_needs_review",
                    "risk_level": "medium",
                    "reason": "blocked or revised scientific object should be reviewed before promotion",
                    "object_refs": _strings([obj.get("object_id", "")]),
                }
            )
    action_counts = _count_by(proposed_actions, "action")
    risk_counts = _count_by(proposed_actions, "risk_level")
    return {
        "memory_governance_loop_id": f"memory-governance-loop::{_slugify(topic)}",
        "topic": topic,
        "action_count": len(proposed_actions),
        "action_counts": action_counts,
        "risk_counts": risk_counts,
        "automation_policy": {
            "auto_commit_low_risk_project_memory": True,
            "propose_group_memory_for_review": True,
            "block_public_memory_without_human_approval": True,
            "version_conflicting_memory": True,
        },
        "closed_loop_targets": [
            "scheduler",
            "hypothesis_validators",
            "failure_reuse_engine",
            "scientific_debate_protocol",
            "provenance_graph",
        ],
        "proposed_actions": proposed_actions[:100],
    }


def build_scheduler_search_kernel_summary(
    *,
    topic: str,
    experiment_execution_loop_summary: dict[str, Any],
    value_of_information_summary: dict[str, Any],
    uncertainty_ledger_summary: dict[str, Any],
    research_campaign_plan_summary: dict[str, Any] | None = None,
    route_selector_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidates = _items(experiment_execution_loop_summary.get("candidate_experiments", []))
    execution_queue_ids = {
        str(item.get("experiment_id", "")).strip()
        for item in _items(experiment_execution_loop_summary.get("execution_queue", []))
        if str(item.get("experiment_id", "")).strip()
    }
    research_campaign_plan_summary = research_campaign_plan_summary or {}
    route_selector_summary = route_selector_summary or {}
    if not route_selector_summary and isinstance(research_campaign_plan_summary, dict):
        embedded_route_selector = research_campaign_plan_summary.get("route_selector_summary", {})
        route_selector_summary = embedded_route_selector if isinstance(embedded_route_selector, dict) else {}
    voi_by_id = {
        str(item.get("experiment_id", "")): item
        for item in _items(value_of_information_summary.get("items", []))
    }
    nodes: list[dict[str, Any]] = [
        {
            "node_id": f"scheduler-node::{_slugify(topic)}::root",
            "node_type": "root",
            "parent_id": "",
            "action": "choose_next_research_action",
            "visit_count": max(1, len(candidates)),
            "value_estimate": value_of_information_summary.get("top_value_of_information", 0),
            "uncertainty_refs": [entry.get("uncertainty_id") for entry in uncertainty_ledger_summary.get("entries", [])[:8]],
        }
    ]
    edges: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates[:40], start=1):
        experiment_id = str(candidate.get("experiment_id", "")).strip()
        voi = voi_by_id.get(experiment_id, {})
        base_value = _float(
            candidate.get(
                "judge_adjusted_selection_score",
                candidate.get("selection_score", voi.get("value_of_information", candidate.get("portfolio_score", 0))),
            )
        )
        value = _float(voi.get("value_of_information", base_value))
        gate_state = str(candidate.get("gate_state", "")).strip()
        llm_action = str(candidate.get("llm_recommended_action", "")).strip()
        executable = experiment_id in execution_queue_ids or gate_state in {"ready_to_schedule", "ready", ""}
        blocked_by_judge = llm_action == "block"
        gate_penalty = 1000.0 if blocked_by_judge or gate_state == "blocked" else 100.0 if not executable else 0.0
        ucb_score = round(value + (1.0 / max(1, index)) - gate_penalty, 3)
        node_id = f"scheduler-node::{_slugify(experiment_id or str(index))}"
        nodes.append(
            {
                "node_id": node_id,
                "node_type": "experiment_action",
                "parent_id": nodes[0]["node_id"],
                "experiment_id": experiment_id,
                "action": str(candidate.get("action", "schedule")),
                "visit_count": max(1, int(abs(value) * 2)),
                "value_estimate": value,
                "ucb_score": ucb_score,
                "bo_acquisition": {
                    "expected_improvement": max(0.0, round(value / 10.0, 3)),
                    "exploration_bonus": round(1.0 / max(1, index), 3),
                    "cost_penalty": _float(candidate.get("cost_score", 0)),
                    "gate_penalty": gate_penalty,
                },
                "target_ids": _strings(candidate.get("target_ids", [])),
                "gate_state": gate_state,
                "executable": executable and not blocked_by_judge and gate_state != "blocked",
                "llm_recommended_action": llm_action,
                "validator_penalty": _float(candidate.get("validator_penalty", 0)),
            }
        )
        edges.append({"source": nodes[0]["node_id"], "target": node_id, "relation": "expands_experiment"})
    for index, route in enumerate(_items(route_selector_summary.get("route_nodes", []))[:40], start=1):
        route_id = str(route.get("node_id", "")).strip() or f"route-node::{index}"
        llm_action = str(route.get("llm_recommended_action", "")).strip()
        executable = llm_action != "block"
        value = _float(route.get("judge_adjusted_selection_score", route.get("selection_score", 0)))
        node_id = f"scheduler-node::route::{_slugify(route_id)}"
        nodes.append(
            {
                "node_id": node_id,
                "node_type": "route_action",
                "parent_id": nodes[0]["node_id"],
                "route_node_id": route_id,
                "action": str(route.get("action", "")),
                "visit_count": int(route.get("visit_count", 1) or 1),
                "value_estimate": value,
                "ucb_score": round(value + (1.0 / max(1, index)) - (1000.0 if not executable else 0.0), 3),
                "target_ids": _strings(route.get("target_ids", [])),
                "gate_state": "ready_to_schedule" if executable else "blocked",
                "executable": executable,
                "llm_recommended_action": llm_action,
                "selection_reason": str(route.get("best_selection_reason", route.get("selection_reason", ""))),
            }
        )
        edges.append({"source": nodes[0]["node_id"], "target": node_id, "relation": "expands_route"})
    for step in _items(research_campaign_plan_summary.get("multi_step_route_plan", []))[:20]:
        step_index = int(_float(step.get("step_index", 0)) or 0)
        route_action = str(step.get("route_action", "")).strip()
        if not step_index or not route_action:
            continue
        llm_action = str(step.get("llm_recommended_action", "")).strip()
        executable = llm_action != "block"
        value = _float(step.get("judge_adjusted_priority", max(1.0, 8.0 - float(step_index))))
        step_id = f"campaign-step::{step_index}::{route_action}"
        node_id = f"scheduler-node::campaign::{_slugify(step_id)}"
        nodes.append(
            {
                "node_id": node_id,
                "node_type": "campaign_step",
                "parent_id": nodes[0]["node_id"],
                "campaign_step_id": step_id,
                "campaign_stage": str(step.get("campaign_stage", "")),
                "action": route_action,
                "visit_count": max(1, 8 - step_index),
                "value_estimate": value,
                "ucb_score": round(value + (1.0 / max(1, step_index)) - (1000.0 if not executable else 0.0), 3),
                "target_ids": _strings(step.get("target_ids", [])),
                "gate_state": "ready_to_schedule" if executable else "blocked",
                "executable": executable,
                "llm_recommended_action": llm_action,
                "recommended_agents": _strings(step.get("recommended_agents", [])),
            }
        )
        edges.append({"source": nodes[0]["node_id"], "target": node_id, "relation": "expands_campaign_step"})
    executable_nodes = [item for item in nodes[1:] if item.get("executable", True)]
    best = sorted(executable_nodes, key=lambda item: float(item.get("ucb_score", 0)), reverse=True)
    best_experiment = sorted(
        [item for item in executable_nodes if item.get("node_type") == "experiment_action"],
        key=lambda item: float(item.get("ucb_score", 0)),
        reverse=True,
    )
    best_node = best[0] if best else {}
    best_research_action_id = (
        str(best_node.get("experiment_id", "")).strip()
        or str(best_node.get("route_node_id", "")).strip()
        or str(best_node.get("campaign_step_id", "")).strip()
    )
    return {
        "scheduler_search_kernel_id": f"scheduler-search-kernel::{_slugify(topic)}",
        "topic": topic,
        "search_mode": "mcts_bo_hybrid_summary",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "root_node_id": nodes[0]["node_id"],
        "best_node_id": best_node.get("node_id", ""),
        "best_research_action_id": best_research_action_id,
        "best_research_action_type": best_node.get("node_type", ""),
        "best_research_action": best_node.get("action", ""),
        "best_experiment_id": best_experiment[0].get("experiment_id", "") if best_experiment else "",
        "tree_nodes": nodes,
        "tree_edges": edges,
        "rollout_policy": [
            "prioritize high value-of-information actions",
            "treat blocked gates and LLM block recommendations as non-selectable search nodes",
            "penalize validator-blocked or repeat-failure candidates",
            "keep at least one exploratory candidate when uncertainty is high",
            "include experiment, route, and campaign-step nodes in one active-control search graph",
        ],
        "backpropagation_targets": ["belief_state", "failure_memory", "uncertainty_ledger", "provenance_graph"],
        "research_campaign_plan_summary": research_campaign_plan_summary,
        "route_selector_summary": route_selector_summary,
    }


def build_lab_meeting_protocol_summary(
    *,
    topic: str,
    research_state: dict[str, Any],
    claim_graph: dict[str, Any],
) -> dict[str, Any]:
    debate = research_state.get("scientific_debate_protocol_summary", {})
    roles = debate.get("roles", []) if isinstance(debate.get("roles", []), list) else []
    hypotheses = _items(claim_graph.get("hypotheses", []))
    negative_results = _items(claim_graph.get("negative_results", []))
    agenda = _strings(debate.get("agenda_items", [])) or ["review current route", "challenge assumptions", "decide next action"]
    rounds: list[dict[str, Any]] = []
    for index, role in enumerate(roles or [], start=1):
        if not isinstance(role, dict):
            continue
        role_name = str(role.get("role", f"role-{index}"))
        rounds.append(
            {
                "round_id": f"lab-meeting-round::{_slugify(topic)}::{index}",
                "speaker_role": role_name,
                "prompt": str(role.get("responsibility", "")),
                "required_evidence": _role_required_evidence(role_name),
                "must_record": ["position", "supporting_refs", "objections", "decision_impact"],
            }
        )
    consensus_gate = "blocked" if negative_results and hypotheses else "contested" if debate.get("open_disagreements") else "rough_consensus"
    return {
        "lab_meeting_protocol_id": f"lab-meeting-protocol::{_slugify(topic)}",
        "topic": topic,
        "agenda": agenda[:10],
        "round_count": len(rounds),
        "rounds": rounds,
        "consensus_gate": consensus_gate,
        "decision_outputs": [
            "accepted_claims",
            "revised_hypotheses",
            "blocked_routes",
            "next_experiment",
            "group_memory_updates",
            "minority_reports",
        ],
        "chair_policy": "do not mark consensus clear while skeptic or methodologist objections remain unresolved",
    }


def build_unified_provenance_graph_summary(
    *,
    topic: str,
    object_store_summary: dict[str, Any],
    run_manifest: dict[str, Any],
    research_state: dict[str, Any],
) -> dict[str, Any]:
    objects = _items(object_store_summary.get("objects", []))
    nodes = [
        {
            "node_id": str(item.get("object_id", "")),
            "node_type": str(item.get("object_type", "")),
            "label": str(item.get("label", "")),
            "status": str(item.get("status", "")),
            "source_system": str(item.get("source_system", "")),
        }
        for item in objects
        if str(item.get("object_id", "")).strip()
    ]
    edges: list[dict[str, Any]] = []
    for item in objects:
        source = str(item.get("object_id", "")).strip()
        for target in _strings(item.get("related_object_ids", [])):
            edges.append({"source": source, "target": target, "relation": "relates_to"})
        for ref in _strings(item.get("provenance_refs", [])):
            ref_id = f"provenance-ref::{_slugify(ref)}"
            nodes.append({"node_id": ref_id, "node_type": "provenance_ref", "label": ref, "status": "referenced", "source_system": "provenance"})
            edges.append({"source": source, "target": ref_id, "relation": "derived_from"})
    for item in _items(run_manifest.get("artifacts", [])):
        artifact_id = f"artifact::{_slugify(str(item.get('path', item.get('kind', 'artifact'))))}"
        nodes.append(
            {
                "node_id": artifact_id,
                "node_type": "artifact",
                "label": str(item.get("kind", "artifact")),
                "status": "exists" if item.get("exists") else "planned",
                "source_system": "run_manifest",
            }
        )
    event_summary = research_state.get("event_ledger_summary", {})
    if isinstance(event_summary, dict) and event_summary.get("event_count"):
        nodes.append(
            {
                "node_id": f"event-ledger::{_slugify(topic)}",
                "node_type": "event_ledger",
                "label": "workflow event ledger",
                "status": "active",
                "source_system": "event_ledger",
            }
        )
    unique_nodes = {node["node_id"]: node for node in nodes if node.get("node_id")}
    return {
        "unified_provenance_graph_id": f"unified-provenance-graph::{_slugify(topic)}",
        "topic": topic,
        "node_count": len(unique_nodes),
        "edge_count": len(edges),
        "node_type_counts": _count_by(list(unique_nodes.values()), "node_type"),
        "edge_type_counts": _count_by(edges, "relation"),
        "nodes": list(unique_nodes.values())[:200],
        "edges": edges[:300],
        "query_contract": [
            "trace_claim_to_evidence",
            "trace_hypothesis_to_validation_and_experiment",
            "trace_experiment_to_artifacts_and_memory",
            "trace_decision_to_model_usage_and_runtime_events",
        ],
    }


def build_discipline_native_kernel_summary(
    *,
    topic: str,
    discipline_adapter_summary: dict[str, Any],
    experiment_execution_loop_summary: dict[str, Any],
) -> dict[str, Any]:
    primary = str(discipline_adapter_summary.get("primary_discipline", "") or discipline_adapter_summary.get("selected_adapter_id", "")).lower()
    bindings = _items(discipline_adapter_summary.get("bindings", []))
    candidates = _items(experiment_execution_loop_summary.get("candidate_experiments", []))
    required = _discipline_required_contract(primary)
    coverage = {
        key: any(
            any(term in " ".join(_strings(binding.get(field, []))).lower() for term in terms)
            for binding in bindings
            for field in ["measurement_requirements", "artifact_requirements", "interpretation_boundaries", "scheduler_rules", "quality_gates"]
        )
        for key, terms in required.items()
    }
    missing = [key for key, present in coverage.items() if not present]
    return {
        "discipline_native_kernel_id": f"discipline-native-kernel::{_slugify(topic)}",
        "topic": topic,
        "primary_discipline": primary or "general_science",
        "binding_count": len(bindings),
        "candidate_count": len(candidates),
        "native_readiness": "high" if not missing and bindings else "medium" if len(missing) <= 2 and bindings else "low",
        "required_contract": required,
        "coverage": coverage,
        "missing_native_contracts": missing,
        "discipline_specific_next_steps": _discipline_next_steps(primary, missing),
    }


def build_next_cycle_decision_directives_summary(
    *,
    topic: str,
    benchmark_case_suite_summary: dict[str, Any],
    memory_governance_loop_summary: dict[str, Any],
    scheduler_search_kernel_summary: dict[str, Any],
    lab_meeting_protocol_summary: dict[str, Any],
    unified_provenance_graph_summary: dict[str, Any],
    discipline_native_kernel_summary: dict[str, Any],
) -> dict[str, Any]:
    preferred_agents: list[str] = []
    scheduler_constraints: list[str] = []
    memory_actions: list[str] = []
    human_gates: list[str] = []
    if benchmark_case_suite_summary.get("benchmark_readiness") == "low":
        preferred_agents.extend(["critic", "literature_reviewer", "experiment_designer"])
        human_gates.append("benchmark suite is low-readiness")
    for case_id in _strings(benchmark_case_suite_summary.get("fail_fast_cases", [])):
        scheduler_constraints.append(f"fail-fast benchmark case must pass: {case_id}")
    if int(memory_governance_loop_summary.get("risk_counts", {}).get("medium", 0) or 0) > 0:
        preferred_agents.extend(["lab_meeting_moderator", "belief_updater"])
        memory_actions.extend(
            str(item.get("action", ""))
            for item in _items(memory_governance_loop_summary.get("proposed_actions", []))[:8]
        )
    best_experiment = str(scheduler_search_kernel_summary.get("best_experiment_id", "")).strip()
    best_research_action = str(scheduler_search_kernel_summary.get("best_research_action_id", "")).strip()
    best_research_action_type = str(scheduler_search_kernel_summary.get("best_research_action_type", "")).strip()
    best_research_action_label = str(scheduler_search_kernel_summary.get("best_research_action", "")).strip()
    if best_experiment:
        scheduler_constraints.append(f"prefer scheduler search best experiment: {best_experiment}")
        preferred_agents.extend(["experiment_economist", "experiment_designer"])
    if best_research_action and best_research_action != best_experiment:
        scheduler_constraints.append(
            f"prefer scheduler search best research action: {best_research_action}"
            + (f" ({best_research_action_label})" if best_research_action_label else "")
        )
        if best_research_action_type == "route_action":
            preferred_agents.extend(["coordinator", "critic"])
        elif best_research_action_type == "campaign_step":
            preferred_agents.extend(["research_planner", "coordinator"])
    if lab_meeting_protocol_summary.get("consensus_gate") in {"blocked", "contested"}:
        preferred_agents.extend(["lab_meeting_moderator", "critic"])
        human_gates.append("lab meeting consensus is blocked or contested")
    if int(unified_provenance_graph_summary.get("edge_count", 0) or 0) < max(1, int(unified_provenance_graph_summary.get("node_count", 0) or 0) // 3):
        preferred_agents.extend(["belief_updater", "data_curator"])
        scheduler_constraints.append("do not release claims until provenance edges are strengthened")
    if discipline_native_kernel_summary.get("native_readiness") == "low":
        preferred_agents.extend(["experiment_designer", "quality_control_reviewer", "safety_ethics_reviewer"])
        scheduler_constraints.extend(_strings(discipline_native_kernel_summary.get("discipline_specific_next_steps", []))[:5])
    campaign = (
        scheduler_search_kernel_summary.get("research_campaign_plan_summary", {})
        if isinstance(scheduler_search_kernel_summary.get("research_campaign_plan_summary", {}), dict)
        else {}
    )
    if campaign.get("scheduler_constraints"):
        scheduler_constraints.extend(_strings(campaign.get("scheduler_constraints", []))[:6])
    directive_state = "human_review_required" if human_gates else "ready_for_autonomous_next_cycle"
    return {
        "next_cycle_decision_directives_id": f"next-cycle-directives::{_slugify(topic)}",
        "topic": topic,
        "directive_state": directive_state,
        "preferred_agents": _dedupe(preferred_agents)[:10],
        "scheduler_constraints": _dedupe(scheduler_constraints)[:12],
        "memory_actions": _dedupe(memory_actions)[:12],
        "human_gates": _dedupe(human_gates)[:12],
        "top_experiment_id": best_experiment,
        "top_research_action_id": best_research_action,
        "top_research_action_type": best_research_action_type,
        "top_research_action": best_research_action_label,
        "closed_loop_inputs": [
            "benchmark_case_suite_summary",
            "memory_governance_loop_summary",
            "scheduler_search_kernel_summary",
            "research_campaign_plan_summary",
            "lab_meeting_protocol_summary",
            "unified_provenance_graph_summary",
            "discipline_native_kernel_summary",
        ],
    }


def build_scientific_kernel_state_summary(
    *,
    topic: str,
    project_id: str = "",
    summaries: dict[str, Any],
) -> dict[str, Any]:
    sections = {
        "objects": "scientific_object_store_summary",
        "graph": "unified_provenance_graph_summary",
        "memory": "memory_governance_loop_summary",
        "uncertainty": "uncertainty_ledger_summary",
        "problem_reframing": "scientific_problem_reframer_summary",
        "hypotheses": "hypothesis_validation_summary",
        "hypothesis_system": "hypothesis_system_summary",
        "theory_prediction": "theory_prediction_compiler_summary",
        "evidence": "evidence_review_summary",
        "experiments": "experiment_execution_loop_summary",
        "workflow_control": "workflow_control_summary",
        "debate": "lab_meeting_protocol_summary",
        "evaluation": "benchmark_case_suite_summary",
        "evaluation_system": "scientific_evaluation_system_summary",
        "anomaly_detection": "anomaly_surprise_detector_summary",
        "credit_ledger": "scientific_credit_responsibility_ledger_summary",
        "campaign": "research_campaign_plan_summary",
        "discipline": "discipline_native_kernel_summary",
        "toolchain": "discipline_toolchain_binding_summary",
        "risk_permissions": "experiment_risk_permission_summary",
        "context": "scientific_context_policy_summary",
        "directives": "next_cycle_decision_directives_summary",
    }
    missing = [name for name, key in sections.items() if not summaries.get(key)]
    blocking = []
    directives = summaries.get("next_cycle_decision_directives_summary", {})
    if isinstance(directives, dict) and directives.get("human_gates"):
        blocking.extend(_strings(directives.get("human_gates", [])))
    campaign = summaries.get("research_campaign_plan_summary", {})
    if isinstance(campaign, dict) and campaign.get("planner_state") == "needs_campaign_context":
        blocking.append("research campaign planner needs campaign context")
    release_gate = summaries.get("scientific_release_gate_summary", {})
    if isinstance(release_gate, dict) and release_gate.get("release_state") == "blocked":
        blocking.extend(_strings(release_gate.get("blocking_reasons", [])))
    workflow_control = summaries.get("workflow_control_summary", {})
    if isinstance(workflow_control, dict) and workflow_control.get("control_state") == "blocked":
        blocking.extend(_strings(workflow_control.get("blocking_gates", [])))
    return {
        "scientific_kernel_state_id": f"scientific-kernel-state::{_slugify(project_id or 'workspace')}::{_slugify(topic)}",
        "topic": topic,
        "project_id": project_id,
        "contract_version": "v1",
        "section_keys": sections,
        "available_sections": [name for name, key in sections.items() if summaries.get(key)],
        "missing_sections": missing,
        "kernel_state": "blocked" if blocking else "operational" if not missing else "partial",
        "blocking_reasons": _dedupe(blocking)[:20],
        "next_action": (
            "resolve_kernel_blocks"
            if blocking
            else str(directives.get("top_experiment_id", "")) or "continue_research_cycle"
        ),
    }


def build_scientific_error_taxonomy_summary(
    *,
    topic: str,
    research_state: dict[str, Any],
    claim_graph: dict[str, Any],
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    validation = research_state.get("hypothesis_validation_summary", {})
    for item in _items(validation.get("records", [])):
        flags = _strings(item.get("validator_flags", []))
        for flag in flags:
            errors.append(_error_record(topic, "hypothesis_error", flag, "medium", [str(item.get("hypothesis_id", ""))]))
    evidence = research_state.get("evidence_review_summary", {})
    for blocker in _strings(evidence.get("review_blockers", [])):
        errors.append(_error_record(topic, "evidence_error", blocker, "high", []))
    for gap in _strings(research_state.get("systematic_review_summary", {}).get("review_protocol_gaps", [])):
        errors.append(_error_record(topic, "evidence_error", gap, "medium", []))
    for item in _items(claim_graph.get("negative_results", [])):
        errors.append(
            _error_record(
                topic,
                "experiment_error",
                str(item.get("result", "negative or failed attempt")).strip(),
                "medium",
                _strings(item.get("affected_hypothesis_ids", [])),
            )
        )
    debate = research_state.get("lab_meeting_protocol_summary", {})
    if isinstance(debate, dict) and debate.get("consensus_gate") in {"blocked", "contested"}:
        errors.append(_error_record(topic, "collaboration_error", "consensus remains blocked or contested", "medium", []))
    provenance = research_state.get("unified_provenance_graph_summary", {})
    if isinstance(provenance, dict) and int(provenance.get("edge_count", 0) or 0) < int(provenance.get("node_count", 0) or 0) // 3:
        errors.append(_error_record(topic, "provenance_error", "provenance graph has weak edge density", "medium", []))
    replay = research_state.get("provenance_replay_summary", {})
    if not isinstance(replay, dict):
        replay = {}
    if int(replay.get("fact_count", 0) or 0) == 0:
        errors.append(_error_record(topic, "provenance_error", "no provenance facts are available for replay", "high", []))
    elif (
        int(replay.get("claim_count", 0) or 0) + int(replay.get("hypothesis_count", 0) or 0) == 0
        or int(replay.get("evidence_count", 0) or 0) + int(replay.get("experiment_count", 0) or 0) == 0
    ):
        errors.append(_error_record(topic, "provenance_error", "provenance replay cannot reconstruct both claims/hypotheses and evidence/experiments", "medium", []))
    model = research_state.get("model_reliability_layer_summary", {})
    for item in _items(model.get("records", [])):
        for flag in _strings(item.get("reliability_flags", [])):
            errors.append(_error_record(topic, "model_error", flag, "medium", [str(item.get("profile_name", ""))]))
    return {
        "scientific_error_taxonomy_id": f"scientific-error-taxonomy::{_slugify(topic)}",
        "topic": topic,
        "error_count": len(errors),
        "error_type_counts": _count_by(errors, "error_type"),
        "severity_counts": _count_by(errors, "severity"),
        "records": errors[:100],
        "taxonomy": [
            "evidence_error",
            "hypothesis_error",
            "experiment_error",
            "analysis_error",
            "interpretation_error",
            "memory_error",
            "collaboration_error",
            "model_error",
            "provenance_error",
        ],
    }


def build_scientific_release_gate_summary(
    *,
    topic: str,
    research_state: dict[str, Any],
) -> dict[str, Any]:
    provenance_replay = research_state.get("provenance_replay_summary", {})
    if not isinstance(provenance_replay, dict):
        provenance_replay = {}
    fact_count = int(provenance_replay.get("fact_count", 0) or 0)
    replay_claim_count = int(provenance_replay.get("claim_count", 0) or 0)
    replay_hypothesis_count = int(provenance_replay.get("hypothesis_count", 0) or 0)
    replay_evidence_count = int(provenance_replay.get("evidence_count", 0) or 0)
    replay_experiment_count = int(provenance_replay.get("experiment_count", 0) or 0)
    checks = {
        "evidence_sufficient": research_state.get("evidence_review_summary", {}).get("review_readiness") in {"ready", "decision_ready"},
        "systematic_review_not_blocked": research_state.get("systematic_review_summary", {}).get("synthesis_state") != "blocked",
        "hypotheses_falsifiable": not bool(research_state.get("hypothesis_validation_summary", {}).get("low_falsifiability_hypotheses")),
        "problem_frame_checked": bool(research_state.get("scientific_problem_reframer_summary", {})),
        "theory_predictions_compiled": research_state.get("theory_prediction_compiler_summary", {}).get("formalization_readiness") in {"medium", "high", ""},
        "uncertainty_acknowledged": bool(research_state.get("uncertainty_ledger_summary", {})),
        "provenance_complete": int(research_state.get("unified_provenance_graph_summary", {}).get("edge_count", 0) or 0) > 0 or fact_count > 0,
        "provenance_facts_exist": fact_count > 0,
        "claim_or_hypothesis_fact_backed": replay_claim_count > 0 or replay_hypothesis_count > 0,
        "evidence_or_experiment_fact_backed": replay_evidence_count > 0 or replay_experiment_count > 0,
        "reproducibility_package_exists": research_state.get("reproducibility_kernel_summary", {}).get("readiness") in {"medium", "high"},
        "debate_not_blocked": research_state.get("lab_meeting_protocol_summary", {}).get("consensus_gate") not in {"blocked"},
        "failed_attempts_considered": bool(research_state.get("failure_reuse_engine_summary", {})),
        "discipline_native_passed": research_state.get("discipline_native_kernel_summary", {}).get("native_readiness") in {"medium", "high"},
        "discipline_toolchain_bound": research_state.get("discipline_toolchain_binding_summary", {}).get("binding_readiness") in {"medium", "high", ""},
        "context_policy_ready": bool(research_state.get("scientific_context_policy_summary", {})),
        "risk_permissions_clear": research_state.get("experiment_risk_permission_summary", {}).get("permission_state") != "blocked",
        "benchmark_cases_passed": research_state.get("benchmark_case_suite_summary", {}).get("benchmark_readiness") in {"medium", "high"},
        "benchmark_quality_passed": research_state.get("benchmark_case_suite_summary", {}).get("quality_gate_state") in {"passed", ""},
        "scientific_evaluation_benchmark_usable": research_state.get("benchmark_case_suite_summary", {}).get(
            "scientific_evaluation_benchmark_state",
            "",
        )
        in {"usable", "strong", ""},
        "high_surprises_resolved": research_state.get("anomaly_surprise_detector_summary", {}).get("surprise_level") != "high",
        "credit_responsibility_recorded": bool(research_state.get("scientific_credit_responsibility_ledger_summary", {}).get("record_count", 0))
        or not bool(research_state.get("scientific_credit_responsibility_ledger_summary", {})),
    }
    failed = [name for name, passed in checks.items() if not passed]
    blocking_reasons = [_release_gate_blocking_reason(name) for name in failed]
    release_state = "release_ready" if not failed else "needs_targeted_repairs" if len(failed) <= 3 else "blocked"
    return {
        "scientific_release_gate_id": f"scientific-release-gate::{_slugify(topic)}",
        "topic": topic,
        "release_state": release_state,
        "check_count": len(checks),
        "passed_count": sum(1 for passed in checks.values() if passed),
        "failed_count": len(failed),
        "checks": checks,
        "provenance_replay_summary": provenance_replay,
        "failed_checks": failed,
        "blocking_reasons": blocking_reasons,
        "allowed_outputs": _allowed_outputs(release_state),
    }


def build_memory_conflict_version_graph_summary(
    *,
    topic: str,
    research_state: dict[str, Any],
    claim_graph: dict[str, Any],
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for item in _items(claim_graph.get("memory_updates", [])):
        node_id = f"memory-version::{_slugify(str(item.get('filename', 'memory')))}"
        nodes.append(
            {
                "node_id": node_id,
                "memory_file": str(item.get("filename", "")),
                "status": str(item.get("status", "active")),
                "updated_by": str(item.get("updated_by", "")),
            }
        )
        hypothesis_id = str(item.get("hypothesis_id", "")).strip()
        if hypothesis_id:
            edges.append({"source": node_id, "target": hypothesis_id, "relation": "describes"})
    for item in _items(claim_graph.get("negative_results", [])):
        failure_id = str(item.get("negative_result_id", "")).strip()
        for target in _strings(item.get("affected_hypothesis_ids", [])):
            edges.append({"source": failure_id, "target": target, "relation": "challenges"})
    error_summary = research_state.get("scientific_error_taxonomy_summary", {})
    for item in _items(error_summary.get("records", [])):
        if item.get("error_type") == "memory_error":
            nodes.append(
                {
                    "node_id": str(item.get("error_id", "")),
                    "memory_file": "",
                    "status": "conflict",
                    "updated_by": "scientific_error_taxonomy",
                }
            )
    return {
        "memory_conflict_version_graph_id": f"memory-conflict-version-graph::{_slugify(topic)}",
        "topic": topic,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "conflict_count": sum(1 for node in nodes if node.get("status") == "conflict"),
        "nodes": nodes[:100],
        "edges": edges[:200],
        "policy": {
            "never_overwrite_conflicting_memory": True,
            "prefer_conditional_revision_over_deletion": True,
            "quarantine_public_promotion_when_conflicted": True,
        },
    }


def load_builtin_benchmark_case_files(root: str | Path | None = None) -> list[dict[str, Any]]:
    base = Path(root) if root else Path(__file__).resolve().parent / "benchmarks" / "cases"
    if (base / "cases").exists():
        base = base / "cases"
    cases: list[dict[str, Any]] = []
    if not base.exists():
        return cases
    for path in sorted(base.glob("*.yaml")):
        cases.append({"case_id": path.stem, "path": str(path), "content": path.read_text(encoding="utf-8")})
    return cases


def _parse_benchmark_case_yaml(content: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    current_key = ""
    nested_key = ""
    for raw_line in content.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        if indent == 0 and ":" in line:
            key, value = line.split(":", 1)
            current_key = key.strip()
            nested_key = ""
            value = value.strip()
            if value:
                result[current_key] = value.strip('"').strip("'")
            else:
                result[current_key] = [] if current_key in {"expected_outputs", "rubric"} else {}
            continue
        if line.startswith("- "):
            value = line[2:].strip().strip('"').strip("'")
            if nested_key:
                parent = result.setdefault(current_key, {})
                if isinstance(parent, dict):
                    parent.setdefault(nested_key, []).append(value)
            elif current_key:
                bucket = result.setdefault(current_key, [])
                if isinstance(bucket, list):
                    bucket.append(value)
            continue
        if indent > 0 and ":" in line and current_key:
            key, value = line.split(":", 1)
            nested_key = key.strip()
            parent = result.setdefault(current_key, {})
            if isinstance(parent, dict):
                value = value.strip()
                parent[nested_key] = value.strip('"').strip("'") if value else []
    return result


def _claim_graph_context_from_replay(replay: dict[str, Any]) -> dict[str, Any]:
    claims: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    hypotheses: list[dict[str, Any]] = []
    negative_results: list[dict[str, Any]] = []
    asset_registry: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    for item in _items(replay.get("claims", [])):
        fields = item.get("fields", {}) if isinstance(item.get("fields", {}), dict) else {}
        claims.append(
            {
                "global_claim_id": str(item.get("id", "")),
                "statement": str(fields.get("states", "")) or str(item.get("id", "")),
                "source_refs": _strings(item.get("source_refs", [])),
                "fact_ids": _strings(item.get("fact_ids", [])),
            }
        )
    for item in _items(replay.get("evidence", [])):
        fields = item.get("fields", {}) if isinstance(item.get("fields", {}), dict) else {}
        evidence.append(
            {
                "global_evidence_id": str(item.get("id", "")),
                "summary": str(fields.get("summarizes", "")) or str(item.get("id", "")),
                "source_refs": _strings(item.get("source_refs", [])),
                "fact_ids": _strings(item.get("fact_ids", [])),
            }
        )
    for item in _items(replay.get("hypotheses", [])):
        fields = item.get("fields", {}) if isinstance(item.get("fields", {}), dict) else {}
        record = fields.get("has_record", {}) if isinstance(fields.get("has_record", {}), dict) else {}
        hypotheses.append(
            {
                **record,
                "global_hypothesis_id": str(item.get("id", "")),
                "name": str(record.get("name", "")) or str(item.get("id", "")),
                "fact_ids": _strings(item.get("fact_ids", [])),
            }
        )
    for item in _items(replay.get("artifacts", [])):
        fields = item.get("fields", {}) if isinstance(item.get("fields", {}), dict) else {}
        value = next((value for value in fields.values() if isinstance(value, dict)), {})
        asset_registry.append(
            {
                **(value if isinstance(value, dict) else {}),
                "asset_id": str(item.get("id", "")),
                "fact_ids": _strings(item.get("fact_ids", [])),
            }
        )
    for relation in _items(replay.get("relations", [])):
        source_id = str(relation.get("source_id", "")).strip()
        target_id = str(relation.get("target_id", "")).strip()
        rel = str(relation.get("relation", "")).strip()
        if source_id and target_id and rel:
            edges.append({"source": source_id, "target": target_id, "relation": rel})
            if rel == "challenges":
                negative_results.append(
                    {
                        "negative_result_id": source_id,
                        "result": source_id,
                        "affected_hypothesis_ids": [target_id],
                    }
                )
    return {
        "claims": claims,
        "evidence": evidence,
        "hypotheses": hypotheses,
        "negative_results": list({str(item.get("negative_result_id", "")): item for item in negative_results}.values()),
        "asset_registry": asset_registry,
        "edges": edges,
    }


def _research_state_context_from_replay(
    replay: dict[str, Any],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    experiments = _items(replay.get("experiments", []))
    artifacts = _items(replay.get("artifacts", []))
    experiment_queue = []
    execution_packages = []
    for item in experiments:
        fields = item.get("fields", {}) if isinstance(item.get("fields", {}), dict) else {}
        subject_id = str(item.get("id", ""))
        if "scheduled_by" in fields:
            experiment_queue.append(
                {
                    "experiment_id": subject_id,
                    "schedule_state": "ready_to_schedule",
                    "source_system": "provenance_replay",
                }
            )
        if "execution_package_for" in fields:
            execution_packages.append(
                {
                    "package_id": subject_id,
                    "experiment_id": str(fields.get("execution_package_for", "")),
                    "package_state": "ready_for_handoff",
                    "source_system": "provenance_replay",
                }
            )
    return {
        "provenance_replay_summary": {
            "fact_count": replay.get("fact_count", 0),
            "claim_count": replay.get("claim_count", 0),
            "hypothesis_count": replay.get("hypothesis_count", 0),
            "evidence_count": replay.get("evidence_count", 0),
            "experiment_count": replay.get("experiment_count", 0),
            "artifact_count": replay.get("artifact_count", 0),
        },
        "experiment_execution_loop_summary": {
            "execution_queue": experiment_queue,
            "candidate_count": len(experiment_queue),
        },
        "execution_adapter_registry_summary": {
            "execution_packages": execution_packages,
            "execution_package_count": len(execution_packages),
            "ready_package_count": len(execution_packages),
        },
        "run_handoff_contract_summary": {
            "contracts": [
                {"package_id": item.get("package_id", ""), "contract_state": "replayed"}
                for item in execution_packages
            ],
            "contract_count": len(execution_packages),
        },
        "unified_provenance_graph_summary": {
            "nodes": _items(snapshot.get("node_ids", [])),
            "edges": _items(snapshot.get("edge_ids", [])),
            "node_count": len(snapshot.get("node_ids", []) if isinstance(snapshot.get("node_ids", []), list) else []),
            "edge_count": len(snapshot.get("edge_ids", []) if isinstance(snapshot.get("edge_ids", []), list) else []),
        },
        "reproducibility_kernel_summary": {
            "replay_contract": {
                "snapshot_id": str(snapshot.get("snapshot_id", "")),
                "fact_count": replay.get("fact_count", 0),
                "artifact_count": len(artifacts),
            },
            "readiness": "medium" if replay.get("fact_count", 0) else "low",
        },
    }


def _run_manifest_context_from_replay(replay: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    artifacts = []
    for item in _items(replay.get("artifacts", [])):
        fields = item.get("fields", {}) if isinstance(item.get("fields", {}), dict) else {}
        value = next((value for value in fields.values() if isinstance(value, dict)), {})
        artifacts.append(
            {
                **(value if isinstance(value, dict) else {}),
                "id": str(item.get("id", "")),
                "source_system": "provenance_replay",
            }
        )
    return {
        "artifacts": artifacts,
        "usage_summary": {
            "source": "provenance_replay",
            "snapshot_id": str(snapshot.get("snapshot_id", "")),
            "fact_count": replay.get("fact_count", 0),
        },
    }


def _baseline_cases_by_id(baseline: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if not isinstance(baseline, dict):
        return {}
    candidates = baseline.get("cases", [])
    if not isinstance(candidates, list):
        nested = baseline.get("benchmark_regression_suite", {})
        if isinstance(nested, dict):
            candidates = nested.get("cases", [])
    if not isinstance(candidates, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in candidates:
        if not isinstance(item, dict):
            continue
        case_id = str(item.get("case_id", "")).strip()
        if case_id:
            result[case_id] = item
    return result


def _resolve_context_path(context: dict[str, Any], path: str) -> Any:
    current: Any = context
    for part in [item for item in path.split(".") if item]:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except Exception:
                return None
        else:
            return None
    return current


def _path_value_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (list, dict, str)):
        return bool(value)
    if isinstance(value, (int, float)):
        return value != 0
    return True


def _benchmark_expected_value_results(
    *,
    expected_values: dict[str, Any],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path, expected in expected_values.items():
        resolved = _resolve_context_path(context, str(path))
        passed = _expected_value_matches(resolved, expected)
        results.append(
            {
                "path": str(path),
                "expected": expected,
                "actual": resolved,
                "status": "passed" if passed else "failed",
                "finding": "" if passed else f"expected {path} to match {expected!r}, got {resolved!r}",
            }
        )
    return results


def _expected_value_matches(actual: Any, expected: Any) -> bool:
    expected_text = str(expected).strip()
    if expected_text.startswith("contains:"):
        needle = expected_text.split(":", 1)[1].strip()
        if isinstance(actual, list):
            return any(needle in str(item) for item in actual)
        return needle in str(actual)
    if expected_text.startswith("not:"):
        forbidden = expected_text.split(":", 1)[1].strip()
        return str(actual).strip() != forbidden
    if expected_text in {"true", "false"}:
        return bool(actual) is (expected_text == "true")
    return str(actual).strip() == expected_text


def _benchmark_rubric_results(
    *,
    case: dict[str, Any],
    context: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rubric = _strings(case.get("rubric", [])) or ["expected outputs are present"]
    context_text = str(context).lower()
    results: list[dict[str, Any]] = []
    for item in rubric:
        lowered = item.lower()
        keywords = [
            token
            for token in lowered.replace("/", " ").replace("-", " ").split()
            if len(token) >= 5
        ][:6]
        matched_keywords = [token for token in keywords if token in context_text]
        passed = bool(evidence) and (not keywords or bool(matched_keywords))
        results.append(
            {
                "rubric_item": item,
                "status": "passed" if passed else "needs_review",
                "matched_keywords": matched_keywords,
                "finding": "" if passed else f"rubric signal not found strongly enough: {item}",
            }
        )
    return results


def _benchmark_task(task_id: str, description: str, passed: bool) -> dict[str, Any]:
    return {"task_id": task_id, "description": description, "passed": bool(passed), "evidence": []}


def _benchmark_quality_score(task: dict[str, Any], research_state: dict[str, Any], claim_graph: dict[str, Any]) -> float:
    task_id = task["task_id"]
    score = 0.4 if task["passed"] else 0.15
    if task_id == "literature_systematicity":
        review = research_state.get("systematic_review_summary", {})
        score += min(
            0.6,
            0.1
            * len(
                review.get("evidence_table", [])
                if isinstance(review.get("evidence_table", []), list)
                else []
            ),
        )
    elif task_id == "theory_prediction":
        compiler = research_state.get("theory_prediction_compiler_summary", {})
        score += min(0.6, 0.15 * int(compiler.get("discriminating_test_count", 0) or 0))
    elif task_id == "anomaly_response":
        anomaly = research_state.get("anomaly_surprise_detector_summary", {})
        score += 0.3 if anomaly.get("scheduler_constraints") else 0.0
    elif task_id == "credit_responsibility":
        ledger = research_state.get("scientific_credit_responsibility_ledger_summary", {})
        score += min(0.6, 0.08 * int(ledger.get("record_count", 0) or 0))
    elif task_id == "problem_reframing":
        reframer = research_state.get("scientific_problem_reframer_summary", {})
        score += 0.3 if reframer.get("scheduler_constraints") else 0.0
    elif task_id == "closed_loop_execution":
        score += 0.3 if claim_graph.get("executor_belief_backpropagation_summary") else 0.0
    return round(min(1.0, score), 3)


def _canonical_stage(stage: str) -> str:
    return {
        "question": "question_formulation",
        "review": "literature_review",
        "hypothesis": "hypothesis_generation",
        "design": "experiment_design",
        "execute": "running",
        "analyze": "interpretation",
        "decide": "decision",
        "report": "publishable",
    }.get(stage, stage or "question_formulation")


def _legal_next_states(state: str) -> list[str]:
    return {
        "question_formulation": ["literature_review"],
        "literature_review": ["hypothesis_generation", "literature_review"],
        "hypothesis_generation": ["hypothesis_validation"],
        "hypothesis_validation": ["experiment_design", "hypothesis_generation"],
        "experiment_design": ["execution_ready", "hypothesis_validation"],
        "human_governance": ["paused", "experiment_design", "literature_review"],
        "execution_ready": ["running"],
        "running": ["quality_review"],
        "quality_review": ["interpretation", "running"],
        "interpretation": ["belief_update", "experiment_design"],
        "belief_update": ["decision"],
        "decision": ["experiment_design", "publishable", "paused"],
        "publishable": [],
        "paused": ["literature_review", "experiment_design"],
    }.get(state, ["literature_review"])


def _transition_guards(research_state: dict[str, Any]) -> list[str]:
    guards: list[str] = []
    if research_state.get("missing_prerequisites"):
        guards.append("missing_prerequisites_must_be_resolved")
    if research_state.get("hypothesis_gate_summary", {}).get("gate_state") in {"blocked", "revision_required"}:
        guards.append("hypothesis_gate_must_clear")
    if research_state.get("evidence_review_summary", {}).get("review_blockers"):
        guards.append("evidence_review_blockers_must_clear")
    if research_state.get("human_governance_checkpoint_summary", {}).get("open_checkpoint_count"):
        guards.append("human_governance_checkpoint_open")
    if research_state.get("experiment_risk_permission_summary", {}).get("permission_state") in {"blocked", "requires_human_approval"}:
        guards.append("experiment_risk_permission_must_clear")
    return guards


def _benchmark_case(
    case_id: str,
    description: str,
    evidence_objects: list[dict[str, Any]],
    rubric: list[str],
    passed: bool,
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "description": description,
        "priority": "P0" if case_id in {"hypothesis_validator", "provenance_replay"} else "P1",
        "status": "passed" if passed else "failed",
        "rubric": rubric,
        "evidence_object_count": len(evidence_objects),
        "failure_mode": "" if passed else f"{case_id} did not meet the minimum rubric",
    }


def _role_required_evidence(role_name: str) -> list[str]:
    role = role_name.lower()
    if role == "supporter":
        return ["supporting papers", "positive experiments", "boundary conditions"]
    if role == "skeptic":
        return ["negative results", "alternative mechanisms", "confounders"]
    if role == "methodologist":
        return ["controls", "protocol", "quality gates", "reproducibility contract"]
    if role == "statistician":
        return ["uncertainty ledger", "effect size", "power or sensitivity analysis"]
    if role == "chair":
        return ["positions", "unresolved objections", "decision rule"]
    return ["claim statement", "hypothesis refs", "evidence refs"]


def _research_objective_contract(*, topic: str, research_state: dict[str, Any], claim_graph: dict[str, Any]) -> dict[str, Any]:
    plan = research_state.get("research_plan_summary", {}) if isinstance(research_state.get("research_plan_summary", {}), dict) else {}
    reframer = research_state.get("scientific_problem_reframer_summary", {}) if isinstance(research_state.get("scientific_problem_reframer_summary", {}), dict) else {}
    goal = str(plan.get("research_goal", "") or reframer.get("reframed_problem", "") or topic).strip()
    scope = _strings(plan.get("scope", [])) or _strings(reframer.get("scope_constraints", []))
    success = _strings(plan.get("success_criteria", [])) or [
        "decision-grade evidence map exists",
        "at least one falsifiable hypothesis has explicit predictions",
        "next experiment or proof obligation is justified by information value",
    ]
    failure = _strings(plan.get("failure_criteria", [])) or [
        "core hypothesis cannot be made falsifiable",
        "available evidence is too weak or conflicted for decision use",
        "resource cost exceeds expected information value",
    ]
    boundary = _strings(plan.get("boundary_conditions", [])) or _strings(reframer.get("boundary_conditions", []))
    milestones = _strings(plan.get("milestones", [])) or [
        "question framed",
        "evidence map compiled",
        "hypotheses gated",
        "experiment or proof route scheduled",
        "belief state updated",
    ]
    missing = []
    if not goal:
        missing.append("research_goal")
    if not scope:
        missing.append("scope")
    if len(success) < 2:
        missing.append("success_criteria")
    if len(failure) < 2:
        missing.append("failure_criteria")
    if not boundary:
        missing.append("boundary_conditions")
    return {
        "goal": goal,
        "scope": scope[:8],
        "success_criteria": success[:8],
        "failure_criteria": failure[:8],
        "boundary_conditions": boundary[:8],
        "milestones": milestones[:10],
        "claim_count": len(_items(claim_graph.get("claims", []))),
        "hypothesis_count": len(_items(claim_graph.get("hypotheses", []))),
        "contract_state": "operational" if not missing else "underspecified",
        "missing_fields": missing,
    }


def _hypothesis_lifecycle_map(*, research_state: dict[str, Any], claim_graph: dict[str, Any]) -> dict[str, Any]:
    theory = research_state.get("hypothesis_theory_summary", {}) if isinstance(research_state.get("hypothesis_theory_summary", {}), dict) else {}
    validations = research_state.get("hypothesis_validation_summary", {}) if isinstance(research_state.get("hypothesis_validation_summary", {}), dict) else {}
    gate = research_state.get("hypothesis_gate_summary", {}) if isinstance(research_state.get("hypothesis_gate_summary", {}), dict) else {}
    negative_results = _items(claim_graph.get("negative_results", []))
    validation_records = _items(validations.get("records", []))
    gate_records = _items(gate.get("records", []))
    by_id: dict[str, dict[str, Any]] = {}
    for item in _items(claim_graph.get("hypotheses", [])):
        hypothesis_id = str(item.get("global_hypothesis_id", "") or item.get("hypothesis_id", "")).strip()
        if not hypothesis_id:
            continue
        by_id[hypothesis_id] = {
            "hypothesis_id": hypothesis_id,
            "name": str(item.get("name", "")).strip() or hypothesis_id,
            "status": str(item.get("status", "active")).strip() or "active",
            "lifecycle_state": "proposed",
            "competing_hypothesis_ids": [],
            "negative_result_refs": [],
            "missing_theory_fields": [],
            "recommended_transition": "validate",
        }
    for obj in _items(theory.get("objects", [])):
        hypothesis_id = str(obj.get("hypothesis_id", "")).strip()
        if not hypothesis_id:
            continue
        record = by_id.setdefault(hypothesis_id, {"hypothesis_id": hypothesis_id, "name": hypothesis_id})
        record.update(
            {
                "lifecycle_state": _lifecycle_from_theory_object(obj),
                "competing_hypothesis_ids": _strings(obj.get("competing_hypothesis_ids", [])),
                "negative_result_refs": _strings(obj.get("negative_result_refs", [])),
                "missing_theory_fields": _strings(obj.get("missing_theory_fields", [])),
                "recommended_transition": _transition_from_theory_object(obj),
            }
        )
    for record in validation_records:
        hypothesis_id = str(record.get("hypothesis_id", "")).strip()
        if hypothesis_id in by_id:
            by_id[hypothesis_id]["validator_summary"] = record
    for record in gate_records:
        hypothesis_id = str(record.get("hypothesis_id", "")).strip()
        if hypothesis_id in by_id:
            by_id[hypothesis_id]["gate_summary"] = record
    for result in negative_results:
        result_id = str(result.get("negative_result_id", "") or result.get("id", "")).strip()
        for hypothesis_id in _strings(result.get("affected_hypothesis_ids", [])):
            if hypothesis_id in by_id:
                by_id[hypothesis_id].setdefault("negative_result_refs", []).append(result_id)
                by_id[hypothesis_id]["lifecycle_state"] = "challenged"
                by_id[hypothesis_id]["recommended_transition"] = "revise_or_retire"
    records = list(by_id.values())
    return {
        "record_count": len(records),
        "state_counts": _count_by(records, "lifecycle_state"),
        "advance_count": len([item for item in records if item.get("recommended_transition") == "advance"]),
        "revise_or_retire_count": len([item for item in records if item.get("recommended_transition") in {"revise", "revise_or_retire", "retire"}]),
        "records": records[:100],
    }


def _evidence_map(*, research_state: dict[str, Any], claim_graph: dict[str, Any]) -> dict[str, Any]:
    evidence_review = research_state.get("evidence_review_summary", {}) if isinstance(research_state.get("evidence_review_summary", {}), dict) else {}
    compiler = research_state.get("literature_claim_compiler_summary", {}) if isinstance(research_state.get("literature_claim_compiler_summary", {}), dict) else {}
    links = _items(evidence_review.get("evidence_claim_links", [])) or _items(compiler.get("claim_evidence_links", []))
    evidence_items = _items(claim_graph.get("evidence", []))
    claims = _items(claim_graph.get("claims", []))
    support_counts: dict[str, int] = {}
    refute_counts: dict[str, int] = {}
    for link in links:
        claim_id = str(link.get("claim_id", "") or link.get("target", "")).strip()
        relation = str(link.get("relation", "supports")).strip().lower()
        if not claim_id:
            continue
        if relation in {"refutes", "contradicts", "against"}:
            refute_counts[claim_id] = refute_counts.get(claim_id, 0) + 1
        else:
            support_counts[claim_id] = support_counts.get(claim_id, 0) + 1
    unsupported = []
    contested = []
    for claim in claims:
        claim_id = str(claim.get("global_claim_id", "") or claim.get("claim_id", "") or claim.get("id", "")).strip()
        if not claim_id:
            continue
        if not support_counts.get(claim_id) and not _strings(claim.get("supports", [])):
            unsupported.append(claim_id)
        if refute_counts.get(claim_id) or str(claim.get("status", "")).lower() in {"contested", "conflicted"}:
            contested.append(claim_id)
    return {
        "claim_count": len(claims),
        "evidence_count": len(evidence_items),
        "link_count": len(links),
        "unsupported_claim_ids": unsupported[:20],
        "contested_claim_ids": contested[:20],
        "quality_balance": evidence_review.get("evidence_grade_balance", {}),
        "bias_risk_summary": evidence_review.get("bias_risk_summary", {}),
        "review_readiness": evidence_review.get("review_readiness", "draft"),
        "map_state": "decision_grade" if evidence_review.get("review_readiness") == "decision_ready" and not unsupported else "needs_curation",
    }


def _resource_economics_model(*, research_state: dict[str, Any]) -> dict[str, Any]:
    economics = research_state.get("experiment_economics_summary", {}) if isinstance(research_state.get("experiment_economics_summary", {}), dict) else {}
    voi = research_state.get("value_of_information_summary", {}) if isinstance(research_state.get("value_of_information_summary", {}), dict) else {}
    scheduler = research_state.get("experiment_execution_loop_summary", {}) if isinstance(research_state.get("experiment_execution_loop_summary", {}), dict) else {}
    candidates = _items(scheduler.get("candidate_experiments", []))
    high_value = [
        item for item in _items(voi.get("items", []))
        if _float(item.get("value_of_information", 0)) >= 2.0
    ]
    expensive = [
        item for item in candidates
        if _float(item.get("cost_score", 0)) + _float(item.get("time_score", 0)) >= 3.0
    ]
    return {
        "cost_pressure": str(economics.get("cost_pressure", "medium")),
        "time_pressure": str(economics.get("time_pressure", "medium")),
        "candidate_count": len(candidates),
        "high_value_candidate_count": len(high_value),
        "expensive_candidate_count": len(expensive),
        "top_value_of_information": voi.get("top_value_of_information", 0),
        "policy": "cheap_screening_then_discriminative_tests",
        "stop_loss_rule": "pause or pivot when repeated failures do not reduce uncertainty",
        "economics_state": "resource_constrained" if expensive and not high_value else "actionable",
    }


def _autonomy_control_ladder(*, research_state: dict[str, Any]) -> dict[str, Any]:
    autonomy = research_state.get("autonomy_summary", {}) if isinstance(research_state.get("autonomy_summary", {}), dict) else {}
    controller = research_state.get("autonomous_controller_summary", {}) if isinstance(research_state.get("autonomous_controller_summary", {}), dict) else {}
    human = research_state.get("human_governance_checkpoint_summary", {}) if isinstance(research_state.get("human_governance_checkpoint_summary", {}), dict) else {}
    risk = research_state.get("experiment_risk_permission_summary", {}) if isinstance(research_state.get("experiment_risk_permission_summary", {}), dict) else {}
    requested = str(autonomy.get("autonomy_level", "") or autonomy.get("mode", "")).strip().upper()
    if requested.startswith("L") and requested[1:].isdigit():
        level = requested
    elif risk.get("permission_state") in {"blocked", "requires_human_approval"} or human.get("open_checkpoint_count"):
        level = "L2"
    elif controller.get("controller_state") in {"continue_autonomously", "active"}:
        level = "L3"
    else:
        level = "L1"
    permissions = {
        "L0": ["answer_only"],
        "L1": ["suggest_actions"],
        "L2": ["draft_digest", "wait_for_confirmation"],
        "L3": ["auto_promote_low_risk_memory", "log_all_migrations"],
        "L4": ["auto_schedule_computational_experiments", "pause_for_claim_promotion"],
        "L5": ["autonomous_campaign", "full_replay_required"],
    }
    return {
        "current_level": level,
        "allowed_actions": permissions.get(level, permissions["L1"]),
        "must_pause_for": _dedupe(
            _strings(human.get("required_checkpoints", []))
            + _strings(risk.get("required_approvals", []))
            + ["high-risk memory promotion", "major hypothesis retirement"]
        )[:12],
        "logging_required": level in {"L2", "L3", "L4", "L5"},
        "controller_state": controller.get("controller_state", ""),
    }


def _provenance_source_policy(*, research_state: dict[str, Any], claim_graph: dict[str, Any], run_manifest: dict[str, Any]) -> dict[str, Any]:
    unified = research_state.get("unified_provenance_graph_summary", {}) if isinstance(research_state.get("unified_provenance_graph_summary", {}), dict) else {}
    object_store = research_state.get("scientific_object_store_summary", {}) if isinstance(research_state.get("scientific_object_store_summary", {}), dict) else {}
    node_count = _safe_int(unified.get("node_count", 0))
    edge_count = _safe_int(unified.get("edge_count", 0))
    object_count = _safe_int(object_store.get("object_count", 0))
    graph_coverage = round(min(1.0, node_count / max(1, object_count)), 3) if object_count else 0.0
    missing = []
    if not node_count:
        missing.append("provenance_nodes")
    if not edge_count:
        missing.append("provenance_edges")
    if not run_manifest.get("artifacts"):
        missing.append("artifact_manifest")
    if claim_graph.get("claims") and not claim_graph.get("edges"):
        missing.append("claim_evidence_edges")
    return {
        "canonical_source": "unified_provenance_graph",
        "graph_coverage": graph_coverage,
        "node_count": node_count,
        "edge_count": edge_count,
        "object_count": object_count,
        "missing_contracts": missing[:12],
        "policy_state": "canonical_ready" if graph_coverage >= 0.8 and not missing else "needs_graph_sync",
        "read_policy": "runtime decisions should prefer graph facts, then memory, then raw step outputs",
        "write_policy": "claims, hypotheses, experiments, artifacts, and decisions should emit provenance facts",
    }


def _lab_meeting_governance_model(*, research_state: dict[str, Any], claim_graph: dict[str, Any]) -> dict[str, Any]:
    debate = research_state.get("scientific_debate_protocol_summary", {}) if isinstance(research_state.get("scientific_debate_protocol_summary", {}), dict) else {}
    meeting = research_state.get("lab_meeting_protocol_summary", {}) if isinstance(research_state.get("lab_meeting_protocol_summary", {}), dict) else {}
    stance = research_state.get("agent_stance_continuity_summary", {}) if isinstance(research_state.get("agent_stance_continuity_summary", {}), dict) else {}
    disagreements = _strings(debate.get("open_disagreements", [])) + _strings(meeting.get("open_disagreements", []))
    records = _items(stance.get("records", []))
    required_roles = ["proposer", "supporter", "skeptic", "methodologist", "statistician", "chair"]
    present_roles = _dedupe([str(item.get("role", "") or item.get("agent_role", "")).strip() for item in records])
    missing_roles = [role for role in required_roles if role not in present_roles]
    return {
        "consensus_level": debate.get("consensus_level", meeting.get("consensus_level", "forming")),
        "formal_record_required": bool(debate.get("formal_record_required") or disagreements or claim_graph.get("hypotheses")),
        "required_roles": required_roles,
        "present_roles": present_roles,
        "missing_roles": missing_roles,
        "open_disagreements": disagreements[:12],
        "decision_rule": debate.get("decision_rule", "advance only after skeptic and methodologist objections are resolved or recorded"),
        "governance_state": "ready_for_decision" if not missing_roles and not disagreements else "needs_structured_meeting",
    }


def _scientific_capability_evaluation_view(*, research_state: dict[str, Any]) -> dict[str, Any]:
    harness = research_state.get("kaivu_evaluation_harness_summary", {}) if isinstance(research_state.get("kaivu_evaluation_harness_summary", {}), dict) else {}
    benchmark = research_state.get("benchmark_case_suite_summary", {}) if isinstance(research_state.get("benchmark_case_suite_summary", {}), dict) else {}
    system = research_state.get("scientific_evaluation_system_summary", {}) if isinstance(research_state.get("scientific_evaluation_system_summary", {}), dict) else {}
    gaps = _dedupe(
        _strings(harness.get("blocking_gates", []))
        + _strings(benchmark.get("failed_cases", []))
        + _strings(system.get("gaps", []))
    )
    score = _float(harness.get("overall_score", system.get("overall_score", 0)))
    return {
        "overall_score": score,
        "release_state": harness.get("release_state", system.get("release_state", "")),
        "benchmark_state": benchmark.get("benchmark_state", ""),
        "blocking_gap_count": len(gaps),
        "blocking_gaps": gaps[:20],
        "evaluation_state": "regression_ready" if score >= 0.75 and not gaps else "needs_benchmark_hardening",
    }


def _operating_system_control_actions(
    *,
    objective: dict[str, Any],
    hypothesis_lifecycle: dict[str, Any],
    evidence_map: dict[str, Any],
    resource_model: dict[str, Any],
    autonomy: dict[str, Any],
    provenance: dict[str, Any],
    lab_meeting: dict[str, Any],
    evaluation: dict[str, Any],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if objective.get("contract_state") != "operational":
        actions.append(_control_action("tighten_research_objective", "blocking", objective.get("missing_fields", [])))
    if evidence_map.get("map_state") != "decision_grade":
        actions.append(_control_action("curate_evidence_map_before_major_decision", "high", evidence_map.get("unsupported_claim_ids", [])))
    if hypothesis_lifecycle.get("revise_or_retire_count", 0):
        actions.append(_control_action("update_hypothesis_tree_lifecycle", "high", ["challenged or weak hypotheses exist"]))
    if resource_model.get("economics_state") == "resource_constrained":
        actions.append(_control_action("apply_resource_stop_loss_or_screening", "medium", ["expensive candidates without enough value-of-information"]))
    if provenance.get("policy_state") != "canonical_ready":
        actions.append(_control_action("sync_provenance_graph_as_source_of_truth", "high", provenance.get("missing_contracts", [])))
    if lab_meeting.get("governance_state") != "ready_for_decision":
        actions.append(_control_action("run_structured_lab_meeting_record", "medium", lab_meeting.get("missing_roles", [])))
    if evaluation.get("evaluation_state") != "regression_ready":
        actions.append(_control_action("harden_scientific_evaluation_benchmark", "medium", evaluation.get("blocking_gaps", [])))
    if autonomy.get("current_level") in {"L3", "L4", "L5"} and autonomy.get("must_pause_for"):
        actions.append(_control_action("enforce_autonomy_pause_points", "high", autonomy.get("must_pause_for", [])))
    return actions[:12]


def _control_action(action: str, severity: str, reasons: list[str]) -> dict[str, Any]:
    return {
        "action": action,
        "severity": severity,
        "reasons": _strings(reasons)[:8],
    }


def _lifecycle_from_theory_object(obj: dict[str, Any]) -> str:
    decision = str(obj.get("decision_state", "")).strip().lower()
    status = str(obj.get("status", "")).strip().lower()
    maturity = str(obj.get("theory_maturity", "")).strip().lower()
    if status == "rejected" or decision == "block":
        return "retired"
    if obj.get("negative_result_refs"):
        return "challenged"
    if decision == "advance" and maturity == "predictive":
        return "ready_for_discriminative_test"
    if decision == "revise":
        return "needs_revision"
    if maturity in {"structured", "predictive"}:
        return "formalized"
    return "proposed"


def _transition_from_theory_object(obj: dict[str, Any]) -> str:
    state = _lifecycle_from_theory_object(obj)
    return {
        "retired": "retire",
        "challenged": "revise_or_retire",
        "ready_for_discriminative_test": "advance",
        "needs_revision": "revise",
        "formalized": "schedule_or_compare",
        "proposed": "validate",
    }.get(state, "observe")


def _error_record(topic: str, error_type: str, description: str, severity: str, refs: list[str]) -> dict[str, Any]:
    return {
        "error_id": f"scientific-error::{_slugify(topic)}::{error_type}::{_slugify(description[:80])}",
        "error_type": error_type,
        "description": description,
        "severity": severity,
        "related_object_ids": refs,
        "recommended_response": _error_response(error_type),
    }


def _error_response(error_type: str) -> str:
    return {
        "evidence_error": "repair systematic review or downgrade claim confidence",
        "hypothesis_error": "revise hypothesis before scheduling expensive experiments",
        "experiment_error": "add controls, repeat only with changed conditions, and update failure memory",
        "analysis_error": "rerun analysis with sensitivity checks",
        "interpretation_error": "separate correlation from causal claims and update uncertainty ledger",
        "memory_error": "quarantine or version conflicting memory",
        "collaboration_error": "run formal lab meeting protocol",
        "model_error": "rerun with stronger or independent model",
        "provenance_error": "add missing provenance edges before release",
    }.get(error_type, "review before release")


def _allowed_outputs(release_state: str) -> list[str]:
    if release_state == "release_ready":
        return ["final_report", "group_memory", "publication_draft", "experiment_handoff"]
    if release_state == "needs_targeted_repairs":
        return ["internal_report", "project_memory", "next_cycle_plan"]
    return ["draft_report", "private_or_project_notes"]


def _release_gate_blocking_reason(check_name: str) -> str:
    labels = {
        "evidence_sufficient": "evidence is not yet sufficient for release",
        "systematic_review_not_blocked": "systematic review is blocked",
        "hypotheses_falsifiable": "one or more hypotheses are not falsifiable enough",
        "problem_frame_checked": "problem frame has not been checked",
        "theory_predictions_compiled": "theory predictions are not compiled",
        "uncertainty_acknowledged": "uncertainty has not been acknowledged",
        "provenance_complete": "provenance graph is incomplete",
        "provenance_facts_exist": "no provenance facts are available",
        "claim_or_hypothesis_fact_backed": "claims or hypotheses are not fact-backed",
        "evidence_or_experiment_fact_backed": "evidence or experiments are not fact-backed",
        "reproducibility_package_exists": "reproducibility package is missing",
        "debate_not_blocked": "lab-meeting debate is blocked",
        "failed_attempts_considered": "failed attempts have not been considered",
        "discipline_native_passed": "discipline-native checks have not passed",
        "discipline_toolchain_bound": "discipline toolchain is not bound",
        "context_policy_ready": "scientific context policy is not ready",
        "risk_permissions_clear": "risk or permission gate is blocked",
        "benchmark_cases_passed": "benchmark cases have not passed",
        "benchmark_quality_passed": "benchmark quality gate has not passed",
        "scientific_evaluation_benchmark_usable": "scientific evaluation benchmark is not usable",
        "high_surprises_resolved": "high-priority surprises remain unresolved",
        "credit_responsibility_recorded": "scientific credit and responsibility record is missing",
    }
    return labels.get(check_name, f"release check failed: {check_name}")


def _discipline_required_contract(primary: str) -> dict[str, list[str]]:
    if "chem" in primary and "engineering" not in primary:
        return {
            "safety": ["safety", "hazard", "ppe"],
            "characterization": ["characterization", "spectra", "purity", "nmr", "ms"],
            "yield_or_selectivity": ["yield", "selectivity", "conversion"],
            "controls": ["control", "blank", "standard"],
        }
    if "chemical_engineering" in primary or "chemical-engineering" in primary:
        return {
            "process_safety": ["process safety", "hazop", "pressure", "temperature"],
            "transport": ["mass transfer", "heat transfer", "residence"],
            "scaleup": ["scale", "pilot", "throughput"],
            "process_window": ["operating window", "process window", "stability"],
        }
    if "mathematics" in primary or primary == "math":
        return {
            "definitions": ["definition", "assumption"],
            "lemma_graph": ["lemma", "theorem", "proof"],
            "counterexample": ["counterexample", "edge case"],
            "formalization": ["formal", "verification", "proof assistant"],
        }
    if "artificial" in primary or primary == "ai":
        return {
            "dataset_card": ["dataset", "split", "leakage"],
            "baseline": ["baseline", "comparison"],
            "ablation": ["ablation", "sensitivity"],
            "seed_variance": ["seed", "variance", "reproducibility"],
        }
    if "physics" in primary:
        return {
            "dimensional_analysis": ["dimension", "unit", "scale"],
            "error_propagation": ["error", "uncertainty", "calibration"],
            "simulation_experiment_link": ["simulation", "experiment", "model"],
            "apparatus": ["apparatus", "instrument", "setup"],
        }
    return {
        "evidence_protocol": ["protocol", "evidence"],
        "measurement": ["measurement", "metric"],
        "quality_control": ["quality", "control"],
    }


def _discipline_next_steps(primary: str, missing: list[str]) -> list[str]:
    if not missing:
        return ["keep discipline adapter constraints attached to scheduler, quality control, and interpretation"]
    return [
        f"add native {item.replace('_', ' ')} contract for {primary or 'general science'}"
        for item in missing[:8]
    ]


def _uncertainty_entry(
    topic: str,
    index: int,
    kind: str,
    statement: str,
    severity: str,
    resolution_route: str,
    *,
    related_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "uncertainty_id": f"uncertainty::{_slugify(topic)}::{kind}-{index}",
        "kind": kind,
        "statement": statement,
        "severity": severity,
        "decision_blocking": severity == "high",
        "resolution_route": resolution_route,
        "related_object_ids": related_ids or [],
    }


def _items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key, "")).strip() or "unknown"
        counts[value] = counts.get(value, 0) + 1
    return counts


def _float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value).strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "object"



