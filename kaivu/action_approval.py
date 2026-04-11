from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


HIGH_RISK_ACTIONS = {
    "execute_experiment",
    "run_external_executor",
    "publish_report",
    "promote_group_memory",
    "promote_public_memory",
    "retire_hypothesis",
    "delete_artifact",
    "modify_raw_source",
}


@dataclass(slots=True)
class ScientificActionApproval:
    action_id: str
    action: str
    decision: str
    reason: str
    risk_level: str = "medium"
    autonomy_level: str = "L1"
    required_approvals: list[str] = field(default_factory=list)
    audit_required: bool = True
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_scientific_action(
    *,
    action: str,
    autonomy_level: str = "L1",
    risk_level: str = "medium",
    target_scope: str = "project",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = metadata or {}
    action = str(action).strip()
    autonomy_level = str(autonomy_level).strip().upper() or "L1"
    risk_level = str(risk_level).strip().lower() or "medium"
    target_scope = str(target_scope).strip().lower() or "project"
    required: list[str] = []
    decision = "allow"
    reason = "action is allowed by current scientific action policy"

    if autonomy_level == "L0":
        decision = "deny"
        reason = "L0 only permits read-only responses"
    elif autonomy_level == "L1" and action != "read_context":
        decision = "draft_only"
        required.append("human_confirmation")
        reason = "L1 can draft actions but should not mutate durable research state"
    elif autonomy_level == "L2" and action in {"write_memory", "write_graph", "promote_memory"}:
        decision = "review_required"
        required.append("digest_confirmation")
        reason = "L2 requires confirmation before durable state writes"
    elif autonomy_level == "L3" and action in {"execute_experiment", "run_external_executor", "publish_report"}:
        decision = "review_required"
        required.append("execution_or_release_approval")
        reason = "L3 permits low-risk state updates, not autonomous execution or release"
    elif autonomy_level == "L4" and action == "publish_report":
        decision = "review_required"
        required.append("release_gate")
        reason = "L4 permits computational execution but publication still requires a release gate"

    if action in HIGH_RISK_ACTIONS or risk_level == "high":
        if decision == "allow":
            decision = "review_required"
            reason = "high-risk scientific action requires approval"
        required.append(_approval_for_action(action, target_scope))
    if target_scope in {"group", "public"} and action in {"write_memory", "promote_memory", "publish_report"}:
        if decision == "allow":
            decision = "review_required"
            reason = "broader-scope scientific state change requires review"
        required.append("scope_owner_review")

    required = list(dict.fromkeys(item for item in required if item))
    return ScientificActionApproval(
        action_id=f"scientific-action::{_slugify(action)}::{_slugify(autonomy_level)}::{_slugify(target_scope)}",
        action=action,
        decision=decision,
        reason=reason,
        risk_level=risk_level,
        autonomy_level=autonomy_level,
        required_approvals=required,
        metadata={**metadata, "target_scope": target_scope},
    ).to_dict()


def build_scientific_action_approval_summary(
    *,
    autonomy_level: str,
    planned_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    decisions = [
        evaluate_scientific_action(
            action=str(item.get("action", "")),
            autonomy_level=autonomy_level,
            risk_level=str(item.get("risk_level", "medium")),
            target_scope=str(item.get("target_scope", "project")),
            metadata=item,
        )
        for item in planned_actions
        if isinstance(item, dict) and str(item.get("action", "")).strip()
    ]
    return {
        "approval_state": "blocked" if any(item["decision"] == "deny" for item in decisions) else "requires_review" if any(item["decision"] == "review_required" for item in decisions) else "clear",
        "decision_count": len(decisions),
        "review_required_count": len([item for item in decisions if item["decision"] == "review_required"]),
        "deny_count": len([item for item in decisions if item["decision"] == "deny"]),
        "decisions": decisions,
    }


def _approval_for_action(action: str, target_scope: str) -> str:
    if action in {"execute_experiment", "run_external_executor"}:
        return "experiment_owner_or_safety_review"
    if action == "publish_report":
        return "release_owner_review"
    if action in {"retire_hypothesis"}:
        return "lab_meeting_review"
    if target_scope in {"group", "public"}:
        return "scope_owner_review"
    return "human_review"


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value).strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "action"
