from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ResearchEvent:
    event_id: str
    event_type: str
    topic: str
    project_id: str = ""
    user_id: str = ""
    group_id: str = ""
    actor: str = "workflow"
    timestamp: str = ""
    asset_type: str = ""
    asset_id: str = ""
    action: str = ""
    summary: str = ""
    source_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if not payload["timestamp"]:
            payload["timestamp"] = datetime.now(timezone.utc).isoformat()
        return payload


class ResearchEventLedger:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def append(self, event: ResearchEvent) -> Path:
        path = self._event_path(event.project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        return path

    def append_many(self, events: list[ResearchEvent]) -> Path | None:
        path: Path | None = None
        for event in events:
            path = self.append(event)
        return path

    def load(
        self,
        *,
        project_id: str = "",
        topic: str = "",
        event_type: str = "",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        paths = [self._event_path(project_id)] if project_id else sorted(self.root.glob("events-*.jsonl"))
        events: list[dict[str, Any]] = []
        for path in paths:
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                if not isinstance(item, dict):
                    continue
                if topic and str(item.get("topic", "")).strip() != topic:
                    continue
                if event_type and str(item.get("event_type", "")).strip() != event_type:
                    continue
                events.append(item)
        events.sort(key=lambda item: str(item.get("timestamp", "")), reverse=True)
        return events[: max(1, min(limit, 1000))]

    def summarize(self, *, project_id: str = "", topic: str = "") -> dict[str, Any]:
        events = self.load(project_id=project_id, topic=topic, limit=1000)
        event_type_counts: dict[str, int] = {}
        asset_type_counts: dict[str, int] = {}
        actors: dict[str, int] = {}
        for item in events:
            event_type = str(item.get("event_type", "")).strip() or "unknown"
            asset_type = str(item.get("asset_type", "")).strip() or "unknown"
            actor = str(item.get("actor", "")).strip() or "unknown"
            event_type_counts[event_type] = event_type_counts.get(event_type, 0) + 1
            asset_type_counts[asset_type] = asset_type_counts.get(asset_type, 0) + 1
            actors[actor] = actors.get(actor, 0) + 1
        latest = events[0] if events else {}
        return {
            "project_id": project_id,
            "topic": topic,
            "event_count": len(events),
            "event_type_counts": event_type_counts,
            "asset_type_counts": asset_type_counts,
            "actor_counts": actors,
            "latest_event_id": str(latest.get("event_id", "")),
            "latest_timestamp": str(latest.get("timestamp", "")),
        }

    def _event_path(self, project_id: str) -> Path:
        safe = _slugify(project_id or "workspace")
        return self.root / f"events-{safe}.jsonl"


def build_workflow_events(
    *,
    topic: str,
    project_id: str = "",
    user_id: str = "",
    group_id: str = "",
    run_manifest: dict[str, Any],
    claim_graph: dict[str, Any],
    research_state: dict[str, Any],
) -> list[ResearchEvent]:
    base = {
        "topic": topic,
        "project_id": project_id,
        "user_id": user_id,
        "group_id": group_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    events: list[ResearchEvent] = [
        ResearchEvent(
            **base,
            event_id=_event_id("workflow_completed", topic, run_manifest.get("generated_at", "")),
            event_type="workflow_completed",
            actor="workflow",
            asset_type="workflow_run",
            asset_id=str(run_manifest.get("generated_at", "")) or _slugify(topic),
            action="completed",
            summary=(
                f"steps={len(run_manifest.get('models_used', []))}; "
                f"tools={len(run_manifest.get('tools_used', []))}; "
                f"artifacts={len(run_manifest.get('artifacts', []))}"
            ),
            metadata={
                "tools_used": run_manifest.get("tools_used", []),
                "models_used": run_manifest.get("models_used", []),
                "usage_summary": run_manifest.get("usage_summary", {}),
            },
        )
    ]

    typed_graph = research_state.get("typed_research_graph_summary", {})
    if isinstance(typed_graph, dict) and typed_graph:
        events.append(
            ResearchEvent(
                **base,
                event_id=_event_id("graph_snapshot_created", topic, typed_graph.get("snapshot_id", "")),
                event_type="graph_snapshot_created",
                actor="graph_registry",
                asset_type="typed_research_graph",
                asset_id=str(typed_graph.get("snapshot_id", "")),
                action="snapshot_created",
                summary=(
                    f"nodes={typed_graph.get('node_count', 0)}; "
                    f"edges={typed_graph.get('edge_count', 0)}; "
                    f"facts={typed_graph.get('fact_count', 0)}; "
                    f"source={typed_graph.get('source_of_truth', '')}"
                ),
                metadata=typed_graph,
            )
        )

    systematic_summary = research_state.get("systematic_review_summary", {})
    systematic_engine = (
        systematic_summary.get("engine", {})
        if isinstance(systematic_summary, dict) and isinstance(systematic_summary.get("engine", {}), dict)
        else {}
    )
    if isinstance(systematic_engine, dict) and systematic_engine:
        events.append(
            ResearchEvent(
                **base,
                event_id=_event_id("systematic_review_completed", topic, systematic_engine.get("systematic_review_engine_id", "")),
                event_type="systematic_review_completed",
                actor="systematic_review_engine",
                asset_type="systematic_review",
                asset_id=str(systematic_engine.get("systematic_review_engine_id", "")) or _slugify(topic),
                action=str(systematic_engine.get("synthesis_state", "")),
                summary=(
                    f"evidence={len(systematic_engine.get('evidence_table', []) if isinstance(systematic_engine.get('evidence_table', []), list) else [])}; "
                    f"conflicts={len(systematic_engine.get('conflict_matrix', []) if isinstance(systematic_engine.get('conflict_matrix', []), list) else [])}"
                ),
                metadata=systematic_engine,
            )
        )

    hypothesis_theory = research_state.get("hypothesis_theory_summary", {})
    if isinstance(hypothesis_theory, dict) and hypothesis_theory:
        for item in hypothesis_theory.get("objects", [])[:20]:
            if not isinstance(item, dict):
                continue
            asset_id = str(item.get("theory_object_id", "") or item.get("hypothesis_id", "")).strip()
            if not asset_id:
                continue
            events.append(
                ResearchEvent(
                    **base,
                    event_id=_event_id("hypothesis_theory_recorded", topic, asset_id),
                    event_type="hypothesis_theory_recorded",
                    actor="hypothesis_generator",
                    asset_type="hypothesis_theory_object",
                    asset_id=asset_id,
                    action=str(item.get("decision_state", "observe")),
                    summary=f"maturity={item.get('theory_maturity', 'flat')}; missing={len(item.get('missing_theory_fields', []))}",
                    source_refs=[str(ref) for ref in item.get("negative_result_refs", []) if str(ref).strip()],
                    metadata={
                        "hypothesis_id": item.get("hypothesis_id", ""),
                        "theory_maturity": item.get("theory_maturity", ""),
                        "decision_state": item.get("decision_state", ""),
                        "missing_theory_fields": item.get("missing_theory_fields", []),
                    },
                )
            )

    problem_reframer = research_state.get("scientific_problem_reframer_summary", {})
    if isinstance(problem_reframer, dict) and problem_reframer:
        events.append(
            ResearchEvent(
                **base,
                event_id=_event_id("scientific_problem_reframed", topic, problem_reframer.get("scientific_problem_reframer_id", "")),
                event_type="scientific_problem_reframed",
                actor="problem_reframer",
                asset_type="scientific_problem_frame",
                asset_id=str(problem_reframer.get("scientific_problem_reframer_id", "")) or _slugify(topic),
                action=str(problem_reframer.get("reframing_state", "")),
                summary=(
                    f"triggers={problem_reframer.get('trigger_count', 0)}; "
                    f"frame={problem_reframer.get('selected_frame', {}).get('frame_type', '') if isinstance(problem_reframer.get('selected_frame', {}), dict) else ''}"
                ),
                source_refs=[
                    str(item.get("frame_id", "")).strip()
                    for item in problem_reframer.get("candidate_frames", [])
                    if isinstance(item, dict) and str(item.get("frame_id", "")).strip()
                ][:20] if isinstance(problem_reframer.get("candidate_frames", []), list) else [],
                metadata=problem_reframer,
            )
        )

    theory_compiler = research_state.get("theory_prediction_compiler_summary", {})
    if isinstance(theory_compiler, dict) and theory_compiler:
        events.append(
            ResearchEvent(
                **base,
                event_id=_event_id("theory_predictions_compiled", topic, theory_compiler.get("theory_prediction_compiler_id", "")),
                event_type="theory_predictions_compiled",
                actor="theory_formalizer",
                asset_type="theory_prediction_compiler",
                asset_id=str(theory_compiler.get("theory_prediction_compiler_id", "")) or _slugify(topic),
                action=str(theory_compiler.get("formalization_readiness", "")),
                summary=(
                    f"theories={theory_compiler.get('compiled_theory_count', 0)}; "
                    f"predictions={theory_compiler.get('prediction_count', 0)}; "
                    f"tests={theory_compiler.get('discriminating_test_count', 0)}"
                ),
                source_refs=[
                    str(item.get("hypothesis_id", "")).strip()
                    for item in theory_compiler.get("compiled_theories", [])
                    if isinstance(item, dict) and str(item.get("hypothesis_id", "")).strip()
                ][:20] if isinstance(theory_compiler.get("compiled_theories", []), list) else [],
                metadata=theory_compiler,
            )
        )

    anomaly = research_state.get("anomaly_surprise_detector_summary", {})
    if isinstance(anomaly, dict) and anomaly:
        events.append(
            ResearchEvent(
                **base,
                event_id=_event_id("anomaly_surprise_detected", topic, anomaly.get("anomaly_surprise_detector_id", "")),
                event_type="anomaly_surprise_detected",
                actor="anomaly_surprise_detector",
                asset_type="anomaly_summary",
                asset_id=str(anomaly.get("anomaly_surprise_detector_id", "")) or _slugify(topic),
                action=str(anomaly.get("surprise_level", "")),
                summary=f"anomalies={anomaly.get('anomaly_count', 0)}; surprise={anomaly.get('surprise_level', '')}",
                metadata=anomaly,
            )
        )

    credit = research_state.get("scientific_credit_responsibility_ledger_summary", {})
    if isinstance(credit, dict) and credit:
        events.append(
            ResearchEvent(
                **base,
                event_id=_event_id("credit_responsibility_recorded", topic, credit.get("scientific_credit_responsibility_ledger_id", "")),
                event_type="credit_responsibility_recorded",
                actor="credit_ledger",
                asset_type="scientific_credit_responsibility_ledger",
                asset_id=str(credit.get("scientific_credit_responsibility_ledger_id", "")) or _slugify(topic),
                action="recorded",
                summary=f"records={credit.get('record_count', 0)}",
                metadata={
                    "record_count": credit.get("record_count", 0),
                    "credit_by_actor": credit.get("credit_by_actor", {}),
                    "responsibility_by_actor": credit.get("responsibility_by_actor", {}),
                },
            )
        )

    scientific_decision = research_state.get("scientific_decision_summary", {})
    if isinstance(scientific_decision, dict) and scientific_decision:
        for item in scientific_decision.get("decision_queue", [])[:20]:
            if not isinstance(item, dict):
                continue
            asset_id = str(item.get("decision_id", "")).strip()
            if not asset_id:
                continue
            events.append(
                ResearchEvent(
                    **base,
                    event_id=_event_id("scientific_decision_recorded", topic, asset_id),
                    event_type="scientific_decision_recorded",
                    actor="decision_engine",
                    asset_type="scientific_decision",
                    asset_id=asset_id,
                    action=str(item.get("action", "")),
                    summary=(
                        f"target={item.get('target_id', '')}; priority={item.get('priority', '')}; "
                        f"value={item.get('route_value_score', '')}"
                    ),
                    source_refs=[
                        str(trace.get("source_id", ""))
                        for trace in item.get("evidence_trace", [])
                        if isinstance(trace, dict) and str(trace.get("source_id", "")).strip()
                    ],
                    metadata={
                        "target_id": item.get("target_id", ""),
                        "target_type": item.get("target_type", ""),
                        "priority": item.get("priority", ""),
                        "route_value_score": item.get("route_value_score", 0),
                        "human_review_required": item.get("human_review_required", False),
                        "recommended_agents": item.get("recommended_agents", []),
                    },
                )
            )

    unified_assets = research_state.get("unified_asset_summary", {})
    if isinstance(unified_assets, dict) and unified_assets:
        for item in unified_assets.get("assets", [])[:50]:
            if not isinstance(item, dict):
                continue
            asset_id = str(item.get("asset_id", "")).strip()
            if not asset_id:
                continue
            events.append(
                ResearchEvent(
                    **base,
                    event_id=_event_id("scientific_asset_indexed", topic, asset_id),
                    event_type="scientific_asset_indexed",
                    actor="asset_indexer",
                    asset_type=str(item.get("asset_type", "scientific_asset")),
                    asset_id=asset_id,
                    action="indexed",
                    summary=f"role={item.get('role', '')}; source={item.get('source_system', '')}; status={item.get('status', '')}",
                    source_refs=[
                        *[
                            str(ref)
                            for ref in item.get("parent_asset_ids", [])
                            if str(ref).strip()
                        ],
                        *[
                            str(ref)
                            for ref in item.get("derived_from_asset_ids", [])
                            if str(ref).strip()
                        ],
                    ],
                    metadata={
                        "role": item.get("role", ""),
                        "source_system": item.get("source_system", ""),
                        "governance_status": item.get("governance_status", ""),
                    },
                )
            )

    for item in claim_graph.get("negative_results", [])[:20] if isinstance(claim_graph.get("negative_results", []), list) else []:
        if not isinstance(item, dict):
            continue
        asset_id = str(item.get("negative_result_id", "")).strip()
        if not asset_id:
            continue
        events.append(
            ResearchEvent(
                **base,
                event_id=_event_id("negative_result_recorded", topic, asset_id),
                event_type="negative_result_recorded",
                actor=str(item.get("profile_name", "workflow")),
                asset_type="negative_result",
                asset_id=asset_id,
                action="recorded",
                summary=str(item.get("result", ""))[:240],
                source_refs=[str(ref) for ref in item.get("affected_hypothesis_ids", []) if str(ref).strip()],
                metadata=item,
            )
        )

    literature = research_state.get("systematic_review_summary", {})
    if isinstance(literature, dict) and literature:
        events.append(
            ResearchEvent(
                **base,
                event_id=_event_id("evidence_review_updated", topic, literature.get("review_question", "")),
                event_type="evidence_review_updated",
                actor="literature_reviewer",
                asset_type="systematic_review",
                asset_id=_slugify(str(literature.get("review_question", "") or topic)),
                action="updated",
                summary=f"screened={literature.get('screened_evidence_count', 0)}; bias_hotspots={len(literature.get('bias_hotspots', []))}",
                metadata={
                    "review_question": literature.get("review_question", ""),
                    "screened_evidence_count": literature.get("screened_evidence_count", 0),
                    "bias_hotspots": literature.get("bias_hotspots", []),
                    "review_protocol_gaps": literature.get("review_protocol_gaps", []),
                },
            )
        )

    evidence_review = research_state.get("evidence_review_summary", {})
    if isinstance(evidence_review, dict) and evidence_review:
        events.append(
            ResearchEvent(
                **base,
                event_id=_event_id("evidence_review_assessed", topic, evidence_review.get("review_id", "")),
                event_type="evidence_review_assessed",
                actor="evidence_review_engine",
                asset_type="evidence_review",
                asset_id=str(evidence_review.get("review_id", "")) or _slugify(topic),
                action=str(evidence_review.get("review_readiness", "draft")),
                summary=(
                    f"quality={evidence_review.get('review_quality_state', '')}; "
                    f"protocol={evidence_review.get('protocol_completeness_score', 0)}; "
                    f"screening={evidence_review.get('screening_quality_score', 0)}"
                ),
                source_refs=[
                    str(item.get("evidence_id", "")).strip()
                    for item in evidence_review.get("assessment_records", [])
                    if isinstance(item, dict) and str(item.get("evidence_id", "")).strip()
                ],
                metadata={
                    "review_readiness": evidence_review.get("review_readiness", ""),
                    "review_quality_state": evidence_review.get("review_quality_state", ""),
                    "evidence_grade_balance": evidence_review.get("evidence_grade_balance", {}),
                    "bias_risk_summary": evidence_review.get("bias_risk_summary", {}),
                    "conflict_resolution_state": evidence_review.get("conflict_resolution_state", ""),
                    "review_blockers": evidence_review.get("review_blockers", []),
                    "recommended_review_actions": evidence_review.get("recommended_review_actions", []),
                },
            )
        )

    autonomous_controller = research_state.get("autonomous_controller_summary", {})
    if isinstance(autonomous_controller, dict) and autonomous_controller:
        events.append(
            ResearchEvent(
                **base,
                event_id=_event_id(
                    "autonomous_controller_decided",
                    topic,
                    autonomous_controller.get("controller_id", ""),
                ),
                event_type="autonomous_controller_decided",
                actor="autonomous_research_controller",
                asset_type="autonomous_controller",
                asset_id=str(autonomous_controller.get("controller_id", "")) or _slugify(topic),
                action=str(autonomous_controller.get("loop_decision", "")),
                summary=(
                    f"state={autonomous_controller.get('controller_state', '')}; "
                    f"next={autonomous_controller.get('next_cycle_action', '')}; "
                    f"pause={autonomous_controller.get('must_pause_for_human', False)}"
                ),
                source_refs=[
                    str(trace.get("source_id", "")).strip()
                    for trace in autonomous_controller.get("decision_trace", [])
                    if isinstance(trace, dict) and str(trace.get("source_id", "")).strip()
                ],
                metadata={
                    "controller_state": autonomous_controller.get("controller_state", ""),
                    "loop_decision": autonomous_controller.get("loop_decision", ""),
                    "next_cycle_stage": autonomous_controller.get("next_cycle_stage", ""),
                    "next_cycle_action": autonomous_controller.get("next_cycle_action", ""),
                    "recommended_agents": autonomous_controller.get("recommended_agents", []),
                    "pause_reasons": autonomous_controller.get("pause_reasons", []),
                    "safety_gates": autonomous_controller.get("safety_gates", []),
                    "continuation_budget": autonomous_controller.get("continuation_budget", {}),
                },
            )
        )

    mid_run_control = research_state.get("mid_run_control_summary", {})
    if isinstance(mid_run_control, dict) and mid_run_control.get("decision_count"):
        events.append(
            ResearchEvent(
                **base,
                event_id=_event_id(
                    "mid_run_control_applied",
                    topic,
                    str(mid_run_control.get("decision_count", "")),
                ),
                event_type="mid_run_control_applied",
                actor="mid_run_controller",
                asset_type="workflow_control",
                asset_id=f"mid-run-control::{_slugify(topic)}",
                action="stop_routing" if mid_run_control.get("stop_routing") else "control_directives",
                summary=(
                    f"decisions={mid_run_control.get('decision_count', 0)}; "
                    f"hard={mid_run_control.get('hard_control_count', 0)}; "
                    f"paused={len(mid_run_control.get('paused_workstreams', []) if isinstance(mid_run_control.get('paused_workstreams', []), list) else [])}"
                ),
                source_refs=[
                    str(item).strip()
                    for item in mid_run_control.get("terminated_routes", [])
                    if str(item).strip()
                ] if isinstance(mid_run_control.get("terminated_routes", []), list) else [],
                metadata={
                    "decision_count": mid_run_control.get("decision_count", 0),
                    "inserted_count": mid_run_control.get("inserted_count", 0),
                    "hard_control_count": mid_run_control.get("hard_control_count", 0),
                    "stop_routing": mid_run_control.get("stop_routing", False),
                    "paused_workstreams": mid_run_control.get("paused_workstreams", []),
                    "required_evidence_repairs": mid_run_control.get("required_evidence_repairs", []),
                    "hypothesis_rollbacks": mid_run_control.get("hypothesis_rollbacks", []),
                    "scheduler_overrides": mid_run_control.get("scheduler_overrides", []),
                    "terminated_routes": mid_run_control.get("terminated_routes", []),
                    "blocked_profiles": mid_run_control.get("blocked_profiles", []),
                },
            )
        )

    stance_continuity = research_state.get("agent_stance_continuity_summary", {})
    if isinstance(stance_continuity, dict) and stance_continuity.get("agent_count"):
        events.append(
            ResearchEvent(
                **base,
                event_id=_event_id(
                    "agent_stance_continuity_recorded",
                    topic,
                    str(stance_continuity.get("agent_count", "")),
                ),
                event_type="agent_stance_continuity_recorded",
                actor="lab_meeting_moderator",
                asset_type="multi_agent_role_memory",
                asset_id=f"agent-stance-continuity::{_slugify(topic)}",
                action=str(stance_continuity.get("role_memory_state", "")),
                summary=(
                    f"agents={stance_continuity.get('agent_count', 0)}; "
                    f"changed={stance_continuity.get('changed_count', 0)}; "
                    f"missing_reasons={stance_continuity.get('missing_change_reason_count', 0)}"
                ),
                source_refs=[
                    str(ref).strip()
                    for record in stance_continuity.get("records", [])
                    if isinstance(record, dict)
                    for ref in (
                        record.get("evidence_refs", [])
                        if isinstance(record.get("evidence_refs", []), list)
                        else []
                    )
                    if str(ref).strip()
                ][:20],
                metadata={
                    "role_memory_state": stance_continuity.get("role_memory_state", ""),
                    "continuity_ready": stance_continuity.get("continuity_ready", False),
                    "agent_count": stance_continuity.get("agent_count", 0),
                    "prior_agent_count": stance_continuity.get("prior_agent_count", 0),
                    "changed_count": stance_continuity.get("changed_count", 0),
                    "missing_change_reason_count": stance_continuity.get(
                        "missing_change_reason_count", 0
                    ),
                    "unresolved_objection_count": stance_continuity.get(
                        "unresolved_objection_count", 0
                    ),
                    "role_memory_updates": stance_continuity.get("role_memory_updates", []),
                },
            )
        )

    experiment_scheduler = research_state.get("experiment_execution_loop_summary", {})
    if isinstance(experiment_scheduler, dict) and experiment_scheduler:
        events.append(
            ResearchEvent(
                **base,
                event_id=_event_id(
                    "experiment_scheduler_planned",
                    topic,
                    experiment_scheduler.get("scheduler_id", ""),
                ),
                event_type="experiment_scheduler_planned",
                actor="experiment_scheduler",
                asset_type="experiment_scheduler",
                asset_id=str(experiment_scheduler.get("scheduler_id", "")) or _slugify(topic),
                action=str(experiment_scheduler.get("scheduler_state", "")),
                summary=(
                    f"candidates={experiment_scheduler.get('candidate_count', 0)}; "
                    f"top={experiment_scheduler.get('top_experiment_id', '')}; "
                    f"parameter_optimization={experiment_scheduler.get('parameter_optimization_supported', False)}"
                ),
                source_refs=[
                    str(item.get("experiment_id", "")).strip()
                    for item in experiment_scheduler.get("execution_queue", [])
                    if isinstance(item, dict) and str(item.get("experiment_id", "")).strip()
                ],
                metadata={
                    "scheduler_state": experiment_scheduler.get("scheduler_state", ""),
                    "top_experiment_id": experiment_scheduler.get("top_experiment_id", ""),
                    "top_action": experiment_scheduler.get("top_action", ""),
                    "candidate_count": experiment_scheduler.get("candidate_count", 0),
                    "mcts_like_search": experiment_scheduler.get("mcts_like_search", {}),
                    "parameter_optimization_supported": experiment_scheduler.get(
                        "parameter_optimization_supported", False
                    ),
                    "llm_judge_state": experiment_scheduler.get("llm_judge_state", ""),
                    "llm_judge_mode": experiment_scheduler.get("llm_judge_mode", ""),
                },
            )
        )
        if experiment_scheduler.get("llm_judgment"):
            judgment = experiment_scheduler.get("llm_judgment", {})
            events.append(
                ResearchEvent(
                    **base,
                    event_id=_event_id(
                        "scheduler_llm_judge_completed",
                        topic,
                        experiment_scheduler.get("scheduler_id", ""),
                    ),
                    event_type="scheduler_llm_judge_completed",
                    actor="scheduler_llm_judge",
                    asset_type="scheduler_judgment",
                    asset_id=f"scheduler-llm-judge::{_slugify(topic)}",
                    action=str(judgment.get("judge_state", "")),
                    summary=(
                        f"mode={judgment.get('judge_mode', '')}; "
                        f"ranked={len(judgment.get('ranked_candidates', []) if isinstance(judgment.get('ranked_candidates', []), list) else [])}; "
                        f"blocked={len(judgment.get('blocked_candidates', []) if isinstance(judgment.get('blocked_candidates', []), list) else [])}"
                    ),
                    source_refs=[
                        str(item.get("experiment_id", "")).strip()
                        for item in judgment.get("ranked_candidates", [])
                        if isinstance(item, dict) and str(item.get("experiment_id", "")).strip()
                    ][:20] if isinstance(judgment.get("ranked_candidates", []), list) else [],
                    metadata={
                        "judge_state": judgment.get("judge_state", ""),
                        "judge_mode": judgment.get("judge_mode", ""),
                        "missing_information": judgment.get("missing_information", []),
                        "policy_notes": judgment.get("policy_notes", []),
                    },
                )
            )

    executor_runs = research_state.get("executor_run_summary", {})
    if isinstance(executor_runs, dict) and executor_runs.get("run_count"):
        for run in executor_runs.get("runs", []) if isinstance(executor_runs.get("runs", []), list) else []:
            if not isinstance(run, dict):
                continue
            package_id = str(run.get("package_id", "")).strip()
            experiment_id = str(run.get("experiment_id", "")).strip()
            events.append(
                ResearchEvent(
                    **base,
                    event_id=_event_id("executor_run_completed", topic, package_id or experiment_id),
                    event_type="executor_run_completed",
                    actor=str(run.get("executor_id", "scientific_executor")),
                    asset_type="executor_run",
                    asset_id=package_id or experiment_id or _slugify(topic),
                    action=str(run.get("execution_state", "")),
                    summary=(
                        f"package={package_id}; "
                        f"experiment={experiment_id}; "
                        f"facts={len(run.get('provenance_fact_ids', []) if isinstance(run.get('provenance_fact_ids', []), list) else [])}; "
                        f"errors={len(run.get('errors', []) if isinstance(run.get('errors', []), list) else [])}"
                    ),
                    source_refs=[
                        str(item).strip()
                        for item in run.get("provenance_fact_ids", [])
                        if str(item).strip()
                    ] if isinstance(run.get("provenance_fact_ids", []), list) else [],
                    metadata={
                        "execution_state": run.get("execution_state", ""),
                        "package_id": package_id,
                        "experiment_id": experiment_id,
                        "executor_id": run.get("executor_id", ""),
                        "provenance_fact_ids": run.get("provenance_fact_ids", []),
                        "provenance_event_ids": run.get("provenance_event_ids", []),
                        "errors": run.get("errors", []),
                    },
                )
            )

    executor_backpropagation = research_state.get("executor_belief_backpropagation_summary", {})
    if isinstance(executor_backpropagation, dict) and executor_backpropagation:
        events.append(
            ResearchEvent(
                **base,
                event_id=_event_id(
                    "executor_backpropagation_applied",
                    topic,
                    executor_backpropagation.get("executor_belief_backpropagation_id", ""),
                ),
                event_type="executor_backpropagation_applied",
                actor="belief_updater",
                asset_type="executor_belief_backpropagation",
                asset_id=str(executor_backpropagation.get("executor_belief_backpropagation_id", "")) or _slugify(topic),
                action=str(executor_backpropagation.get("closed_loop_state", "")),
                summary=(
                    f"runs={executor_backpropagation.get('run_count', 0)}; "
                    f"updates={executor_backpropagation.get('update_count', 0)}; "
                    f"challenged={len(executor_backpropagation.get('challenged_hypothesis_ids', []) if isinstance(executor_backpropagation.get('challenged_hypothesis_ids', []), list) else [])}"
                ),
                source_refs=[
                    str(item.get("experiment_id", "")).strip()
                    for item in executor_backpropagation.get("hypothesis_updates", [])
                    if isinstance(item, dict) and str(item.get("experiment_id", "")).strip()
                ][:20] if isinstance(executor_backpropagation.get("hypothesis_updates", []), list) else [],
                metadata=executor_backpropagation,
            )
        )

    toolchain = research_state.get("discipline_toolchain_binding_summary", {})
    if isinstance(toolchain, dict) and toolchain:
        events.append(
            ResearchEvent(
                **base,
                event_id=_event_id("discipline_toolchain_bound", topic, toolchain.get("discipline_toolchain_binding_id", "")),
                event_type="discipline_toolchain_bound",
                actor="discipline_adapter",
                asset_type="discipline_toolchain",
                asset_id=str(toolchain.get("discipline_toolchain_binding_id", "")) or _slugify(topic),
                action=str(toolchain.get("binding_readiness", "")),
                summary=(
                    f"discipline={toolchain.get('primary_discipline', '')}; "
                    f"missing={len(toolchain.get('missing_required_bindings', []) if isinstance(toolchain.get('missing_required_bindings', []), list) else [])}"
                ),
                metadata=toolchain,
            )
        )

    risk_permission = research_state.get("experiment_risk_permission_summary", {})
    if isinstance(risk_permission, dict) and risk_permission:
        events.append(
            ResearchEvent(
                **base,
                event_id=_event_id("experiment_permission_gated", topic, risk_permission.get("experiment_risk_permission_id", "")),
                event_type="experiment_permission_gated",
                actor="safety_ethics_reviewer",
                asset_type="experiment_permission_gate",
                asset_id=str(risk_permission.get("experiment_risk_permission_id", "")) or _slugify(topic),
                action=str(risk_permission.get("permission_state", "")),
                summary=(
                    f"risk={risk_permission.get('overall_risk_level', '')}; "
                    f"approval_required={risk_permission.get('approval_required', False)}"
                ),
                metadata=risk_permission,
            )
        )

    context_policy = research_state.get("scientific_context_policy_summary", {})
    if isinstance(context_policy, dict) and context_policy:
        events.append(
            ResearchEvent(
                **base,
                event_id=_event_id("context_policy_selected", topic, context_policy.get("scientific_context_policy_id", "")),
                event_type="context_policy_selected",
                actor="context_manager",
                asset_type="scientific_context_policy",
                asset_id=str(context_policy.get("scientific_context_policy_id", "")) or _slugify(topic),
                action=str(context_policy.get("stage", "")),
                summary=(
                    f"required_packs={len(context_policy.get('required_context_packs', []) if isinstance(context_policy.get('required_context_packs', []), list) else [])}; "
                    f"target_tokens={context_policy.get('context_budget', {}).get('target_tokens', '') if isinstance(context_policy.get('context_budget', {}), dict) else ''}"
                ),
                metadata=context_policy,
            )
        )

    workflow_control = research_state.get("workflow_control_summary", {})
    if isinstance(workflow_control, dict) and workflow_control:
        events.append(
            ResearchEvent(
                **base,
                event_id=_event_id("workflow_control_evaluated", topic, workflow_control.get("workflow_control_id", "")),
                event_type="workflow_control_evaluated",
                actor="workflow_controller",
                asset_type="workflow_control",
                asset_id=str(workflow_control.get("workflow_control_id", "")) or _slugify(topic),
                action=str(workflow_control.get("execution_gate", "")),
                summary=(
                    f"control={workflow_control.get('control_state', '')}; "
                    f"allowed={len(workflow_control.get('allowed_next_actions', []) if isinstance(workflow_control.get('allowed_next_actions', []), list) else [])}; "
                    f"blocked={len(workflow_control.get('blocking_gates', []) if isinstance(workflow_control.get('blocking_gates', []), list) else [])}"
                ),
                metadata=workflow_control,
            )
        )

    hypothesis_system = research_state.get("hypothesis_system_summary", {})
    if isinstance(hypothesis_system, dict) and hypothesis_system:
        events.append(
            ResearchEvent(
                **base,
                event_id=_event_id("hypothesis_system_evaluated", topic, hypothesis_system.get("hypothesis_system_id", "")),
                event_type="hypothesis_system_evaluated",
                actor="hypothesis_system",
                asset_type="hypothesis_system",
                asset_id=str(hypothesis_system.get("hypothesis_system_id", "")) or _slugify(topic),
                action=str(hypothesis_system.get("system_state", "")),
                summary=(
                    f"hypotheses={hypothesis_system.get('hypothesis_count', 0)}; "
                    f"theory_objects={hypothesis_system.get('theory_object_count', 0)}; "
                    f"predictions={hypothesis_system.get('prediction_count', 0)}"
                ),
                metadata={
                    key: value
                    for key, value in hypothesis_system.items()
                    if key != "canonical_layers"
                },
            )
        )

    evaluation_system = research_state.get("scientific_evaluation_system_summary", {})
    if isinstance(evaluation_system, dict) and evaluation_system:
        events.append(
            ResearchEvent(
                **base,
                event_id=_event_id(
                    "scientific_evaluation_system_evaluated",
                    topic,
                    evaluation_system.get("scientific_evaluation_system_id", ""),
                ),
                event_type="scientific_evaluation_system_evaluated",
                actor="scientific_evaluation_system",
                asset_type="scientific_evaluation_system",
                asset_id=str(evaluation_system.get("scientific_evaluation_system_id", "")) or _slugify(topic),
                action=str(evaluation_system.get("system_state", "")),
                summary=(
                    f"case_suite={evaluation_system.get('case_suite_state', '')}; "
                    f"benchmark={evaluation_system.get('benchmark_state', '')}; "
                    f"blocking={evaluation_system.get('blocking_gate_count', 0)}"
                ),
                metadata={
                    key: value
                    for key, value in evaluation_system.items()
                    if key != "canonical_layers"
                },
            )
        )

    benchmark_summary = research_state.get("benchmark_case_suite_summary", {})
    scientific_benchmark = (
        benchmark_summary.get("scientific_evaluation_benchmark_summary", {})
        if isinstance(benchmark_summary, dict)
        and isinstance(benchmark_summary.get("scientific_evaluation_benchmark_summary", {}), dict)
        else {}
    )
    if isinstance(scientific_benchmark, dict) and scientific_benchmark:
        events.append(
            ResearchEvent(
                **base,
                event_id=_event_id(
                    "scientific_benchmark_evaluated",
                    topic,
                    scientific_benchmark.get("scientific_evaluation_benchmark_id", ""),
                ),
                event_type="scientific_benchmark_evaluated",
                actor="scientific_evaluation_benchmark",
                asset_type="scientific_evaluation_benchmark",
                asset_id=str(scientific_benchmark.get("scientific_evaluation_benchmark_id", ""))
                or _slugify(topic),
                action=str(scientific_benchmark.get("benchmark_state", "")),
                summary=(
                    f"tasks={scientific_benchmark.get('task_count', 0)}; "
                    f"passed={scientific_benchmark.get('passed_count', 0)}; "
                    f"quality={scientific_benchmark.get('average_quality_score', 0)}"
                ),
                metadata=scientific_benchmark,
            )
        )

    campaign = research_state.get("research_campaign_plan_summary", {})
    route_selector = (
        campaign.get("route_selector_summary", {})
        if isinstance(campaign, dict) and isinstance(campaign.get("route_selector_summary", {}), dict)
        else {}
    )
    if isinstance(route_selector, dict) and route_selector:
        events.append(
            ResearchEvent(
                **base,
                event_id=_event_id(
                    "route_selector_planned",
                    topic,
                    route_selector.get("route_scheduler_id", ""),
                ),
                event_type="route_selector_planned",
                actor="research_campaign_planner",
                asset_type="research_route_selector",
                asset_id=str(route_selector.get("route_scheduler_id", "")) or _slugify(topic),
                action=str(route_selector.get("best_action", "")),
                summary=(
                    f"candidates={route_selector.get('candidate_count', 0)}; "
                    f"best={route_selector.get('best_action', '')}"
                ),
                source_refs=[
                    str(node.get("node_id", "")).strip()
                    for node in route_selector.get("route_nodes", [])
                    if isinstance(node, dict) and str(node.get("node_id", "")).strip()
                ][:20] if isinstance(route_selector.get("route_nodes", []), list) else [],
                metadata={
                    "scheduler_state": route_selector.get("scheduler_state", ""),
                    "best_action": route_selector.get("best_action", ""),
                    "best_route_node_id": route_selector.get("best_route_node_id", ""),
                    "best_selection_reason": route_selector.get("best_selection_reason", ""),
                    "candidate_count": route_selector.get("candidate_count", 0),
                    "llm_judge_state": route_selector.get("llm_judge_state", ""),
                    "llm_judge_mode": route_selector.get("llm_judge_mode", ""),
                    "llm_judge_default": route_selector.get("llm_judge_default", False),
                },
            )
        )
        if route_selector.get("llm_judgment"):
            events.append(
                ResearchEvent(
                    **base,
                    event_id=_event_id("route_llm_judge_completed", topic, route_selector.get("route_scheduler_id", "")),
                    event_type="route_llm_judge_completed",
                    actor="scheduler_llm_judge",
                    asset_type="route_selector_judgment",
                    asset_id=f"route-llm-judge::{_slugify(topic)}",
                    action=str(route_selector.get("llm_judge_state", "")),
                    summary=(
                        f"mode={route_selector.get('llm_judge_mode', '')}; "
                        f"default={route_selector.get('llm_judge_default', False)}; "
                        f"best={route_selector.get('best_action', '')}"
                    ),
                    metadata=route_selector.get("llm_judgment", {}),
                )
            )

    if isinstance(campaign, dict) and campaign:
        events.append(
            ResearchEvent(
                **base,
                event_id=_event_id("research_campaign_planned", topic, campaign.get("research_campaign_plan_id", "")),
                event_type="research_campaign_planned",
                actor="campaign_planner",
                asset_type="research_campaign_plan",
                asset_id=str(campaign.get("research_campaign_plan_id", "")) or _slugify(topic),
                action=str(campaign.get("next_campaign_decision", "")),
                summary=(
                    f"stage={campaign.get('current_campaign_stage', '')}; "
                    f"steps={len(campaign.get('multi_step_route_plan', []) if isinstance(campaign.get('multi_step_route_plan', []), list) else [])}; "
                    f"next={campaign.get('next_campaign_decision', '')}"
                ),
                source_refs=[
                    str(item.get("route_action", "")).strip()
                    for item in campaign.get("multi_step_route_plan", [])
                    if isinstance(item, dict) and str(item.get("route_action", "")).strip()
                ][:20] if isinstance(campaign.get("multi_step_route_plan", []), list) else [],
                metadata={
                    "current_campaign_stage": campaign.get("current_campaign_stage", ""),
                    "next_campaign_decision": campaign.get("next_campaign_decision", ""),
                    "scheduler_constraints": campaign.get("scheduler_constraints", []),
                    "pivot_rules": campaign.get("pivot_rules", []),
                    "kill_rules": campaign.get("kill_rules", []),
                    "replication_rules": campaign.get("replication_rules", []),
                    "llm_judge_state": campaign.get("llm_judge_state", ""),
                    "llm_judge_mode": campaign.get("llm_judge_mode", ""),
                    "llm_judge_default": campaign.get("llm_judge_default", False),
                },
            )
        )
        if campaign.get("llm_judgment"):
            events.append(
                ResearchEvent(
                    **base,
                    event_id=_event_id("campaign_llm_judge_completed", topic, campaign.get("research_campaign_plan_id", "")),
                    event_type="campaign_llm_judge_completed",
                    actor="scheduler_llm_judge",
                    asset_type="campaign_judgment",
                    asset_id=f"campaign-llm-judge::{_slugify(topic)}",
                    action=str(campaign.get("llm_judge_state", "")),
                    summary=(
                        f"mode={campaign.get('llm_judge_mode', '')}; "
                        f"default={campaign.get('llm_judge_default', False)}; "
                        f"next={campaign.get('next_campaign_decision', '')}"
                    ),
                    metadata=campaign.get("llm_judgment", {}),
                )
            )

    optimization_adapter = research_state.get("optimization_adapter_summary", {})
    if isinstance(optimization_adapter, dict) and optimization_adapter:
        events.append(
            ResearchEvent(
                **base,
                event_id=_event_id(
                    "optimization_adapter_planned",
                    topic,
                    optimization_adapter.get("adapter_id", ""),
                ),
                event_type="optimization_adapter_planned",
                actor="optimization_adapter",
                asset_type="optimization_adapter",
                asset_id=str(optimization_adapter.get("adapter_id", "")) or _slugify(topic),
                action=str(optimization_adapter.get("adapter_state", "")),
                summary=(
                    f"plans={optimization_adapter.get('plan_count', 0)}; "
                    f"candidates={optimization_adapter.get('optimization_candidate_count', 0)}"
                ),
                source_refs=[
                    str(plan.get("experiment_id", "")).strip()
                    for plan in optimization_adapter.get("plans", [])
                    if isinstance(plan, dict) and str(plan.get("experiment_id", "")).strip()
                ],
                metadata={
                    "adapter_state": optimization_adapter.get("adapter_state", ""),
                    "plan_count": optimization_adapter.get("plan_count", 0),
                    "optimization_candidate_count": optimization_adapter.get(
                        "optimization_candidate_count", 0
                    ),
                    "execution_boundary": optimization_adapter.get("execution_boundary", {}),
                },
            )
        )

    discipline_adapter = research_state.get("discipline_adapter_summary", {})
    if isinstance(discipline_adapter, dict) and discipline_adapter:
        events.append(
            ResearchEvent(
                **base,
                event_id=_event_id(
                    "discipline_adapter_planned",
                    topic,
                    discipline_adapter.get("adapter_id", ""),
                ),
                event_type="discipline_adapter_planned",
                actor="discipline_adapter",
                asset_type="discipline_adapter",
                asset_id=str(discipline_adapter.get("adapter_id", "")) or _slugify(topic),
                action=str(discipline_adapter.get("adapter_state", "")),
                summary=(
                    f"adapter={discipline_adapter.get('selected_adapter_id', '')}; "
                    f"bindings={discipline_adapter.get('binding_count', 0)}; "
                    f"blocked={discipline_adapter.get('blocked_binding_count', 0)}"
                ),
                source_refs=[
                    str(binding.get("binding_id", "")).strip()
                    for binding in discipline_adapter.get("bindings", [])
                    if isinstance(binding, dict) and str(binding.get("binding_id", "")).strip()
                ],
                metadata={
                    "adapter_state": discipline_adapter.get("adapter_state", ""),
                    "selected_adapter_id": discipline_adapter.get("selected_adapter_id", ""),
                    "primary_discipline": discipline_adapter.get("primary_discipline", ""),
                    "binding_count": discipline_adapter.get("binding_count", 0),
                    "blocked_binding_count": discipline_adapter.get("blocked_binding_count", 0),
                },
            )
        )

    execution_registry = research_state.get("execution_adapter_registry_summary", {})
    if isinstance(execution_registry, dict) and execution_registry:
        events.append(
            ResearchEvent(
                **base,
                event_id=_event_id(
                    "execution_adapter_registry_planned",
                    topic,
                    execution_registry.get("registry_id", ""),
                ),
                event_type="execution_adapter_registry_planned",
                actor="execution_adapter_registry",
                asset_type="execution_adapter_registry",
                asset_id=str(execution_registry.get("registry_id", "")) or _slugify(topic),
                action=str(execution_registry.get("registry_state", "")),
                summary=(
                    f"adapter={execution_registry.get('selected_adapter_id', '')}; "
                    f"packages={execution_registry.get('execution_package_count', 0)}; "
                    f"ready={execution_registry.get('ready_package_count', 0)}"
                ),
                source_refs=[
                    str(package.get("package_id", "")).strip()
                    for package in execution_registry.get("execution_packages", [])
                    if isinstance(package, dict) and str(package.get("package_id", "")).strip()
                ],
                metadata={
                    "registry_state": execution_registry.get("registry_state", ""),
                    "selected_adapter_id": execution_registry.get("selected_adapter_id", ""),
                    "primary_discipline": execution_registry.get("primary_discipline", ""),
                    "execution_package_count": execution_registry.get("execution_package_count", 0),
                    "ready_package_count": execution_registry.get("ready_package_count", 0),
                    "blocked_package_count": execution_registry.get("blocked_package_count", 0),
                },
            )
        )

    run_handoff = research_state.get("run_handoff_contract_summary", {})
    if isinstance(run_handoff, dict) and run_handoff:
        events.append(
            ResearchEvent(
                **base,
                event_id=_event_id(
                    "run_handoff_contract_created",
                    topic,
                    run_handoff.get("handoff_contract_id", ""),
                ),
                event_type="run_handoff_contract_created",
                actor="run_handoff",
                asset_type="run_handoff_contract",
                asset_id=str(run_handoff.get("handoff_contract_id", "")) or _slugify(topic),
                action=str(run_handoff.get("contract_state", "")),
                summary=f"contracts={run_handoff.get('contract_count', 0)}",
                source_refs=[
                    str(contract.get("package_id", "")).strip()
                    for contract in run_handoff.get("contracts", [])
                    if isinstance(contract, dict) and str(contract.get("package_id", "")).strip()
                ],
                metadata={
                    "contract_state": run_handoff.get("contract_state", ""),
                    "contract_count": run_handoff.get("contract_count", 0),
                    "return_contract": run_handoff.get("return_contract", {}),
                    "normalization_function": run_handoff.get("normalization_function", ""),
                },
            )
        )

    evaluation_harness = research_state.get("kaivu_evaluation_harness_summary", {})
    if isinstance(evaluation_harness, dict) and evaluation_harness:
        events.append(
            ResearchEvent(
                **base,
                event_id=_event_id(
                    "kaivu_evaluation_harness_completed",
                    topic,
                    evaluation_harness.get("harness_id", ""),
                ),
                event_type="kaivu_evaluation_harness_completed",
                actor="evaluation_harness",
                asset_type="kaivu_evaluation_harness",
                asset_id=str(evaluation_harness.get("harness_id", "")) or _slugify(topic),
                action=str(evaluation_harness.get("release_state", "")),
                summary=(
                    f"score={evaluation_harness.get('overall_score', 0)}; "
                    f"blocking_gates={evaluation_harness.get('blocking_gate_count', 0)}"
                ),
                source_refs=[
                    str(axis.get("axis_id", "")).strip()
                    for axis in evaluation_harness.get("axes", [])
                    if isinstance(axis, dict) and str(axis.get("axis_id", "")).strip()
                ],
                metadata={
                    "overall_score": evaluation_harness.get("overall_score", 0),
                    "release_state": evaluation_harness.get("release_state", ""),
                    "blocking_gate_count": evaluation_harness.get("blocking_gate_count", 0),
                    "axis_count": evaluation_harness.get("axis_count", 0),
                },
            )
        )

    research_program = research_state.get("research_program_summary", {})
    if isinstance(research_program, dict) and research_program:
        events.append(
            ResearchEvent(
                **base,
                event_id=_event_id("research_program_snapshot_saved", topic, research_program.get("program_id", "")),
                event_type="research_program_snapshot_saved",
                actor="research_program_registry",
                asset_type="research_program",
                asset_id=str(research_program.get("program_id", "")) or _slugify(topic),
                action=str(research_program.get("status", "")),
                summary=(
                    f"actions={len(research_program.get('control_actions', []) if isinstance(research_program.get('control_actions', []), list) else [])}; "
                    f"portfolio={research_program.get('experiment_portfolio', {}).get('selected_count', 0) if isinstance(research_program.get('experiment_portfolio', {}), dict) else 0}; "
                    f"release={research_program.get('report_release_policy', {}).get('release_level', '') if isinstance(research_program.get('report_release_policy', {}), dict) else ''}"
                ),
                source_refs=[
                    str(item.get("action", "")).strip()
                    for item in research_program.get("control_actions", [])
                    if isinstance(item, dict) and str(item.get("action", "")).strip()
                ][:20] if isinstance(research_program.get("control_actions", []), list) else [],
                metadata={
                    "program_id": research_program.get("program_id", ""),
                    "status": research_program.get("status", ""),
                    "objective_contract": research_program.get("objective_contract", {}),
                    "failed_attempt_recall": research_program.get("failed_attempt_recall", {}),
                    "experiment_portfolio": research_program.get("experiment_portfolio", {}),
                    "report_release_policy": research_program.get("report_release_policy", {}),
                    "research_action_policy_matrix": research_program.get("research_action_policy_matrix", []),
                    "rival_hypothesis_reasoning": research_program.get("rival_hypothesis_reasoning", {}),
                },
            )
        )

    return events


def _event_id(event_type: str, topic: str, suffix: Any) -> str:
    return f"{event_type}::{_slugify(topic)}::{_slugify(str(suffix) or datetime.now(timezone.utc).isoformat())}"


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "event"

