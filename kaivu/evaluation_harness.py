from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ScientificAgentEvaluationAxis:
    axis_id: str
    name: str
    score: float
    state: str
    evidence: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    regression_checks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_kaivu_evaluation_harness_summary(
    *,
    topic: str,
    project_id: str = "",
    evaluation_summary: dict[str, Any],
    benchmark_harness_summary: dict[str, Any],
    hypothesis_validation_summary: dict[str, Any],
    evidence_review_summary: dict[str, Any],
    discipline_adapter_summary: dict[str, Any],
    experiment_execution_loop_summary: dict[str, Any],
    execution_adapter_registry_summary: dict[str, Any],
    run_handoff_contract_summary: dict[str, Any],
    autonomous_controller_summary: dict[str, Any],
    failure_intelligence_summary: dict[str, Any],
    graph_learning_summary: dict[str, Any],
    mid_run_control_summary: dict[str, Any] | None = None,
    agent_stance_continuity_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mid_run_control_summary = mid_run_control_summary or {}
    agent_stance_continuity_summary = agent_stance_continuity_summary or {}
    axes = [
        _hypothesis_axis(hypothesis_validation_summary),
        _evidence_axis(evaluation_summary, evidence_review_summary),
        _discipline_axis(discipline_adapter_summary),
        _execution_loop_axis(experiment_execution_loop_summary, execution_adapter_registry_summary),
        _handoff_axis(run_handoff_contract_summary),
        _autonomy_axis(autonomous_controller_summary),
        _mid_run_control_axis(mid_run_control_summary, autonomous_controller_summary),
        _agent_stance_axis(agent_stance_continuity_summary),
        _failure_learning_axis(failure_intelligence_summary, graph_learning_summary),
        _benchmark_axis(benchmark_harness_summary),
    ]
    axis_dicts = [axis.to_dict() for axis in axes]
    overall_score = round(sum(axis.score for axis in axes) / max(1, len(axes)), 3)
    blocking_gates = [
        gate
        for axis in axis_dicts
        for gate in axis.get("gaps", [])
        if str(gate).strip() and axis.get("state") in {"blocked", "weak"}
    ][:20]
    regression_suite = _dedupe(
        [
            check
            for axis in axis_dicts
            for check in axis.get("regression_checks", [])
            if str(check).strip()
        ]
        + [
            str(item)
            for item in benchmark_harness_summary.get("regression_checks", [])
            if str(item).strip()
        ]
    )[:30]
    fail_fast_checks = _dedupe(
        [
            str(item)
            for item in benchmark_harness_summary.get("fail_fast_checks", [])
            if str(item).strip()
        ]
        + [
            "stop release if handoff contracts are missing for ready execution packages",
            "stop autonomous continuation if discipline interpretation boundaries are absent",
            "stop belief upgrade if quality-control or evidence gates are blocked",
        ]
    )[:20]
    release_state = _release_state(overall_score, blocking_gates)
    return {
        "harness_id": f"kaivu-evaluation-harness::{_slugify(project_id or 'workspace')}::{_slugify(topic)}",
        "topic": topic,
        "project_id": project_id,
        "overall_score": overall_score,
        "release_state": release_state,
        "axis_count": len(axis_dicts),
        "axes": axis_dicts,
        "blocking_gate_count": len(blocking_gates),
        "blocking_gates": blocking_gates,
        "regression_suite": regression_suite,
        "fail_fast_checks": fail_fast_checks,
        "minimum_release_contract": [
            "hypotheses have novelty, falsifiability, and testability scores",
            "evidence review is decision-ready or explicitly gated",
            "discipline adapter bindings exist for scheduled experiments",
            "execution packages have handoff contracts",
            "negative and failed attempts can backpropagate to memory and graph",
            "autonomous controller knows when to pause",
            "mid-run control decisions are evaluated, enforced, and logged",
            "multi-agent roles preserve stance continuity or justify stance changes",
        ],
    }


def _hypothesis_axis(summary: dict[str, Any]) -> ScientificAgentEvaluationAxis:
    novelty = _safe_float(summary.get("average_novelty_score", 0))
    falsifiability = _safe_float(summary.get("average_falsifiability_score", 0))
    testability = _safe_float(summary.get("average_testability_score", 0))
    mechanism = _safe_float(summary.get("average_mechanistic_coherence_score", 0))
    score = _mean([novelty, falsifiability, testability, mechanism])
    gaps: list[str] = []
    if novelty < 0.5:
        gaps.append("hypothesis novelty is weak")
    if falsifiability < 0.5:
        gaps.append("hypotheses are not falsifiable enough")
    if testability < 0.5:
        gaps.append("hypotheses are not testable enough")
    return ScientificAgentEvaluationAxis(
        axis_id="hypothesis_quality",
        name="Hypothesis quality",
        score=score,
        state=_state(score),
        evidence=[
            f"novelty={novelty}",
            f"falsifiability={falsifiability}",
            f"testability={testability}",
            f"mechanistic_coherence={mechanism}",
        ],
        gaps=gaps,
        regression_checks=["detect lower hypothesis validator scores than previous run"],
    )


def _evidence_axis(evaluation: dict[str, Any], evidence_review: dict[str, Any]) -> ScientificAgentEvaluationAxis:
    readiness = str(evaluation.get("systematic_review_readiness", "low")).strip().lower()
    review = str(evidence_review.get("review_readiness", "")).strip().lower()
    protocol = _safe_float(evidence_review.get("protocol_completeness_score", 0))
    screening = _safe_float(evidence_review.get("screening_quality_score", 0))
    base = {"high": 1.0, "medium": 0.65, "low": 0.25}.get(readiness, 0.25)
    if review == "decision_ready":
        base = max(base, 0.85)
    score = round(_mean([base, protocol, screening]), 3)
    gaps = []
    if review not in {"decision_ready", "ready"}:
        gaps.append("evidence review is not decision-ready")
    if protocol < 0.6:
        gaps.append("review protocol completeness is low")
    if screening < 0.5:
        gaps.append("screening quality is low")
    return ScientificAgentEvaluationAxis(
        axis_id="evidence_readiness",
        name="Evidence readiness",
        score=score,
        state=_state(score),
        evidence=[f"systematic_review={readiness}", f"review={review}", f"protocol={protocol}", f"screening={screening}"],
        gaps=gaps,
        regression_checks=["compare evidence readiness and conflict count against previous run"],
    )


def _discipline_axis(summary: dict[str, Any]) -> ScientificAgentEvaluationAxis:
    bindings = summary.get("bindings", []) if isinstance(summary.get("bindings", []), list) else []
    binding_count = len(bindings)
    blocked = int(summary.get("blocked_binding_count", 0) or 0)
    with_boundaries = len([b for b in bindings if isinstance(b, dict) and b.get("interpretation_boundaries")])
    with_scheduler = len([b for b in bindings if isinstance(b, dict) and b.get("scheduler_rules")])
    if binding_count == 0:
        score = 0.0
    else:
        score = round((with_boundaries + with_scheduler + max(0, binding_count - blocked)) / (3 * binding_count), 3)
    gaps = []
    if binding_count == 0:
        gaps.append("no discipline adapter bindings exist")
    if blocked:
        gaps.append("some discipline adapter bindings are blocked")
    if with_boundaries < binding_count:
        gaps.append("some discipline interpretation boundaries are missing")
    return ScientificAgentEvaluationAxis(
        axis_id="discipline_adaptation",
        name="Discipline adaptation",
        score=score,
        state=_state(score),
        evidence=[f"bindings={binding_count}", f"blocked={blocked}", f"with_boundaries={with_boundaries}", f"with_scheduler_rules={with_scheduler}"],
        gaps=gaps,
        regression_checks=["ensure scheduled experiments keep discipline adapter bindings"],
    )


def _execution_loop_axis(loop: dict[str, Any], registry: dict[str, Any]) -> ScientificAgentEvaluationAxis:
    queue_count = len(loop.get("execution_queue", []) if isinstance(loop.get("execution_queue", []), list) else [])
    package_count = int(registry.get("execution_package_count", 0) or 0)
    ready_count = int(registry.get("ready_package_count", 0) or 0)
    discipline_aware = bool(loop.get("mcts_like_search", {}).get("discipline_rule_aware", False))
    score = 0.0
    if queue_count:
        score += 0.35
    if package_count:
        score += 0.25
    if package_count and ready_count == package_count:
        score += 0.2
    if discipline_aware:
        score += 0.2
    gaps = []
    if not queue_count:
        gaps.append("execution loop has no ready queue")
    if not package_count:
        gaps.append("execution packages are missing")
    if not discipline_aware:
        gaps.append("execution loop is not discipline-rule-aware")
    return ScientificAgentEvaluationAxis(
        axis_id="execution_loop",
        name="Experiment execution loop",
        score=round(score, 3),
        state=_state(score),
        evidence=[f"queue={queue_count}", f"packages={package_count}", f"ready_packages={ready_count}", f"discipline_aware={discipline_aware}"],
        gaps=gaps,
        regression_checks=["ensure top scheduled experiment still has quality gates and handoff target"],
    )


def _handoff_axis(summary: dict[str, Any]) -> ScientificAgentEvaluationAxis:
    contract_count = int(summary.get("contract_count", 0) or 0)
    state = str(summary.get("contract_state", "")).strip()
    score = 0.8 if contract_count else 0.2
    if state in {"ready", "contracts_ready"}:
        score = 1.0
    gaps = [] if contract_count else ["run handoff contracts are missing"]
    return ScientificAgentEvaluationAxis(
        axis_id="run_handoff",
        name="Run handoff contract",
        score=round(score, 3),
        state=_state(score),
        evidence=[f"contracts={contract_count}", f"state={state}"],
        gaps=gaps,
        regression_checks=["validate returned run payloads include quality control and interpretation records"],
    )


def _autonomy_axis(summary: dict[str, Any]) -> ScientificAgentEvaluationAxis:
    controller = str(summary.get("controller_state", "")).strip()
    pause = bool(summary.get("must_pause_for_human", False) or summary.get("pause_for_human", False))
    has_next = bool(summary.get("next_cycle_action", "") or summary.get("next_cycle_stage", ""))
    score = 0.75 if has_next else 0.35
    if controller in {"ready_for_next_cycle", "paused_for_human"}:
        score += 0.2
    if pause:
        score += 0.05
    score = min(1.0, score)
    gaps = [] if has_next else ["autonomous controller lacks next action"]
    return ScientificAgentEvaluationAxis(
        axis_id="autonomy_governance",
        name="Autonomy governance",
        score=round(score, 3),
        state=_state(score),
        evidence=[f"controller={controller}", f"pause_for_human={pause}", f"has_next={has_next}"],
        gaps=gaps,
        regression_checks=["ensure autonomous controller pauses when evidence or governance gates are blocked"],
    )


def _mid_run_control_axis(
    summary: dict[str, Any],
    autonomous_controller: dict[str, Any],
) -> ScientificAgentEvaluationAxis:
    decision_count = int(summary.get("decision_count", 0) or 0)
    hard_control_count = int(summary.get("hard_control_count", 0) or 0)
    stop_routing = bool(summary.get("stop_routing", False))
    paused_count = len(summary.get("paused_workstreams", []) if isinstance(summary.get("paused_workstreams", []), list) else [])
    blocked_count = len(summary.get("blocked_profiles", []) if isinstance(summary.get("blocked_profiles", []), list) else [])
    controller_seen = bool(autonomous_controller.get("mid_run_control_state", {}).get("decision_count", 0))
    score = 0.25
    if decision_count:
        score += 0.25
    if hard_control_count or paused_count or blocked_count:
        score += 0.25
    if controller_seen:
        score += 0.15
    if stop_routing and autonomous_controller.get("must_pause_for_human"):
        score += 0.10
    gaps: list[str] = []
    if not decision_count:
        gaps.append("mid-run controller has not evaluated workflow state")
    if hard_control_count and not controller_seen:
        gaps.append("mid-run control is not visible to autonomous controller")
    if blocked_count and not paused_count:
        gaps.append("blocked specialists are not tied to an explicit paused workstream")
    return ScientificAgentEvaluationAxis(
        axis_id="mid_run_active_control",
        name="Mid-run active control",
        score=round(min(1.0, score), 3),
        state=_state(score),
        evidence=[
            f"decisions={decision_count}",
            f"hard_controls={hard_control_count}",
            f"paused_workstreams={paused_count}",
            f"blocked_profiles={blocked_count}",
            f"controller_seen={controller_seen}",
        ],
        gaps=gaps,
        regression_checks=[
            "ensure low-quality intermediate outputs trigger mid-run control decisions",
            "ensure blocked profiles are skipped or repaired before execution",
            "ensure mid-run control decisions are present in the event ledger",
        ],
    )


def _agent_stance_axis(summary: dict[str, Any]) -> ScientificAgentEvaluationAxis:
    agent_count = int(summary.get("agent_count", 0) or 0)
    changed_count = int(summary.get("changed_count", 0) or 0)
    missing_reason_count = int(summary.get("missing_change_reason_count", 0) or 0)
    unresolved_count = int(summary.get("unresolved_objection_count", 0) or 0)
    continuity_ready = bool(summary.get("continuity_ready", False))
    score = 0.2
    if agent_count:
        score += 0.35
    if continuity_ready:
        score += 0.25
    if changed_count and not missing_reason_count:
        score += 0.1
    if unresolved_count:
        score += 0.1
    if missing_reason_count:
        score -= 0.25
    score = max(0.0, min(1.0, score))
    gaps: list[str] = []
    if not agent_count:
        gaps.append("agent stance records are missing")
    if missing_reason_count:
        gaps.append("some changed agent stances lack explicit reasons")
    if not unresolved_count:
        gaps.append("role memory does not preserve standing objections")
    return ScientificAgentEvaluationAxis(
        axis_id="multi_agent_stance_continuity",
        name="Multi-agent stance continuity",
        score=round(score, 3),
        state=_state(score),
        evidence=[
            f"agents={agent_count}",
            f"changed={changed_count}",
            f"missing_reasons={missing_reason_count}",
            f"standing_objections={unresolved_count}",
            f"continuity_ready={continuity_ready}",
        ],
        gaps=gaps,
        regression_checks=[
            "ensure each specialist has a role-memory stance record",
            "ensure changed stances cite evidence, failed attempts, or boundary conditions",
            "ensure standing objections survive into the next lab meeting",
        ],
    )


def _failure_learning_axis(failure: dict[str, Any], graph_learning: dict[str, Any]) -> ScientificAgentEvaluationAxis:
    signal = str(graph_learning.get("learning_signal_strength", "low")).strip().lower()
    avoid_count = len(failure.get("avoid_repeat_routes", []) if isinstance(failure.get("avoid_repeat_routes", []), list) else [])
    score = {"high": 0.9, "medium": 0.65, "low": 0.35}.get(signal, 0.35)
    if avoid_count:
        score = max(score, 0.65)
    gaps = [] if avoid_count or signal in {"medium", "high"} else ["failed attempts are not yet actively shaping decisions"]
    return ScientificAgentEvaluationAxis(
        axis_id="failure_learning",
        name="Failure learning",
        score=round(score, 3),
        state=_state(score),
        evidence=[f"learning_signal={signal}", f"avoid_repeat_routes={avoid_count}"],
        gaps=gaps,
        regression_checks=["detect repeated scheduling of retired or failed routes"],
    )


def _benchmark_axis(summary: dict[str, Any]) -> ScientificAgentEvaluationAxis:
    ready = bool(summary.get("benchmark_ready", False))
    release = str(summary.get("release_readiness", "low")).strip().lower()
    gap_count = len(summary.get("benchmark_gaps", []) if isinstance(summary.get("benchmark_gaps", []), list) else [])
    score = {"high": 1.0, "medium": 0.65, "low": 0.25}.get(release, 0.25)
    if ready:
        score = max(score, 0.85)
    if gap_count:
        score = min(score, 0.6)
    return ScientificAgentEvaluationAxis(
        axis_id="benchmark_release",
        name="Benchmark release",
        score=round(score, 3),
        state=_state(score),
        evidence=[f"ready={ready}", f"release={release}", f"gaps={gap_count}"],
        gaps=[str(item) for item in summary.get("benchmark_gaps", []) if str(item).strip()][:8],
        regression_checks=["compare benchmark readiness and fail-fast checks against previous run"],
    )


def _release_state(score: float, blocking_gates: list[str]) -> str:
    if blocking_gates:
        return "blocked"
    if score >= 0.8:
        return "release_ready"
    if score >= 0.6:
        return "needs_targeted_repairs"
    return "not_ready"


def _state(score: float) -> str:
    if score >= 0.8:
        return "strong"
    if score >= 0.6:
        return "usable"
    if score >= 0.35:
        return "weak"
    return "blocked"


def _mean(values: list[float]) -> float:
    clean = [max(0.0, min(1.0, float(value))) for value in values]
    return round(sum(clean) / max(1, len(clean)), 3)


def _safe_float(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.0


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys([str(item).strip() for item in values if str(item).strip()]))


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "evaluation-harness"



