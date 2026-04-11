from __future__ import annotations

from typing import Any


def build_scientific_problem_reframer_summary(
    *,
    topic: str,
    research_state: dict[str, Any],
    claim_graph: dict[str, Any],
) -> dict[str, Any]:
    claims = _items(claim_graph.get("claims", []))
    hypotheses = _items(claim_graph.get("hypotheses", []))
    negative_results = _items(claim_graph.get("negative_results", []))
    conflicts = _items(research_state.get("conflict_attribution", {}).get("groups", [])) if isinstance(research_state.get("conflict_attribution", {}), dict) else []
    evidence = research_state.get("evidence_review_summary", {}) if isinstance(research_state.get("evidence_review_summary", {}), dict) else {}
    validation = research_state.get("hypothesis_validation_summary", {}) if isinstance(research_state.get("hypothesis_validation_summary", {}), dict) else {}
    triggers = _reframing_triggers(
        claims=claims,
        hypotheses=hypotheses,
        negative_results=negative_results,
        conflicts=conflicts,
        evidence=evidence,
        validation=validation,
    )
    candidate_frames = _candidate_frames(topic=topic, triggers=triggers, research_state=research_state, claim_graph=claim_graph)
    selected = candidate_frames[0] if candidate_frames else {}
    return {
        "scientific_problem_reframer_id": f"problem-reframer::{_slugify(topic)}",
        "topic": topic,
        "reframing_state": "reframe_recommended" if triggers else "current_frame_usable",
        "trigger_count": len(triggers),
        "triggers": triggers,
        "current_frame": {
            "question": topic,
            "claim_count": len(claims),
            "hypothesis_count": len(hypotheses),
            "negative_result_count": len(negative_results),
            "evidence_readiness": evidence.get("review_readiness", ""),
        },
        "candidate_frames": candidate_frames,
        "selected_frame": selected,
        "representation_shifts": _representation_shifts(triggers, selected),
        "metric_shifts": _metric_shifts(topic, triggers),
        "scale_shifts": _scale_shifts(topic, triggers),
        "scheduler_constraints": _scheduler_constraints(triggers, selected),
        "memory_queries": _memory_queries(topic, selected),
    }


def _reframing_triggers(
    *,
    claims: list[dict[str, Any]],
    hypotheses: list[dict[str, Any]],
    negative_results: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
    evidence: dict[str, Any],
    validation: dict[str, Any],
) -> list[dict[str, Any]]:
    triggers: list[dict[str, Any]] = []
    if not claims:
        triggers.append({"trigger": "claim_space_empty", "reason": "no normalized claims exist"})
    if not hypotheses:
        triggers.append({"trigger": "hypothesis_space_empty", "reason": "no candidate hypotheses exist"})
    if negative_results:
        triggers.append({"trigger": "failed_attempt_pressure", "reason": "negative or failed attempts should change the problem frame"})
    if conflicts:
        triggers.append({"trigger": "evidence_conflict_pressure", "reason": "conflicting evidence may indicate wrong population, method, scale, or metric"})
    if evidence.get("review_blockers"):
        triggers.append({"trigger": "evidence_blocked", "reason": "evidence review has blockers"})
    if validation.get("low_falsifiability_hypotheses"):
        triggers.append({"trigger": "low_falsifiability", "reason": "some hypotheses are too hard to falsify"})
    if validation.get("weak_testability_hypotheses"):
        triggers.append({"trigger": "weak_testability", "reason": "some hypotheses are not operational enough"})
    return triggers[:12]


