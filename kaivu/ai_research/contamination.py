from __future__ import annotations

from typing import Any


def build_contamination_risk_report(
    *,
    dataset_profile: dict[str, Any],
    target_column: str = "",
    id_column: str = "",
    task_type: str = "",
) -> dict[str, Any]:
    risks: list[dict[str, Any]] = []
    columns = dataset_profile.get("columns", [])
    names = [str(item.get("name", "")).lower() for item in columns if isinstance(item, dict)]
    target = target_column.lower().strip()
    if target:
        suspicious = [
            name
            for name in names
            if name != target and target and (target in name or name in {f"{target}_encoded", f"{target}_mean"})
        ]
        if suspicious:
            risks.append(
                {
                    "risk_type": "target_leakage",
                    "severity": "high",
                    "evidence": suspicious[:10],
                    "mitigation": "remove or fold-generate target-derived features before validation",
                }
            )
    if id_column:
        risks.append(
            {
                "risk_type": "identifier_leakage",
                "severity": "medium",
                "evidence": [id_column],
                "mitigation": "do not use raw identifiers as predictive features unless explicitly justified",
            }
        )
    time_like = [name for name in names if any(token in name for token in ("date", "time", "timestamp", "year", "month"))]
    if time_like:
        risks.append(
            {
                "risk_type": "temporal_leakage",
                "severity": "medium",
                "evidence": time_like[:10],
                "mitigation": "prefer time-aware split or leakage audit for future-derived fields",
            }
        )
    duplicate_warning = [
        warning
        for warning in dataset_profile.get("warnings", [])
        if "duplicate id" in str(warning).lower()
    ]
    if duplicate_warning:
        risks.append(
            {
                "risk_type": "duplicate_leakage",
                "severity": "medium",
                "evidence": duplicate_warning,
                "mitigation": "deduplicate or group split by entity id",
            }
        )
    if str(task_type).lower() in {"benchmark_reproduction", "llm_fine_tuning", "generation"}:
        risks.append(
            {
                "risk_type": "benchmark_contamination",
                "severity": "high",
                "evidence": ["task type may use public benchmark examples"],
                "mitigation": "audit train/eval overlap and preserve a heldout confirmatory set",
            }
        )
    severity_order = {"low": 1, "medium": 2, "high": 3}
    max_severity = "low"
    for risk in risks:
        severity = str(risk.get("severity", "low"))
        if severity_order.get(severity, 0) > severity_order.get(max_severity, 0):
            max_severity = severity
    return {
        "report_state": "needs_review" if risks else "no_obvious_risk",
        "overall_risk": max_severity,
        "risk_count": len(risks),
        "risks": risks,
        "required_before_claim": [
            "document split policy",
            "run leakage checks before using validation as evidence",
            "mark any public-leaderboard or reused-test feedback as contaminated evidence",
        ],
    }
