from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .action_approval import evaluate_scientific_action


@dataclass(slots=True)
class ScientificToolPolicyDecision:
    tool_name: str
    action: str
    decision: str
    allowed: bool
    reason: str
    risk_level: str = "medium"
    audit_required: bool = False
    required_approvals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


TOOL_ACTION_MAP: dict[str, tuple[str, str, str]] = {
    "read_file": ("inspect_workspace", "low", "local"),
    "query_literature_wiki": ("literature_query", "low", "project"),
    "search_memory": ("memory_recall", "low", "project"),
    "query_typed_graph": ("graph_query", "low", "project"),
    "record_observation": ("record_observation", "low", "project"),
    "python_exec": ("execute_computation", "medium", "local"),
    "shell": ("execute_computation", "high", "local"),
    "write_file": ("write_artifact", "medium", "project"),
    "save_memory": ("memory_write", "medium", "project"),
    "review_memory": ("memory_governance", "medium", "project"),
    "forget_memory": ("memory_delete", "high", "project"),
    "ingest_literature_source": ("literature_ingest", "medium", "project"),
    "lint_literature_workspace": ("workspace_lint_write", "medium", "project"),
}


def evaluate_scientific_tool_call(
    *,
    tool_name: str,
    arguments: dict[str, Any],
    autonomy_level: str = "L2",
    destructive: bool = False,
    enforce_review: bool = False,
) -> ScientificToolPolicyDecision:
    action, risk, scope = TOOL_ACTION_MAP.get(
        tool_name,
        ("tool_call", "high" if destructive else "medium", "project"),
    )
    approval = evaluate_scientific_action(
        action=action,
        autonomy_level=autonomy_level,
        risk_level=risk,
        target_scope=scope,
        metadata={"tool_name": tool_name, "arguments_preview": _preview_arguments(arguments)},
    )
    decision = str(approval.get("decision", "review_required"))
    allowed = decision in {"allow", "draft_only"} or (decision == "review_required" and not enforce_review)
    return ScientificToolPolicyDecision(
        tool_name=tool_name,
        action=action,
        decision=decision,
        allowed=allowed,
        reason=str(approval.get("reason", "")),
        risk_level=risk,
        audit_required=bool(approval.get("audit_required", False)),
        required_approvals=[
            str(item) for item in approval.get("required_approvals", []) if str(item).strip()
        ],
    )


def build_tool_permission_policy_summary(
    *,
    autonomy_level: str = "L2",
    enforce_review: bool = False,
    tool_names: list[str] | None = None,
) -> dict[str, Any]:
    names = tool_names or sorted(TOOL_ACTION_MAP)
    decisions = [
        evaluate_scientific_tool_call(
            tool_name=name,
            arguments={},
            autonomy_level=autonomy_level,
            destructive=False,
            enforce_review=enforce_review,
        ).to_dict()
        for name in names
    ]
    return {
        "autonomy_level": autonomy_level,
        "enforce_review": enforce_review,
        "tool_count": len(names),
        "review_required_tools": [
            item["tool_name"] for item in decisions if item["decision"] == "review_required"
        ],
        "denied_tools": [item["tool_name"] for item in decisions if not item["allowed"]],
        "decisions": decisions,
    }


def _preview_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    preview: dict[str, Any] = {}
    for key, value in arguments.items():
        if isinstance(value, str):
            preview[key] = value[:200]
        elif isinstance(value, (int, float, bool)) or value is None:
            preview[key] = value
        elif isinstance(value, list):
            preview[key] = value[:5]
        else:
            preview[key] = str(value)[:200]
    return preview


