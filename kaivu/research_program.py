from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .action_approval import evaluate_scientific_action


SCIENTIFIC_ID_PREFIXES = {
    "program",
    "claim",
    "evidence",
    "hypothesis",
    "experiment",
    "artifact",
    "memory",
    "decision",
    "meeting",
    "report",
}


@dataclass(slots=True)
class ResearchProgram:
    program_id: str
    topic: str
    project_id: str = ""
    status: str = "active"
    objective_contract: dict[str, Any] = field(default_factory=dict)
    hypothesis_lifecycle: dict[str, Any] = field(default_factory=dict)
    evidence_map: dict[str, Any] = field(default_factory=dict)
    resource_economics: dict[str, Any] = field(default_factory=dict)
    autonomy_policy: dict[str, Any] = field(default_factory=dict)
    provenance_policy: dict[str, Any] = field(default_factory=dict)
    meeting_governance: dict[str, Any] = field(default_factory=dict)
    evaluation_contract: dict[str, Any] = field(default_factory=dict)
    failed_attempt_recall: dict[str, Any] = field(default_factory=dict)
    experiment_portfolio: dict[str, Any] = field(default_factory=dict)
    report_release_policy: dict[str, Any] = field(default_factory=dict)
    control_actions: list[dict[str, Any]] = field(default_factory=list)
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ResearchActionPolicy:
    policy_id: str
    autonomy_level: str
    action: str
    decision: str
    required_review: str = ""
    reasons: list[str] = field(default_factory=list)
    audit_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ResearchProgramRegistry:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save_program(self, program: ResearchProgram) -> Path:
        return self._save("programs", program.program_id, program.to_dict())

    def save_meeting_record(self, record: dict[str, Any]) -> Path:
        identifier = str(record.get("meeting_id", "")).strip() or "meeting"
        return self._save("meetings", identifier, record)

    def load_programs(self, *, project_id: str = "", topic: str = "") -> list[dict[str, Any]]:
        return self._load_filtered("programs", project_id=project_id, topic=topic)

    def latest_program(self, *, project_id: str = "", topic: str = "") -> dict[str, Any] | None:
        items = self.load_programs(project_id=project_id, topic=topic)
        return items[-1] if items else None

    def _save(self, collection: str, identifier: str, payload: dict[str, Any]) -> Path:
        directory = self.root / collection
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{_slugify(identifier)}.json"
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    def _load_filtered(self, collection: str, *, project_id: str = "", topic: str = "") -> list[dict[str, Any]]:
        directory = self.root / collection
        if not directory.exists():
            return []
        items: list[dict[str, Any]] = []
        for path in sorted(directory.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            if project_id and str(payload.get("project_id", "")).strip() != project_id:
                continue
            if topic and str(payload.get("topic", "")).strip() != topic:
                continue
            items.append(payload)
        return items


def normalize_scientific_id(kind: str, label: str, *, project_id: str = "", topic: str = "") -> str:
    kind = str(kind).strip().lower().replace("_", "-") or "object"
    if kind not in SCIENTIFIC_ID_PREFIXES:
        kind = "object"
    parts = [kind, project_id or "workspace", topic, label]
    raw = "::".join(str(item).strip() for item in parts if str(item).strip())
    slug = _slugify(raw)
    return f"{kind}::{slug}"


def decide_research_action_policy(
    *,
    action: str,
    autonomy_level: str = "L1",
    risk_level: str = "medium",
    target_scope: str = "project",
) -> dict[str, Any]:
    action = str(action).strip() or "unknown_action"
    level = str(autonomy_level).strip().upper() or "L1"
    risk = str(risk_level).strip().lower() or "medium"
    scope = str(target_scope).strip().lower() or "project"
    reasons: list[str] = []
    decision = "allow"
    required_review = ""

    if level == "L0":
        decision = "deny"
        reasons.append("L0 only allows answering without state mutation")
    elif level == "L1" and action in {"write_memory", "write_graph", "execute_experiment", "publish_report", "retire_hypothesis"}:
        decision = "draft_only"
        required_review = "human_confirmation"
        reasons.append("L1 can suggest but should not mutate durable research state")
    elif level == "L2" and action in {"write_memory", "write_graph"}:
        decision = "review_required"
        required_review = "digest_confirmation"
        reasons.append("L2 can prepare durable updates but needs confirmation")
    elif level == "L3" and action == "execute_experiment":
        decision = "review_required"
        required_review = "execution_approval"
        reasons.append("L3 allows low-risk memory promotion but not autonomous execution")
    elif level == "L4" and action == "publish_report":
        decision = "review_required"
        required_review = "release_gate"
        reasons.append("L4 may run computational work but cannot publish conclusions without review")
    elif action == "retire_hypothesis" and level != "L5":
        decision = "review_required"
        required_review = "lab_meeting_or_owner_review"
        reasons.append("major hypothesis retirement requires explicit review below L5")

    if risk == "high" and decision == "allow":
        decision = "review_required"
        required_review = required_review or "high_risk_review"
        reasons.append("high-risk action requires review")
    if scope in {"group", "public"} and action in {"write_memory", "publish_report"} and decision == "allow":
        decision = "review_required"
        required_review = required_review or "scope_promotion_review"
        reasons.append("broader-scope state changes require review")

    if not reasons:
        reasons.append("action is permitted by current autonomy level and risk policy")
    return ResearchActionPolicy(
        policy_id=normalize_scientific_id("decision", f"{level}-{action}-{scope}"),
        autonomy_level=level,
        action=action,
        decision=decision,
        required_review=required_review,
        reasons=reasons[:8],
        audit_required=True,
    ).to_dict()


def build_research_program_from_state(
    *,
    topic: str,
    project_id: str = "",
    research_state: dict[str, Any],
    claim_graph: dict[str, Any],
    run_manifest: dict[str, Any],
) -> dict[str, Any]:
    operating = research_state.get("research_operating_system_summary", {})
    if not isinstance(operating, dict):
        operating = {}
    evidence_map = build_queryable_evidence_map(claim_graph=claim_graph, research_state=research_state)
    rival_reasoning = build_rival_hypothesis_reasoning(
        claim_graph=claim_graph,
        hypothesis_lifecycle=operating.get("hypothesis_lifecycle", {}),
    )
    failed_recall = build_failed_attempt_recall(
        topic=topic,
        claim_graph=claim_graph,
        scheduler_summary=research_state.get("experiment_execution_loop_summary", {}),
    )
    portfolio = select_experiment_portfolio(
        experiment_execution_loop_summary=research_state.get("experiment_execution_loop_summary", {}),
        value_of_information_summary=research_state.get("value_of_information_summary", {}),
    )
    autonomy_policy = build_autonomy_execution_policy(
        autonomy_control=operating.get("autonomy_control", {}),
        literature_ingest_policy=research_state.get("literature_ingest_policy_summary", {}),
        risk_permission_summary=research_state.get("experiment_risk_permission_summary", {}),
    )
    meeting_record = build_formal_meeting_record(
        topic=topic,
        project_id=project_id,
        lab_meeting_governance=operating.get("lab_meeting_governance", {}),
        claim_graph=claim_graph,
    )
    report_policy = classify_report_release_level(
        release_gate_summary=research_state.get("scientific_release_gate_summary", {}),
        evaluation_summary=operating.get("capability_evaluation", {}),
        provenance_policy=operating.get("provenance_source_policy", {}),
    )
    action_policies = build_research_action_policy_matrix(
        autonomy_policy=autonomy_policy,
        report_release_policy=report_policy,
    )
    program = ResearchProgram(
        program_id=normalize_scientific_id("program", topic, project_id=project_id, topic=topic),
        topic=topic,
        project_id=project_id,
        status=str(operating.get("operating_state", "active")),
        objective_contract=operating.get("objective_contract", {}),
        hypothesis_lifecycle=operating.get("hypothesis_lifecycle", {}),
        evidence_map=evidence_map,
        resource_economics=operating.get("resource_economics", {}),
        autonomy_policy=autonomy_policy,
        provenance_policy=operating.get("provenance_source_policy", {}),
        meeting_governance=meeting_record,
        evaluation_contract=operating.get("capability_evaluation", {}),
        failed_attempt_recall=failed_recall,
        experiment_portfolio=portfolio,
        report_release_policy=report_policy,
        control_actions=[
            *(
                operating.get("control_actions", [])
                if isinstance(operating.get("control_actions", []), list)
                else []
            ),
            {
                "action": "enforce_research_action_policy",
                "severity": "high" if any(item.get("decision") in {"deny", "review_required"} for item in action_policies) else "low",
                "reasons": [f"{item.get('action')}={item.get('decision')}" for item in action_policies],
            },
        ],
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    return {
        **program.to_dict(),
        "research_action_policy_matrix": action_policies,
        "rival_hypothesis_reasoning": rival_reasoning,
        "run_manifest_summary": {
            "artifact_count": len(run_manifest.get("artifacts", [])) if isinstance(run_manifest.get("artifacts", []), list) else 0,
            "tool_count": len(run_manifest.get("tools_used", [])) if isinstance(run_manifest.get("tools_used", []), list) else 0,
            "model_count": len(run_manifest.get("models_used", [])) if isinstance(run_manifest.get("models_used", []), list) else 0,
        },
    }


def build_queryable_evidence_map(*, claim_graph: dict[str, Any], research_state: dict[str, Any]) -> dict[str, Any]:
    claims = _items(claim_graph.get("claims", []))
    evidence = _items(claim_graph.get("evidence", []))
    edges = _items(claim_graph.get("edges", []))
    evidence_by_id = {
        _record_id(item, "evidence"): item
        for item in evidence
        if _record_id(item, "evidence")
    }
    claim_records: list[dict[str, Any]] = []
    for claim in claims:
        claim_id = _record_id(claim, "claim")
        supporting = _linked_evidence_ids(claim_id, claim, edges, relations={"supports", "supported_by"})
        refuting = _linked_evidence_ids(claim_id, claim, edges, relations={"refutes", "contradicts", "against"})
        qualities = [
            str(evidence_by_id.get(item, {}).get("quality_grade", "unclear")).strip().lower() or "unclear"
            for item in supporting + refuting
        ]
        conditions = _dedupe(
            _strings(claim.get("conditions", []))
            + _strings(claim.get("boundary_conditions", []))
            + [
                text
                for evidence_id in supporting + refuting
                for text in _strings(evidence_by_id.get(evidence_id, {}).get("conditions", []))
            ]
        )
        evidence_types = _dedupe(
            [
                str(evidence_by_id.get(evidence_id, {}).get("evidence_type", "")).strip()
                or str(evidence_by_id.get(evidence_id, {}).get("source_type", "")).strip()
                or "unspecified"
                for evidence_id in supporting + refuting
            ]
        )
        claim_records.append(
            {
                "claim_id": claim_id,
                "statement": str(claim.get("statement", "") or claim.get("claim", "")).strip(),
                "supporting_evidence_ids": supporting,
                "refuting_evidence_ids": refuting,
                "quality_grades": qualities,
                "conditions": conditions[:12],
                "evidence_types": evidence_types[:8],
                "extrapolation_risk": _extrapolation_risk(conditions=conditions, evidence_types=evidence_types, qualities=qualities),
                "evidence_state": _claim_evidence_state(supporting, refuting, qualities),
            }
        )
    return {
        "map_id": normalize_scientific_id("evidence", "map", topic=str(research_state.get("topic", ""))),
        "claim_count": len(claim_records),
        "evidence_count": len(evidence),
        "unsupported_claim_ids": [item["claim_id"] for item in claim_records if item["evidence_state"] == "unsupported"],
        "contested_claim_ids": [item["claim_id"] for item in claim_records if item["evidence_state"] == "contested"],
        "decision_grade_claim_ids": [item["claim_id"] for item in claim_records if item["evidence_state"] == "decision_grade"],
        "claim_records": claim_records[:200],
        "query_examples": [
            "unsupported_claim_ids",
            "contested_claim_ids",
            "decision_grade_claim_ids",
            "claim_records[claim_id].supporting_evidence_ids",
        ],
    }


def query_evidence_map(evidence_map: dict[str, Any], *, claim_id: str = "", state: str = "") -> list[dict[str, Any]]:
    records = _items(evidence_map.get("claim_records", []))
    if claim_id:
        records = [item for item in records if str(item.get("claim_id", "")).strip() == claim_id]
    if state:
        records = [item for item in records if str(item.get("evidence_state", "")).strip() == state]
    return records


def apply_hypothesis_lifecycle_transition(
    hypothesis_record: dict[str, Any],
    *,
    transition: str,
    reason: str = "",
    actor: str = "system",
) -> dict[str, Any]:
    allowed = {
        "validate": "under_validation",
        "advance": "ready_for_discriminative_test",
        "revise": "needs_revision",
        "revise_or_retire": "challenged",
        "retire": "retired",
        "merge": "merged",
        "pause": "paused",
    }
    next_state = allowed.get(transition)
    if next_state is None:
        return {**hypothesis_record, "transition_applied": False, "transition_error": f"unsupported transition: {transition}"}
    history = _items(hypothesis_record.get("transition_history", []))
    history.append(
        {
            "transition": transition,
            "from_state": str(hypothesis_record.get("lifecycle_state", "")),
            "to_state": next_state,
            "reason": reason,
            "actor": actor,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
    return {
        **hypothesis_record,
        "lifecycle_state": next_state,
        "recommended_transition": "observe",
        "transition_history": history,
        "transition_applied": True,
    }


def build_rival_hypothesis_reasoning(*, claim_graph: dict[str, Any], hypothesis_lifecycle: dict[str, Any]) -> dict[str, Any]:
    hypotheses = _items(claim_graph.get("hypotheses", []))
    relations = _items(claim_graph.get("hypothesis_relations", [])) + _items(claim_graph.get("edges", []))
    pairs: list[dict[str, Any]] = []
    for relation in relations:
        relation_name = str(relation.get("relation", "")).strip().lower()
        if relation_name not in {"competes_with", "contradicts", "rival_of", "alternative_to", "refutes"}:
            continue
        source = str(relation.get("source", "") or relation.get("source_hypothesis_id", "")).strip()
        target = str(relation.get("target", "") or relation.get("target_hypothesis_id", "")).strip()
        if source and target:
            pairs.append(_rival_pair(source, target, relation_name))
    if not pairs and len(hypotheses) >= 2:
        for left, right in zip(hypotheses, hypotheses[1:]):
            left_id = _record_id(left, "hypothesis")
            right_id = _record_id(right, "hypothesis")
            if left_id and right_id:
                pairs.append(_rival_pair(left_id, right_id, "implicit_competition"))
    lifecycle_records = _items(hypothesis_lifecycle.get("records", []))
    challenged = {
        str(item.get("hypothesis_id", "")).strip()
        for item in lifecycle_records
        if str(item.get("lifecycle_state", "")).strip() == "challenged"
    }
    for pair in pairs:
        pair["priority"] = "high" if pair["hypothesis_a_id"] in challenged or pair["hypothesis_b_id"] in challenged else "medium"
        pair["scheduler_hint"] = "choose experiments that make opposite predictions for the rival pair"
    return {
        "rival_pair_count": len(pairs),
        "high_priority_pair_count": len([item for item in pairs if item.get("priority") == "high"]),
        "pairs": pairs[:100],
        "reasoning_state": "active" if pairs else "needs_rival_hypotheses",
    }


def build_research_action_policy_matrix(*, autonomy_policy: dict[str, Any], report_release_policy: dict[str, Any]) -> list[dict[str, Any]]:
    level = str(autonomy_policy.get("autonomy_level", "L1")).strip() or "L1"
    report_level = str(report_release_policy.get("release_level", "private_notes"))
    publish_risk = "low" if report_level == "external_publishable" else "high"
    return [
        evaluate_scientific_action(action="write_memory", autonomy_level=level, risk_level="medium", target_scope="project"),
        evaluate_scientific_action(action="write_graph", autonomy_level=level, risk_level="medium", target_scope="project"),
        evaluate_scientific_action(action="execute_experiment", autonomy_level=level, risk_level="high", target_scope="project"),
        evaluate_scientific_action(action="retire_hypothesis", autonomy_level=level, risk_level="high", target_scope="project"),
        evaluate_scientific_action(action="publish_report", autonomy_level=level, risk_level=publish_risk, target_scope="group"),
    ]


def select_experiment_portfolio(
    *,
    experiment_execution_loop_summary: dict[str, Any],
    value_of_information_summary: dict[str, Any],
    max_cost: float = 5.0,
    max_risk: float = 4.0,
    max_items: int = 5,
) -> dict[str, Any]:
    candidates = _items(experiment_execution_loop_summary.get("candidate_experiments", []))
    voi_by_id = {
        str(item.get("experiment_id", "")).strip(): _float(item.get("value_of_information", 0))
        for item in _items(value_of_information_summary.get("items", []))
    }
    scored = []
    for item in candidates:
        experiment_id = str(item.get("experiment_id", "")).strip()
        cost = _float(item.get("cost_score", item.get("estimated_cost", 0))) + _float(item.get("time_score", 0))
        risk = _float(item.get("risk_score", 0)) + _float(item.get("validator_penalty", 0))
        value = voi_by_id.get(experiment_id, _float(item.get("selection_score", item.get("portfolio_score", 0))))
        score = round(value - 0.35 * cost - 0.45 * risk, 3)
        scored.append({**item, "portfolio_value": value, "portfolio_cost": cost, "portfolio_risk": risk, "portfolio_selection_score": score})
    scored.sort(key=lambda item: float(item.get("portfolio_selection_score", 0)), reverse=True)
    selected = []
    cost_used = 0.0
    risk_used = 0.0
    for item in scored:
        next_cost = cost_used + _float(item.get("portfolio_cost", 0))
        next_risk = risk_used + _float(item.get("portfolio_risk", 0))
        if next_cost <= max_cost and next_risk <= max_risk and len(selected) < max_items:
            selected.append(item)
            cost_used = next_cost
            risk_used = next_risk
    return {
        "portfolio_state": "ready" if selected else "needs_candidates",
        "selected_count": len(selected),
        "total_cost": round(cost_used, 3),
        "total_risk": round(risk_used, 3),
        "budget": {"max_cost": max_cost, "max_risk": max_risk, "max_items": max_items},
        "selected_experiments": selected,
        "rejected_high_cost_ids": [
            str(item.get("experiment_id", ""))
            for item in scored
            if _float(item.get("portfolio_cost", 0)) > max_cost or _float(item.get("portfolio_risk", 0)) > max_risk
        ][:20],
    }


def build_autonomy_execution_policy(
    *,
    autonomy_control: dict[str, Any],
    literature_ingest_policy: dict[str, Any],
    risk_permission_summary: dict[str, Any],
) -> dict[str, Any]:
    level = str(autonomy_control.get("current_level", "L1")).strip().upper() or "L1"
    gates = _strings(autonomy_control.get("must_pause_for", []))
    if risk_permission_summary.get("permission_state") in {"blocked", "requires_human_approval"}:
        gates.append("risk_permission_required")
    if literature_ingest_policy.get("action") in {"propose", "draft_only"}:
        gates.append("literature_digest_confirmation")
    return {
        "autonomy_level": level,
        "memory_write_policy": "auto_low_risk_only" if level in {"L3", "L4", "L5"} else "draft_or_confirm",
        "experiment_execution_policy": "allow_computational_execution" if level in {"L4", "L5"} else "plan_only",
        "claim_promotion_policy": "human_review_required" if level != "L5" else "release_gate_required",
        "pause_gates": _dedupe(gates)[:20],
        "policy_state": "blocked" if gates and level in {"L4", "L5"} else "active",
    }


def build_formal_meeting_record(
    *,
    topic: str,
    project_id: str,
    lab_meeting_governance: dict[str, Any],
    claim_graph: dict[str, Any],
) -> dict[str, Any]:
    return {
        "meeting_id": normalize_scientific_id("meeting", topic, project_id=project_id, topic=topic),
        "topic": topic,
        "project_id": project_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "consensus_level": lab_meeting_governance.get("consensus_level", "forming"),
        "required_roles": lab_meeting_governance.get("required_roles", []),
        "present_roles": lab_meeting_governance.get("present_roles", []),
        "missing_roles": lab_meeting_governance.get("missing_roles", []),
        "open_disagreements": lab_meeting_governance.get("open_disagreements", []),
        "decision_rule": lab_meeting_governance.get("decision_rule", ""),
        "agenda": [
            "review evidence map",
            "challenge active hypotheses",
            "select discriminative experiment portfolio",
            "assign owners for unresolved disagreements",
        ],
        "claim_count": len(_items(claim_graph.get("claims", []))),
        "hypothesis_count": len(_items(claim_graph.get("hypotheses", []))),
        "record_state": "complete" if not lab_meeting_governance.get("missing_roles") else "needs_roles",
    }


def build_failed_attempt_recall(
    *,
    topic: str,
    claim_graph: dict[str, Any],
    scheduler_summary: dict[str, Any],
) -> dict[str, Any]:
    failures = _items(claim_graph.get("negative_results", []))
    candidates = _items(scheduler_summary.get("candidate_experiments", []))
    warnings = []
    for candidate in candidates:
        text = " ".join(
            [
                str(candidate.get("title", "")),
                str(candidate.get("objective", "")),
                " ".join(_strings(candidate.get("target_ids", []))),
            ]
        ).lower()
        for failure in failures:
            failure_text = " ".join(
                [
                    str(failure.get("result", "")),
                    str(failure.get("reason", "")),
                    " ".join(_strings(failure.get("affected_hypothesis_ids", []))),
                ]
            ).lower()
            overlap = sorted({token for token in text.split() if len(token) >= 5 and token in failure_text})[:8]
            if overlap:
                warnings.append(
                    {
                        "candidate_experiment_id": str(candidate.get("experiment_id", "")),
                        "negative_result_id": str(failure.get("negative_result_id", "") or failure.get("id", "")),
                        "overlap_terms": overlap,
                        "required_change": "provide changed condition, new mechanism, or explicit reason before repeating",
                    }
                )
    return {
        "recall_id": normalize_scientific_id("memory", "failed-attempt-recall", topic=topic),
        "failure_count": len(failures),
        "candidate_count": len(candidates),
        "repeat_risk_count": len(warnings),
        "repeat_risk_warnings": warnings[:30],
        "recall_policy": "scheduler and hypothesis generator should check failed attempts before proposing repeats",
    }


def classify_report_release_level(
    *,
    release_gate_summary: dict[str, Any],
    evaluation_summary: dict[str, Any],
    provenance_policy: dict[str, Any],
) -> dict[str, Any]:
    release_state = str(release_gate_summary.get("release_state", "")).strip()
    score = _float(evaluation_summary.get("overall_score", 0))
    provenance_ready = provenance_policy.get("policy_state") == "canonical_ready"
    if release_state == "release_ready" and score >= 0.8 and provenance_ready:
        level = "external_publishable"
    elif score >= 0.65:
        level = "internal_research_report"
    elif score >= 0.45:
        level = "working_draft"
    else:
        level = "private_notes"
    return {
        "release_level": level,
        "release_state": release_state,
        "evaluation_score": score,
        "provenance_ready": provenance_ready,
        "allowed_outputs": {
            "private_notes": ["private_notes", "scratch_report"],
            "working_draft": ["draft_report", "project_memory"],
            "internal_research_report": ["group_report", "experiment_plan", "internal_slides"],
            "external_publishable": ["publication_draft", "public_report", "reproducibility_package"],
        }.get(level, ["private_notes"]),
    }


def _linked_evidence_ids(claim_id: str, claim: dict[str, Any], edges: list[dict[str, Any]], *, relations: set[str]) -> list[str]:
    linked: list[str] = []
    if "supports" in relations:
        linked.extend(_strings(claim.get("supports", [])))
    for edge in edges:
        relation = str(edge.get("relation", "")).strip().lower()
        source = str(edge.get("source", "") or edge.get("source_id", "")).strip()
        target = str(edge.get("target", "") or edge.get("target_id", "")).strip()
        if relation not in relations:
            continue
        if relation == "supported_by" and source == claim_id and target:
            linked.append(target)
        elif relation == "supports" and target == claim_id and source:
            linked.append(source)
        elif relation in {"refutes", "contradicts", "against"} and target == claim_id and source:
            linked.append(source)
    return _dedupe(linked)


def _claim_evidence_state(supporting: list[str], refuting: list[str], qualities: list[str]) -> str:
    if not supporting and not refuting:
        return "unsupported"
    if supporting and refuting:
        return "contested"
    if any(item in {"high", "moderate"} for item in qualities):
        return "decision_grade"
    return "weakly_supported"


def _rival_pair(source: str, target: str, relation: str) -> dict[str, Any]:
    return {
        "rival_pair_id": normalize_scientific_id("hypothesis", f"{source}-vs-{target}"),
        "hypothesis_a_id": source,
        "hypothesis_b_id": target,
        "relation": relation,
        "discriminating_question": f"what observation would support {source} while weakening {target}, or the reverse?",
        "required_output": "paired predictions, boundary conditions, and a discriminative experiment",
    }


def _extrapolation_risk(*, conditions: list[str], evidence_types: list[str], qualities: list[str]) -> str:
    if not conditions:
        return "high"
    if not any(item in {"high", "moderate"} for item in qualities):
        return "high"
    if len(evidence_types) <= 1:
        return "medium"
    return "low"


def _record_id(item: dict[str, Any], kind: str) -> str:
    for key in (f"global_{kind}_id", f"{kind}_id", "id"):
        value = str(item.get(key, "")).strip()
        if value:
            return value
    label = str(item.get("name", "") or item.get("title", "") or item.get("statement", "")).strip()
    return normalize_scientific_id(kind, label) if label else ""


def _items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value).strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    slug = safe.strip("-") or "research-program"
    if len(slug) <= 140:
        return slug
    digest = hashlib.sha1(str(value).encode("utf-8")).hexdigest()[:12]
    return f"{slug[:127].rstrip('-')}-{digest}"
