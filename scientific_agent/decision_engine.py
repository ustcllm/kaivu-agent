from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ScientificDecision:
    decision_id: str
    target_id: str
    target_type: str
    action: str
    priority: str
    information_gain_score: int
    cost_score: int
    time_score: int
    risk_score: int
    governance_burden_score: int
    route_value_score: int
    rationale: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    recommended_agents: list[str] = field(default_factory=list)
    evidence_trace: list[dict[str, str]] = field(default_factory=list)
    decision_inputs: dict[str, Any] = field(default_factory=dict)
    human_review_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_scientific_decision_summary(
    *,
    topic: str,
    hypothesis_theory_summary: dict[str, Any],
    research_route_search_summary: dict[str, Any],
    experiment_economics_summary: dict[str, Any],
    failure_intelligence_summary: dict[str, Any],
    systematic_review_summary: dict[str, Any],
    evidence_review_summary: dict[str, Any],
    human_governance_checkpoint_summary: dict[str, Any],
    lab_meeting_consensus_summary: dict[str, Any],
    termination_strategy_summary: dict[str, Any],
) -> dict[str, Any]:
    evidence_review_summary = evidence_review_summary or {}
    decisions: list[ScientificDecision] = []
    theory_objects = [
        item
        for item in hypothesis_theory_summary.get("objects", [])
        if isinstance(item, dict)
    ]
    if theory_objects:
        for item in theory_objects:
            decisions.append(
                _decision_for_theory_object(
                    item,
                    experiment_economics_summary=experiment_economics_summary,
                    failure_intelligence_summary=failure_intelligence_summary,
                    evidence_review_summary=evidence_review_summary,
                    human_governance_checkpoint_summary=human_governance_checkpoint_summary,
                    lab_meeting_consensus_summary=lab_meeting_consensus_summary,
                )
            )
    else:
        decisions.append(
            _general_decision(
                topic=topic,
                research_route_search_summary=research_route_search_summary,
                systematic_review_summary=systematic_review_summary,
                evidence_review_summary=evidence_review_summary,
                human_governance_checkpoint_summary=human_governance_checkpoint_summary,
            )
        )

    evidence_review_decision = _decision_for_evidence_review(
        topic=topic,
        systematic_review_summary=systematic_review_summary,
        evidence_review_summary=evidence_review_summary,
    )
    if evidence_review_decision is not None:
        decisions.append(evidence_review_decision)
    elif systematic_review_summary.get("review_protocol_gaps") or systematic_review_summary.get("bias_hotspots"):
        decisions.append(
            _make_decision(
                target_id="literature-review",
                target_type="literature",
                action="strengthen_evidence_review",
                information_gain=4,
                cost=1,
                time_cost=1,
                risk=1,
                governance=0,
                rationale=["systematic review has protocol gaps or bias hotspots"],
                prerequisites=["update screening and evidence tables before changing consensus"],
                agents=["literature_reviewer", "critic"],
                evidence_trace=_trace_items(
                    [
                        ("systematic_review", "literature-review", "review protocol gaps or bias hotspots"),
                    ]
                ),
                decision_inputs={
                    "review_protocol_gaps": systematic_review_summary.get("review_protocol_gaps", []),
                    "bias_hotspots": systematic_review_summary.get("bias_hotspots", []),
                },
            )
        )

    if human_governance_checkpoint_summary.get("human_approval_checkpoint_count", 0):
        decisions.append(
            _make_decision(
                target_id="human-governance",
                target_type="governance",
                action="request_group_adjudication",
                information_gain=3,
                cost=0,
                time_cost=1,
                risk=0,
                governance=4,
                rationale=["open governance checkpoints block autonomous route advancement"],
                prerequisites=human_governance_checkpoint_summary.get("recommended_decision_packet", []),
                agents=["lab_meeting_moderator", "coordinator"],
                evidence_trace=_trace_items(
                    [
                        ("governance_checkpoint", "human-governance", "open human governance checkpoint"),
                    ]
                ),
                decision_inputs={
                    "checkpoint_count": human_governance_checkpoint_summary.get(
                        "human_approval_checkpoint_count", 0
                    ),
                    "governance_state": human_governance_checkpoint_summary.get("governance_state", ""),
                },
                human_review_required=True,
            )
        )

    retired_routes = [
        str(item.get("route_id", "")).strip()
        for item in termination_strategy_summary.get("retired_routes", [])
        if isinstance(item, dict) and str(item.get("route_id", "")).strip()
    ]
    for route_id in retired_routes[:6]:
        decisions.append(
            _make_decision(
                target_id=route_id,
                target_type="research_route",
                action="retire_or_freeze_route",
                information_gain=2,
                cost=0,
                time_cost=0,
                risk=1,
                governance=2,
                rationale=["termination strategy marks this route as retired or no longer viable"],
                prerequisites=["record rationale and prevent automatic reuse unless revived by new evidence"],
                agents=["belief_updater", "lab_meeting_moderator"],
                evidence_trace=_trace_items(
                    [
                        ("termination_strategy", route_id, "route listed in retired_routes"),
                    ]
                ),
                decision_inputs={"retired_route_id": route_id},
                human_review_required=True,
            )
        )

    decisions = sorted(
        decisions,
        key=lambda item: (
            item.route_value_score,
            item.information_gain_score,
            -item.governance_burden_score,
        ),
        reverse=True,
    )
    decision_dicts = [item.to_dict() for item in decisions]
    top = decision_dicts[0] if decision_dicts else {}
    return {
        "topic": topic,
        "decision_count": len(decision_dicts),
        "recommended_next_action": str(top.get("action", "continue_current_route")),
        "recommended_target_id": str(top.get("target_id", "")),
        "decision_state": _overall_decision_state(decision_dicts),
        "must_pause_for_human_review": any(bool(item.get("human_review_required")) for item in decision_dicts[:3]),
        "decision_queue": decision_dicts[:12],
        "provenance_trace_count": sum(len(item.get("evidence_trace", [])) for item in decision_dicts),
        "route_search_best_action": research_route_search_summary.get("best_next_action", ""),
        "evidence_review_readiness": evidence_review_summary.get("review_readiness", ""),
        "evidence_review_quality_state": evidence_review_summary.get("review_quality_state", ""),
    }


