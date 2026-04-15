from __future__ import annotations

from typing import Any


def build_scientific_context_policy_summary(
    *,
    topic: str,
    research_state: dict[str, Any],
    claim_graph: dict[str, Any],
    scheduler_memory_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stage = str(research_state.get("recommended_next_stage", "") or research_state.get("current_stage", "")).strip().lower()
    if not stage:
        stage = "literature_review"
    packs = _packs_for_stage(stage)
    signals = {
        "claim_count": len(_items(claim_graph.get("claims", []))),
        "hypothesis_count": len(_items(claim_graph.get("hypotheses", []))),
        "negative_result_count": len(_items(claim_graph.get("negative_results", []))),
        "scheduler_failure_memory_count": len(_strings((scheduler_memory_context or {}).get("failed_routes", []))),
        "benchmark_readiness": str(research_state.get("benchmark_case_suite_summary", {}).get("benchmark_readiness", "")),
    }
    budget = _budget_for_stage(stage, signals)
    return {
        "scientific_context_policy_id": f"scientific-context-policy::{_slugify(topic)}",
        "topic": topic,
        "stage": stage,
        "context_budget": budget,
        "required_context_packs": packs["required"],
        "optional_context_packs": packs["optional"],
        "deprioritized_context_packs": packs["deprioritized"],
        "compression_rules": [
            "keep claim, evidence, hypothesis, experiment, decision, and provenance ids verbatim",
            "summarize literature pages by controversy, mechanism, method, and evidence grade",
            "collapse repeated failed attempts into route-level failure memories",
            "never compress away safety blockers, permission gates, or quality-control failures",
        ],
        "recall_signals": signals,
        "policy_state": "ready",
    }


def _packs_for_stage(stage: str) -> dict[str, list[str]]:
    if "literature" in stage:
        return {
            "required": ["literature_wiki_index", "systematic_review_protocol", "claim_compiler"],
            "optional": ["controversy_pages", "source_quality_table"],
            "deprioritized": ["executor_trace_details", "hyperparameter_trials"],
        }
    if "hypothesis" in stage or "belief" in stage:
        return {
            "required": ["hypothesis_tree", "mechanism_families", "failed_attempts", "evidence_conflicts"],
            "optional": ["agent_stance_memory", "counterfactual_experiments"],
            "deprioritized": ["raw_source_chunks_without_claims"],
        }
    if "experiment" in stage or "running" in stage or "execution" in stage:
        return {
            "required": ["experiment_scheduler", "discipline_toolchain", "risk_permission_gate", "run_handoff_contract"],
            "optional": ["scheduler_memory_context", "value_of_information"],
            "deprioritized": ["long literature summaries"],
        }
    if "review" in stage or "meeting" in stage or "decision" in stage:
        return {
            "required": ["lab_meeting_records", "agent_stance_continuity", "benchmark_quality", "release_gate"],
            "optional": ["formal_review_records", "route_scheduler"],
            "deprioritized": ["raw executor stdout"],
        }
    return {
        "required": ["kernel_state", "provenance_graph", "release_gate"],
        "optional": ["report_outline", "memory_distill"],
        "deprioritized": ["raw scratchpads"],
    }


def _budget_for_stage(stage: str, signals: dict[str, Any]) -> dict[str, Any]:
    base_tokens = 12000
    if "experiment" in stage or int(signals.get("negative_result_count", 0) or 0) >= 3:
        base_tokens = 16000
    if "literature" in stage:
        base_tokens = 18000
    return {
        "target_tokens": base_tokens,
        "hard_cap_tokens": int(base_tokens * 1.5),
        "max_raw_sources": 8 if "literature" in stage else 3,
        "max_memory_files": 12,
        "max_failed_attempt_records": 10,
    }


def _items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value).strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "context"


