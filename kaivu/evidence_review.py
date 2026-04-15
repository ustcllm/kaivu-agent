from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class EvidenceReviewAssessment:
    review_id: str
    review_question: str
    review_readiness: str
    protocol_completeness_score: float
    screening_quality_score: float
    evidence_grade_balance: dict[str, int] = field(default_factory=dict)
    bias_risk_summary: dict[str, Any] = field(default_factory=dict)
    conflict_resolution_state: str = "none"
    review_blockers: list[str] = field(default_factory=list)
    recommended_review_actions: list[str] = field(default_factory=list)
    evidence_claim_links: list[dict[str, str]] = field(default_factory=list)
    assessment_records: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_evidence_review_summary(
    *,
    topic: str,
    project_id: str = "",
    literature_synthesis: dict[str, Any],
    systematic_review_summary: dict[str, Any],
    literature_quality_summary: dict[str, Any],
    conflict_attribution: dict[str, Any],
    formal_review_record_summary: dict[str, Any],
    claim_graph: dict[str, Any],
) -> dict[str, Any]:
    review_question = (
        str(systematic_review_summary.get("review_question", "")).strip()
        or str(literature_synthesis.get("review_question", "")).strip()
        or topic
    )
    review_id = f"evidence-review::{_slugify(project_id or 'workspace')}::{_slugify(topic)}"
    protocol_score, protocol_missing = _score_protocol(systematic_review_summary)
    screening_score, screening_missing = _score_screening(
        systematic_review_summary=systematic_review_summary,
        formal_review_record_summary=formal_review_record_summary,
        claim_graph=claim_graph,
    )
    evidence_grade_balance = _grade_balance(
        claim_graph=claim_graph,
        literature_quality_summary=literature_quality_summary,
    )
    bias_risk_summary = _bias_risk_summary(
        claim_graph=claim_graph,
        systematic_review_summary=systematic_review_summary,
    )
    conflict_state = _conflict_resolution_state(
        conflict_attribution=conflict_attribution,
        systematic_review_summary=systematic_review_summary,
        literature_synthesis=literature_synthesis,
    )
    evidence_claim_links = _evidence_claim_links(claim_graph)
    assessment_records = _assessment_records(claim_graph)
    review_blockers = _review_blockers(
        protocol_missing=protocol_missing,
        screening_missing=screening_missing,
        bias_risk_summary=bias_risk_summary,
        conflict_state=conflict_state,
        evidence_grade_balance=evidence_grade_balance,
    )
    readiness = _readiness(
        protocol_score=protocol_score,
        screening_score=screening_score,
        evidence_grade_balance=evidence_grade_balance,
        bias_risk_summary=bias_risk_summary,
        conflict_state=conflict_state,
        blockers=review_blockers,
    )
    actions = _recommended_actions(
        readiness=readiness,
        protocol_missing=protocol_missing,
        screening_missing=screening_missing,
        bias_risk_summary=bias_risk_summary,
        conflict_state=conflict_state,
        evidence_grade_balance=evidence_grade_balance,
    )
    assessment = EvidenceReviewAssessment(
        review_id=review_id,
        review_question=review_question,
        review_readiness=readiness,
        protocol_completeness_score=protocol_score,
        screening_quality_score=screening_score,
        evidence_grade_balance=evidence_grade_balance,
        bias_risk_summary=bias_risk_summary,
        conflict_resolution_state=conflict_state,
        review_blockers=review_blockers,
        recommended_review_actions=actions,
        evidence_claim_links=evidence_claim_links,
        assessment_records=assessment_records,
    )
    high_or_moderate = evidence_grade_balance.get("high", 0) + evidence_grade_balance.get("moderate", 0)
    return {
        **assessment.to_dict(),
        "project_id": project_id,
        "topic": topic,
        "evidence_count": len(_evidence_items(claim_graph)),
        "linked_evidence_count": len(evidence_claim_links),
        "high_or_moderate_evidence_count": high_or_moderate,
        "needs_human_adjudication": conflict_state == "adjudication_needed"
        or bool(bias_risk_summary.get("high_risk_count", 0)),
        "review_quality_state": _quality_state(
            readiness=readiness,
            protocol_score=protocol_score,
            screening_score=screening_score,
            bias_risk_summary=bias_risk_summary,
        ),
    }


def _score_protocol(systematic_review_summary: dict[str, Any]) -> tuple[float, list[str]]:
    checks = [
        ("review_question", bool(str(systematic_review_summary.get("review_question", "")).strip())),
        ("review_protocol_version", bool(str(systematic_review_summary.get("review_protocol_version", "")).strip())),
        ("inclusion_logic", bool(systematic_review_summary.get("inclusion_logic"))),
        ("exclusion_logic", bool(systematic_review_summary.get("exclusion_logic"))),
        ("evidence_table_focus", bool(systematic_review_summary.get("evidence_table_focus"))),
        ("bias_hotspot_tracking", "bias_hotspots" in systematic_review_summary),
    ]
    missing = [name for name, ok in checks if not ok]
    explicit_gaps = [
        str(item).strip()
        for item in systematic_review_summary.get("review_protocol_gaps", [])
        if str(item).strip()
    ] if isinstance(systematic_review_summary.get("review_protocol_gaps", []), list) else []
    missing.extend([f"protocol_gap:{item}" for item in explicit_gaps[:5]])
    score = sum(1 for _, ok in checks if ok) / max(1, len(checks))
    if explicit_gaps:
        score = max(0.0, score - min(0.3, 0.08 * len(explicit_gaps)))
    return round(score, 3), missing[:12]


