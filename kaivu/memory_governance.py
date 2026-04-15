from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from .memory import MemoryManager, MemoryRecord, MemoryScope, VisibilityLevel


@dataclass(slots=True)
class MemoryMigrationDecision:
    filename: str
    title: str
    source_scope: str
    target_scope: str
    action: str
    risk_level: str
    confidence_score: float
    reasons: list[str] = field(default_factory=list)
    required_role: str = "contributor"
    target_visibility: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def plan_memory_migrations(
    *,
    records: list[MemoryRecord],
    target_scope: MemoryScope,
    user_id: str = "",
    project_id: str = "",
    group_id: str = "",
    automation_mode: str = "safe",
    max_items: int = 25,
) -> list[dict[str, Any]]:
    decisions: list[MemoryMigrationDecision] = []
    for record in records:
        if not _in_scope(record, user_id=user_id, project_id=project_id, group_id=group_id):
            continue
        if record.scope == target_scope:
            continue
        decisions.append(
            _decision_for_record(
                record=record,
                target_scope=target_scope,
                automation_mode=automation_mode,
            )
        )
    decisions.sort(
        key=lambda item: (
            {"auto_promote": 0, "propose": 1, "block": 2}.get(item.action, 3),
            -item.confidence_score,
            item.filename,
        )
    )
    return [item.to_dict() for item in decisions[:max_items]]


def apply_memory_migration_decisions(
    *,
    manager: MemoryManager,
    decisions: list[dict[str, Any]],
    actor: str = "memory-governance",
    dry_run: bool = False,
) -> dict[str, Any]:
    applied: list[dict[str, Any]] = []
    proposed: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for decision in decisions:
        if not isinstance(decision, dict):
            continue
        filename = str(decision.get("filename", "")).strip()
        action = str(decision.get("action", "")).strip()
        target_scope = str(decision.get("target_scope", "")).strip()
        target_visibility = str(decision.get("target_visibility", "")).strip()
        if not filename:
            continue
        audit = migration_audit_tag(action=action, target_scope=target_scope, actor=actor)
        try:
            if action == "auto_promote" and not dry_run:
                destination = manager.promote_memory(
                    filename,
                    target_scope=target_scope,  # type: ignore[arg-type]
                    target_visibility=target_visibility or None,  # type: ignore[arg-type]
                    approved_by=audit,
                )
                if destination is None:
                    failed.append({**decision, "result": "not_found"})
                else:
                    applied.append({**decision, "result": "promoted", "path": str(destination)})
            elif action == "auto_promote":
                applied.append({**decision, "result": "dry_run_promote"})
            elif action == "propose":
                if not dry_run:
                    manager.review_memory(
                        filename,
                        needs_review=True,
                        validated_by=[audit],
                        visibility=target_visibility or None,  # type: ignore[arg-type]
                    )
                proposed.append({**decision, "result": "review_required"})
            else:
                if not dry_run:
                    manager.review_memory(
                        filename,
                        needs_review=True,
                        validated_by=[audit],
                    )
                blocked.append({**decision, "result": "blocked"})
        except Exception as exc:
            failed.append({**decision, "result": "error", "error": str(exc)})
    return {
        "migration_state": "failed" if failed and not (applied or proposed or blocked) else "completed",
        "dry_run": dry_run,
        "applied_count": len(applied),
        "proposed_count": len(proposed),
        "blocked_count": len(blocked),
        "failed_count": len(failed),
        "applied": applied,
        "proposed": proposed,
        "blocked": blocked,
        "failed": failed,
    }