def _candidate_frames(
    *,
    topic: str,
    triggers: list[dict[str, Any]],
    research_state: dict[str, Any],
    claim_graph: dict[str, Any],
) -> list[dict[str, Any]]:
    trigger_names = {str(item.get("trigger", "")) for item in triggers}
    frames: list[dict[str, Any]] = []
    if "low_falsifiability" in trigger_names or "weak_testability" in trigger_names:
        frames.append(
            {
                "frame_id": f"frame::{_slugify(topic)}::operational",
                "frame_type": "operationalization",
                "question": f"What measurable prediction would make '{topic}' false or less plausible?",
                "why": "current hypotheses need stronger observables and decision thresholds",
                "preferred_next_route": "hypothesis_formalization",
            }
        )
    if "evidence_conflict_pressure" in trigger_names or "evidence_blocked" in trigger_names:
        frames.append(
            {
                "frame_id": f"frame::{_slugify(topic)}::conflict_attribution",
                "frame_type": "conflict_attribution",
                "question": f"Which population, method, boundary condition, or measurement difference explains the conflict in '{topic}'?",
                "why": "conflicting evidence should be split before averaging conclusions",
                "preferred_next_route": "literature_mapping",
            }
        )
    if "failed_attempt_pressure" in trigger_names:
        frames.append(
            {
                "frame_id": f"frame::{_slugify(topic)}::failure_informed",
                "frame_type": "failure_informed",
                "question": f"What changed condition or rival mechanism would explain the failed attempts for '{topic}'?",
                "why": "failure knowledge should constrain the next route rather than repeat it",
                "preferred_next_route": "theory_integration",
            }
        )
    if not frames:
        frames.append(
            {
                "frame_id": f"frame::{_slugify(topic)}::baseline",
                "frame_type": "baseline_scientific_question",
                "question": topic,
                "why": "current frame has enough claims and hypotheses to proceed",
                "preferred_next_route": str(research_state.get("recommended_next_stage", "continue_research_cycle")),
            }
        )
    hypotheses = _items(claim_graph.get("hypotheses", []))
    for frame in frames:
        frame["affected_hypothesis_ids"] = [
            str(item.get("global_hypothesis_id", "") or item.get("hypothesis_id", "")).strip()
            for item in hypotheses[:6]
            if str(item.get("global_hypothesis_id", "") or item.get("hypothesis_id", "")).strip()
        ]
        frame["decision_value"] = _frame_value(frame, triggers)
    frames.sort(key=lambda item: float(item.get("decision_value", 0)), reverse=True)
    return frames[:6]


def _frame_value(frame: dict[str, Any], triggers: list[dict[str, Any]]) -> float:
    value = 1.0 + len(triggers) * 0.4
    if frame.get("frame_type") in {"operationalization", "failure_informed"}:
        value += 1.0
    if frame.get("frame_type") == "conflict_attribution":
        value += 0.7
    return round(value, 3)


def _representation_shifts(triggers: list[dict[str, Any]], selected: dict[str, Any]) -> list[str]:
    frame_type = str(selected.get("frame_type", ""))
    shifts = []
    if frame_type == "operationalization":
        shifts.append("represent hypotheses as variables, observables, thresholds, and falsification tests")
    if frame_type == "conflict_attribution":
        shifts.append("represent evidence by method, population, scale, and measurement quality")
    if frame_type == "failure_informed":
        shifts.append("represent failed attempts as constraints on mechanism families")
    if not shifts and triggers:
        shifts.append("split the problem into mechanism, evidence, and execution subframes")
    return shifts or ["keep current representation but preserve explicit assumptions"]


def _metric_shifts(topic: str, triggers: list[dict[str, Any]]) -> list[str]:
    text = topic.lower()
    metrics = []
    if any(token in text for token in ["ai", "model", "benchmark", "accuracy"]):
        metrics.extend(["use held-out performance, calibration, robustness, and ablation deltas"])
    if any(token in text for token in ["chem", "catalyst", "reaction"]):
        metrics.extend(["use yield, selectivity, conversion, purity, and safety margin"])
    if any(token in text for token in ["physics", "material", "quantum"]):
        metrics.extend(["use effect size, uncertainty, calibration error, and boundary-condition sensitivity"])
    if any(item.get("trigger") == "low_falsifiability" for item in triggers):
        metrics.append("add explicit decision thresholds for falsification")
    return metrics[:8] or ["define primary outcome, secondary outcome, and minimum meaningful effect"]


def _scale_shifts(topic: str, triggers: list[dict[str, Any]]) -> list[str]:
    shifts = []
    if any(item.get("trigger") == "evidence_conflict_pressure" for item in triggers):
        shifts.append("separate molecular/component scale from system/population scale")
    if any(item.get("trigger") == "failed_attempt_pressure" for item in triggers):
        shifts.append("compare cheap proxy scale against confirmatory target scale")
    return shifts or ["state the scale at which the claim is expected to hold"]


def _scheduler_constraints(triggers: list[dict[str, Any]], selected: dict[str, Any]) -> list[str]:
    constraints = [f"preferred route from reframer: {selected.get('preferred_next_route', '')}"]
    for trigger in triggers[:5]:
        constraints.append(f"address reframing trigger: {trigger.get('trigger', '')}")
    return constraints[:10]


def _memory_queries(topic: str, selected: dict[str, Any]) -> list[str]:
    return [
        f"prior failed attempts related to {topic}",
        f"evidence conflicts matching frame {selected.get('frame_type', 'baseline')}",
        f"alternate representations or metrics for {topic}",
    ]


def _items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value).strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "problem"
