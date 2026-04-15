from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from .messages import Message
from .model import ModelBackend


@dataclass(slots=True)
class SchedulerCandidateJudgment:
    experiment_id: str
    llm_scientific_value_score: float = 0.0
    llm_mechanism_discrimination_score: float = 0.0
    llm_risk_score: float = 0.0
    score_adjustment: float = 0.0
    recommended_action: str = "schedule"
    rationale: str = ""
    risk_flags: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SchedulerLLMJudge:
    def __init__(self, model: ModelBackend | None = None) -> None:
        self.model = model

    async def review_candidates(
        self,
        *,
        topic: str,
        scheduler_type: str,
        scheduler_summary: dict[str, Any],
        research_context: dict[str, Any],
        max_candidates: int = 12,
    ) -> dict[str, Any]:
        packet = build_scheduler_judge_packet(
            topic=topic,
            scheduler_type=scheduler_type,
            scheduler_summary=scheduler_summary,
            research_context=research_context,
            max_candidates=max_candidates,
        )
        if self.model is None:
            return heuristic_scheduler_judgment(packet)
        messages = [
            Message(
                role="system",
                content=(
                    "You are a scientific scheduler judge. Review candidate research actions. "
                    "Do not invent unavailable evidence. Return valid JSON only."
                ),
            ),
            Message(
                role="user",
                content=(
                    "Judge these scheduler candidates. Prefer actions that distinguish hypotheses, "
                    "reduce uncertainty, avoid repeated failures, respect discipline constraints, "
                    "and are executable under the stated gates.\n\n"
                    f"{json.dumps(packet, ensure_ascii=False, indent=2)}\n\n"
                    "Return JSON with keys: judge_state, ranked_candidates, blocked_candidates, "
                    "missing_information, policy_notes. Each ranked candidate must include "
                    "experiment_id, llm_scientific_value_score, llm_mechanism_discrimination_score, "
                    "llm_risk_score, score_adjustment, recommended_action, rationale, risk_flags, "
                    "missing_information."
                ),
            ),
        ]
        try:
            action = await self.model.decide(messages, tools=[])
            parsed = _parse_judge_json(action.message)
            parsed["judge_mode"] = "llm"
            parsed["model_meta"] = action.meta
            return normalize_scheduler_judgment(parsed, packet)
        except Exception as exc:
            fallback = heuristic_scheduler_judgment(packet)
            fallback["judge_mode"] = "heuristic_fallback"
            fallback["judge_error"] = str(exc)
            return fallback


def build_scheduler_judge_packet(
    *,
    topic: str,
    scheduler_type: str,
    scheduler_summary: dict[str, Any],
    research_context: dict[str, Any],
    max_candidates: int = 12,
) -> dict[str, Any]:
    candidates = _candidate_shortlist(scheduler_summary, max_candidates=max_candidates)
    mechanism_families = research_context.get("mechanism_families", [])
    if not isinstance(mechanism_families, list):
        mechanism_families = []
    mechanism_summary = research_context.get("mechanism_family_lifecycle_summary", {})
    if not mechanism_families and isinstance(mechanism_summary, dict):
        mechanism_families = (
            mechanism_summary.get("families", [])
            if isinstance(mechanism_summary.get("families", []), list)
            else []
        )
    return {
        "topic": topic,
        "scheduler_type": scheduler_type,
        "current_stage": str(research_context.get("current_stage", "")).strip(),
        "recommended_next_stage": str(research_context.get("recommended_next_stage", "")).strip(),
        "active_hypotheses": _compact_items(research_context.get("active_hypotheses", []), limit=5),
        "mechanism_families": _compact_items(mechanism_families, limit=5),
        "evidence_conflicts": _strings(research_context.get("evidence_conflicts", []))[:8],
        "failed_attempts": _strings(research_context.get("failed_attempts", []))[:8],
        "discipline_constraints": _strings(research_context.get("discipline_constraints", []))[:12],
        "budget_constraints": research_context.get("budget_constraints", {})
        if isinstance(research_context.get("budget_constraints", {}), dict)
        else {},
        "candidate_experiments": candidates,
        "numeric_policy": {
            "scheduler_state": scheduler_summary.get("scheduler_state", ""),
            "top_experiment_id": scheduler_summary.get("top_experiment_id", ""),
            "mcts_like_search": scheduler_summary.get("mcts_like_search", {})
            if isinstance(scheduler_summary.get("mcts_like_search", {}), dict)
            else {},
        },
    }