def recommended_agents_for_decision_action(action: str) -> list[str]:
    return {
        "run_discriminative_test": ["experiment_designer", "experiment_economist", "run_manager"],
        "revise_theory_object": ["hypothesis_generator", "critic", "experiment_designer"],
        "complete_theory_specification": ["hypothesis_generator", "critic"],
        "block_or_retire_hypothesis": ["belief_updater", "lab_meeting_moderator"],
        "strengthen_evidence_review": ["literature_reviewer", "critic"],
        "resolve_evidence_conflicts": ["literature_reviewer", "conflict_resolver", "lab_meeting_moderator"],
        "request_group_adjudication": ["lab_meeting_moderator", "coordinator"],
        "retire_or_freeze_route": ["belief_updater", "lab_meeting_moderator"],
        "monitor_hypothesis": ["coordinator"],
    }.get(str(action).strip().lower(), ["coordinator"])


def _decision_for_theory_object(
    item: dict[str, Any],
    *,
    experiment_economics_summary: dict[str, Any],
    failure_intelligence_summary: dict[str, Any],
    evidence_review_summary: dict[str, Any],
    human_governance_checkpoint_summary: dict[str, Any],
    lab_meeting_consensus_summary: dict[str, Any],
) -> ScientificDecision:
    target_id = str(item.get("hypothesis_id", "")).strip()
    decision_state = str(item.get("decision_state", "observe")).strip().lower()
    maturity = str(item.get("theory_maturity", "flat")).strip().lower()
    missing = [str(value) for value in item.get("missing_theory_fields", []) if str(value).strip()]
    rationale = [
        f"theory maturity is {maturity}",
        f"hypothesis decision state is {decision_state}",
    ]
    evidence_trace = _trace_items(
        [
            ("hypothesis_theory_object", str(item.get("theory_object_id", "")).strip() or target_id, "decision target"),
            ("hypothesis", target_id, "formalized hypothesis"),
        ]
    )
    prerequisites = []
    action = "monitor_hypothesis"
    information_gain = 2
    cost = _pressure_score(experiment_economics_summary.get("cost_pressure", "medium"))
    time_cost = _pressure_score(experiment_economics_summary.get("time_pressure", "medium"))
    risk = 1
    governance = 1 if human_governance_checkpoint_summary.get("must_pause_execution") else 0
    agents = ["coordinator"]
    human_review_required = False

    if decision_state == "advance":
        action = "run_discriminative_test"
        information_gain = 5 if maturity == "predictive" else 4
        prerequisites = item.get("discriminating_experiments", []) or item.get("falsification_tests", [])
        agents = ["experiment_designer", "experiment_economist", "run_manager"]
    elif decision_state == "revise":
        action = "revise_theory_object"
        information_gain = 4
        cost = min(cost, 1)
        time_cost = min(time_cost, 1)
        prerequisites = [f"fill missing theory field: {field_name}" for field_name in missing[:5]]
        if item.get("negative_result_refs"):
            prerequisites.append("explain why prior negative results should not invalidate the revised route")
        agents = ["hypothesis_generator", "critic", "experiment_designer"]
    elif decision_state == "block":
        action = "block_or_retire_hypothesis"
        information_gain = 2
        cost = 0
        time_cost = 0
        risk = 1
        governance = 3
        prerequisites = ["record retirement rationale and revival conditions"]
        agents = ["belief_updater", "lab_meeting_moderator"]
        human_review_required = True
    elif missing:
        action = "complete_theory_specification"
        information_gain = 3
        cost = 1
        time_cost = 1
        prerequisites = [f"fill missing theory field: {field_name}" for field_name in missing[:5]]
        agents = ["hypothesis_generator", "critic"]

    if failure_intelligence_summary.get("avoid_repeat_routes") or item.get("negative_result_refs"):
        risk += 1
        rationale.append("failure memory indicates repeat-risk should be checked")
        evidence_trace.extend(
            _trace_items(
                [
                    ("negative_result", str(ref), "negative result challenges or informs this route")
                    for ref in item.get("negative_result_refs", [])
                    if str(ref).strip()
                ]
            )
        )
    if lab_meeting_consensus_summary.get("blocking_concerns"):
        governance += 1
        rationale.append("lab meeting still has blocking concerns")
        evidence_trace.append(
            {
                "source_type": "lab_meeting",
                "source_id": "lab-meeting-consensus",
                "reason": "blocking concerns affect route governance",
            }
        )
    review_readiness = str(evidence_review_summary.get("review_readiness", "")).strip()
    review_quality = str(evidence_review_summary.get("review_quality_state", "")).strip()
    if review_readiness and review_readiness != "decision_ready":
        rationale.append(f"evidence review readiness is {review_readiness}")
        prerequisites.append("resolve evidence review blockers before treating this route as decision-grade")
        risk += 1
        if action == "run_discriminative_test" and review_readiness in {"draft", "screening_ready"}:
            action = "strengthen_evidence_review"
            agents = ["literature_reviewer", "critic"]
            information_gain = max(information_gain, 4)
    if evidence_review_summary.get("needs_human_adjudication"):
        governance += 2
        human_review_required = True
        rationale.append("evidence review requires human adjudication")
        prerequisites.extend(evidence_review_summary.get("review_blockers", [])[:3])
        if str(evidence_review_summary.get("conflict_resolution_state", "")).strip().lower() in {
            "unresolved",
            "adjudication_needed",
        }:
            action = "resolve_evidence_conflicts"
            agents = ["literature_reviewer", "conflict_resolver", "lab_meeting_moderator"]
            information_gain = max(information_gain, 5)
    if evidence_review_summary:
        evidence_trace.append(
            {
                "source_type": "evidence_review",
                "source_id": str(evidence_review_summary.get("review_id", "evidence-review")),
                "reason": f"readiness={review_readiness or 'unknown'}; quality={review_quality or 'unknown'}",
            }
        )
    if not prerequisites:
        prerequisites = ["confirm evidence grounding and smallest next discriminative action"]

    return _make_decision(
        target_id=target_id,
        target_type="hypothesis_theory_object",
        action=action,
        information_gain=information_gain,
        cost=cost,
        time_cost=time_cost,
        risk=risk,
        governance=governance,
        rationale=rationale,
        prerequisites=prerequisites,
        agents=agents or recommended_agents_for_decision_action(action),
        evidence_trace=evidence_trace,
        decision_inputs={
            "theory_maturity": maturity,
            "hypothesis_decision_state": decision_state,
            "missing_theory_fields": missing,
            "cost_pressure": experiment_economics_summary.get("cost_pressure", "medium"),
            "time_pressure": experiment_economics_summary.get("time_pressure", "medium"),
            "negative_result_refs": item.get("negative_result_refs", []),
            "evidence_review_readiness": review_readiness,
            "evidence_review_quality_state": review_quality,
            "evidence_review_blockers": evidence_review_summary.get("review_blockers", []),
        },
        human_review_required=human_review_required,
    )