def _score_screening(
    *,
    systematic_review_summary: dict[str, Any],
    formal_review_record_summary: dict[str, Any],
    claim_graph: dict[str, Any],
) -> tuple[float, list[str]]:
    screened = _safe_int(systematic_review_summary.get("screened_evidence_count", 0))
    evidence_count = len(_evidence_items(claim_graph))
    screening_records = _safe_int(formal_review_record_summary.get("screening_record_count", 0))
    evidence_table_records = _safe_int(formal_review_record_summary.get("evidence_table_record_count", 0))
    exclusion_reasons = _safe_int(formal_review_record_summary.get("exclusion_reason_count", 0))
    checks = [
        ("screened_evidence_count", screened > 0 or evidence_count > 0),
        ("screening_records", screening_records > 0 or bool(systematic_review_summary.get("screening_decisions"))),
        ("evidence_table_records", evidence_table_records > 0 or bool(systematic_review_summary.get("evidence_table_records"))),
        ("exclusion_reasons", exclusion_reasons > 0 or bool(systematic_review_summary.get("exclusion_reasons"))),
        ("claim_evidence_links", bool(_evidence_claim_links(claim_graph))),
    ]
    missing = [name for name, ok in checks if not ok]
    score = sum(1 for _, ok in checks if ok) / max(1, len(checks))
    if screened < max(3, min(8, evidence_count)) and evidence_count >= 3:
        missing.append("screened_evidence_count_below_claim_graph_evidence")
        score = max(0.0, score - 0.15)
    return round(score, 3), missing[:12]


def _grade_balance(*, claim_graph: dict[str, Any], literature_quality_summary: dict[str, Any]) -> dict[str, int]:
    counts = {"high": 0, "moderate": 0, "low": 0, "unclear": 0}
    for evidence in _evidence_items(claim_graph):
        grade = str(evidence.get("quality_grade", "")).strip().lower() or "unclear"
        if grade not in counts:
            grade = "unclear"
        counts[grade] += 1
    quality_counts = (
        literature_quality_summary.get("counts", {})
        if isinstance(literature_quality_summary.get("counts", {}), dict)
        else literature_quality_summary
    )
    for key, value in quality_counts.items() if isinstance(quality_counts, dict) else []:
        grade = str(key).strip().lower()
        if grade in counts and counts[grade] == 0:
            counts[grade] = _safe_int(value)
    return counts


def _bias_risk_summary(*, claim_graph: dict[str, Any], systematic_review_summary: dict[str, Any]) -> dict[str, Any]:
    counts = {"high": 0, "moderate": 0, "low": 0, "unclear": 0}
    hotspots = [
        str(item).strip()
        for item in systematic_review_summary.get("bias_hotspots", [])
        if str(item).strip()
    ] if isinstance(systematic_review_summary.get("bias_hotspots", []), list) else []
    for evidence in _evidence_items(claim_graph):
        risk = str(evidence.get("bias_risk", "")).strip().lower() or "unclear"
        if risk not in counts:
            risk = "unclear"
        counts[risk] += 1
    return {
        "risk_counts": counts,
        "high_risk_count": counts["high"],
        "moderate_or_high_risk_count": counts["high"] + counts["moderate"],
        "bias_hotspots": hotspots[:12],
        "has_bias_hotspots": bool(hotspots),
    }


def _conflict_resolution_state(
    *,
    conflict_attribution: dict[str, Any],
    systematic_review_summary: dict[str, Any],
    literature_synthesis: dict[str, Any],
) -> str:
    conflict_count = _safe_int(conflict_attribution.get("conflict_group_count", 0))
    directional_count = _safe_int(conflict_attribution.get("directional_conflict_count", 0))
    contested = literature_synthesis.get("contested_questions", [])
    evidence_balance = systematic_review_summary.get("evidence_balance", [])
    if conflict_count == 0 and directional_count == 0 and not contested:
        return "none"
    if conflict_count > 0 and not evidence_balance:
        return "unresolved"
    if directional_count > 0 or len(contested if isinstance(contested, list) else []) >= 2:
        return "adjudication_needed"
    return "mapped"


def _review_blockers(
    *,
    protocol_missing: list[str],
    screening_missing: list[str],
    bias_risk_summary: dict[str, Any],
    conflict_state: str,
    evidence_grade_balance: dict[str, int],
) -> list[str]:
    blockers: list[str] = []
    if protocol_missing:
        blockers.append("Review protocol is incomplete.")
    if screening_missing:
        blockers.append("Screening and evidence table records are incomplete.")
    if bias_risk_summary.get("high_risk_count", 0):
        blockers.append("High bias-risk evidence requires adjudication before decision use.")
    if conflict_state in {"unresolved", "adjudication_needed"}:
        blockers.append("Evidence conflicts need resolution or explicit attribution.")
    if not any(evidence_grade_balance.values()):
        blockers.append("No evidence has been graded yet.")
    return blockers[:10]