def heuristic_scheduler_judgment(packet: dict[str, Any]) -> dict[str, Any]:
    judgments: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    role_reviews: list[dict[str, Any]] = []
    for candidate in packet.get("candidate_experiments", []) if isinstance(packet.get("candidate_experiments", []), list) else []:
        experiment_id = str(candidate.get("experiment_id", "")).strip()
        if not experiment_id:
            continue
        acquisition = candidate.get("acquisition_function", {}) if isinstance(candidate.get("acquisition_function", {}), dict) else {}
        numeric = _float(candidate.get("selection_score", candidate.get("portfolio_score", 0)))
        info_gain = _float(candidate.get("information_gain_score", 0))
        discrimination = _float(candidate.get("discrimination_score", 0))
        risk = _float(candidate.get("risk_score", 0)) + _float(candidate.get("repeat_failure_risk", 0))
        validator = _float(candidate.get("validator_penalty", 0))
        scientific_value = _clamp((info_gain + _float(acquisition.get("expected_improvement", 0)) * 5.0) / 8.0)
        mechanism_value = _clamp(discrimination / 3.0)
        risk_score = _clamp((risk + validator) / 6.0)
        adjustment = round(0.25 * scientific_value + 0.20 * mechanism_value - 0.35 * risk_score, 3)
        recommended_action = "schedule"
        risk_flags: list[str] = []
        if validator >= 3 or str(candidate.get("gate_state", "")).strip() == "blocked":
            recommended_action = "block"
            risk_flags.append("blocked_by_gate_or_validator")
        elif risk_score >= 0.55:
            recommended_action = "human_review"
            risk_flags.append("high_risk_or_repeat_failure")
        if candidate.get("search_space"):
            risk_flags.append("requires_frozen_search_space_and_validation_split")
        rationale = _heuristic_rationale(candidate, scientific_value, mechanism_value, risk_score, numeric)
        item = SchedulerCandidateJudgment(
            experiment_id=experiment_id,
            llm_scientific_value_score=round(scientific_value, 3),
            llm_mechanism_discrimination_score=round(mechanism_value, 3),
            llm_risk_score=round(risk_score, 3),
            score_adjustment=adjustment,
            recommended_action=recommended_action,
            rationale=rationale,
            risk_flags=risk_flags,
            missing_information=_missing_information(candidate),
        ).to_dict()
        judgments.append(item)
        role_reviews.extend(_role_reviews_for_candidate(candidate, item))
        if recommended_action == "block":
            blocked.append({"experiment_id": experiment_id, "reason": "; ".join(risk_flags)})
    judgments.sort(
        key=lambda item: (
            item.get("recommended_action") == "schedule",
            _float(item.get("score_adjustment", 0)),
            _float(item.get("llm_scientific_value_score", 0)),
        ),
        reverse=True,
    )
    return normalize_scheduler_judgment(
        {
            "judge_state": "usable",
            "judge_mode": "heuristic",
            "ranked_candidates": judgments,
            "blocked_candidates": blocked,
            "missing_information": _dedupe(
                [
                    info
                    for item in judgments
                    for info in item.get("missing_information", [])
                    if str(info).strip()
                ]
            )[:12],
            "policy_notes": [
                "numeric scheduler remains authoritative for reproducibility",
                "judge adds scientific-semantics score adjustments and risk flags",
            ],
            "role_reviews": role_reviews,
            "calibration_record": _judge_calibration_record(judgments),
        },
        packet,
    )