def _decision_for_evidence_review(
    *,
    topic: str,
    systematic_review_summary: dict[str, Any],
    evidence_review_summary: dict[str, Any],
) -> ScientificDecision | None:
    if not evidence_review_summary:
        return None
    readiness = str(evidence_review_summary.get("review_readiness", "draft")).strip().lower()
    quality_state = str(evidence_review_summary.get("review_quality_state", "needs_review")).strip().lower()
    blockers = [
        str(item).strip()
        for item in evidence_review_summary.get("review_blockers", [])
        if str(item).strip()
    ] if isinstance(evidence_review_summary.get("review_blockers", []), list) else []
    actions = [
        str(item).strip()
        for item in evidence_review_summary.get("recommended_review_actions", [])
        if str(item).strip()
    ] if isinstance(evidence_review_summary.get("recommended_review_actions", []), list) else []
    conflict_state = str(evidence_review_summary.get("conflict_resolution_state", "none")).strip().lower()
    bias_summary = (
        evidence_review_summary.get("bias_risk_summary", {})
        if isinstance(evidence_review_summary.get("bias_risk_summary", {}), dict)
        else {}
    )
    needs_human = bool(evidence_review_summary.get("needs_human_adjudication"))
    if readiness == "decision_ready" and quality_state == "decision_grade" and not needs_human:
        return None

    action = "strengthen_evidence_review"
    agents = ["literature_reviewer", "critic"]
    information_gain = 4
    governance = 0
    risk = 1
    if conflict_state in {"unresolved", "adjudication_needed"}:
        action = "resolve_evidence_conflicts"
        agents = ["literature_reviewer", "conflict_resolver", "lab_meeting_moderator"]
        information_gain = 5
        governance = 2 if needs_human else 1
        risk = 2
    elif bias_summary.get("high_risk_count", 0):
        action = "resolve_evidence_conflicts"
        agents = ["literature_reviewer", "critic", "lab_meeting_moderator"]
        information_gain = 5
        governance = 2
        risk = 2

    return _make_decision(
        target_id=str(evidence_review_summary.get("review_id", "")).strip() or topic,
        target_type="evidence_review",
        action=action,
        information_gain=information_gain,
        cost=1,
        time_cost=1,
        risk=risk,
        governance=governance,
        rationale=[
            f"evidence review readiness is {readiness}",
            f"evidence review quality state is {quality_state}",
            f"conflict resolution state is {conflict_state}",
        ],
        prerequisites=blockers or actions or ["complete evidence review before decision-grade synthesis"],
        agents=agents,
        evidence_trace=_trace_items(
            [
                ("evidence_review", str(evidence_review_summary.get("review_id", "")), "evidence review governs decision quality"),
                ("systematic_review", str(systematic_review_summary.get("review_question", "") or topic), "underlying systematic review"),
            ]
        ),
        decision_inputs={
            "review_readiness": readiness,
            "review_quality_state": quality_state,
            "protocol_completeness_score": evidence_review_summary.get("protocol_completeness_score", 0),
            "screening_quality_score": evidence_review_summary.get("screening_quality_score", 0),
            "evidence_grade_balance": evidence_review_summary.get("evidence_grade_balance", {}),
            "bias_risk_summary": bias_summary,
            "conflict_resolution_state": conflict_state,
            "recommended_review_actions": actions,
        },
        human_review_required=needs_human or conflict_state == "adjudication_needed",
    )


