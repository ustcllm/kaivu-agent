from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class AutonomousResearchControllerState:
    controller_id: str
    controller_state: str
    loop_decision: str
    next_cycle_stage: str
    next_cycle_action: str
    recommended_agents: list[str] = field(default_factory=list)
    pause_reasons: list[str] = field(default_factory=list)
    escalation_reasons: list[str] = field(default_factory=list)
    required_inputs: list[str] = field(default_factory=list)
    safety_gates: list[str] = field(default_factory=list)
    continuation_budget: dict[str, int] = field(default_factory=dict)
    stop_conditions: list[str] = field(default_factory=list)
    monitoring_plan: list[str] = field(default_factory=list)
    decision_trace: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_autonomous_controller_summary(
    *,
    topic: str,
    project_id: str = "",
    stage_machine: dict[str, Any],
    autonomy_summary: dict[str, Any],
    scientific_decision_summary: dict[str, Any],
    evidence_review_summary: dict[str, Any],
    experiment_governance_summary: dict[str, Any],
    experiment_execution_loop_summary: dict[str, Any],
    termination_strategy_summary: dict[str, Any],
    human_governance_checkpoint_summary: dict[str, Any],
    evaluation_summary: dict[str, Any],
    run_manifest: dict[str, Any],
    mid_run_control_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    experiment_execution_loop_summary = experiment_execution_loop_summary or {}
    mid_run_control_summary = mid_run_control_summary or {}
    decision_action = str(
        scientific_decision_summary.get("recommended_next_action", "continue_current_route")
    ).strip()
    decision_state = str(scientific_decision_summary.get("decision_state", "continue")).strip()
    recommended_agents = _recommended_agents(scientific_decision_summary, autonomy_summary)
    pause_reasons = _pause_reasons(
        stage_machine=stage_machine,
        scientific_decision_summary=scientific_decision_summary,
        evidence_review_summary=evidence_review_summary,
        experiment_governance_summary=experiment_governance_summary,
        experiment_execution_loop_summary=experiment_execution_loop_summary,
        termination_strategy_summary=termination_strategy_summary,
        human_governance_checkpoint_summary=human_governance_checkpoint_summary,
        mid_run_control_summary=mid_run_control_summary,
    )
    escalation_reasons = _escalation_reasons(
        evidence_review_summary=evidence_review_summary,
        termination_strategy_summary=termination_strategy_summary,
        human_governance_checkpoint_summary=human_governance_checkpoint_summary,
        evaluation_summary=evaluation_summary,
        mid_run_control_summary=mid_run_control_summary,
    )
    next_stage = _next_stage(
        stage_machine=stage_machine,
        decision_action=decision_action,
        pause_reasons=pause_reasons,
    )
    loop_decision = _loop_decision(
        decision_action=decision_action,
        decision_state=decision_state,
        pause_reasons=pause_reasons,
        termination_strategy_summary=termination_strategy_summary,
    )
    controller_state = _controller_state(
        loop_decision=loop_decision,
        pause_reasons=pause_reasons,
        escalation_reasons=escalation_reasons,
    )
    required_inputs = _required_inputs(
        decision_action=decision_action,
        stage_machine=stage_machine,
        evidence_review_summary=evidence_review_summary,
        experiment_governance_summary=experiment_governance_summary,
        experiment_execution_loop_summary=experiment_execution_loop_summary,
        mid_run_control_summary=mid_run_control_summary,
    )
    safety_gates = _safety_gates(
        evidence_review_summary=evidence_review_summary,
        experiment_governance_summary=experiment_governance_summary,
        human_governance_checkpoint_summary=human_governance_checkpoint_summary,
    )
    continuation_budget = _continuation_budget(
        controller_state=controller_state,
        decision_state=decision_state,
        run_manifest=run_manifest,
    )
    monitoring_plan = _monitoring_plan(
        autonomy_summary=autonomy_summary,
        evidence_review_summary=evidence_review_summary,
        experiment_governance_summary=experiment_governance_summary,
        experiment_execution_loop_summary=experiment_execution_loop_summary,
    )
    state = AutonomousResearchControllerState(
        controller_id=f"autonomous-controller::{_slugify(project_id or 'workspace')}::{_slugify(topic)}",
        controller_state=controller_state,
        loop_decision=loop_decision,
        next_cycle_stage=next_stage,
        next_cycle_action=decision_action or "continue_current_route",
        recommended_agents=recommended_agents,
        pause_reasons=pause_reasons,
        escalation_reasons=escalation_reasons,
        required_inputs=required_inputs,
        safety_gates=safety_gates,
        continuation_budget=continuation_budget,
        stop_conditions=_stop_conditions(autonomy_summary, termination_strategy_summary),
        monitoring_plan=monitoring_plan,
        decision_trace=_decision_trace(
            scientific_decision_summary=scientific_decision_summary,
            evidence_review_summary=evidence_review_summary,
            termination_strategy_summary=termination_strategy_summary,
        ),
    )
    payload = state.to_dict()
    payload.update(
        {
            "topic": topic,
            "project_id": project_id,
            "can_continue_autonomously": controller_state in {
                "continue_autonomously",
                "ready_for_next_cycle",
            },
            "must_pause_for_human": controller_state in {
                "pause_for_human",
                "blocked",
                "terminate_or_retire",
            },
            "source_decision_state": decision_state,
            "source_recommended_action": decision_action,
            "experiment_scheduler_state": experiment_execution_loop_summary.get("scheduler_state", ""),
            "scheduled_top_experiment_id": experiment_execution_loop_summary.get("top_experiment_id", ""),
            "mid_run_control_state": {
                "decision_count": mid_run_control_summary.get("decision_count", 0),
                "hard_control_count": mid_run_control_summary.get("hard_control_count", 0),
                "stop_routing": bool(mid_run_control_summary.get("stop_routing")),
                "paused_workstreams": mid_run_control_summary.get("paused_workstreams", []),
                "required_evidence_repairs": mid_run_control_summary.get("required_evidence_repairs", []),
                "terminated_routes": mid_run_control_summary.get("terminated_routes", []),
            },
        }
    )
    return payload


def _recommended_agents(
    scientific_decision_summary: dict[str, Any],
    autonomy_summary: dict[str, Any],
) -> list[str]:
    queue = scientific_decision_summary.get("decision_queue", [])
    if isinstance(queue, list):
        for item in queue:
            if isinstance(item, dict) and item.get("recommended_agents"):
                return [
                    str(agent).strip()
                    for agent in item.get("recommended_agents", [])
                    if str(agent).strip()
                ][:6]
    actions = autonomy_summary.get("autonomous_next_actions", [])
    agents: list[str] = []
    for action in actions if isinstance(actions, list) else []:
        action_text = str(action).lower()
        if "review" in action_text or "evidence" in action_text:
            agents.append("literature_reviewer")
        if "hypothesis" in action_text:
            agents.append("hypothesis_generator")
        if "experiment" in action_text or "execute" in action_text:
            agents.extend(["experiment_designer", "run_manager"])
    return list(dict.fromkeys(agents or ["coordinator"]))[:6]


def _pause_reasons(
    *,
    stage_machine: dict[str, Any],
    scientific_decision_summary: dict[str, Any],
    evidence_review_summary: dict[str, Any],
    experiment_governance_summary: dict[str, Any],
    experiment_execution_loop_summary: dict[str, Any],
    termination_strategy_summary: dict[str, Any],
    human_governance_checkpoint_summary: dict[str, Any],
    mid_run_control_summary: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if stage_machine.get("blockers"):
        reasons.extend([str(item) for item in stage_machine.get("blockers", []) if str(item).strip()])
    if scientific_decision_summary.get("must_pause_for_human_review"):
        reasons.append("scientific decision engine requires human review")
    if evidence_review_summary.get("needs_human_adjudication"):
        reasons.append("evidence review requires human adjudication")
    if experiment_governance_summary.get("approval_gate_needed"):
        reasons.append("experiment governance requires approval before execution")
    if experiment_execution_loop_summary.get("scheduler_state") in {"needs_human_approval", "blocked"}:
        reasons.append(f"experiment scheduler is {experiment_execution_loop_summary.get('scheduler_state')}")
    if human_governance_checkpoint_summary.get("must_pause_execution"):
        reasons.append("human governance checkpoint requires pause")
    if termination_strategy_summary.get("human_confirmation_required"):
        reasons.append("termination or route retirement requires human confirmation")
    if mid_run_control_summary.get("stop_routing"):
        reasons.append("mid-run controller stopped downstream routing")
    for item in mid_run_control_summary.get("paused_workstreams", []) if isinstance(mid_run_control_summary.get("paused_workstreams", []), list) else []:
        if str(item).strip():
            reasons.append(f"mid-run controller paused {item}")
    return list(dict.fromkeys(reasons))[:12]


def _escalation_reasons(
    *,
    evidence_review_summary: dict[str, Any],
    termination_strategy_summary: dict[str, Any],
    human_governance_checkpoint_summary: dict[str, Any],
    evaluation_summary: dict[str, Any],
    mid_run_control_summary: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if evidence_review_summary.get("conflict_resolution_state") == "adjudication_needed":
        reasons.append("evidence conflicts need group adjudication")
    if evidence_review_summary.get("bias_risk_summary", {}).get("high_risk_count", 0):
        reasons.append("high-bias evidence is affecting decisions")
    if termination_strategy_summary.get("retired_routes"):
        reasons.append("route retirement is under consideration")
    if human_governance_checkpoint_summary.get("required_roles"):
        roles = ", ".join(str(item) for item in human_governance_checkpoint_summary.get("required_roles", []))
        reasons.append(f"required human roles: {roles}")
    if evaluation_summary.get("retired_route_reuse_risk") == "high":
        reasons.append("retired route reuse risk is high")
    if mid_run_control_summary.get("hard_control_count", 0):
        reasons.append("mid-run active control changed the workflow path")
    return list(dict.fromkeys(reasons))[:10]


def _next_stage(*, stage_machine: dict[str, Any], decision_action: str, pause_reasons: list[str]) -> str:
    if pause_reasons:
        return "decide"
    action = decision_action.lower()
    if "evidence" in action or "literature" in action:
        return "review"
    if "hypothesis" in action or "theory" in action:
        return "hypothesis"
    if "experiment" in action or "test" in action:
        return "design"
    if "run" in action or "execute" in action:
        return "execute"
    return str(stage_machine.get("recommended_next_stage", "review")).strip() or "review"


def _loop_decision(
    *,
    decision_action: str,
    decision_state: str,
    pause_reasons: list[str],
    termination_strategy_summary: dict[str, Any],
) -> str:
    if termination_strategy_summary.get("recommended_action") in {"terminate", "terminate_or_retire_route"}:
        return "terminate_or_retire"
    if pause_reasons:
        return "pause_and_escalate"
    if decision_state == "ready_to_execute":
        return "advance_next_cycle"
    if decision_action in {"strengthen_evidence_review", "resolve_evidence_conflicts"}:
        return "repair_evidence_base"
    if decision_action in {"revise_theory_object", "complete_theory_specification"}:
        return "repair_theory"
    return "continue_monitoring"


def _controller_state(
    *,
    loop_decision: str,
    pause_reasons: list[str],
    escalation_reasons: list[str],
) -> str:
    if loop_decision == "terminate_or_retire":
        return "terminate_or_retire"
    if pause_reasons and escalation_reasons:
        return "pause_for_human"
    if pause_reasons:
        return "blocked"
    if loop_decision == "advance_next_cycle":
        return "ready_for_next_cycle"
    return "continue_autonomously"


def _required_inputs(
    *,
    decision_action: str,
    stage_machine: dict[str, Any],
    evidence_review_summary: dict[str, Any],
    experiment_governance_summary: dict[str, Any],
    experiment_execution_loop_summary: dict[str, Any],
    mid_run_control_summary: dict[str, Any],
) -> list[str]:
    required: list[str] = []
    required.extend(str(item) for item in stage_machine.get("missing_prerequisites", []) if str(item).strip())
    required.extend(str(item) for item in evidence_review_summary.get("review_blockers", []) if str(item).strip())
    if decision_action == "run_discriminative_test":
        required.append("minimal executable protocol and success/failure criteria")
    if experiment_governance_summary.get("approval_gate_needed"):
        required.append("experiment approval record")
    required.extend(
        str(item)
        for item in mid_run_control_summary.get("required_evidence_repairs", [])
        if str(item).strip()
    ) if isinstance(mid_run_control_summary.get("required_evidence_repairs", []), list) else None
    return list(dict.fromkeys(required))[:12]


def _safety_gates(
    *,
    evidence_review_summary: dict[str, Any],
    experiment_governance_summary: dict[str, Any],
    human_governance_checkpoint_summary: dict[str, Any],
) -> list[str]:
    gates: list[str] = []
    if evidence_review_summary.get("review_readiness") != "decision_ready":
        gates.append("do not freeze conclusions until evidence review is decision-ready")
    if evidence_review_summary.get("needs_human_adjudication"):
        gates.append("human adjudication required before autonomous execution")
    if experiment_governance_summary.get("approval_gate_needed"):
        gates.append("approval required before running experiments")
    if human_governance_checkpoint_summary.get("must_pause_execution"):
        gates.append("human governance checkpoint blocks execution")
    return list(dict.fromkeys(gates))[:10]


def _continuation_budget(
    *,
    controller_state: str,
    decision_state: str,
    run_manifest: dict[str, Any],
) -> dict[str, int]:
    base_steps = 0 if controller_state in {"pause_for_human", "blocked", "terminate_or_retire"} else 2
    if controller_state == "ready_for_next_cycle" and decision_state == "ready_to_execute":
        base_steps = 3
    model_count = len(run_manifest.get("models_used", [])) if isinstance(run_manifest.get("models_used", []), list) else 0
    return {
        "max_autonomous_agent_steps": base_steps,
        "max_tool_calls_before_review": max(3, 8 - model_count),
        "max_new_hypotheses_before_review": 3,
    }


def _stop_conditions(
    autonomy_summary: dict[str, Any],
    termination_strategy_summary: dict[str, Any],
) -> list[str]:
    stop_conditions = [
        str(item)
        for item in autonomy_summary.get("termination_conditions", [])
        if str(item).strip()
    ] if isinstance(autonomy_summary.get("termination_conditions", []), list) else []
    stop_conditions.extend(
        str(item)
        for item in termination_strategy_summary.get("termination_condition_hits", [])
        if str(item).strip()
    ) if isinstance(termination_strategy_summary.get("termination_condition_hits", []), list) else None
    return list(dict.fromkeys(stop_conditions))[:10]


def _monitoring_plan(
    *,
    autonomy_summary: dict[str, Any],
    evidence_review_summary: dict[str, Any],
    experiment_governance_summary: dict[str, Any],
    experiment_execution_loop_summary: dict[str, Any],
) -> list[str]:
    signals = [
        str(item)
        for item in autonomy_summary.get("monitoring_signals", [])
        if str(item).strip()
    ] if isinstance(autonomy_summary.get("monitoring_signals", []), list) else []
    if evidence_review_summary:
        signals.append("evidence review readiness changes")
    if experiment_governance_summary:
        signals.append("experiment run status or quality control status changes")
    if experiment_execution_loop_summary:
        signals.append("experiment scheduler queue or gate state changes")
    return list(dict.fromkeys(signals))[:10]


def _decision_trace(
    *,
    scientific_decision_summary: dict[str, Any],
    evidence_review_summary: dict[str, Any],
    termination_strategy_summary: dict[str, Any],
) -> list[dict[str, str]]:
    traces = [
        {
            "source_type": "scientific_decision",
            "source_id": str(scientific_decision_summary.get("recommended_target_id", "")),
            "reason": str(scientific_decision_summary.get("recommended_next_action", "")),
        },
        {
            "source_type": "evidence_review",
            "source_id": str(evidence_review_summary.get("review_id", "")),
            "reason": str(evidence_review_summary.get("review_readiness", "")),
        },
        {
            "source_type": "termination_strategy",
            "source_id": "route-termination",
            "reason": str(termination_strategy_summary.get("recommended_action", "")),
        },
    ]
    return [trace for trace in traces if trace["reason"] or trace["source_id"]]


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "controller"