def _decision_for_record(
    *,
    record: MemoryRecord,
    target_scope: MemoryScope,
    automation_mode: str,
) -> MemoryMigrationDecision:
    reasons: list[str] = []
    risk = "low"
    score = _confidence_score(record)
    required_role = _required_role(target_scope)
    target_visibility = _target_visibility(target_scope)
    action = "auto_promote"

    if record.status in {"deprecated", "rejected"}:
        action = "block"
        risk = "high"
        reasons.append(f"record status is {record.status}")
    if record.conflicts_with:
        action = "block"
        risk = "high"
        reasons.append("record has unresolved conflicts")
    if record.needs_review:
        action = "propose" if action != "block" else action
        risk = _max_risk(risk, "medium")
        reasons.append("record already needs review")
    if record.evidence_level == "low" or record.confidence == "low":
        action = "propose" if action != "block" else action
        risk = _max_risk(risk, "medium")
        reasons.append("record has low evidence or confidence")
    if _is_failure_or_negative_result(record) and target_scope in {"group", "public"}:
        action = "propose" if action != "block" else action
        risk = _max_risk(risk, "medium")
        reasons.append("failed attempts or negative results require review before broader sharing")
    if record.scope == "personal" and target_scope in {"project", "group", "public"}:
        action = "propose" if action != "block" else action
        risk = _max_risk(risk, "medium")
        reasons.append("personal memory requires human review before broader sharing")
    if target_scope == "public":
        action = "propose" if action != "block" else action
        risk = _max_risk(risk, "high")
        required_role = "admin"
        reasons.append("public promotion always requires review")
    if _looks_sensitive(record):
        action = "block" if target_scope in {"group", "public"} else "propose"
        risk = "high"
        reasons.append("memory appears sensitive or private")
    if automation_mode == "propose_only" and action == "auto_promote":
        action = "propose"
        reasons.append("automation mode is propose_only")
    if automation_mode == "dry_run":
        reasons.append("dry_run mode does not mutate memory")
    if action == "auto_promote" and target_scope == "group":
        required_role = "curator"
    if action == "auto_promote" and score < 0.72:
        action = "propose"
        risk = _max_risk(risk, "medium")
        reasons.append("confidence score below auto-promotion threshold")

    if not reasons:
        reasons.append("record is active, non-conflicting, and sufficiently trusted")
    return MemoryMigrationDecision(
        filename=record.path.name,
        title=record.title,
        source_scope=record.scope,
        target_scope=target_scope,
        action=action,
        risk_level=risk,
        confidence_score=round(score, 3),
        reasons=reasons[:8],
        required_role=required_role,
        target_visibility=target_visibility,
    )


def migration_audit_tag(*, action: str, target_scope: str, actor: str) -> str:
    timestamp = datetime.now(timezone.utc).isoformat()
    if action == "auto_promote":
        return f"auto-promoted-by:{actor or 'automation'}:{target_scope}:{timestamp}"
    if action == "propose":
        return f"auto-promotion-proposal:{target_scope}:{actor or 'automation'}:{timestamp}"
    return f"auto-migration-blocked:{target_scope}:{actor or 'automation'}:{timestamp}"


def _confidence_score(record: MemoryRecord) -> float:
    evidence = {"low": 0.25, "medium": 0.65, "high": 0.9}.get(record.evidence_level, 0.5)
    confidence = {"low": 0.25, "medium": 0.65, "high": 0.9}.get(record.confidence, 0.5)
    status = {"active": 0.9, "revised": 0.7, "uncertain": 0.45, "deprecated": 0.1, "rejected": 0.0}.get(
        record.status,
        0.5,
    )
    validation_bonus = min(0.12, 0.03 * len(record.validated_by))
    conflict_penalty = 0.2 if record.conflicts_with else 0.0
    review_penalty = 0.12 if record.needs_review else 0.0
    return max(0.0, min(1.0, ((evidence + confidence + status) / 3) + validation_bonus - conflict_penalty - review_penalty))


def _in_scope(record: MemoryRecord, *, user_id: str, project_id: str, group_id: str) -> bool:
    if user_id and record.user_id and record.user_id != user_id:
        return False
    if project_id and record.project_id and record.project_id != project_id:
        return False
    if group_id and record.group_id and record.group_id != group_id:
        return False
    return True


def _looks_sensitive(record: MemoryRecord) -> bool:
    haystack = " ".join(
        [
            record.title,
            record.summary,
            record.excerpt,
            " ".join(record.tags),
            record.kind,
            record.visibility,
        ]
    ).lower()
    sensitive_terms = [
        "private",
        "personal",
        "secret",
        "credential",
        "password",
        "token",
        "api key",
        "unpublished",
        "confidential",
        "patient",
        "human subject",
    ]
    return any(term in haystack for term in sensitive_terms)


def _is_failure_or_negative_result(record: MemoryRecord) -> bool:
    haystack = " ".join(
        [
            record.title,
            record.summary,
            record.excerpt,
            " ".join(record.tags),
            record.kind,
        ]
    ).lower()
    return record.kind == "warning" and any(
        term in haystack
        for term in [
            "failed-route",
            "failed-attempt",
            "negative-result",
            "negative result",
            "failed experiment",
            "did not replicate",
            "null result",
        ]
    )


def _required_role(target_scope: str) -> str:
    if target_scope == "group":
        return "curator"
    if target_scope == "public":
        return "admin"
    return "contributor"


def _target_visibility(target_scope: str) -> VisibilityLevel:
    if target_scope == "personal":
        return "private"
    if target_scope == "project":
        return "project"
    if target_scope == "group":
        return "group"
    if target_scope == "public":
        return "public"
    return "private"


def _max_risk(left: str, right: str) -> str:
    rank = {"low": 0, "medium": 1, "high": 2}
    return left if rank.get(left, 0) >= rank.get(right, 0) else right


