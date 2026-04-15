from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ScientificAsset:
    asset_id: str
    asset_type: str
    label: str
    role: str
    source_system: str
    status: str = "active"
    governance_status: str = ""
    path_or_reference: str = ""
    project_id: str = ""
    topic: str = ""
    parent_asset_ids: list[str] = field(default_factory=list)
    derived_from_asset_ids: list[str] = field(default_factory=list)
    related_hypothesis_ids: list[str] = field(default_factory=list)
    related_decision_ids: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_unified_asset_summary(
    *,
    topic: str,
    project_id: str = "",
    claim_graph: dict[str, Any],
    run_manifest: dict[str, Any],
    hypothesis_theory_summary: dict[str, Any],
    scientific_decision_summary: dict[str, Any],
    systematic_review_summary: dict[str, Any],
    causal_graph_summary: dict[str, Any],
    evidence_review_summary: dict[str, Any] | None = None,
    autonomous_controller_summary: dict[str, Any] | None = None,
    experiment_execution_loop_summary: dict[str, Any] | None = None,
    optimization_adapter_summary: dict[str, Any] | None = None,
    discipline_adapter_summary: dict[str, Any] | None = None,
    execution_adapter_registry_summary: dict[str, Any] | None = None,
    run_handoff_contract_summary: dict[str, Any] | None = None,
    kaivu_evaluation_harness_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    assets: dict[str, ScientificAsset] = {}

    def add(asset: ScientificAsset) -> None:
        if not asset.asset_id:
            return
        existing = assets.get(asset.asset_id)
        if existing is None:
            assets[asset.asset_id] = asset
            return
        existing.related_hypothesis_ids = _dedupe(existing.related_hypothesis_ids + asset.related_hypothesis_ids)
        existing.related_decision_ids = _dedupe(existing.related_decision_ids + asset.related_decision_ids)
        existing.evidence_refs = _dedupe(existing.evidence_refs + asset.evidence_refs)
        existing.parent_asset_ids = _dedupe(existing.parent_asset_ids + asset.parent_asset_ids)
        existing.derived_from_asset_ids = _dedupe(existing.derived_from_asset_ids + asset.derived_from_asset_ids)
        existing.metadata = {**existing.metadata, **asset.metadata}

    for item in claim_graph.get("hypotheses", []) if isinstance(claim_graph.get("hypotheses", []), list) else []:
        if not isinstance(item, dict):
            continue
        asset_id = str(item.get("global_hypothesis_id", "") or item.get("hypothesis_id", "")).strip()
        add(
            ScientificAsset(
                asset_id=asset_id,
                asset_type="hypothesis",
                label=str(item.get("name", "")).strip() or asset_id,
                role="candidate_explanation",
                source_system="claim_graph",
                status=str(item.get("status", "active")).strip() or "active",
                project_id=project_id,
                topic=topic,
                evidence_refs=_string_list(item.get("evidence_refs", [])),
                metadata=item,
            )
        )

    for item in hypothesis_theory_summary.get("objects", []) if isinstance(hypothesis_theory_summary.get("objects", []), list) else []:
        if not isinstance(item, dict):
            continue
        asset_id = str(item.get("theory_object_id", "")).strip()
        hypothesis_id = str(item.get("hypothesis_id", "")).strip()
        add(
            ScientificAsset(
                asset_id=asset_id,
                asset_type="hypothesis_theory_object",
                label=str(item.get("name", "")).strip() or asset_id,
                role="formalized_theory",
                source_system="hypothesis_theory_builder",
                status=str(item.get("decision_state", "observe")).strip() or "observe",
                governance_status=str(item.get("theory_maturity", "")).strip(),
                project_id=project_id,
                topic=topic,
                parent_asset_ids=[hypothesis_id] if hypothesis_id else [],
                related_hypothesis_ids=[hypothesis_id] if hypothesis_id else [],
                evidence_refs=_string_list(item.get("negative_result_refs", [])),
                metadata=item,
            )
        )

    for item in scientific_decision_summary.get("decision_queue", []) if isinstance(scientific_decision_summary.get("decision_queue", []), list) else []:
        if not isinstance(item, dict):
            continue
        asset_id = str(item.get("decision_id", "")).strip()
        target_id = str(item.get("target_id", "")).strip()
        add(
            ScientificAsset(
                asset_id=asset_id,
                asset_type="scientific_decision",
                label=str(item.get("action", "")).strip() or asset_id,
                role="next_action_decision",
                source_system="decision_engine",
                status=str(item.get("priority", "medium")).strip() or "medium",
                governance_status="human_review_required" if item.get("human_review_required") else "autonomous_ok",
                project_id=project_id,
                topic=topic,
                parent_asset_ids=[target_id] if target_id else [],
                related_hypothesis_ids=[target_id] if "hypothesis" in str(item.get("target_type", "")) and target_id else [],
                evidence_refs=[
                    str(trace.get("source_id", ""))
                    for trace in item.get("evidence_trace", [])
                    if isinstance(trace, dict) and str(trace.get("source_id", "")).strip()
                ],
                metadata=item,
            )
        )

    for item in claim_graph.get("evidence", []) if isinstance(claim_graph.get("evidence", []), list) else []:
        if not isinstance(item, dict):
            continue
        asset_id = str(item.get("global_evidence_id", "") or item.get("evidence_id", "")).strip()
        add(
            ScientificAsset(
                asset_id=asset_id,
                asset_type="evidence",
                label=str(item.get("summary", "")).strip()[:200] or asset_id,
                role=str(item.get("evidence_direction", "contextual")).strip() or "contextual",
                source_system="claim_graph",
                status=str(item.get("quality_grade", "unclear")).strip() or "unclear",
                governance_status=str(item.get("bias_risk", "")).strip(),
                path_or_reference=str(item.get("source_ref", "")).strip(),
                project_id=project_id,
                topic=topic,
                metadata=item,
            )
        )

    for item in claim_graph.get("negative_results", []) if isinstance(claim_graph.get("negative_results", []), list) else []:
        if not isinstance(item, dict):
            continue
        asset_id = str(item.get("negative_result_id", "")).strip()
        add(
            ScientificAsset(
                asset_id=asset_id,
                asset_type="negative_result",
                label=str(item.get("result", "")).strip()[:200] or asset_id,
                role="failure_knowledge",
                source_system="claim_graph",
                status="active",
                project_id=project_id,
                topic=topic,
                related_hypothesis_ids=_string_list(item.get("affected_hypothesis_ids", [])),
                metadata=item,
            )
        )

    for item in claim_graph.get("asset_registry", []) if isinstance(claim_graph.get("asset_registry", []), list) else []:
        if not isinstance(item, dict):
            continue
        asset_id = str(item.get("asset_id", "")).strip()
        add(
            ScientificAsset(
                asset_id=asset_id,
                asset_type=str(item.get("asset_type", "")).strip() or "asset",
                label=str(item.get("label", "")).strip() or asset_id,
                role=str(item.get("role", "")).strip() or "registered_asset",
                source_system="agent_asset_registry",
                status=str(item.get("status", "active")).strip() or "active",
                governance_status=str(item.get("governance_status", "")).strip(),
                path_or_reference=str(item.get("path_or_ref", "") or item.get("path_or_reference", "")).strip(),
                project_id=project_id,
                topic=topic,
                parent_asset_ids=[str(item.get("parent_asset_id", "")).strip()] if str(item.get("parent_asset_id", "")).strip() else [],
                derived_from_asset_ids=_string_list(item.get("derived_from_asset_ids", [])),
                metadata=item,
            )
        )

    for item in run_manifest.get("artifacts", []) if isinstance(run_manifest.get("artifacts", []), list) else []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", "")).strip()
        if not path:
            continue
        asset_type = _artifact_asset_type(item)
        add(
            ScientificAsset(
                asset_id=f"artifact::{path}",
                asset_type=asset_type,
                label=path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1] or path,
                role=str(item.get("kind", "")).strip() or "output_artifact",
                source_system="run_manifest",
                status="present" if item.get("exists") else "planned",
                governance_status=str(item.get("scope", "")).strip(),
                path_or_reference=path,
                project_id=project_id,
                topic=topic,
                metadata=item,
            )
        )

    if systematic_review_summary:
        review_id = f"systematic-review::{_slugify(topic)}"
        add(
            ScientificAsset(
                asset_id=review_id,
                asset_type="systematic_review",
                label=str(systematic_review_summary.get("review_question", "")).strip() or topic,
                role="evidence_synthesis",
                source_system="literature_workspace",
                status=str(systematic_review_summary.get("review_protocol_version", "draft")).strip() or "draft",
                governance_status="needs_review" if systematic_review_summary.get("review_protocol_gaps") else "reviewed",
                project_id=project_id,
                topic=topic,
                metadata=systematic_review_summary,
            )
        )

    if evidence_review_summary:
        review_id = str(evidence_review_summary.get("review_id", "")).strip() or f"evidence-review::{_slugify(topic)}"
        add(
            ScientificAsset(
                asset_id=review_id,
                asset_type="evidence_review",
                label=str(evidence_review_summary.get("review_question", "")).strip() or topic,
                role="evidence_quality_governance",
                source_system="evidence_review_engine",
                status=str(evidence_review_summary.get("review_readiness", "draft")).strip() or "draft",
                governance_status=str(evidence_review_summary.get("review_quality_state", "needs_review")).strip(),
                project_id=project_id,
                topic=topic,
                parent_asset_ids=[f"systematic-review::{_slugify(topic)}"] if systematic_review_summary else [],
                evidence_refs=[
                    str(item.get("evidence_id", "")).strip()
                    for item in evidence_review_summary.get("assessment_records", [])
                    if isinstance(item, dict) and str(item.get("evidence_id", "")).strip()
                ],
                metadata=evidence_review_summary,
            )
        )

    if causal_graph_summary:
        causal_id = f"causal-model::{_slugify(topic)}"
        add(
            ScientificAsset(
                asset_id=causal_id,
                asset_type="causal_model",
                label=topic,
                role="causal_explanation",
                source_system="causal_reasoning",
                status="active",
                governance_status="identification_risk" if causal_graph_summary.get("identifiability_risks") else "identified",
                project_id=project_id,
                topic=topic,
                metadata=causal_graph_summary,
            )
        )

    if autonomous_controller_summary:
        controller_id = (
            str(autonomous_controller_summary.get("controller_id", "")).strip()
            or f"autonomous-controller::{_slugify(topic)}"
        )
        add(
            ScientificAsset(
                asset_id=controller_id,
                asset_type="autonomous_controller",
                label=f"autonomous controller for {topic}",
                role="research_loop_control",
                source_system="autonomous_research_controller",
                status=str(autonomous_controller_summary.get("controller_state", "continue_autonomously")).strip(),
                governance_status=(
                    "human_pause_required"
                    if autonomous_controller_summary.get("must_pause_for_human")
                    else "autonomous_continuation_allowed"
                ),
                project_id=project_id,
                topic=topic,
                related_decision_ids=[
                    str(trace.get("source_id", "")).strip()
                    for trace in autonomous_controller_summary.get("decision_trace", [])
                    if isinstance(trace, dict)
                    and str(trace.get("source_type", "")).strip() == "scientific_decision"
                    and str(trace.get("source_id", "")).strip()
                ],
                metadata=autonomous_controller_summary,
            )
        )

    if experiment_execution_loop_summary:
        scheduler_id = (
            str(experiment_execution_loop_summary.get("scheduler_id", "")).strip()
            or f"experiment-scheduler::{_slugify(topic)}"
        )
        add(
            ScientificAsset(
                asset_id=scheduler_id,
                asset_type="experiment_scheduler",
                label=f"experiment scheduler for {topic}",
                role="experiment_execution_loop",
                source_system="experiment_scheduler",
                status=str(experiment_execution_loop_summary.get("scheduler_state", "needs_candidates")).strip(),
                governance_status=(
                    "execution_ready"
                    if experiment_execution_loop_summary.get("scheduler_state") == "ready_to_schedule"
                    else "execution_gated"
                ),
                project_id=project_id,
                topic=topic,
                parent_asset_ids=[
                    str(item.get("experiment_id", "")).strip()
                    for item in experiment_execution_loop_summary.get("execution_queue", [])
                    if isinstance(item, dict) and str(item.get("experiment_id", "")).strip()
                ],
                metadata=experiment_execution_loop_summary,
            )
        )

    if optimization_adapter_summary:
        adapter_id = (
            str(optimization_adapter_summary.get("adapter_id", "")).strip()
            or f"optimization-adapter::{_slugify(topic)}"
        )
        add(
            ScientificAsset(
                asset_id=adapter_id,
                asset_type="optimization_adapter",
                label=f"optimization adapter for {topic}",
                role="parameter_optimization_planning",
                source_system="optimization_adapter",
                status=str(optimization_adapter_summary.get("adapter_state", "no_parameter_optimization_candidates")).strip(),
                governance_status="confirmatory_required",
                project_id=project_id,
                topic=topic,
                parent_asset_ids=[
                    str(plan.get("experiment_id", "")).strip()
                    for plan in optimization_adapter_summary.get("plans", [])
                    if isinstance(plan, dict) and str(plan.get("experiment_id", "")).strip()
                ],
                metadata=optimization_adapter_summary,
            )
        )

    if discipline_adapter_summary:
        adapter_id = (
            str(discipline_adapter_summary.get("adapter_id", "")).strip()
            or f"discipline-adapter::{_slugify(topic)}"
        )
        add(
            ScientificAsset(
                asset_id=adapter_id,
                asset_type="discipline_adapter",
                label=f"discipline adapter for {topic}",
                role="discipline_specific_execution_contract",
                source_system="discipline_adapter",
                status=str(discipline_adapter_summary.get("adapter_state", "no_execution_bindings")).strip(),
                governance_status="plan_only_until_approved",
                project_id=project_id,
                topic=topic,
                parent_asset_ids=[
                    str(binding.get("experiment_id", "")).strip()
                    for binding in discipline_adapter_summary.get("bindings", [])
                    if isinstance(binding, dict) and str(binding.get("experiment_id", "")).strip()
                ],
                metadata=discipline_adapter_summary,
            )
        )

    if execution_adapter_registry_summary:
        registry_id = (
            str(execution_adapter_registry_summary.get("registry_id", "")).strip()
            or f"execution-adapter-registry::{_slugify(topic)}"
        )
        add(
            ScientificAsset(
                asset_id=registry_id,
                asset_type="execution_adapter_registry",
                label=f"execution adapter registry for {topic}",
                role="execution_handoff_routing",
                source_system="execution_adapter_registry",
                status=str(execution_adapter_registry_summary.get("registry_state", "no_scheduled_experiments")).strip(),
                governance_status="plan_only_until_approved",
                project_id=project_id,
                topic=topic,
                parent_asset_ids=[
                    str(item.get("experiment_id", "")).strip()
                    for item in execution_adapter_registry_summary.get("execution_packages", [])
                    if isinstance(item, dict) and str(item.get("experiment_id", "")).strip()
                ],
                metadata=execution_adapter_registry_summary,
            )
        )

    if run_handoff_contract_summary:
        contract_id = (
            str(run_handoff_contract_summary.get("handoff_contract_id", "")).strip()
            or f"run-handoff-contract::{_slugify(topic)}"
        )
        add(
            ScientificAsset(
                asset_id=contract_id,
                asset_type="run_handoff_contract",
                label=f"run handoff contract for {topic}",
                role="execution_result_return_contract",
                source_system="run_handoff",
                status=str(run_handoff_contract_summary.get("contract_state", "no_execution_packages")).strip(),
                governance_status="required_for_external_execution",
                project_id=project_id,
                topic=topic,
                parent_asset_ids=[
                    str(contract.get("package_id", "")).strip()
                    for contract in run_handoff_contract_summary.get("contracts", [])
                    if isinstance(contract, dict) and str(contract.get("package_id", "")).strip()
                ],
                metadata=run_handoff_contract_summary,
            )
        )

    if kaivu_evaluation_harness_summary:
        harness_id = (
            str(kaivu_evaluation_harness_summary.get("harness_id", "")).strip()
            or f"kaivu-evaluation-harness::{_slugify(topic)}"
        )
        add(
            ScientificAsset(
                asset_id=harness_id,
                asset_type="kaivu_evaluation_harness",
                label=f"Kaivu evaluation harness for {topic}",
                role="system_quality_evaluation",
                source_system="evaluation_harness",
                status=str(kaivu_evaluation_harness_summary.get("release_state", "not_ready")).strip(),
                governance_status="required_before_release",
                project_id=project_id,
                topic=topic,
                evidence_refs=[
                    str(axis.get("axis_id", "")).strip()
                    for axis in kaivu_evaluation_harness_summary.get("axes", [])
                    if isinstance(axis, dict) and str(axis.get("axis_id", "")).strip()
                ],
                metadata=kaivu_evaluation_harness_summary,
            )
        )

    asset_dicts = [asset.to_dict() for asset in assets.values()]
    asset_type_counts = _count_by(asset_dicts, "asset_type")
    role_counts = _count_by(asset_dicts, "role")
    source_system_counts = _count_by(asset_dicts, "source_system")
    governed_assets = [
        item for item in asset_dicts if str(item.get("governance_status", "")).strip()
    ]
    review_required_assets = [
        item["asset_id"]
        for item in asset_dicts
        if "review" in str(item.get("governance_status", "")).lower()
        or str(item.get("status", "")).lower() in {"revise", "block", "governance_blocking"}
    ]
    return {
        "asset_count": len(asset_dicts),
        "asset_type_counts": asset_type_counts,
        "role_counts": role_counts,
        "source_system_counts": source_system_counts,
        "governed_asset_count": len(governed_assets),
        "review_required_assets": review_required_assets[:20],
        "assets": asset_dicts[:200],
    }


def _artifact_asset_type(item: dict[str, Any]) -> str:
    path = str(item.get("path", "")).lower()
    kind = str(item.get("kind", "")).lower()
    if kind in {"dataset", "table"} or path.endswith((".csv", ".tsv", ".xlsx", ".parquet")):
        return "dataset"
    if kind in {"figure", "plot"} or path.endswith((".png", ".jpg", ".jpeg", ".svg", ".pdf")):
        return "figure"
    if kind == "report" or path.endswith(".md"):
        return "report"
    return "artifact"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys([str(item).strip() for item in values if str(item).strip()]))


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key, "")).strip() or "unknown"
        counts[value] = counts.get(value, 0) + 1
    return counts


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "asset"