def apply_scheduler_judgment_to_summary(
    scheduler_summary: dict[str, Any],
    judgment: dict[str, Any],
    *,
    adjustment_weight: float = 1.0,
) -> dict[str, Any]:
    if not isinstance(scheduler_summary, dict) or not scheduler_summary:
        return scheduler_summary
    by_id = {
        str(item.get("experiment_id", "")).strip(): item
        for item in judgment.get("ranked_candidates", [])
        if isinstance(item, dict) and str(item.get("experiment_id", "")).strip()
    }
    blocked_ids = {
        str(item.get("experiment_id", "")).strip()
        for item in judgment.get("blocked_candidates", [])
        if isinstance(item, dict) and str(item.get("experiment_id", "")).strip()
    }
    updated = dict(scheduler_summary)
    updated["llm_judgment"] = judgment
    updated["llm_judge_state"] = str(judgment.get("judge_state", "")).strip()
    updated["llm_judge_mode"] = str(judgment.get("judge_mode", "")).strip()
    updated["candidate_experiments"] = [
        _attach_judgment(candidate, by_id, blocked_ids, adjustment_weight)
        for candidate in scheduler_summary.get("candidate_experiments", [])
        if isinstance(candidate, dict)
    ]
    updated_queue = [
        _attach_judgment(item, by_id, blocked_ids, adjustment_weight)
        for item in scheduler_summary.get("execution_queue", [])
        if isinstance(item, dict)
    ]
    updated_queue = [
        item
        for item in updated_queue
        if item.get("llm_recommended_action") != "block"
    ]
    updated_queue.sort(key=lambda item: _float(item.get("judge_adjusted_selection_score", item.get("portfolio_score", 0))), reverse=True)
    for index, item in enumerate(updated_queue, start=1):
        item["rank"] = index
    updated["execution_queue"] = updated_queue
    blocked = list(scheduler_summary.get("blocked_experiments", []) if isinstance(scheduler_summary.get("blocked_experiments", []), list) else [])
    for candidate in updated.get("candidate_experiments", []):
        if candidate.get("llm_recommended_action") == "block":
            blocked.append(
                {
                    **candidate,
                    "gate_state": "blocked",
                    "gate_reasons": _dedupe(
                        _strings(candidate.get("gate_reasons", []))
                        + _strings(candidate.get("llm_risk_flags", []))
                        + ["blocked by scheduler LLM judge"]
                    ),
                }
            )
    updated["blocked_experiments"] = blocked[:30]
    top = updated_queue[0] if updated_queue else {}
    updated["top_experiment_id"] = str(top.get("experiment_id", ""))
    updated["top_action"] = str(top.get("action", ""))
    mcts = dict(updated.get("mcts_like_search", {}) if isinstance(updated.get("mcts_like_search", {}), dict) else {})
    mcts["llm_judge_integrated"] = True
    mcts["llm_judge_top_reason"] = str(top.get("llm_rationale", ""))
    updated["mcts_like_search"] = mcts
    return updated


