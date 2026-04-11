from __future__ import annotations

from copy import deepcopy
from typing import Any


def build_ai_experiment_candidates(ai_research_workflow_summary: dict[str, Any]) -> list[dict[str, Any]]:
    if not ai_research_workflow_summary:
        return []
    candidates: list[dict[str, Any]] = []
    output_dir = str(ai_research_workflow_summary.get("output_dir", "")).strip()
    evaluation = ai_research_workflow_summary.get("evaluation_protocol", {})
    training = ai_research_workflow_summary.get("training_recipe", {})
    ablation = ai_research_workflow_summary.get("ablation_plan", {})
    metric = str(evaluation.get("primary_metric", "")).strip()
    split = evaluation.get("split_strategy", {}) if isinstance(evaluation, dict) else {}

    for index, action in enumerate(_items(ai_research_workflow_summary.get("next_actions", [])), start=1):
        action_name = str(action.get("action", "")).strip()
        if not action_name:
            continue
        candidates.append(
            _candidate(
                experiment_id=f"ai-exp-next-{index:03d}",
                title=action_name.replace("_", " "),
                experiment_type=_action_to_experiment_type(action_name),
                objective=str(action.get("reason", "")).strip(),
                priority=str(action.get("priority", "medium")).strip() or "medium",
                metric=metric,
                output_dir=output_dir,
                split_strategy=split,
                source="ai_research_workflow.next_actions",
                required_before_execution=_required_for_action(action_name),
            )
        )

    baseline = training.get("baseline_recipe", {}) if isinstance(training, dict) else {}
    model = str(baseline.get("model", "")).strip()
    if model:
        candidates.append(
            _candidate(
                experiment_id="ai-exp-baseline-001",
                title=f"Run reproducible AI baseline: {model}",
                experiment_type="ai_baseline",
                objective="establish reproducible baseline before advanced model claims",
                priority="high",
                metric=metric,
                output_dir=output_dir,
                split_strategy=split,
                source="ai_research_workflow.training_recipe",
                search_space={"model": model, "seed_policy": baseline.get("seed_policy", [42])},
                required_before_execution=["freeze_evaluation_protocol", "save_config_snapshot"],
            )
        )

    for item in _items(ablation.get("experiments", []) if isinstance(ablation, dict) else []):
        ablation_id = str(item.get("ablation_id", "")).strip()
        if not ablation_id or ablation_id == "abl_000_baseline":
            continue
        candidates.append(
            _candidate(
                experiment_id=f"ai-exp-{_slugify(ablation_id)}",
                title=str(item.get("change", "")).strip() or ablation_id,
                experiment_type="ai_ablation",
                objective=str(item.get("purpose", "")).strip(),
                priority="medium",
                metric=metric,
                output_dir=output_dir,
                split_strategy=split,
                source="ai_research_workflow.ablation_plan",
                search_space={"ablation_id": ablation_id, "control_rule": item.get("control_rule", "")},
                required_before_execution=["baseline_completed", "single_factor_change_documented"],
            )
        )
    return _dedupe_by_id(candidates)


def augment_experiment_execution_loop_with_ai(
    experiment_execution_loop_summary: dict[str, Any],
    *,
    ai_research_workflow_summary: dict[str, Any],
) -> dict[str, Any]:
    candidates = build_ai_experiment_candidates(ai_research_workflow_summary)
    if not candidates:
        return experiment_execution_loop_summary
    summary = deepcopy(experiment_execution_loop_summary)
    existing_candidates = _items(summary.get("candidate_experiments", []))
    existing_queue = _items(summary.get("execution_queue", []))
    seen = {str(item.get("experiment_id", "")).strip() for item in existing_candidates + existing_queue}
    new_candidates = [item for item in candidates if item["experiment_id"] not in seen]
    summary["candidate_experiments"] = existing_candidates + new_candidates
    queue_additions = [
        _schedule_item(item, rank=len(existing_queue) + index)
        for index, item in enumerate(new_candidates, start=1)
        if item.get("gate_state") not in {"blocked", "needs_human_approval"}
    ]
    summary["execution_queue"] = existing_queue + queue_additions
    summary["candidate_count"] = len(summary["candidate_experiments"])
    summary["ai_research_candidate_count"] = len(new_candidates)
    summary["ai_research_scheduler_integration"] = {
        "enabled": True,
        "mode": "guided",
        "source_output_dir": ai_research_workflow_summary.get("output_dir", ""),
        "injected_candidate_ids": [item["experiment_id"] for item in new_candidates],
    }
    if not summary.get("top_experiment_id") and summary["execution_queue"]:
        summary["top_experiment_id"] = str(summary["execution_queue"][0].get("experiment_id", ""))
        summary["top_action"] = str(summary["execution_queue"][0].get("action", ""))
    return summary


