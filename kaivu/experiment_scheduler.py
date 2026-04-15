from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


OUTCOME_SCENARIOS = [
    "positive_support",
    "negative_falsification",
    "ambiguous_result",
    "failed_execution",
    "quality_blocked",
]

MCTS_EXPLORATION_WEIGHT = 1.414


@dataclass(slots=True)
class ExperimentCandidate:
    experiment_id: str
    title: str
    experiment_type: str
    target_ids: list[str] = field(default_factory=list)
    source: str = ""
    objective: str = ""
    information_gain_score: float = 0.0
    discrimination_score: float = 0.0
    reproducibility_score: float = 0.0
    evidence_quality_gain: float = 0.0
    failure_knowledge_gain: float = 0.0
    cost_score: float = 0.0
    time_score: float = 0.0
    risk_score: float = 0.0
    repeat_failure_risk: float = 0.0
    requires_human_approval: bool = False
    requires_protocol: bool = True
    search_space: dict[str, Any] = field(default_factory=dict)
    success_criteria: list[str] = field(default_factory=list)
    failure_criteria: list[str] = field(default_factory=list)
    quality_gates: list[str] = field(default_factory=list)
    provenance_refs: list[str] = field(default_factory=list)
    discipline_binding_id: str = ""
    lifecycle_stages: list[str] = field(default_factory=list)
    measurement_requirements: list[str] = field(default_factory=list)
    artifact_requirements: list[str] = field(default_factory=list)
    interpretation_boundaries: list[str] = field(default_factory=list)
    scheduler_rules: list[str] = field(default_factory=list)
    hypothesis_gate_state: str = ""
    hypothesis_validator_flags: list[str] = field(default_factory=list)
    validator_penalty: float = 0.0
    search_priority: float = 0.0
    acquisition_function: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExperimentScheduleItem:
    experiment_id: str
    rank: int
    schedule_state: str
    portfolio_score: float
    action: str
    required_before_execution: list[str] = field(default_factory=list)
    recommended_agents: list[str] = field(default_factory=list)
    mcts_like_path: list[str] = field(default_factory=list)
    discipline_binding_id: str = ""
    lifecycle_stages: list[str] = field(default_factory=list)
    interpretation_boundaries: list[str] = field(default_factory=list)
    scheduler_rules: list[str] = field(default_factory=list)
    hypothesis_gate_state: str = ""
    hypothesis_validator_flags: list[str] = field(default_factory=list)
    validator_penalty: float = 0.0
    search_priority: float = 0.0
    acquisition_function: dict[str, Any] = field(default_factory=dict)
    scheduler_node_id: str = ""
    selection_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_experiment_execution_loop_summary(
    *,
    topic: str,
    project_id: str = "",
    hypothesis_theory_summary: dict[str, Any],
    scientific_decision_summary: dict[str, Any],
    research_plan_summary: dict[str, Any],
    experiment_economics_summary: dict[str, Any],
    evidence_review_summary: dict[str, Any],
    failure_intelligence_summary: dict[str, Any],
    experiment_governance_summary: dict[str, Any],
    execution_cycle_summary: dict[str, Any],
    discipline_adaptation_summary: dict[str, Any],
    hypothesis_validation_summary: dict[str, Any] | None = None,
    hypothesis_gate_summary: dict[str, Any] | None = None,
    discipline_adapter_summary: dict[str, Any] | None = None,
    mid_run_control_summary: dict[str, Any] | None = None,
    scheduler_memory_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mid_run_control_summary = mid_run_control_summary or {}
    scheduler_memory_context = scheduler_memory_context or {}
    candidates = _collect_candidates(
        topic=topic,
        hypothesis_theory_summary=hypothesis_theory_summary,
        scientific_decision_summary=scientific_decision_summary,
        research_plan_summary=research_plan_summary,
        experiment_economics_summary=experiment_economics_summary,
        evidence_review_summary=evidence_review_summary,
        failure_intelligence_summary=failure_intelligence_summary,
        execution_cycle_summary=execution_cycle_summary,
        discipline_adaptation_summary=discipline_adaptation_summary,
        hypothesis_validation_summary=hypothesis_validation_summary or {},
        hypothesis_gate_summary=hypothesis_gate_summary or {},
        discipline_adapter_summary=discipline_adapter_summary or {},
        mid_run_control_summary=mid_run_control_summary,
    )
    _apply_search_feedback(
        candidates,
        failure_intelligence_summary=failure_intelligence_summary,
        execution_cycle_summary=execution_cycle_summary,
    )
    _apply_scheduler_memory_context(candidates, scheduler_memory_context=scheduler_memory_context)
    scored = [
        {
            "candidate": candidate,
            "score": _portfolio_score(candidate),
            "search": _scheduler_search_node(candidate, index=index, candidate_count=len(candidates)),
            "scenarios": _expand_outcome_scenarios(candidate),
            "gate": _execution_gate(
                candidate=candidate,
                scientific_decision_summary=scientific_decision_summary,
                evidence_review_summary=evidence_review_summary,
                experiment_governance_summary=experiment_governance_summary,
                failure_intelligence_summary=failure_intelligence_summary,
                discipline_adapter_summary=discipline_adapter_summary or {},
                mid_run_control_summary=mid_run_control_summary,
            ),
        }
        for index, candidate in enumerate(candidates, start=1)
    ]
    scored = sorted(
        scored,
        key=lambda item: float(item.get("search", {}).get("selection_score", item["score"])),
        reverse=True,
    )
    execution_queue = _execution_queue(scored)
    blocked = [
        {
            **item["candidate"].to_dict(),
            "portfolio_score": round(float(item["score"]), 3),
            "selection_score": round(float(item.get("search", {}).get("selection_score", item["score"])), 3),
            "scheduler_search_node": item.get("search", {}),
            "gate_state": item["gate"]["state"],
            "gate_reasons": item["gate"]["reasons"],
        }
        for item in scored
        if item["gate"]["state"] in {"blocked", "needs_human_approval", "needs_protocol"}
    ][:20]
    top = execution_queue[0] if execution_queue else {}
    scheduler_state = _scheduler_state(execution_queue=execution_queue, blocked=blocked, scored=scored)
    candidate_dicts = [
        {
            **item["candidate"].to_dict(),
            "portfolio_score": round(float(item["score"]), 3),
            "selection_score": round(float(item.get("search", {}).get("selection_score", item["score"])), 3),
            "scheduler_search_node": item.get("search", {}),
            "gate_state": item["gate"]["state"],
            "gate_reasons": item["gate"]["reasons"],
        }
        for item in scored
    ][:30]
    return {
        "scheduler_id": f"experiment-scheduler::{_slugify(project_id or 'workspace')}::{_slugify(topic)}",
        "topic": topic,
        "project_id": project_id,
        "scheduler_state": scheduler_state,
        "top_experiment_id": str(top.get("experiment_id", "")),
        "top_action": str(top.get("action", "")),
        "candidate_count": len(candidates),
        "execution_queue": execution_queue,
        "blocked_experiments": blocked,
        "candidate_experiments": candidate_dicts,
        "mcts_like_search": {
            "root_state": _root_state(scientific_decision_summary, evidence_review_summary),
            "candidate_count": len(candidates),
            "expanded_node_count": len(candidates) * len(OUTCOME_SCENARIOS),
            "outcome_scenarios": OUTCOME_SCENARIOS,
            "best_path": top.get("mcts_like_path", []) if isinstance(top, dict) else [],
            "best_node_id": str(top.get("scheduler_node_id", "")) if isinstance(top, dict) else "",
            "best_selection_reason": str(top.get("selection_reason", "")) if isinstance(top, dict) else "",
            "discipline_rule_aware": bool(discipline_adapter_summary),
            "hypothesis_validator_aware": bool(hypothesis_validation_summary or hypothesis_gate_summary),
            "mid_run_control_aware": bool(mid_run_control_summary.get("decision_count")),
            "uncertainty_reduction_estimate": round(
                max([float(item["score"]) for item in scored], default=0.0) / 15.0,
                3,
            ),
            "tree": _mcts_tree_summary(scored),
            "bo_policy": {
                "acquisition": "expected_improvement_plus_uncertainty_minus_cost_risk_failure",
                "supports_parameter_optimization": any(
                    item.experiment_type == "parameter_optimization" for item in candidates
                ),
                "posterior_source": "heuristic_from_value_of_information_failure_memory_and_quality_gates",
                "update_rule": "executor outcomes update value estimate, uncertainty, failure penalty, and route visits",
            },
            "posterior_update_summary": _posterior_update_summary(
                scored=scored,
                execution_cycle_summary=execution_cycle_summary,
                failure_intelligence_summary=failure_intelligence_summary,
                scheduler_memory_context=scheduler_memory_context,
            ),
        },
        "scheduler_memory_context": {
            "memory_signal_count": len(
                scheduler_memory_context.get("memory_signals", [])
                if isinstance(scheduler_memory_context.get("memory_signals", []), list)
                else []
            ),
            "failed_route_count": len(
                scheduler_memory_context.get("failed_routes", [])
                if isinstance(scheduler_memory_context.get("failed_routes", []), list)
                else []
            ),
            "standing_objection_count": len(
                scheduler_memory_context.get("standing_objections", [])
                if isinstance(scheduler_memory_context.get("standing_objections", []), list)
                else []
            ),
        },
        "parameter_optimization_supported": any(
            item.experiment_type == "parameter_optimization" for item in candidates
        ),
        "execution_loop": {
            "plan": "schedule_candidate",
            "execute": "run_manager_or_domain_adapter",
            "quality_control": "quality_control_reviewer",
            "interpret": "result_interpreter",
            "backpropagate": "belief_updater_memory_graph",
        },
        "discipline_feedback_loop": {
            "enabled": bool(discipline_adapter_summary),
            "adapter_id": str(
                (discipline_adapter_summary or {}).get("adapter_id", "")
            ).strip(),
            "uses": [
                "lifecycle_stages",
                "interpretation_boundaries",
                "scheduler_rules",
                "quality_gates",
                "failure_modes",
            ],
        },
        "mid_run_control_feedback_loop": {
            "enabled": bool(mid_run_control_summary.get("decision_count")),
            "stop_routing": bool(mid_run_control_summary.get("stop_routing")),
            "paused_workstreams": mid_run_control_summary.get("paused_workstreams", []),
            "required_evidence_repairs": mid_run_control_summary.get("required_evidence_repairs", []),
            "scheduler_overrides": mid_run_control_summary.get("scheduler_overrides", []),
            "terminated_routes": mid_run_control_summary.get("terminated_routes", []),
        },
    }


def _collect_candidates(
    *,
    topic: str,
    hypothesis_theory_summary: dict[str, Any],
    scientific_decision_summary: dict[str, Any],
    research_plan_summary: dict[str, Any],
    experiment_economics_summary: dict[str, Any],
    evidence_review_summary: dict[str, Any],
    failure_intelligence_summary: dict[str, Any],
    execution_cycle_summary: dict[str, Any],
    discipline_adaptation_summary: dict[str, Any],
    hypothesis_validation_summary: dict[str, Any],
    hypothesis_gate_summary: dict[str, Any],
    discipline_adapter_summary: dict[str, Any],
    mid_run_control_summary: dict[str, Any],
) -> list[ExperimentCandidate]:
    candidates: list[ExperimentCandidate] = []
    primary_discipline = str(discipline_adaptation_summary.get("primary_discipline", "")).strip()
    decision_queue = scientific_decision_summary.get("decision_queue", [])
    for item in decision_queue if isinstance(decision_queue, list) else []:
        if not isinstance(item, dict):
            continue
        action = str(item.get("action", "")).strip()
        target_id = str(item.get("target_id", "")).strip()
        if action in {"run_discriminative_test", "resolve_evidence_conflicts"}:
            candidates.append(
                _candidate(
                    topic=topic,
                    title=action.replace("_", " "),
                    experiment_type="discriminative_experiment" if action == "run_discriminative_test" else "evidence_resolution",
                    target_ids=[target_id] if target_id else [],
                    source="scientific_decision",
                    objective="execute the decision engine's top route",
                    information_gain=_safe_float(item.get("information_gain_score", 3)),
                    cost=_safe_float(item.get("cost_score", 1)),
                    time_cost=_safe_float(item.get("time_score", 1)),
                    risk=_safe_float(item.get("risk_score", 1)),
                    governance=_safe_float(item.get("governance_burden_score", 0)),
                    primary_discipline=primary_discipline,
                    provenance_refs=[str(trace.get("source_id", "")) for trace in item.get("evidence_trace", []) if isinstance(trace, dict)],
                )
            )
    for theory in hypothesis_theory_summary.get("objects", []) if isinstance(hypothesis_theory_summary.get("objects", []), list) else []:
        if not isinstance(theory, dict):
            continue
        hypothesis_id = str(theory.get("hypothesis_id", "")).strip()
        experiments = theory.get("discriminating_experiments", []) or theory.get("falsification_tests", [])
        for index, experiment in enumerate(experiments if isinstance(experiments, list) else []):
            text = str(experiment).strip()
            if not text:
                continue
            candidates.append(
                _candidate(
                    topic=topic,
                    title=text,
                    experiment_type="discriminative_experiment",
                    target_ids=[hypothesis_id] if hypothesis_id else [],
                    source="hypothesis_theory_object",
                    objective="distinguish or falsify a hypothesis mechanism",
                    information_gain=5 if str(theory.get("theory_maturity", "")).strip() == "predictive" else 4,
                    cost=_pressure_score(experiment_economics_summary.get("cost_pressure", "medium")),
                    time_cost=_pressure_score(experiment_economics_summary.get("time_pressure", "medium")),
                    risk=1,
                    governance=0,
                    primary_discipline=primary_discipline,
                    provenance_refs=[str(theory.get("theory_object_id", ""))],
                    suffix=str(index),
                )
            )
    for index, experiment in enumerate(research_plan_summary.get("next_cycle_experiments", []) if isinstance(research_plan_summary.get("next_cycle_experiments", []), list) else []):
        text = str(experiment).strip()
        if not text:
            continue
        candidates.append(
            _candidate(
                topic=topic,
                title=text,
                experiment_type=_infer_experiment_type(text, primary_discipline),
                target_ids=[],
                source="research_plan",
                objective="advance next-cycle research plan",
                information_gain=3,
                cost=_pressure_score(experiment_economics_summary.get("cost_pressure", "medium")),
                time_cost=_pressure_score(experiment_economics_summary.get("time_pressure", "medium")),
                risk=1,
                governance=0,
                primary_discipline=primary_discipline,
                provenance_refs=[],
                suffix=f"plan-{index}",
            )
        )
    if int(execution_cycle_summary.get("repeat_required_count", 0) or 0) > 0:
        candidates.append(
            _candidate(
                topic=topic,
                title="reproduce or rerun failed-quality experiment",
                experiment_type="reproducibility_check",
                target_ids=failure_intelligence_summary.get("avoid_repeat_routes", [])[:3],
                source="quality_control",
                objective="recover interpretable evidence from failed or warning runs",
                information_gain=3,
                cost=1,
                time_cost=1,
                risk=1,
                governance=1,
                primary_discipline=primary_discipline,
                provenance_refs=[],
            )
        )
    if _should_add_parameter_optimization(topic, primary_discipline, scientific_decision_summary, research_plan_summary):
        candidates.append(
            _candidate(
                topic=topic,
                title="parameter optimization under frozen validation protocol",
                experiment_type="parameter_optimization",
                target_ids=[],
                source="optimization_adapter",
                objective="search parameter space without contaminating confirmatory evaluation",
                information_gain=4,
                cost=2,
                time_cost=2,
                risk=2,
                governance=1,
                primary_discipline=primary_discipline,
                provenance_refs=[],
                search_space=_search_space_template(primary_discipline),
            )
        )
    if evidence_review_summary.get("review_readiness") not in {"", "decision_ready"}:
        candidates.append(
            _candidate(
                topic=topic,
                title="repair evidence base before execution",
                experiment_type="evidence_quality_repair",
                target_ids=[],
                source="evidence_review",
                objective="close evidence review blockers before expensive experiments",
                information_gain=4,
                cost=1,
                time_cost=1,
                risk=0,
                governance=1 if evidence_review_summary.get("needs_human_adjudication") else 0,
                primary_discipline=primary_discipline,
                provenance_refs=[str(evidence_review_summary.get("review_id", ""))],
            )
        )
    for index, repair in enumerate(mid_run_control_summary.get("required_evidence_repairs", []) if isinstance(mid_run_control_summary.get("required_evidence_repairs", []), list) else []):
        text = str(repair).strip()
        if not text:
            continue
        candidates.append(
            _candidate(
                topic=topic,
                title=text,
                experiment_type="evidence_quality_repair",
                target_ids=[],
                source="mid_run_controller",
                objective="satisfy active control evidence requirements before downstream execution",
                information_gain=5,
                cost=1,
                time_cost=1,
                risk=0,
                governance=0,
                primary_discipline=primary_discipline,
                provenance_refs=[],
                suffix=f"mid-run-{index}",
            )
        )
    bound_candidates = _apply_discipline_bindings(
        candidates=_dedupe_candidates(candidates),
        discipline_adapter_summary=discipline_adapter_summary,
    )
    _apply_hypothesis_validator_feedback(
        bound_candidates,
        hypothesis_validation_summary=hypothesis_validation_summary,
        hypothesis_gate_summary=hypothesis_gate_summary,
    )
    _apply_mid_run_control_feedback(bound_candidates, mid_run_control_summary=mid_run_control_summary)
    return bound_candidates


def _apply_mid_run_control_feedback(
    candidates: list[ExperimentCandidate],
    *,
    mid_run_control_summary: dict[str, Any],
) -> None:
    paused = {
        str(item).strip()
        for item in mid_run_control_summary.get("paused_workstreams", [])
        if str(item).strip()
    } if isinstance(mid_run_control_summary.get("paused_workstreams", []), list) else set()
    terminated = {
        str(item).strip()
        for item in mid_run_control_summary.get("terminated_routes", [])
        if str(item).strip()
    } if isinstance(mid_run_control_summary.get("terminated_routes", []), list) else set()
    scheduler_overrides = (
        mid_run_control_summary.get("scheduler_overrides", [])
        if isinstance(mid_run_control_summary.get("scheduler_overrides", []), list)
        else []
    )
    override_names = {
        str(item.get("override", "")).strip()
        for item in scheduler_overrides
        if isinstance(item, dict) and str(item.get("override", "")).strip()
    }
    for candidate in candidates:
        if terminated.intersection(candidate.target_ids):
            candidate.validator_penalty += 6.0
            candidate.requires_human_approval = True
            candidate.scheduler_rules.append("mid_run_control:terminated_route_requires_explicit_reopen")
        if "downstream_experiment_execution" in paused and candidate.experiment_type not in {
            "evidence_quality_repair",
            "evidence_resolution",
        }:
            candidate.validator_penalty += 2.0
            candidate.scheduler_rules.append("mid_run_control:evidence_repair_before_execution")
        if "experiment_execution" in paused and candidate.experiment_type not in {
            "evidence_quality_repair",
            "reproducibility_check",
            "control_or_ablation",
        }:
            candidate.validator_penalty += 1.5
            candidate.scheduler_rules.append("mid_run_control:quality_gate_repair_before_execution")
        if "prioritize_evidence_repair" in override_names and candidate.experiment_type == "evidence_quality_repair":
            candidate.information_gain_score += 1.5
            candidate.scheduler_rules.append("mid_run_control:priority_evidence_repair")
        if "design_discriminative_or_falsification_test_first" in override_names and candidate.experiment_type == "discriminative_experiment":
            candidate.discrimination_score += 1.5
            candidate.scheduler_rules.append("mid_run_control:validator_repair_discriminative_test")
        candidate.validator_penalty = round(float(candidate.validator_penalty), 3)
        candidate.search_priority = round(_portfolio_score(candidate), 3)
        candidate.acquisition_function = _acquisition_function(candidate)


def _apply_hypothesis_validator_feedback(
    candidates: list[ExperimentCandidate],
    *,
    hypothesis_validation_summary: dict[str, Any],
    hypothesis_gate_summary: dict[str, Any],
) -> None:
    validation_by_id: dict[str, dict[str, Any]] = {}
    for item in hypothesis_validation_summary.get("records", []) if isinstance(hypothesis_validation_summary.get("records", []), list) else []:
        if not isinstance(item, dict):
            continue
        hypothesis_id = str(item.get("hypothesis_id", "")).strip()
        if hypothesis_id:
            validation_by_id[hypothesis_id] = item
    gate_by_id: dict[str, dict[str, Any]] = {}
    for item in hypothesis_gate_summary.get("records", []) if isinstance(hypothesis_gate_summary.get("records", []), list) else []:
        if not isinstance(item, dict):
            continue
        hypothesis_id = str(item.get("hypothesis_id", "")).strip()
        if hypothesis_id:
            gate_by_id[hypothesis_id] = item

    for candidate in candidates:
        matched_ids = [
            target_id
            for target_id in candidate.target_ids
            if target_id in validation_by_id or target_id in gate_by_id
        ]
        if not matched_ids:
            continue
        flags: list[str] = []
        penalties: list[float] = []
        gate_states: list[str] = []
        for hypothesis_id in matched_ids:
            validation = validation_by_id.get(hypothesis_id, {})
            raw_flags = validation.get("validator_flags", []) if isinstance(validation.get("validator_flags", []), list) else []
            flags.extend(str(flag) for flag in raw_flags if str(flag).strip())
            min_score = min(
                [
                    _safe_float(validation.get("falsifiability_score", 1.0)),
                    _safe_float(validation.get("testability_score", 1.0)),
                    _safe_float(validation.get("mechanistic_coherence_score", 1.0)),
                    _safe_float(validation.get("evidence_grounding_score", 1.0)),
                ]
            )
            if min_score < 0.35:
                penalties.append(2.5)
            elif min_score < 0.5:
                penalties.append(1.25)
            gate = gate_by_id.get(hypothesis_id, {})
            decision = str(gate.get("gate_decision", "")).strip().lower()
            if decision:
                gate_states.append(decision)
            if decision == "reject":
                penalties.append(3.0)
                candidate.requires_human_approval = True
            elif decision == "revise":
                penalties.append(1.0)
        candidate.hypothesis_validator_flags = list(dict.fromkeys(flags))[:12]
        candidate.hypothesis_gate_state = ",".join(sorted(set(gate_states)))[:120]
        candidate.validator_penalty = round(max(penalties, default=0.0), 3)
        candidate.search_priority = round(_portfolio_score(candidate), 3)
        candidate.acquisition_function = _acquisition_function(candidate)
        if candidate.hypothesis_validator_flags:
            candidate.scheduler_rules.extend(
                [
                    f"validator:{flag}"
                    for flag in candidate.hypothesis_validator_flags
                    if f"validator:{flag}" not in candidate.scheduler_rules
                ]
            )


def _candidate(
    *,
    topic: str,
    title: str,
    experiment_type: str,
    target_ids: list[str],
    source: str,
    objective: str,
    information_gain: float,
    cost: float,
    time_cost: float,
    risk: float,
    governance: float,
    primary_discipline: str,
    provenance_refs: list[str],
    suffix: str = "",
    search_space: dict[str, Any] | None = None,
) -> ExperimentCandidate:
    base = f"{experiment_type}-{title}-{suffix or source}"
    quality_gates = _quality_gates_for_type(experiment_type, primary_discipline)
    return ExperimentCandidate(
        experiment_id=f"experiment-candidate::{_slugify(base)}",
        title=title or topic,
        experiment_type=experiment_type,
        target_ids=[str(item).strip() for item in target_ids if str(item).strip()],
        source=source,
        objective=objective,
        information_gain_score=float(information_gain),
        discrimination_score=2.0 if experiment_type == "discriminative_experiment" else 1.0,
        reproducibility_score=2.0 if experiment_type == "reproducibility_check" else 1.0,
        evidence_quality_gain=2.0 if "evidence" in experiment_type else 1.0,
        failure_knowledge_gain=2.0 if experiment_type in {"reproducibility_check", "discriminative_experiment"} else 1.0,
        cost_score=float(cost),
        time_score=float(time_cost),
        risk_score=float(risk),
        repeat_failure_risk=1.0 if target_ids else 0.0,
        requires_human_approval=governance >= 2,
        requires_protocol=experiment_type not in {"evidence_quality_repair", "evidence_resolution"},
        search_space=search_space or {},
        success_criteria=_success_criteria(experiment_type),
        failure_criteria=_failure_criteria(experiment_type),
        quality_gates=quality_gates,
        provenance_refs=[str(item).strip() for item in provenance_refs if str(item).strip()],
    )


def _portfolio_score(candidate: ExperimentCandidate) -> float:
    discipline_rule_bonus = 0.0
    if candidate.scheduler_rules:
        discipline_rule_bonus += 0.75
    if candidate.lifecycle_stages:
        discipline_rule_bonus += 0.25
    if candidate.interpretation_boundaries:
        discipline_rule_bonus += 0.25
    return (
        candidate.information_gain_score * 3.0
        + candidate.discrimination_score
        + candidate.reproducibility_score
        + candidate.evidence_quality_gain
        + candidate.failure_knowledge_gain
        + discipline_rule_bonus
        - candidate.cost_score
        - candidate.time_score
        - candidate.risk_score
        - candidate.repeat_failure_risk
        - candidate.validator_penalty
    )


def _apply_search_feedback(
    candidates: list[ExperimentCandidate],
    *,
    failure_intelligence_summary: dict[str, Any],
    execution_cycle_summary: dict[str, Any],
) -> None:
    failed_routes = {
        str(item).strip()
        for item in failure_intelligence_summary.get("avoid_repeat_routes", [])
        if str(item).strip()
    } if isinstance(failure_intelligence_summary.get("avoid_repeat_routes", []), list) else set()
    failed_run_count = int(execution_cycle_summary.get("failed_run_count", 0) or 0)
    warning_run_count = int(execution_cycle_summary.get("warning_run_count", 0) or 0)
    for candidate in candidates:
        repeat_overlap = failed_routes.intersection(candidate.target_ids)
        if repeat_overlap:
            candidate.repeat_failure_risk = max(candidate.repeat_failure_risk, 2.5)
            candidate.scheduler_rules.append("failure_memory:avoid_repeat_without_changed_conditions")
        if candidate.experiment_type == "reproducibility_check" and (failed_run_count or warning_run_count):
            candidate.failure_knowledge_gain += min(2.0, 0.5 + 0.25 * (failed_run_count + warning_run_count))
        candidate.search_priority = round(_portfolio_score(candidate), 3)
        candidate.acquisition_function = _acquisition_function(candidate)


def _apply_scheduler_memory_context(
    candidates: list[ExperimentCandidate],
    *,
    scheduler_memory_context: dict[str, Any],
) -> None:
    failed_routes = {
        str(item).strip()
        for item in scheduler_memory_context.get("failed_routes", [])
        if str(item).strip()
    } if isinstance(scheduler_memory_context.get("failed_routes", []), list) else set()
    successful_routes = {
        str(item).strip()
        for item in scheduler_memory_context.get("successful_routes", [])
        if str(item).strip()
    } if isinstance(scheduler_memory_context.get("successful_routes", []), list) else set()
    standing_objections = [
        str(item).strip()
        for item in scheduler_memory_context.get("standing_objections", [])
        if str(item).strip()
    ] if isinstance(scheduler_memory_context.get("standing_objections", []), list) else []
    for candidate in candidates:
        searchable = " ".join([candidate.experiment_id, candidate.title, candidate.objective, *candidate.target_ids]).lower()
        if any(route.lower() in searchable for route in failed_routes):
            candidate.repeat_failure_risk = max(candidate.repeat_failure_risk, 3.0)
            candidate.scheduler_rules.append("scheduler_memory:failed_route_requires_changed_conditions")
        if any(route.lower() in searchable for route in successful_routes):
            candidate.reproducibility_score += 0.5
            candidate.scheduler_rules.append("scheduler_memory:successful_route_prior")
        if standing_objections and candidate.experiment_type not in {"evidence_quality_repair", "evidence_resolution"}:
            candidate.scheduler_rules.append("scheduler_memory:standing_objections_must_be_addressed")
        candidate.search_priority = round(_portfolio_score(candidate), 3)
        candidate.acquisition_function = _acquisition_function(candidate)


def _acquisition_function(candidate: ExperimentCandidate) -> dict[str, Any]:
    exploitation = candidate.information_gain_score + candidate.discrimination_score + candidate.evidence_quality_gain
    posterior_mean = exploitation - candidate.cost_score - candidate.time_score
    posterior_uncertainty = max(
        0.1,
        candidate.failure_knowledge_gain
        + (1.0 if candidate.search_space else 0.0)
        + (0.5 if candidate.experiment_type in {"discriminative_experiment", "parameter_optimization"} else 0.0),
    )
    expected_improvement = max(0.0, posterior_mean / 10.0)
    exploration = posterior_uncertainty
    failure_penalty = candidate.repeat_failure_risk + candidate.validator_penalty
    safety_penalty = candidate.risk_score + failure_penalty
    acquisition_score = (
        expected_improvement
        + 0.35 * exploration
        - 0.15 * candidate.cost_score
        - 0.15 * candidate.time_score
        - 0.35 * safety_penalty
    )
    return {
        "kind": "expected_improvement_plus_uncertainty_minus_penalties",
        "posterior_mean": round(posterior_mean, 3),
        "posterior_uncertainty": round(posterior_uncertainty, 3),
        "expected_improvement": round(expected_improvement, 3),
        "exploration": round(exploration, 3),
        "cost_penalty": round(candidate.cost_score, 3),
        "time_penalty": round(candidate.time_score, 3),
        "failure_penalty": round(failure_penalty, 3),
        "safety_penalty": round(safety_penalty, 3),
        "score": round(acquisition_score, 3),
    }


def _posterior_update_summary(
    *,
    scored: list[dict[str, Any]],
    execution_cycle_summary: dict[str, Any],
    failure_intelligence_summary: dict[str, Any],
    scheduler_memory_context: dict[str, Any],
) -> dict[str, Any]:
    failed_count = int(execution_cycle_summary.get("failed_run_count", 0) or 0)
    repeat_required = int(execution_cycle_summary.get("repeat_required_count", 0) or 0)
    negative_pressure = len(
        failure_intelligence_summary.get("avoid_repeat_routes", [])
        if isinstance(failure_intelligence_summary.get("avoid_repeat_routes", []), list)
        else []
    )
    updates: list[dict[str, Any]] = []
    for item in scored[:20]:
        candidate = item.get("candidate")
        search = item.get("search", {}) if isinstance(item.get("search", {}), dict) else {}
        if not isinstance(candidate, ExperimentCandidate):
            continue
        posterior_mean = _safe_float(search.get("value_estimate", item.get("score", 0)))
        posterior_uncertainty = _safe_float(
            (candidate.acquisition_function or {}).get("posterior_uncertainty", 0.5)
        )
        if failed_count or negative_pressure:
            posterior_uncertainty = min(10.0, posterior_uncertainty + 0.2 * failed_count + 0.15 * negative_pressure)
        if repeat_required and candidate.experiment_type == "reproducibility_check":
            posterior_mean += 0.5
        updates.append(
            {
                "experiment_id": candidate.experiment_id,
                "visit_count": search.get("visit_count", 1),
                "posterior_mean": round(posterior_mean, 3),
                "posterior_uncertainty": round(posterior_uncertainty, 3),
                "failure_penalty": round(candidate.repeat_failure_risk + candidate.validator_penalty, 3),
                "memory_adjusted": bool(candidate.scheduler_rules),
            }
        )
    return {
        "update_state": "active" if updates else "no_candidates",
        "failed_run_count": failed_count,
        "repeat_required_count": repeat_required,
        "negative_route_pressure": negative_pressure,
        "memory_signal_count": len(
            scheduler_memory_context.get("memory_signals", [])
            if isinstance(scheduler_memory_context.get("memory_signals", []), list)
            else []
        ),
        "updates": updates,
        "next_update_trigger": "executor_result_or_failed_attempt_recorded",
    }


def _scheduler_search_node(
    candidate: ExperimentCandidate,
    *,
    index: int,
    candidate_count: int,
) -> dict[str, Any]:
    acquisition = candidate.acquisition_function or _acquisition_function(candidate)
    visit_count = max(1, int(abs(candidate.search_priority or _portfolio_score(candidate))))
    parent_visits = max(visit_count + 1, candidate_count + 1)
    value_estimate = _safe_float(acquisition.get("posterior_mean", candidate.search_priority))
    exploration_bonus = MCTS_EXPLORATION_WEIGHT * ((parent_visits ** 0.5) / (1 + visit_count))
    ucb_score = value_estimate + exploration_bonus - candidate.repeat_failure_risk - candidate.validator_penalty
    selection_score = ucb_score + _safe_float(acquisition.get("score", 0))
    return {
        "node_id": f"scheduler-node::{_slugify(candidate.experiment_id)}",
        "parent_id": "scheduler-node::root",
        "node_type": "experiment_candidate",
        "experiment_id": candidate.experiment_id,
        "action": f"schedule_{candidate.experiment_type}",
        "visit_count": visit_count,
        "value_estimate": round(value_estimate, 3),
        "exploration_bonus": round(exploration_bonus, 3),
        "ucb_score": round(ucb_score, 3),
        "selection_score": round(selection_score, 3),
        "acquisition": acquisition,
        "selection_reason": _selection_reason(candidate, acquisition),
        "rank_prior": index,
        "target_ids": candidate.target_ids,
        "terminal_reason": _terminal_reason(candidate),
    }


def _mcts_tree_summary(scored: list[dict[str, Any]]) -> dict[str, Any]:
    nodes = [
        {
            "node_id": "scheduler-node::root",
            "parent_id": "",
            "node_type": "root",
            "action": "choose_next_experiment",
            "visit_count": sum(
                int(item.get("search", {}).get("visit_count", 1) or 1)
                for item in scored
            ),
            "value_estimate": max(
                [_safe_float(item.get("search", {}).get("value_estimate", 0)) for item in scored],
                default=0.0,
            ),
        }
    ]
    nodes.extend(item.get("search", {}) for item in scored if isinstance(item.get("search", {}), dict))
    edges = [
        {
            "source": "scheduler-node::root",
            "target": str(item.get("search", {}).get("node_id", "")),
            "relation": "expands",
        }
        for item in scored
        if str(item.get("search", {}).get("node_id", "")).strip()
    ]
    best = max(
        [item.get("search", {}) for item in scored if isinstance(item.get("search", {}), dict)],
        key=lambda item: _safe_float(item.get("selection_score", 0)),
        default={},
    )
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "best_node_id": str(best.get("node_id", "")),
        "best_experiment_id": str(best.get("experiment_id", "")),
        "best_selection_score": _safe_float(best.get("selection_score", 0)),
        "nodes": nodes[:50],
        "edges": edges[:80],
    }


