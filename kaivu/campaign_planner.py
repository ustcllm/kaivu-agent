from __future__ import annotations

from typing import Any

from .route_scheduler import build_research_route_scheduler_summary


CAMPAIGN_STAGES = [
    "question_framing",
    "literature_mapping",
    "hypothesis_formalization",
    "screening",
    "discriminative_testing",
    "replication",
    "theory_integration",
    "reporting",
]


def build_research_campaign_plan_summary(
    *,
    topic: str,
    research_state: dict[str, Any],
    claim_graph: dict[str, Any],
    scheduler_memory_context: dict[str, Any] | None = None,
    route_scheduler_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scheduler_memory_context = scheduler_memory_context or {}
    route_scheduler_summary = route_scheduler_summary or build_research_route_scheduler_summary(
        topic=topic,
        research_state=research_state,
        claim_graph=claim_graph,
        scheduler_memory_context=scheduler_memory_context,
    )
    current_stage = _infer_campaign_stage(research_state=research_state, claim_graph=claim_graph)
    stage_plan = _stage_plan(
        topic=topic,
        current_stage=current_stage,
        research_state=research_state,
        claim_graph=claim_graph,
        route_scheduler_summary=route_scheduler_summary,
    )
    pivot_rules = _pivot_rules(research_state=research_state, scheduler_memory_context=scheduler_memory_context)
    kill_rules = _kill_rules(research_state=research_state, claim_graph=claim_graph)
    replication_rules = _replication_rules(research_state=research_state)
    multi_step_route_plan = _multi_step_route_plan(stage_plan=stage_plan, route_scheduler_summary=route_scheduler_summary)
    next_step = multi_step_route_plan[0] if multi_step_route_plan else {}
    return {
        "research_campaign_plan_id": f"research-campaign::{_slugify(topic)}",
        "topic": topic,
        "campaign_goal": _campaign_goal(topic=topic, research_state=research_state),
        "current_campaign_stage": current_stage,
        "stage_count": len(stage_plan),
        "stage_plan": stage_plan,
        "route_selector_summary": route_scheduler_summary,
        "multi_step_route_plan": multi_step_route_plan,
        "single_step_recommendation": {
            "next_action": route_scheduler_summary.get("best_action", ""),
            "reason": route_scheduler_summary.get("best_selection_reason", ""),
            "route_node_id": route_scheduler_summary.get("best_route_node_id", ""),
        },
        "pivot_rules": pivot_rules,
        "kill_rules": kill_rules,
        "replication_rules": replication_rules,
        "resource_budget_policy": _resource_budget_policy(research_state),
        "decision_checkpoints": _decision_checkpoints(research_state),
        "scheduler_constraints": _scheduler_constraints(
            stage_plan=stage_plan,
            pivot_rules=pivot_rules,
            kill_rules=kill_rules,
            replication_rules=replication_rules,
            route_scheduler_summary=route_scheduler_summary,
        ),
        "next_campaign_decision": str(next_step.get("route_action", "")) or route_scheduler_summary.get("best_action", "continue_research_cycle"),
        "planner_state": "ready" if stage_plan else "needs_campaign_context",
    }


def _infer_campaign_stage(*, research_state: dict[str, Any], claim_graph: dict[str, Any]) -> str:
    if research_state.get("scientific_release_gate_summary", {}).get("release_state") == "release_ready":
        return "reporting"
    if research_state.get("reproducibility_kernel_summary", {}).get("readiness") in {"medium", "high"}:
        return "replication"
    if research_state.get("executor_run_summary", {}).get("run_count") or research_state.get("executor_belief_backpropagation_summary", {}).get("update_count"):
        return "theory_integration"
    if research_state.get("experiment_execution_loop_summary", {}).get("execution_queue"):
        return "discriminative_testing"
    if research_state.get("experiment_execution_loop_summary", {}).get("candidate_count"):
        return "screening"
    if research_state.get("hypothesis_validation_summary", {}).get("validation_count") or claim_graph.get("hypotheses"):
        return "hypothesis_formalization"
    if research_state.get("systematic_review_summary") or claim_graph.get("claims"):
        return "literature_mapping"
    return "question_framing"


def _stage_plan(
    *,
    topic: str,
    current_stage: str,
    research_state: dict[str, Any],
    claim_graph: dict[str, Any],
    route_scheduler_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    current_index = CAMPAIGN_STAGES.index(current_stage) if current_stage in CAMPAIGN_STAGES else 0
    plan: list[dict[str, Any]] = []
    for index, stage in enumerate(CAMPAIGN_STAGES):
        route_action = _route_action_for_stage(stage, route_scheduler_summary)
        plan.append(
            {
                "stage": stage,
                "stage_state": "completed" if index < current_index else "current" if index == current_index else "next" if index == current_index + 1 else "future",
                "goal": _stage_goal(stage, topic),
                "route_action": route_action,
                "entry_conditions": _entry_conditions(stage),
                "exit_criteria": _exit_criteria(stage, research_state, claim_graph),
                "recommended_agents": _recommended_agents(stage),
                "expected_outputs": _expected_outputs(stage),
            }
        )
    return plan


def _multi_step_route_plan(*, stage_plan: list[dict[str, Any]], route_scheduler_summary: dict[str, Any]) -> list[dict[str, Any]]:
    best_action = str(route_scheduler_summary.get("best_action", "")).strip()
    current_and_next = [
        item for item in stage_plan if item.get("stage_state") in {"current", "next", "future"}
    ][:5]
    steps: list[dict[str, Any]] = []
    for index, item in enumerate(current_and_next, start=1):
        action = best_action if index == 1 and best_action else str(item.get("route_action", ""))
        steps.append(
            {
                "step_index": index,
                "campaign_stage": item.get("stage", ""),
                "route_action": action,
                "goal": item.get("goal", ""),
                "exit_criteria": item.get("exit_criteria", []),
                "recommended_agents": item.get("recommended_agents", []),
            }
        )
    return steps


def _campaign_goal(*, topic: str, research_state: dict[str, Any]) -> str:
    goal = str(research_state.get("research_plan_summary", {}).get("research_goal", "")).strip()
    return goal or f"turn '{topic}' into a testable, evidence-backed, reproducible research conclusion"


def _route_action_for_stage(stage: str, route_scheduler_summary: dict[str, Any]) -> str:
    mapping = {
        "question_framing": "review_more_literature",
        "literature_mapping": "review_more_literature",
        "hypothesis_formalization": "refine_hypothesis",
        "screening": "design_discriminative_experiment",
        "discriminative_testing": "schedule_experiment",
        "replication": "run_reproducibility_check",
        "theory_integration": "hold_lab_meeting",
        "reporting": "publish_or_report",
    }
    return mapping.get(stage, route_scheduler_summary.get("best_action", "review_more_literature"))


def _stage_goal(stage: str, topic: str) -> str:
    return {
        "question_framing": f"define the scientific question, scope, variables, and decision stakes for {topic}",
        "literature_mapping": "map primary evidence, conflicts, mechanisms, methods, and evidence quality",
        "hypothesis_formalization": "convert candidate ideas into falsifiable hypotheses with predictions and boundary conditions",
        "screening": "run cheap or low-risk tests to eliminate weak routes and identify promising mechanisms",
        "discriminative_testing": "design experiments that separate competing mechanisms or explanations",
        "replication": "confirm key observations under independent or changed-condition repetitions",
        "theory_integration": "update the hypothesis tree, mechanism families, uncertainty ledger, and failure memory",
        "reporting": "assemble a provenance-backed report, paper draft, or group decision record",
    }.get(stage, f"advance {topic}")


def _entry_conditions(stage: str) -> list[str]:
    return {
        "question_framing": ["initial topic or research question exists"],
        "literature_mapping": ["question scope is explicit enough to search"],
        "hypothesis_formalization": ["claim or evidence map exists"],
        "screening": ["at least one falsifiable hypothesis exists"],
        "discriminative_testing": ["competing hypotheses or mechanisms remain plausible"],
        "replication": ["a result is important enough to preserve or challenge"],
        "theory_integration": ["executor, literature, or review feedback changed belief state"],
        "reporting": ["release gate and benchmark quality are not blocking"],
    }.get(stage, [])


def _exit_criteria(stage: str, research_state: dict[str, Any], claim_graph: dict[str, Any]) -> list[str]:
    criteria = {
        "question_framing": ["research goal, scope, and key variables are recorded"],
        "literature_mapping": ["systematic review table and conflict matrix are updated"],
        "hypothesis_formalization": ["hypothesis validators pass or blocked hypotheses are revised"],
        "screening": ["cheap tests identify at least one promising route or kill weak routes"],
        "discriminative_testing": ["quality-controlled evidence distinguishes at least one mechanism pair"],
        "replication": ["key result is repeated or downgraded with reason"],
        "theory_integration": ["belief updates, failed attempts, and mechanism lifecycle are synchronized"],
        "reporting": ["release gate passes and provenance can replay core claims"],
    }.get(stage, [])
    if stage == "hypothesis_formalization" and claim_graph.get("negative_results"):
        criteria.append("negative results are linked to affected hypotheses")
    if stage == "discriminative_testing" and research_state.get("experiment_risk_permission_summary", {}).get("approval_required"):
        criteria.append("risk permission gate is cleared before non-dry-run execution")
    return criteria


def _recommended_agents(stage: str) -> list[str]:
    return {
        "question_framing": ["research_planner", "critic"],
        "literature_mapping": ["literature_reviewer", "data_curator"],
        "hypothesis_formalization": ["hypothesis_generator", "critic", "belief_updater"],
        "screening": ["experiment_designer", "experiment_economist"],
        "discriminative_testing": ["experiment_designer", "run_manager", "quality_control_reviewer"],
        "replication": ["quality_control_reviewer", "data_analyst", "critic"],
        "theory_integration": ["belief_updater", "lab_meeting_moderator", "conflict_resolver"],
        "reporting": ["report_writer", "coordinator"],
    }.get(stage, ["coordinator"])


def _expected_outputs(stage: str) -> list[str]:
    return {
        "question_framing": ["research_goal", "scope", "key_variables"],
        "literature_mapping": ["literature_map", "evidence_table", "conflict_matrix"],
        "hypothesis_formalization": ["hypothesis_tree", "prediction_table", "validator_report"],
        "screening": ["screening_plan", "cheap_test_queue", "route_kill_candidates"],
        "discriminative_testing": ["execution_package", "quality_gates", "risk_permission_record"],
        "replication": ["replication_plan", "reproducibility_record"],
        "theory_integration": ["belief_update", "mechanism_lifecycle_update", "failure_memory_update"],
        "reporting": ["release_report", "formal_review_record"],
    }.get(stage, [])


def _pivot_rules(*, research_state: dict[str, Any], scheduler_memory_context: dict[str, Any]) -> list[dict[str, Any]]:
    rules = [
        {
            "condition": "two or more high-value routes fail under changed conditions",
            "action": "return_to_hypothesis_formalization",
        },
        {
            "condition": "literature conflicts cannot be attributed to method, population, or measurement differences",
            "action": "return_to_systematic_review",
        },
    ]
    if scheduler_memory_context.get("failed_routes"):
        rules.append({"condition": "current route matches failed route memory", "action": "require_new_mechanism_or_changed_condition"})
    if research_state.get("experiment_risk_permission_summary", {}).get("permission_state") == "blocked":
        rules.append({"condition": "risk gate blocks execution", "action": "pivot_to_simulation_or_literature"})
    return rules[:10]


def _kill_rules(*, research_state: dict[str, Any], claim_graph: dict[str, Any]) -> list[dict[str, Any]]:
    rules = [
        {
            "condition": "hypothesis fails falsifiability or novelty validators after revision",
            "action": "kill_or_archive_hypothesis_route",
        },
        {
            "condition": "benchmark quality remains low after targeted repairs",
            "action": "stop_release_and_repair_kernel_outputs",
        },
    ]
    if claim_graph.get("negative_results"):
        rules.append({"condition": "negative result directly challenges core prediction", "action": "downgrade_or_retire_hypothesis"})
    if research_state.get("route_temperature_summary", {}).get("cooling_candidates"):
        rules.append({"condition": "route temperature remains hot with low evidence gain", "action": "cool_route"})
    return rules[:10]


def _replication_rules(*, research_state: dict[str, Any]) -> list[dict[str, Any]]:
    rules = [
        {
            "condition": "result would change top hypothesis or campaign stage",
            "action": "replicate_before_belief_promotion",
        },
        {
            "condition": "executor output is usable but only dry-run or single-run",
            "action": "schedule_real_executor_or_independent_repetition",
        },
    ]
    if research_state.get("executor_belief_backpropagation_summary", {}).get("hypothesis_updates"):
        rules.append({"condition": "executor backpropagation changed belief state", "action": "replicate_or_review_before_release"})
    return rules[:10]


def _resource_budget_policy(research_state: dict[str, Any]) -> dict[str, Any]:
    economics = research_state.get("experiment_economics_summary", {}) if isinstance(research_state.get("experiment_economics_summary", {}), dict) else {}
    return {
        "cost_pressure": str(economics.get("cost_pressure", "medium")),
        "time_pressure": str(economics.get("time_pressure", "medium")),
        "budget_strategy": "cheap_screening_first_then_discriminative_tests",
        "stop_loss": "pause route when repeated failures do not reduce uncertainty",
    }


def _decision_checkpoints(research_state: dict[str, Any]) -> list[dict[str, Any]]:
    checkpoints = [
        {"checkpoint": "before_non_dry_run_execution", "owner": "human_or_safety_reviewer"},
        {"checkpoint": "before_hypothesis_kill_or_major_pivot", "owner": "lab_meeting"},
        {"checkpoint": "before_release_or_publication", "owner": "principal_investigator_or_project_owner"},
    ]
    if research_state.get("lab_meeting_protocol_summary", {}).get("consensus_gate") in {"blocked", "contested"}:
        checkpoints.append({"checkpoint": "resolve_formal_dissent", "owner": "lab_meeting_moderator"})
    return checkpoints[:10]


def _scheduler_constraints(
    *,
    stage_plan: list[dict[str, Any]],
    pivot_rules: list[dict[str, Any]],
    kill_rules: list[dict[str, Any]],
    replication_rules: list[dict[str, Any]],
    route_scheduler_summary: dict[str, Any],
) -> list[str]:
    constraints = [
        f"campaign next action should align with route action: {route_scheduler_summary.get('best_action', '')}",
    ]
    current = next((item for item in stage_plan if item.get("stage_state") == "current"), {})
    for criterion in _strings(current.get("exit_criteria", [])):
        constraints.append(f"current stage exit criterion: {criterion}")
    for rule in pivot_rules[:2]:
        constraints.append(f"pivot rule: {rule.get('condition', '')} -> {rule.get('action', '')}")
    for rule in kill_rules[:2]:
        constraints.append(f"kill rule: {rule.get('condition', '')} -> {rule.get('action', '')}")
    for rule in replication_rules[:2]:
        constraints.append(f"replication rule: {rule.get('condition', '')} -> {rule.get('action', '')}")
    return _dedupe(constraints)[:12]


def _items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(item).strip() for item in values if str(item).strip()))


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value).strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "campaign"