def _candidate(
    *,
    experiment_id: str,
    title: str,
    experiment_type: str,
    objective: str,
    priority: str,
    metric: str,
    output_dir: str,
    split_strategy: dict[str, Any],
    source: str,
    required_before_execution: list[str],
    search_space: dict[str, Any] | None = None,
) -> dict[str, Any]:
    priority_score = {"high": 5.0, "medium": 3.0, "low": 1.0}.get(priority.lower(), 3.0)
    return {
        "experiment_id": experiment_id,
        "title": title,
        "experiment_type": experiment_type,
        "target_ids": [],
        "source": source,
        "objective": objective,
        "information_gain_score": priority_score,
        "discrimination_score": 2.0 if "ablation" in experiment_type else 1.0,
        "reproducibility_score": 4.0,
        "evidence_quality_gain": 3.0,
        "failure_knowledge_gain": 2.0,
        "cost_score": 1.0 if experiment_type in {"ai_protocol_repair", "ai_leakage_audit"} else 2.0,
        "time_score": 1.0 if experiment_type in {"ai_protocol_repair", "ai_leakage_audit"} else 2.0,
        "risk_score": 1.0,
        "requires_human_approval": False,
        "requires_protocol": True,
        "search_space": {
            **(search_space or {}),
            "metric": metric,
            "split_strategy": split_strategy,
            "artifact_root": output_dir,
        },
        "success_criteria": [
            "metrics and runtime manifest are saved",
            "quality-control checks pass",
            "result can be compared against baseline or prior run",
        ],
        "failure_criteria": [
            "leakage or contamination is detected",
            "run cannot be reproduced from saved config",
            "metric is missing or computed on an invalid split",
        ],
        "quality_gates": [
            "dataset_split_verified",
            "contamination_or_leakage_checked",
            "configuration_snapshot_saved",
        ],
        "provenance_refs": [output_dir] if output_dir else [],
        "scheduler_rules": [
            "AI research guided mode: plan and schedule, do not run heavy training without executor approval",
            *required_before_execution,
        ],
        "gate_state": "candidate",
        "gate_reasons": [],
        "selection_score": priority_score,
        "portfolio_score": priority_score,
    }


def _schedule_item(candidate: dict[str, Any], *, rank: int) -> dict[str, Any]:
    required = _strings(candidate.get("scheduler_rules", []))
    return {
        "experiment_id": candidate["experiment_id"],
        "rank": rank,
        "schedule_state": "ready_for_planning",
        "portfolio_score": candidate.get("portfolio_score", 0),
        "action": f"schedule_{candidate.get('experiment_type', 'ai_experiment')}",
        "required_before_execution": required[:10],
        "recommended_agents": [
            "evaluation_protocol_designer",
            "training_recipe_planner",
            "ablation_manager",
            "quality_control_reviewer",
        ],
        "scheduler_node_id": f"scheduler-node::{candidate['experiment_id']}",
        "selection_reason": candidate.get("objective", ""),
    }


def _action_to_experiment_type(action: str) -> str:
    if "contamination" in action or "leakage" in action:
        return "ai_leakage_audit"
    if "evaluation" in action or "validation" in action:
        return "ai_protocol_repair"
    if "baseline" in action:
        return "ai_baseline"
    if "ablation" in action:
        return "ai_ablation"
    return "ai_research_planning"


def _required_for_action(action: str) -> list[str]:
    if "baseline" in action:
        return ["freeze_evaluation_protocol", "save_config_snapshot"]
    if "ablation" in action:
        return ["baseline_completed", "single_factor_change_documented"]
    if "contamination" in action or "leakage" in action:
        return ["dataset_profile_completed", "split_policy_documented"]
    if "evaluation" in action or "validation" in action:
        return ["dataset_profile_completed", "metric_reproduced"]
    return ["ai_research_plan_reviewed"]


def _items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []


def _dedupe_by_id(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        identifier = str(item.get("experiment_id", "")).strip()
        if not identifier or identifier in seen:
            continue
        seen.add(identifier)
        result.append(item)
    return result


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value).strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "ai-experiment"