def _selection_reason(candidate: ExperimentCandidate, acquisition: dict[str, Any]) -> str:
    reasons: list[str] = []
    if candidate.information_gain_score >= 4:
        reasons.append("high information gain")
    if candidate.discrimination_score >= 2:
        reasons.append("discriminates competing hypotheses")
    if candidate.search_space:
        reasons.append("supports BO-style parameter search")
    if candidate.failure_knowledge_gain >= 2:
        reasons.append("learns from failure or reproducibility pressure")
    if candidate.cost_score <= 1:
        reasons.append("low cost")
    if candidate.repeat_failure_risk >= 2.0 or candidate.validator_penalty:
        reasons.append("penalized by failure memory or hypothesis validators")
    if not reasons:
        reasons.append(f"acquisition score={acquisition.get('score', 0)}")
    return "; ".join(reasons[:5])


def _terminal_reason(candidate: ExperimentCandidate) -> str:
    if candidate.validator_penalty >= 3:
        return "validator_blocked"
    if candidate.repeat_failure_risk >= 2.5:
        return "repeat_failure_risk"
    if candidate.requires_human_approval:
        return "human_approval_required"
    return ""


def _expand_outcome_scenarios(candidate: ExperimentCandidate) -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []
    for scenario in OUTCOME_SCENARIOS:
        multiplier = {
            "positive_support": 1.0,
            "negative_falsification": 0.95,
            "ambiguous_result": 0.35,
            "failed_execution": 0.2,
            "quality_blocked": 0.1,
        }[scenario]
        scenarios.append(
            {
                "scenario": scenario,
                "estimated_value": round(_portfolio_score(candidate) * multiplier, 3),
                "backpropagation_targets": [
                    "hypothesis_memory",
                    "failure_memory",
                    "experiment_ledger",
                    "asset_graph",
                    "belief_update",
                ],
            }
        )
    return scenarios