def _general_decision(
    *,
    topic: str,
    research_route_search_summary: dict[str, Any],
    systematic_review_summary: dict[str, Any],
    evidence_review_summary: dict[str, Any],
    human_governance_checkpoint_summary: dict[str, Any],
) -> ScientificDecision:
    action = str(research_route_search_summary.get("best_next_action", "")).strip() or "continue_current_route"
    rationale = ["no hypothesis theory objects are available yet"]
    if systematic_review_summary.get("review_protocol_gaps"):
        rationale.append("review protocol gaps should be closed before strong claims")
    if evidence_review_summary and evidence_review_summary.get("review_readiness") != "decision_ready":
        rationale.append(
            f"evidence review readiness is {evidence_review_summary.get('review_readiness', 'draft')}"
        )
    if human_governance_checkpoint_summary.get("human_approval_checkpoint_count"):
        rationale.append("human governance checkpoint is open")
    return _make_decision(
        target_id=topic,
        target_type="research_topic",
        action=action,
        information_gain=3,
        cost=1,
        time_cost=1,
        risk=1,
        governance=1 if human_governance_checkpoint_summary.get("human_approval_checkpoint_count") else 0,
        rationale=rationale,
        prerequisites=["generate at least one explicit hypothesis theory object"],
        agents=["research_planner", "hypothesis_generator"],
        evidence_trace=_trace_items(
            [
                ("research_route_search", topic, "fallback route action because no theory objects exist"),
            ]
        ),
        decision_inputs={
            "route_search_best_action": research_route_search_summary.get("best_next_action", ""),
            "human_checkpoint_count": human_governance_checkpoint_summary.get(
                "human_approval_checkpoint_count", 0
            ),
            "evidence_review_readiness": evidence_review_summary.get("review_readiness", ""),
        },
    )


