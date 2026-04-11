from __future__ import annotations

from typing import Any


def build_experiment_risk_permission_summary(
    *,
    topic: str,
    experiment_execution_loop_summary: dict[str, Any],
    discipline_toolchain_binding_summary: dict[str, Any],
    human_governance_checkpoint_summary: dict[str, Any] | None = None,
    executor_run_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidates = _items(experiment_execution_loop_summary.get("candidate_experiments", []))
    toolchain_constraints = _strings(discipline_toolchain_binding_summary.get("toolchain_constraints", []))
    governance = human_governance_checkpoint_summary or {}
    executor_runs = _items((executor_run_summary or {}).get("runs", []))
    risk_records = [
        _candidate_risk_record(candidate, discipline_toolchain_binding_summary)
        for candidate in candidates
    ]
    max_rank = max([_risk_rank(item["risk_level"]) for item in risk_records] or [1])
    risk_level = _risk_label(max_rank)
    blocked = [
        item
        for item in risk_records
        if item.get("permission_state") in {"blocked", "requires_human_approval"}
    ]
    if toolchain_constraints and risk_level == "low":
        risk_level = "medium"
    approval_required = bool(blocked) or bool(toolchain_constraints) or risk_level in {"high", "critical"}
    return {
        "experiment_risk_permission_id": f"experiment-risk-permission::{_slugify(topic)}",
        "topic": topic,
        "candidate_count": len(candidates),
        "executor_run_count": len(executor_runs),
        "overall_risk_level": risk_level,
        "approval_required": approval_required,
        "permission_state": "blocked" if risk_level == "critical" else "requires_human_approval" if approval_required else "autonomous_allowed",
        "risk_records": risk_records[:50],
        "blocked_actions": [
            item.get("experiment_id", "")
            for item in blocked
            if str(item.get("experiment_id", "")).strip()
        ][:20],
        "required_approvals": _required_approvals(risk_level, toolchain_constraints, governance),
        "safety_checklist": _safety_checklist(discipline_toolchain_binding_summary, risk_level),
        "toolchain_constraints": toolchain_constraints,
        "executor_feedback": [
            {
                "experiment_id": str(run.get("experiment_id", "")).strip(),
                "execution_state": str(run.get("execution_state", "")).strip(),
                "error_count": len(_strings(run.get("errors", []))),
            }
            for run in executor_runs
        ][:20],
    }


def _candidate_risk_record(candidate: dict[str, Any], toolchain: dict[str, Any]) -> dict[str, Any]:
    text = str(candidate).lower()
    primary = str(toolchain.get("primary_discipline", "")).lower()
    risk = "low"
    reasons: list[str] = []
    if any(token in text for token in ["toxic", "hazard", "pressure", "flammable", "laser", "radiation"]):
        risk = "high"
        reasons.append("candidate mentions physical or chemical hazard")
    if "chem" in primary or "physics" in primary:
        risk = "medium" if risk == "low" else risk
        reasons.append("discipline may involve wet-lab or physical-instrument execution")
    if toolchain.get("binding_readiness") == "low":
        risk = "high"
        reasons.append("discipline toolchain is not fully bound")
    if "human" in text or "approval" in text:
        reasons.append("candidate already indicates approval-sensitive execution")
    permission_state = "autonomous_allowed"
    if risk == "medium":
        permission_state = "requires_policy_check"
    if risk == "high":
        permission_state = "requires_human_approval"
    if risk == "critical":
        permission_state = "blocked"
    return {
        "experiment_id": str(candidate.get("experiment_id", "")).strip(),
        "risk_level": risk,
        "permission_state": permission_state,
        "reasons": reasons or ["no elevated risk signal found"],
        "allowed_executor_types": ["dry_run"] if risk in {"medium", "high"} else ["dry_run", "local_python"],
    }


def _required_approvals(risk_level: str, constraints: list[str], governance: dict[str, Any]) -> list[str]:
    approvals: list[str] = []
    if risk_level in {"medium", "high", "critical"}:
        approvals.append("principal_investigator_or_project_owner")
    if risk_level in {"high", "critical"}:
        approvals.append("safety_ethics_reviewer")
    if constraints:
        approvals.append("toolchain_owner")
    if governance.get("approval_gate_needed"):
        approvals.append("human_governance_checkpoint")
    return list(dict.fromkeys(approvals))


def _safety_checklist(toolchain: dict[str, Any], risk_level: str) -> list[str]:
    checklist = [
        "dry-run or simulation must pass before real executor execution",
        "artifact paths and provenance ids must be recorded before belief update",
    ]
    primary = str(toolchain.get("primary_discipline", "")).lower()
    if "chem" in primary:
        checklist.extend(["verify material safety data sheets", "record reagent identity and disposal route"])
    if "physics" in primary:
        checklist.extend(["verify instrument calibration", "record environmental and operator safety constraints"])
    if "artificial" in primary or primary == "ai":
        checklist.extend(["verify dataset license and split integrity", "record seeds and baseline configuration"])
    if "math" in primary:
        checklist.extend(["record assumptions", "separate conjecture from proved theorem"])
    if risk_level in {"high", "critical"}:
        checklist.append("human approval is required before non-dry-run execution")
    return checklist[:12]


def _risk_rank(value: str) -> int:
    return {"low": 1, "medium": 2, "high": 3, "critical": 4}.get(str(value).strip(), 1)


def _risk_label(rank: int) -> str:
    return {1: "low", 2: "medium", 3: "high", 4: "critical"}.get(rank, "low")


def _items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value).strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "risk"