def normalize_scheduler_judgment(payload: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    candidate_ids = {
        str(item.get("experiment_id", "")).strip()
        for item in packet.get("candidate_experiments", [])
        if isinstance(item, dict) and str(item.get("experiment_id", "")).strip()
    }
    ranked = []
    for item in payload.get("ranked_candidates", []) if isinstance(payload.get("ranked_candidates", []), list) else []:
        if not isinstance(item, dict):
            continue
        experiment_id = str(item.get("experiment_id", "")).strip()
        if experiment_id not in candidate_ids:
            continue
        ranked.append(
            SchedulerCandidateJudgment(
                experiment_id=experiment_id,
                llm_scientific_value_score=_clamp(_float(item.get("llm_scientific_value_score", 0))),
                llm_mechanism_discrimination_score=_clamp(
                    _float(item.get("llm_mechanism_discrimination_score", 0))
                ),
                llm_risk_score=_clamp(_float(item.get("llm_risk_score", 0))),
                score_adjustment=_float(item.get("score_adjustment", 0)),
                recommended_action=str(item.get("recommended_action", "schedule")).strip() or "schedule",
                rationale=str(item.get("rationale", "")).strip()[:600],
                risk_flags=_strings(item.get("risk_flags", []))[:8],
                missing_information=_strings(item.get("missing_information", []))[:8],
            ).to_dict()
        )
    seen = {item["experiment_id"] for item in ranked}
    for candidate in packet.get("candidate_experiments", []) if isinstance(packet.get("candidate_experiments", []), list) else []:
        experiment_id = str(candidate.get("experiment_id", "")).strip()
        if experiment_id and experiment_id not in seen:
            ranked.append(
                SchedulerCandidateJudgment(
                    experiment_id=experiment_id,
                    recommended_action="schedule",
                    rationale="not explicitly ranked by judge; keep numeric scheduler order",
                ).to_dict()
            )
    return {
        "judge_state": str(payload.get("judge_state", "usable")).strip() or "usable",
        "judge_mode": str(payload.get("judge_mode", "heuristic")).strip() or "heuristic",
        "ranked_candidates": ranked,
        "blocked_candidates": [
            item
            for item in payload.get("blocked_candidates", [])
            if isinstance(item, dict) and str(item.get("experiment_id", "")).strip() in candidate_ids
        ][:12] if isinstance(payload.get("blocked_candidates", []), list) else [],
        "missing_information": _strings(payload.get("missing_information", []))[:12],
        "policy_notes": _strings(payload.get("policy_notes", []))[:8],
        "role_reviews": payload.get("role_reviews", [])
        if isinstance(payload.get("role_reviews", []), list)
        else [],
        "calibration_record": payload.get("calibration_record", {})
        if isinstance(payload.get("calibration_record", {}), dict)
        else {},
        "model_meta": payload.get("model_meta", {}) if isinstance(payload.get("model_meta", {}), dict) else {},
        "judge_error": str(payload.get("judge_error", "")).strip(),
    }


def _role_reviews_for_candidate(candidate: dict[str, Any], judgment: dict[str, Any]) -> list[dict[str, Any]]:
    experiment_id = str(candidate.get("experiment_id", "")).strip()
    scientific_value = _float(judgment.get("llm_scientific_value_score", 0))
    mechanism_value = _float(judgment.get("llm_mechanism_discrimination_score", 0))
    risk = _float(judgment.get("llm_risk_score", 0))
    reviews = [
        {
            "experiment_id": experiment_id,
            "role": "supporter",
            "position": "support" if scientific_value >= 0.45 else "weak_support",
            "score": round(scientific_value, 3),
            "rationale": "prioritize information gain and hypothesis discrimination",
        },
        {
            "experiment_id": experiment_id,
            "role": "skeptic",
            "position": "object" if risk >= 0.55 else "no_blocking_objection",
            "score": round(1.0 - risk, 3),
            "rationale": "inspect repeated failures, confounders, and unsafe shortcuts",
        },
        {
            "experiment_id": experiment_id,
            "role": "methodologist",
            "position": "requires_protocol" if not candidate.get("quality_gates") else "protocol_present",
            "score": 0.8 if candidate.get("quality_gates") else 0.35,
            "rationale": "check controls, quality gates, and handoff readiness",
        },
        {
            "experiment_id": experiment_id,
            "role": "chair",
            "position": "schedule" if judgment.get("recommended_action") == "schedule" else "hold",
            "score": round((scientific_value + mechanism_value + (1.0 - risk)) / 3.0, 3),
            "rationale": "balance scientific value, mechanism discrimination, and risk",
        },
    ]
    return reviews


def _judge_calibration_record(judgments: list[dict[str, Any]]) -> dict[str, Any]:
    if not judgments:
        return {"state": "empty", "prediction_count": 0}
    schedule_count = len([item for item in judgments if item.get("recommended_action") == "schedule"])
    block_count = len([item for item in judgments if item.get("recommended_action") == "block"])
    avg_value = sum(_float(item.get("llm_scientific_value_score", 0)) for item in judgments) / max(1, len(judgments))
    avg_risk = sum(_float(item.get("llm_risk_score", 0)) for item in judgments) / max(1, len(judgments))
    return {
        "state": "awaiting_outcome_feedback",
        "prediction_count": len(judgments),
        "schedule_count": schedule_count,
        "block_count": block_count,
        "average_scientific_value_score": round(avg_value, 3),
        "average_risk_score": round(avg_risk, 3),
        "future_update_rule": "compare recommended_action and risk score against executor outcomes and failed attempts",
    }


def _candidate_shortlist(scheduler_summary: dict[str, Any], *, max_candidates: int) -> list[dict[str, Any]]:
    candidates = [
        item
        for item in scheduler_summary.get("candidate_experiments", [])
        if isinstance(item, dict)
    ]
    candidates.sort(
        key=lambda item: (
            str(item.get("gate_state", "")) == "ready_to_schedule",
            _float(item.get("selection_score", item.get("portfolio_score", 0))),
        ),
        reverse=True,
    )
    risky = [
        item
        for item in candidates
        if _float(item.get("risk_score", 0)) + _float(item.get("validator_penalty", 0)) >= 2.0
        or str(item.get("gate_state", "")) in {"blocked", "needs_human_approval"}
    ]
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in candidates[:max_candidates] + risky[:4]:
        experiment_id = str(item.get("experiment_id", "")).strip()
        if not experiment_id or experiment_id in seen:
            continue
        seen.add(experiment_id)
        selected.append(_compact_candidate(item))
    return selected[:max_candidates]


def _compact_candidate(item: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "experiment_id",
        "title",
        "experiment_type",
        "target_ids",
        "objective",
        "information_gain_score",
        "discrimination_score",
        "cost_score",
        "time_score",
        "risk_score",
        "repeat_failure_risk",
        "validator_penalty",
        "portfolio_score",
        "selection_score",
        "gate_state",
        "gate_reasons",
        "quality_gates",
        "scheduler_rules",
        "acquisition_function",
        "search_space",
    ]
    return {key: item.get(key) for key in keys if key in item}


def _attach_judgment(
    item: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    blocked_ids: set[str],
    adjustment_weight: float,
) -> dict[str, Any]:
    experiment_id = str(item.get("experiment_id", "")).strip()
    judgment = by_id.get(experiment_id, {})
    adjustment = _float(judgment.get("score_adjustment", 0)) * adjustment_weight
    base_score = _float(item.get("selection_score", item.get("portfolio_score", 0)))
    updated = dict(item)
    updated["llm_judgment"] = judgment
    updated["llm_scientific_value_score"] = judgment.get("llm_scientific_value_score", 0)
    updated["llm_mechanism_discrimination_score"] = judgment.get("llm_mechanism_discrimination_score", 0)
    updated["llm_risk_score"] = judgment.get("llm_risk_score", 0)
    updated["llm_score_adjustment"] = round(adjustment, 3)
    updated["llm_recommended_action"] = (
        "block"
        if experiment_id in blocked_ids
        else str(judgment.get("recommended_action", "schedule")).strip() or "schedule"
    )
    updated["llm_rationale"] = str(judgment.get("rationale", "")).strip()
    updated["llm_risk_flags"] = judgment.get("risk_flags", []) if isinstance(judgment.get("risk_flags", []), list) else []
    updated["judge_adjusted_selection_score"] = round(base_score + adjustment, 3)
    return updated


def _parse_judge_json(text: str) -> dict[str, Any]:
    stripped = str(text).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("scheduler judge did not return JSON")
    data = json.loads(stripped[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("scheduler judge JSON must be an object")
    return data


def _heuristic_rationale(
    candidate: dict[str, Any],
    scientific_value: float,
    mechanism_value: float,
    risk_score: float,
    numeric: float,
) -> str:
    parts = [
        f"numeric={round(numeric, 3)}",
        f"scientific_value={round(scientific_value, 3)}",
        f"mechanism_discrimination={round(mechanism_value, 3)}",
        f"risk={round(risk_score, 3)}",
    ]
    if candidate.get("search_space"):
        parts.append("parameter search requires frozen validation protocol")
    if candidate.get("gate_reasons"):
        parts.append("gate reasons: " + "; ".join(_strings(candidate.get("gate_reasons", []))[:3]))
    return "; ".join(parts)


def _missing_information(candidate: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not candidate.get("quality_gates"):
        missing.append("quality gates")
    if candidate.get("search_space") and "confirmatory_rule" not in candidate.get("search_space", {}):
        missing.append("confirmatory validation rule")
    if not candidate.get("target_ids"):
        missing.append("target hypothesis or uncertainty id")
    return missing[:6]


def _compact_items(value: Any, *, limit: int) -> list[Any]:
    if not isinstance(value, list):
        return []
    compact: list[Any] = []
    for item in value[:limit]:
        if isinstance(item, dict):
            compact.append({key: item.get(key) for key in list(item.keys())[:8]})
        else:
            compact.append(str(item)[:300])
    return compact


def _strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys([str(item).strip() for item in values if str(item).strip()]))


def _float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


