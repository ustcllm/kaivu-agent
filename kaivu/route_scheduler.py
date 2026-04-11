from __future__ import annotations

from typing import Any


ROUTE_ACTIONS = [
    "review_more_literature",
    "refine_hypothesis",
    "design_discriminative_experiment",
    "schedule_experiment",
    "run_reproducibility_check",
    "hold_lab_meeting",
    "pause_for_human_review",
    "terminate_or_cool_route",
    "publish_or_report",
]


def build_research_route_scheduler_summary(
    *,
    topic: str,
    research_state: dict[str, Any],
    claim_graph: dict[str, Any],
    scheduler_memory_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scheduler_memory_context = scheduler_memory_context or {}
    candidates = _route_candidates(
        research_state=research_state,
        claim_graph=claim_graph,
        scheduler_memory_context=scheduler_memory_context,
    )
    nodes = [_route_node(candidate, index=index, candidate_count=len(candidates)) for index, candidate in enumerate(candidates, start=1)]
    nodes.sort(key=lambda item: float(item.get("selection_score", 0)), reverse=True)
    best = nodes[0] if nodes else {}
    return {
        "route_scheduler_id": f"route-scheduler::{_slugify(topic)}",
        "topic": topic,
        "scheduler_state": "ready" if nodes else "needs_route_candidates",
        "candidate_count": len(candidates),
        "best_action": str(best.get("action", "")),
        "best_route_node_id": str(best.get("node_id", "")),
        "best_selection_reason": str(best.get("selection_reason", "")),
        "route_nodes": nodes[:40],
        "route_tree": {
            "root_node_id": f"route-node::{_slugify(topic)}::root",
            "node_count": len(nodes) + 1,
            "edge_count": len(nodes),
            "edges": [
                {
                    "source": f"route-node::{_slugify(topic)}::root",
                    "target": str(node.get("node_id", "")),
                    "relation": "considers",
                }
                for node in nodes[:40]
            ],
        },
        "policy": {
            "numeric_search": "route_value_plus_ucb_exploration",
            "llm_judge_slot": "same SchedulerLLMJudge can review route candidates after route candidate adapter is enabled",
            "memory_aware": bool(scheduler_memory_context),
        },
    }


def _route_candidates(
    *,
    research_state: dict[str, Any],
    claim_graph: dict[str, Any],
    scheduler_memory_context: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    def add(action: str, reason: str, value: float, cost: float = 1.0, risk: float = 1.0) -> None:
        candidates.append(
            {
                "action": action,
                "reason": reason,
                "value": float(value),
                "cost": float(cost),
                "risk": float(risk),
            }
        )

    evidence = research_state.get("evidence_review_summary", {}) if isinstance(research_state.get("evidence_review_summary", {}), dict) else {}
    hypothesis_gate = research_state.get("hypothesis_gate_summary", {}) if isinstance(research_state.get("hypothesis_gate_summary", {}), dict) else {}
    experiment_scheduler = research_state.get("experiment_execution_loop_summary", {}) if isinstance(research_state.get("experiment_execution_loop_summary", {}), dict) else {}
    lab_meeting = research_state.get("lab_meeting_consensus_summary", {}) if isinstance(research_state.get("lab_meeting_consensus_summary", {}), dict) else {}
    route_temperature = research_state.get("route_temperature_summary", {}) if isinstance(research_state.get("route_temperature_summary", {}), dict) else {}
    human_governance = research_state.get("human_governance_checkpoint_summary", {}) if isinstance(research_state.get("human_governance_checkpoint_summary", {}), dict) else {}
    benchmark = research_state.get("benchmark_case_suite_summary", {}) if isinstance(research_state.get("benchmark_case_suite_summary", {}), dict) else {}
    reframer = research_state.get("scientific_problem_reframer_summary", {}) if isinstance(research_state.get("scientific_problem_reframer_summary", {}), dict) else {}
    prior_program = scheduler_memory_context.get("prior_research_program", {}) if isinstance(scheduler_memory_context.get("prior_research_program", {}), dict) else {}
    prior_control_actions = prior_program.get("control_actions", []) if isinstance(prior_program.get("control_actions", []), list) else []
    prior_portfolio = prior_program.get("experiment_portfolio", {}) if isinstance(prior_program.get("experiment_portfolio", {}), dict) else {}
    rival_reasoning = prior_program.get("rival_hypothesis_reasoning", {}) if isinstance(prior_program.get("rival_hypothesis_reasoning", {}), dict) else {}

    if evidence.get("review_blockers") or evidence.get("review_readiness") not in {"", "decision_ready", "ready"}:
        add("review_more_literature", "evidence review has blockers or is not decision-ready", 7, cost=1, risk=1)
    if hypothesis_gate.get("gate_state") in {"blocked", "revision_required"} or hypothesis_gate.get("blocked_count"):
        add("refine_hypothesis", "hypothesis gate indicates revision or rejection pressure", 8, cost=1, risk=1)
    if experiment_scheduler.get("execution_queue"):
        add("schedule_experiment", "experiment scheduler has ready execution queue", 9, cost=2, risk=2)
    if research_state.get("negative_result_count", 0) or scheduler_memory_context.get("failed_routes"):
        add("run_reproducibility_check", "negative or failed attempts require changed-condition rerun or reproducibility check", 7, cost=2, risk=2)
    if lab_meeting.get("blocking_concerns") or scheduler_memory_context.get("standing_objections"):
        add("hold_lab_meeting", "standing objections or unresolved lab-meeting concerns remain", 6, cost=1, risk=1)
    if human_governance.get("must_pause_execution") or human_governance.get("open_checkpoint_count"):
        add("pause_for_human_review", "human governance checkpoint is open", 10, cost=1, risk=0)
    if reframer.get("reframing_state") == "reframe_recommended":
        preferred = _action_for_reframer_route(
            str(
                (reframer.get("selected_frame", {}) if isinstance(reframer.get("selected_frame", {}), dict) else {}).get(
                    "preferred_next_route", ""
                )
            )
        )
        add(
            preferred,
            "problem reframer recommends changing the research frame before advancing",
            8,
            cost=1,
            risk=1,
        )
    if route_temperature.get("route_temperature") == "hot" or route_temperature.get("cooling_candidates"):
        add("terminate_or_cool_route", "route temperature indicates repeated pressure or weak route reuse", 6, cost=1, risk=1)
    if benchmark.get("benchmark_readiness") in {"medium", "high"} and not human_governance.get("must_pause_execution"):
        add("publish_or_report", "benchmark readiness supports reporting or release review", 5, cost=1, risk=2)
    if prior_control_actions:
        first_action = str(prior_control_actions[0].get("action", "") if isinstance(prior_control_actions[0], dict) else "").strip()
        if "evidence" in first_action:
            add("review_more_literature", "prior research program requires evidence-map repair", 8, cost=1, risk=1)
        elif "hypothesis" in first_action:
            add("refine_hypothesis", "prior research program requires hypothesis lifecycle repair", 8, cost=1, risk=1)
        elif "meeting" in first_action:
            add("hold_lab_meeting", "prior research program requires structured meeting resolution", 7, cost=1, risk=1)
    if prior_portfolio.get("selected_experiments"):
        add("schedule_experiment", "prior research program selected an experiment portfolio", 8, cost=2, risk=2)
    if int(rival_reasoning.get("high_priority_pair_count", 0) or 0) > 0:
        add("design_discriminative_experiment", "rival hypothesis reasoning requires discriminative tests", 8, cost=1, risk=1)
    if not candidates:
        add("design_discriminative_experiment", "default next action is to design the smallest discriminative experiment", 5, cost=1, risk=1)
    return candidates


def _route_node(candidate: dict[str, Any], *, index: int, candidate_count: int) -> dict[str, Any]:
    visits = max(1, int(float(candidate.get("value", 0))))
    exploration = (candidate_count ** 0.5) / (1 + visits)
    selection = float(candidate.get("value", 0)) + exploration - float(candidate.get("cost", 0)) - float(candidate.get("risk", 0))
    return {
        "node_id": f"route-node::{_slugify(str(candidate.get('action', 'route')))}",
        "action": candidate.get("action", ""),
        "visit_count": visits,
        "value_estimate": round(float(candidate.get("value", 0)), 3),
        "exploration_bonus": round(exploration, 3),
        "selection_score": round(selection, 3),
        "selection_reason": candidate.get("reason", ""),
        "rank_prior": index,
    }


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "route"


def _action_for_reframer_route(route: str) -> str:
    normalized = route.strip().lower()
    if "literature" in normalized or "review" in normalized:
        return "review_more_literature"
    if "hypothesis" in normalized or "theory" in normalized:
        return "refine_hypothesis"
    if "experiment" in normalized or "testing" in normalized:
        return "design_discriminative_experiment"
    if "integration" in normalized or "meeting" in normalized:
        return "hold_lab_meeting"
    return "refine_hypothesis"