def _recommended_actions(
    *,
    readiness: str,
    protocol_missing: list[str],
    screening_missing: list[str],
    bias_risk_summary: dict[str, Any],
    conflict_state: str,
    evidence_grade_balance: dict[str, int],
) -> list[str]:
    actions: list[str] = []
    if protocol_missing:
        actions.append("Complete review protocol fields before treating synthesis as decision-grade.")
    if screening_missing:
        actions.append("Create explicit screening records, exclusion reasons, and evidence table rows.")
    if not any(evidence_grade_balance.values()):
        actions.append("Grade evidence quality for each cited source or claim.")
    if bias_risk_summary.get("has_bias_hotspots"):
        actions.append("Assign bias hotspots to mitigation notes or downgrade affected evidence.")
    if conflict_state in {"unresolved", "adjudication_needed"}:
        actions.append("Run conflict attribution and record why sources disagree.")
    if readiness in {"analysis_ready", "decision_ready"}:
        actions.append("Use this review to prioritize discriminative hypotheses and experiments.")
    return list(dict.fromkeys(actions))[:10]


def _readiness(
    *,
    protocol_score: float,
    screening_score: float,
    evidence_grade_balance: dict[str, int],
    bias_risk_summary: dict[str, Any],
    conflict_state: str,
    blockers: list[str],
) -> str:
    graded = sum(evidence_grade_balance.values())
    high_or_moderate = evidence_grade_balance.get("high", 0) + evidence_grade_balance.get("moderate", 0)
    if protocol_score >= 0.75 and screening_score >= 0.7 and high_or_moderate > 0:
        if not blockers or (
            bias_risk_summary.get("high_risk_count", 0) == 0
            and conflict_state in {"none", "mapped"}
        ):
            return "decision_ready"
        return "analysis_ready"
    if protocol_score >= 0.6 and (screening_score >= 0.4 or graded > 0):
        return "analysis_ready"
    if protocol_score >= 0.5:
        return "screening_ready"
    return "draft"


def _quality_state(
    *,
    readiness: str,
    protocol_score: float,
    screening_score: float,
    bias_risk_summary: dict[str, Any],
) -> str:
    if readiness == "decision_ready":
        return "decision_grade"
    if readiness == "analysis_ready" and bias_risk_summary.get("high_risk_count", 0) == 0:
        return "analysis_grade"
    if protocol_score < 0.5 or screening_score < 0.4:
        return "record_building"
    return "needs_review"


def _evidence_claim_links(claim_graph: dict[str, Any]) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for edge in claim_graph.get("edges", []) if isinstance(claim_graph.get("edges", []), list) else []:
        if not isinstance(edge, dict):
            continue
        relation = str(edge.get("relation", "")).strip()
        if relation not in {"supported_by", "supports"}:
            continue
        source = str(edge.get("source", "")).strip()
        target = str(edge.get("target", "")).strip()
        if not source or not target:
            continue
        if relation == "supported_by":
            links.append({"claim_id": source, "evidence_id": target, "relation": "supports"})
        else:
            links.append({"claim_id": target, "evidence_id": source, "relation": "supports"})
    if links:
        return _dedupe_links(links)[:100]
    for claim in claim_graph.get("claims", []) if isinstance(claim_graph.get("claims", []), list) else []:
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("global_claim_id", "") or claim.get("claim_id", "")).strip()
        for evidence_id in claim.get("supports", []) if isinstance(claim.get("supports", []), list) else []:
            evidence_text = str(evidence_id).strip()
            if claim_id and evidence_text:
                links.append({"claim_id": claim_id, "evidence_id": evidence_text, "relation": "supports"})
    return _dedupe_links(links)[:100]


def _assessment_records(claim_graph: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for evidence in _evidence_items(claim_graph):
        evidence_id = str(evidence.get("global_evidence_id", "") or evidence.get("evidence_id", "")).strip()
        if not evidence_id:
            continue
        records.append(
            {
                "evidence_id": evidence_id,
                "quality_grade": str(evidence.get("quality_grade", "unclear")).strip() or "unclear",
                "bias_risk": str(evidence.get("bias_risk", "unclear")).strip() or "unclear",
                "evidence_direction": str(evidence.get("evidence_direction", "contextual")).strip() or "contextual",
                "source_ref": str(evidence.get("source_ref", "")).strip(),
            }
        )
    return records[:100]


def _evidence_items(claim_graph: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in claim_graph.get("evidence", [])
        if isinstance(item, dict)
    ] if isinstance(claim_graph.get("evidence", []), list) else []


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _dedupe_links(links: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str]] = set()
    output: list[dict[str, str]] = []
    for link in links:
        key = (
            str(link.get("claim_id", "")).strip(),
            str(link.get("evidence_id", "")).strip(),
            str(link.get("relation", "")).strip(),
        )
        if not all(key) or key in seen:
            continue
        seen.add(key)
        output.append(link)
    return output


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "review"