def _execution_gate(
    *,
    candidate: ExperimentCandidate,
    scientific_decision_summary: dict[str, Any],
    evidence_review_summary: dict[str, Any],
    experiment_governance_summary: dict[str, Any],
    failure_intelligence_summary: dict[str, Any],
    discipline_adapter_summary: dict[str, Any],
    mid_run_control_summary: dict[str, Any],
) -> dict[str, Any]:
    reasons: list[str] = []
    state = "ready_to_schedule"
    paused = {
        str(item).strip()
        for item in mid_run_control_summary.get("paused_workstreams", [])
        if str(item).strip()
    } if isinstance(mid_run_control_summary.get("paused_workstreams", []), list) else set()
    terminated = {
        str(item).strip()
        for item in mid_run_control_summary.get("terminated_routes", [])
        if str(item).strip()
    } if isinstance(mid_run_control_summary.get("terminated_routes", []), list) else set()
    if terminated.intersection(candidate.target_ids):
        state = "blocked"
        reasons.append("mid-run controller terminated or froze this route")
    if "downstream_experiment_execution" in paused and candidate.experiment_type not in {
        "evidence_quality_repair",
        "evidence_resolution",
    }:
        state = "blocked"
        reasons.append("mid-run controller requires evidence repair before downstream execution")
    if "experiment_execution" in paused and candidate.experiment_type not in {
        "evidence_quality_repair",
        "reproducibility_check",
        "control_or_ablation",
    }:
        state = "needs_protocol"
        reasons.append("mid-run controller requires quality gate repair before execution")
    if scientific_decision_summary.get("must_pause_for_human_review") or candidate.requires_human_approval:
        state = "needs_human_approval"
        reasons.append("human review is required before execution")
    if evidence_review_summary.get("needs_human_adjudication") and candidate.experiment_type not in {
        "evidence_quality_repair",
        "evidence_resolution",
    }:
        state = "needs_human_approval"
        reasons.append("evidence adjudication must be completed before running experiments")
    if candidate.requires_protocol and not candidate.success_criteria:
        state = "needs_protocol"
        reasons.append("missing success criteria")
    if experiment_governance_summary.get("approval_gate_needed") and candidate.experiment_type not in {
        "evidence_quality_repair",
        "evidence_resolution",
    }:
        state = "needs_human_approval"
        reasons.append("experiment governance approval gate is open")
    avoid = set(
        str(item).strip()
        for item in failure_intelligence_summary.get("avoid_repeat_routes", [])
        if str(item).strip()
    )
    if avoid.intersection(candidate.target_ids):
        state = "blocked"
        reasons.append("candidate targets a route marked by failure memory as avoid-repeat")
    blocked_bindings = {
        str(binding.get("experiment_id", "")).strip()
        for binding in discipline_adapter_summary.get("bindings", [])
        if isinstance(binding, dict)
        and str(binding.get("experiment_id", "")).strip()
        and str(binding.get("readiness_state", "")).strip() == "blocked"
    }
    if candidate.experiment_id in blocked_bindings:
        state = "blocked"
        reasons.append("discipline adapter binding is blocked")
    return {"state": state, "reasons": list(dict.fromkeys(reasons))[:8]}


