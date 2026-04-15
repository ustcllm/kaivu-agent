from __future__ import annotations

from typing import Any


def derive_graph_reference_summary(steps: list[Any]) -> dict[str, Any]:
    node_refs: set[str] = set()
    edge_refs: set[str] = set()
    by_profile: list[dict[str, Any]] = []
    for step in steps:
        payload = step.parsed_output.get("graph_references", {})
        if not isinstance(payload, dict) or not payload:
            continue
        profile_nodes = (
            [str(item).strip() for item in payload.get("node_refs", []) if str(item).strip()]
            if isinstance(payload.get("node_refs", []), list)
            else []
        )
        profile_edges = (
            [str(item).strip() for item in payload.get("edge_refs", []) if str(item).strip()]
            if isinstance(payload.get("edge_refs", []), list)
            else []
        )
        node_refs.update(profile_nodes)
        edge_refs.update(profile_edges)
        by_profile.append(
            {
                "profile_name": step.profile_name,
                "node_refs": profile_nodes,
                "edge_refs": profile_edges,
                "usage_note": str(payload.get("usage_note", "")).strip(),
            }
        )
    return {
        "node_ref_count": len(node_refs),
        "edge_ref_count": len(edge_refs),
        "node_refs": sorted(node_refs),
        "edge_refs": sorted(edge_refs),
        "by_profile": by_profile,
    }


def derive_graph_learning_summary(
    *,
    typed_research_graph_history: dict[str, Any],
    graph_reference_summary: dict[str, Any],
    failure_intelligence_summary: dict[str, Any],
    evaluation_history_summary: dict[str, Any],
) -> dict[str, Any]:
    consulted_profiles = (
        typed_research_graph_history.get("consulted_profiles", {})
        if isinstance(typed_research_graph_history.get("consulted_profiles", {}), dict)
        else {}
    )
    by_profile = (
        graph_reference_summary.get("by_profile", [])
        if isinstance(graph_reference_summary.get("by_profile", []), list)
        else []
    )
    high_value_profiles = [
        str(item.get("profile_name", "")).strip()
        for item in by_profile
        if isinstance(item, dict)
        and (len(item.get("node_refs", [])) + len(item.get("edge_refs", []))) >= 2
        and str(item.get("profile_name", "")).strip()
    ]
    dominant_failure = str(failure_intelligence_summary.get("dominant_failure_class", "mixed")).strip() or "mixed"
    regression_count = int(evaluation_history_summary.get("regressing_count", 0) or 0)
    learning_signal_strength = "low"
    if consulted_profiles or regression_count >= 2 or high_value_profiles:
        learning_signal_strength = "medium"
    if len(consulted_profiles) >= 2 and regression_count >= 2:
        learning_signal_strength = "high"
    return {
        "learning_signal_strength": learning_signal_strength,
        "dominant_failure_class": dominant_failure,
        "high_value_profiles": list(dict.fromkeys(high_value_profiles))[:8],
        "consulted_profiles": consulted_profiles,
        "regression_count": regression_count,
        "recommended_learning_focus": (
            "avoid repeated technical routes"
            if dominant_failure == "technical"
            else "re-examine theory families"
            if dominant_failure == "theoretical"
            else "close evidence gaps"
        ),
    }


def summarize_asset_registry(
    registry_items: list[dict[str, Any]],
    run_manifest: dict[str, Any],
) -> dict[str, Any]:
    asset_types: dict[str, int] = {}
    for item in registry_items:
        if not isinstance(item, dict):
            continue
        asset_type = str(item.get("asset_type", "unknown")).strip() or "unknown"
        asset_types[asset_type] = asset_types.get(asset_type, 0) + 1
    for item in run_manifest.get("artifacts", []):
        if not isinstance(item, dict):
            continue
        asset_type = str(item.get("scope", "artifact")).strip() or "artifact"
        asset_types[asset_type] = asset_types.get(asset_type, 0) + 1
    return {
        "asset_count": len(registry_items) + len(run_manifest.get("artifacts", [])),
        "asset_types": asset_types,
        "registered_assets": registry_items[:20],
    }


def derive_belief_update_summary(
    *,
    steps: list[Any],
    claim_graph: dict[str, Any],
) -> dict[str, Any]:
    belief_step = next((step for step in steps if step.profile_name == "belief_updater"), None)
    if belief_step is None:
        return {}
    parsed = belief_step.parsed_output if isinstance(belief_step.parsed_output, dict) else {}
    consensus = parsed.get("consensus_summary", {}) if isinstance(parsed.get("consensus_summary", {}), dict) else {}
    project_distill = parsed.get("project_distill", {}) if isinstance(parsed.get("project_distill", {}), dict) else {}
    registry_updates = (
        parsed.get("asset_registry_updates", [])
        if isinstance(parsed.get("asset_registry_updates", []), list)
        else []
    )
    hypotheses = claim_graph.get("hypotheses", [])
    hypothesis_relations = claim_graph.get("hypothesis_relations", [])
    status_counts: dict[str, int] = {}
    challenged_count = 0
    for item in hypotheses if isinstance(hypotheses, list) else []:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status", "active")).strip().lower() or "active"
        status_counts[status] = status_counts.get(status, 0) + 1
        if int(item.get("challenge_count", 0) or 0) > 0:
            challenged_count += 1
    relation_counts: dict[str, int] = {}
    for item in hypothesis_relations if isinstance(hypothesis_relations, list) else []:
        if not isinstance(item, dict):
            continue
        relation = str(item.get("relation", "related_to")).strip().lower() or "related_to"
        relation_counts[relation] = relation_counts.get(relation, 0) + 1
    return {
        "consensus_status": str(consensus.get("consensus_status", "")).strip() or "partial",
        "agreed_points": consensus.get("agreed_points", []) if isinstance(consensus.get("agreed_points", []), list) else [],
        "unresolved_points": (
            consensus.get("unresolved_points", [])
            if isinstance(consensus.get("unresolved_points", []), list)
            else []
        ),
        "adjudication_basis": (
            consensus.get("adjudication_basis", [])
            if isinstance(consensus.get("adjudication_basis", []), list)
            else []
        ),
        "current_consensus": str(project_distill.get("current_consensus", "")).strip(),
        "next_cycle_goals": (
            project_distill.get("next_cycle_goals", [])
            if isinstance(project_distill.get("next_cycle_goals", []), list)
            else []
        ),
        "failed_routes": (
            project_distill.get("failed_routes", [])
            if isinstance(project_distill.get("failed_routes", []), list)
            else []
        ),
        "registry_update_count": len([item for item in registry_updates if isinstance(item, dict)]),
        "status_counts": status_counts,
        "challenged_hypothesis_count": challenged_count,
        "hypothesis_relation_counts": relation_counts,
    }


__all__ = [
    "derive_belief_update_summary",
    "derive_graph_learning_summary",
    "derive_graph_reference_summary",
    "summarize_asset_registry",
]