def _make_decision(
    *,
    target_id: str,
    target_type: str,
    action: str,
    information_gain: int,
    cost: int,
    time_cost: int,
    risk: int,
    governance: int,
    rationale: list[str],
    prerequisites: list[str],
    agents: list[str],
    evidence_trace: list[dict[str, str]] | None = None,
    decision_inputs: dict[str, Any] | None = None,
    human_review_required: bool = False,
) -> ScientificDecision:
    route_value = (information_gain * 3) - (cost + time_cost + risk + governance)
    return ScientificDecision(
        decision_id=f"decision::{_slugify(target_type)}::{_slugify(target_id)}::{_slugify(action)}",
        target_id=target_id,
        target_type=target_type,
        action=action,
        priority=_priority(route_value, human_review_required=human_review_required),
        information_gain_score=information_gain,
        cost_score=cost,
        time_score=time_cost,
        risk_score=risk,
        governance_burden_score=governance,
        route_value_score=route_value,
        rationale=list(dict.fromkeys([str(item) for item in rationale if str(item).strip()]))[:8],
        prerequisites=list(dict.fromkeys([str(item) for item in prerequisites if str(item).strip()]))[:8],
        recommended_agents=list(dict.fromkeys([str(item) for item in agents if str(item).strip()]))[:6],
        evidence_trace=evidence_trace or [],
        decision_inputs=decision_inputs or {},
        human_review_required=human_review_required,
    )


def _trace_items(items: list[tuple[str, str, str]]) -> list[dict[str, str]]:
    traces: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for source_type, source_id, reason in items:
        source_id = str(source_id).strip()
        if not source_id:
            continue
        key = (str(source_type), source_id, str(reason))
        if key in seen:
            continue
        seen.add(key)
        traces.append(
            {
                "source_type": str(source_type),
                "source_id": source_id,
                "reason": str(reason),
            }
        )
    return traces


def _pressure_score(value: Any) -> int:
    normalized = str(value).strip().lower()
    if normalized == "high":
        return 2
    if normalized == "low":
        return 0
    return 1


def _priority(route_value: int, *, human_review_required: bool) -> str:
    if human_review_required:
        return "governance_blocking"
    if route_value >= 10:
        return "high"
    if route_value >= 6:
        return "medium"
    return "low"


def _overall_decision_state(decisions: list[dict[str, Any]]) -> str:
    if not decisions:
        return "no_decision"
    if any(item.get("priority") == "governance_blocking" for item in decisions[:3]):
        return "human_review_required"
    top_action = str(decisions[0].get("action", "")).strip()
    if top_action in {"run_discriminative_test", "benchmark_route"}:
        return "ready_to_execute"
    if top_action in {"revise_theory_object", "complete_theory_specification"}:
        return "needs_theory_revision"
    if top_action in {"strengthen_evidence_review", "resolve_evidence_conflicts"}:
        return "needs_evidence_review"
    return "continue"


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "item"