def _execution_queue(scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    rank = 1
    for item in scored:
        gate = item["gate"]
        if gate["state"] != "ready_to_schedule":
            continue
        candidate = item["candidate"]
        schedule_item = ExperimentScheduleItem(
            experiment_id=candidate.experiment_id,
            rank=rank,
            schedule_state="ready_to_schedule",
            portfolio_score=round(float(item["score"]), 3),
            action=f"schedule_{candidate.experiment_type}",
            required_before_execution=candidate.quality_gates,
            recommended_agents=_agents_for_candidate(candidate),
            mcts_like_path=[
                "select_candidate",
                candidate.experiment_type,
                "apply_discipline_adapter",
                "expand_outcomes",
                "execute_gate_passed",
                "backpropagate_result",
            ],
            discipline_binding_id=candidate.discipline_binding_id,
            lifecycle_stages=candidate.lifecycle_stages,
            interpretation_boundaries=candidate.interpretation_boundaries,
            scheduler_rules=candidate.scheduler_rules,
            hypothesis_gate_state=candidate.hypothesis_gate_state,
            hypothesis_validator_flags=candidate.hypothesis_validator_flags,
            validator_penalty=candidate.validator_penalty,
            search_priority=round(_portfolio_score(candidate), 3),
            acquisition_function=candidate.acquisition_function or _acquisition_function(candidate),
            scheduler_node_id=str(item.get("search", {}).get("node_id", "")),
            selection_reason=str(item.get("search", {}).get("selection_reason", "")),
        )
        queue.append(schedule_item.to_dict())
        rank += 1
    return queue[:12]


def _scheduler_state(*, execution_queue: list[dict[str, Any]], blocked: list[dict[str, Any]], scored: list[dict[str, Any]]) -> str:
    if execution_queue:
        return "ready_to_schedule"
    if not scored:
        return "needs_candidates"
    if any(item.get("gate_state") == "needs_human_approval" for item in blocked):
        return "needs_human_approval"
    if any(item.get("gate_state") == "needs_protocol" for item in blocked):
        return "needs_protocol"
    return "blocked"


def _infer_experiment_type(text: str, primary_discipline: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ["tune", "hyperparameter", "parameter", "optimi", "sweep"]):
        return "parameter_optimization"
    if any(token in lowered for token in ["repeat", "replicate", "reproduce"]):
        return "reproducibility_check"
    if any(token in lowered for token in ["ablation", "control", "baseline"]):
        return "control_or_ablation"
    if primary_discipline in {"chemistry", "chemical_engineering", "physics"} and any(
        token in lowered for token in ["temperature", "pressure", "flow", "field", "power"]
    ):
        return "parameter_optimization"
    return "discriminative_experiment"


def _should_add_parameter_optimization(
    topic: str,
    primary_discipline: str,
    scientific_decision_summary: dict[str, Any],
    research_plan_summary: dict[str, Any],
) -> bool:
    text = " ".join(
        [
            topic,
            str(scientific_decision_summary.get("recommended_next_action", "")),
            " ".join(str(item) for item in research_plan_summary.get("next_cycle_experiments", []) if str(item).strip())
            if isinstance(research_plan_summary.get("next_cycle_experiments", []), list)
            else "",
        ]
    ).lower()
    if any(token in text for token in ["hyperparameter", "tuning", "parameter", "optimization", "sweep"]):
        return True
    return primary_discipline in {"artificial_intelligence", "chemical_engineering"}


def _search_space_template(primary_discipline: str) -> dict[str, Any]:
    if primary_discipline == "artificial_intelligence":
        return {
            "learning_rate": "log_uniform",
            "batch_size": "categorical",
            "weight_decay": "log_uniform",
            "seed_policy": "top_configs_multi_seed",
            "confirmatory_rule": "freeze_config_before_test_set",
        }
    if primary_discipline == "chemistry":
        return {"temperature": "bounded_range", "solvent": "categorical", "reaction_time": "bounded_range"}
    if primary_discipline == "chemical_engineering":
        return {"flow_rate": "bounded_range", "pressure": "bounded_range", "residence_time": "bounded_range"}
    if primary_discipline == "physics":
        return {"field_strength": "bounded_range", "temperature": "bounded_range", "measurement_window": "bounded_range"}
    if primary_discipline == "mathematics":
        return {"construction_size": "bounded_integer", "counterexample_family": "categorical"}
    return {"parameter": "bounded_range"}


def _quality_gates_for_type(experiment_type: str, primary_discipline: str) -> list[str]:
    gates = ["protocol_version_recorded", "success_failure_criteria_recorded", "artifact_provenance_recorded"]
    if experiment_type == "parameter_optimization":
        gates.extend(["search_space_frozen", "budget_recorded", "confirmatory_evaluation_split_frozen"])
    if primary_discipline == "artificial_intelligence":
        gates.extend(["dataset_leakage_check", "multi_seed_top_config_check"])
    elif primary_discipline in {"chemistry", "chemical_engineering", "physics"}:
        gates.extend(["calibration_or_control_check", "safety_review_check"])
    elif primary_discipline == "mathematics":
        gates.extend(["assumption_check", "counterexample_check"])
    return list(dict.fromkeys(gates))[:10]


def _success_criteria(experiment_type: str) -> list[str]:
    if experiment_type == "parameter_optimization":
        return ["best configuration selected under frozen validation metric", "confirmatory evaluation plan generated"]
    if experiment_type == "reproducibility_check":
        return ["independent repeat agrees within predefined tolerance"]
    if experiment_type == "evidence_quality_repair":
        return ["evidence review blockers closed or explicitly escalated"]
    return ["result discriminates at least one active hypothesis or mechanism"]


def _failure_criteria(experiment_type: str) -> list[str]:
    if experiment_type == "parameter_optimization":
        return ["budget exhausted without stable configuration", "test set used during exploratory tuning"]
    if experiment_type == "reproducibility_check":
        return ["repeat fails quality control or cannot reproduce critical observation"]
    if experiment_type == "evidence_quality_repair":
        return ["conflict remains unattributed after review pass"]
    return ["result is ambiguous and fails quality control"]


def _agents_for_candidate(candidate: ExperimentCandidate) -> list[str]:
    if candidate.experiment_type == "parameter_optimization":
        return ["experiment_economist", "run_manager", "quality_control_reviewer"]
    if candidate.experiment_type in {"evidence_quality_repair", "evidence_resolution"}:
        return ["literature_reviewer", "conflict_resolver", "critic"]
    if candidate.experiment_type == "reproducibility_check":
        return ["run_manager", "quality_control_reviewer", "result_interpreter"]
    return ["experiment_designer", "run_manager", "quality_control_reviewer"]


def _apply_discipline_bindings(
    *,
    candidates: list[ExperimentCandidate],
    discipline_adapter_summary: dict[str, Any],
) -> list[ExperimentCandidate]:
    bindings = {
        str(binding.get("experiment_id", "")).strip(): binding
        for binding in discipline_adapter_summary.get("bindings", [])
        if isinstance(binding, dict) and str(binding.get("experiment_id", "")).strip()
    }
    if not bindings:
        return candidates
    enriched: list[ExperimentCandidate] = []
    for candidate in candidates:
        binding = bindings.get(candidate.experiment_id)
        if not binding:
            enriched.append(candidate)
            continue
        candidate.discipline_binding_id = str(binding.get("binding_id", "")).strip()
        candidate.lifecycle_stages = _string_list(binding.get("lifecycle_stages", []))
        candidate.measurement_requirements = _string_list(binding.get("measurement_requirements", []))
        candidate.artifact_requirements = _string_list(binding.get("artifact_requirements", []))
        candidate.interpretation_boundaries = _string_list(binding.get("interpretation_boundaries", []))
        candidate.scheduler_rules = _string_list(binding.get("scheduler_rules", []))
        candidate.quality_gates = _dedupe(
            candidate.quality_gates + _string_list(binding.get("quality_gates", []))
        )[:20]
        enriched.append(candidate)
    return enriched


def _root_state(scientific_decision_summary: dict[str, Any], evidence_review_summary: dict[str, Any]) -> str:
    return (
        f"decision={scientific_decision_summary.get('decision_state', 'continue')}; "
        f"evidence={evidence_review_summary.get('review_readiness', 'unknown')}"
    )


def _pressure_score(value: Any) -> float:
    normalized = str(value).strip().lower()
    if normalized == "high":
        return 2.0
    if normalized == "low":
        return 0.5
    return 1.0


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _dedupe_candidates(candidates: list[ExperimentCandidate]) -> list[ExperimentCandidate]:
    seen: set[str] = set()
    unique: list[ExperimentCandidate] = []
    for item in candidates:
        if item.experiment_id in seen:
            continue
        seen.add(item.experiment_id)
        unique.append(item)
    return unique[:50]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys([str(item).strip() for item in values if str(item).strip()]))


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "experiment"


