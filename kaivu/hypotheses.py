from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class HypothesisTheoryObject:
    theory_object_id: str
    hypothesis_id: str
    name: str
    version: str
    status: str
    theory_family: str
    mechanism_chain: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    boundary_conditions: list[str] = field(default_factory=list)
    predictions: list[str] = field(default_factory=list)
    counterfactual_predictions: list[str] = field(default_factory=list)
    falsification_tests: list[str] = field(default_factory=list)
    measurable_variables: list[str] = field(default_factory=list)
    discriminating_experiments: list[str] = field(default_factory=list)
    failure_conditions: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    competing_hypothesis_ids: list[str] = field(default_factory=list)
    negative_result_refs: list[str] = field(default_factory=list)
    validation: dict[str, Any] = field(default_factory=dict)
    gate: dict[str, Any] = field(default_factory=dict)
    theory_maturity: str = "flat"
    decision_state: str = "observe"
    missing_theory_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_hypothesis_theory_summary(
    *,
    claim_graph: dict[str, Any],
    steps: list[Any],
    causal_graph_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    hypotheses = [
        item
        for item in claim_graph.get("hypotheses", [])
        if isinstance(item, dict)
    ]
    if not hypotheses:
        return {}

    validations = _index_by_hypothesis_id(
        _first_step_list(steps, profile_name="hypothesis_generator", key="hypothesis_validations")
    )
    gates = _index_by_hypothesis_id(
        _first_step_list(steps, profile_name="hypothesis_generator", key="hypothesis_gates")
    )
    mechanism_items = _first_step_list(steps, profile_name="hypothesis_generator", key="mechanism_map")
    counterfactual = _first_step_object(
        steps,
        profile_name="experiment_designer",
        key="counterfactual_experiment_plan",
    )
    relations = [
        item
        for item in claim_graph.get("hypothesis_relations", [])
        if isinstance(item, dict)
    ]
    negative_links = [
        item
        for item in claim_graph.get("negative_result_links", [])
        if isinstance(item, dict)
    ]
    causal_graph_summary = causal_graph_summary or {}

    objects: list[HypothesisTheoryObject] = []
    for item in hypotheses:
        hypothesis_id = str(item.get("global_hypothesis_id") or item.get("hypothesis_id") or "").strip()
        if not hypothesis_id:
            continue
        local_id = str(item.get("hypothesis_id", "")).strip()
        name = str(item.get("name", "")).strip() or hypothesis_id
        validation = _lookup_hypothesis_record(validations, hypothesis_id, local_id)
        gate = _lookup_hypothesis_record(gates, hypothesis_id, local_id)
        mechanisms = _mechanisms_for_hypothesis(
            mechanism_items=mechanism_items,
            hypothesis_id=hypothesis_id,
            local_id=local_id,
            fallback=str(item.get("mechanism", "")).strip(),
        )
        competitors = _related_hypotheses(
            relations=relations,
            hypothesis_id=hypothesis_id,
            local_id=local_id,
            relation_names={"competes_with", "contradicts", "refutes"},
        )
        negative_refs = [
            str(link.get("negative_result_id", "")).strip()
            for link in negative_links
            if _same_hypothesis_ref(str(link.get("hypothesis_id", "")), hypothesis_id, local_id)
            and str(link.get("negative_result_id", "")).strip()
        ]
        assumptions = _string_list(item.get("assumptions", []))
        failure_conditions = _string_list(item.get("failure_conditions", []))
        prediction = str(item.get("prediction", "")).strip()
        falsification_test = str(item.get("falsifiability_test", "")).strip()
        boundary_conditions = _string_list(item.get("boundary_conditions", []))
        if not boundary_conditions:
            boundary_conditions = _infer_boundary_conditions(assumptions)
        counterfactual_predictions = list(
            dict.fromkeys(
                _string_list(counterfactual.get("if_true_predictions", []))
                + _string_list(counterfactual.get("if_false_predictions", []))
            )
        )[:8]
        discriminating_experiments = _string_list(counterfactual.get("discriminative_experiments", []))[:8]
        measurable_variables = list(
            dict.fromkeys(
                _extract_candidate_variables(prediction)
                + _string_list(causal_graph_summary.get("measured_variables", []))
                + _string_list(causal_graph_summary.get("outcome_variables", []))
            )
        )[:8]
        missing = _missing_fields(
            {
                "mechanism_chain": mechanisms,
                "boundary_conditions": boundary_conditions,
                "predictions": [prediction] if prediction else [],
                "falsification_tests": [falsification_test] if falsification_test else [],
                "measurable_variables": measurable_variables,
                "discriminating_experiments": discriminating_experiments,
            }
        )
        decision_state = _decision_state(
            status=str(item.get("status", "active")).strip(),
            gate=gate,
            validation=validation,
            negative_refs=negative_refs,
            missing_fields=missing,
        )
        objects.append(
            HypothesisTheoryObject(
                theory_object_id=f"hypothesis-theory::{_slugify(hypothesis_id)}",
                hypothesis_id=hypothesis_id,
                name=name,
                version=str(item.get("version", "")).strip(),
                status=str(item.get("status", "active")).strip() or "active",
                theory_family=_family_name(name),
                mechanism_chain=mechanisms,
                assumptions=assumptions,
                boundary_conditions=boundary_conditions,
                predictions=[prediction] if prediction else [],
                counterfactual_predictions=counterfactual_predictions,
                falsification_tests=[falsification_test] if falsification_test else [],
                measurable_variables=measurable_variables,
                discriminating_experiments=discriminating_experiments,
                failure_conditions=failure_conditions,
                evidence_refs=_string_list(item.get("evidence_refs", [])),
                competing_hypothesis_ids=competitors,
                negative_result_refs=list(dict.fromkeys(negative_refs))[:8],
                validation=validation,
                gate=gate,
                theory_maturity=_theory_maturity(
                    mechanism_chain=mechanisms,
                    boundary_conditions=boundary_conditions,
                    predictions=[prediction] if prediction else [],
                    falsification_tests=[falsification_test] if falsification_test else [],
                    counterfactual_predictions=counterfactual_predictions,
                    missing_fields=missing,
                ),
                decision_state=decision_state,
                missing_theory_fields=missing,
            )
        )

    object_dicts = [item.to_dict() for item in objects]
    maturity_counts = _count_by(object_dicts, "theory_maturity")
    decision_counts = _count_by(object_dicts, "decision_state")
    missing_field_counts: dict[str, int] = {}
    for item in object_dicts:
        for field_name in item.get("missing_theory_fields", []):
            missing_field_counts[field_name] = missing_field_counts.get(field_name, 0) + 1
    return {
        "theory_object_count": len(object_dicts),
        "maturity_counts": maturity_counts,
        "decision_state_counts": decision_counts,
        "missing_field_counts": missing_field_counts,
        "advance_candidates": [
            item["hypothesis_id"]
            for item in object_dicts
            if item.get("decision_state") == "advance"
        ][:10],
        "revise_candidates": [
            item["hypothesis_id"]
            for item in object_dicts
            if item.get("decision_state") == "revise"
        ][:10],
        "blocked_candidates": [
            item["hypothesis_id"]
            for item in object_dicts
            if item.get("decision_state") == "block"
        ][:10],
        "objects": object_dicts,
    }


def _first_step_list(steps: list[Any], *, profile_name: str, key: str) -> list[dict[str, Any]]:
    for step in steps:
        if getattr(step, "profile_name", "") != profile_name:
            continue
        parsed = getattr(step, "parsed_output", {})
        value = parsed.get(key, []) if isinstance(parsed, dict) else []
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _first_step_object(steps: list[Any], *, profile_name: str, key: str) -> dict[str, Any]:
    for step in steps:
        if getattr(step, "profile_name", "") != profile_name:
            continue
        parsed = getattr(step, "parsed_output", {})
        value = parsed.get(key, {}) if isinstance(parsed, dict) else {}
        if isinstance(value, dict):
            return value
    return {}


def _index_by_hypothesis_id(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for item in items:
        hypothesis_id = str(item.get("hypothesis_id", "")).strip()
        if hypothesis_id:
            output[hypothesis_id] = item
    return output


def _lookup_hypothesis_record(
    records: dict[str, dict[str, Any]],
    hypothesis_id: str,
    local_id: str,
) -> dict[str, Any]:
    return records.get(hypothesis_id) or records.get(local_id) or {}


def _mechanisms_for_hypothesis(
    *,
    mechanism_items: list[dict[str, Any]],
    hypothesis_id: str,
    local_id: str,
    fallback: str,
) -> list[str]:
    matches = []
    for mechanism in mechanism_items:
        supported = _string_list(mechanism.get("supports_hypothesis_ids", []))
        if any(_same_hypothesis_ref(ref, hypothesis_id, local_id) for ref in supported):
            label = str(mechanism.get("label", "")).strip()
            if label:
                matches.append(label)
    if not matches and fallback:
        matches.append(fallback)
    return list(dict.fromkeys(matches))[:8]


def _related_hypotheses(
    *,
    relations: list[dict[str, Any]],
    hypothesis_id: str,
    local_id: str,
    relation_names: set[str],
) -> list[str]:
    related: list[str] = []
    for relation in relations:
        relation_name = str(relation.get("relation", "")).strip().lower()
        if relation_name not in relation_names:
            continue
        source = str(relation.get("source", "") or relation.get("source_hypothesis_id", "")).strip()
        target = str(relation.get("target", "") or relation.get("target_hypothesis_id", "")).strip()
        if _same_hypothesis_ref(source, hypothesis_id, local_id) and target:
            related.append(target)
        elif _same_hypothesis_ref(target, hypothesis_id, local_id) and source:
            related.append(source)
    return list(dict.fromkeys(related))[:8]


def _same_hypothesis_ref(ref: str, hypothesis_id: str, local_id: str) -> bool:
    ref = str(ref).strip()
    return bool(ref) and (ref == hypothesis_id or ref == local_id or ref.endswith(f"::{local_id}"))


def _infer_boundary_conditions(assumptions: list[str]) -> list[str]:
    return [
        item
        for item in assumptions
        if any(token in item.lower() for token in ("when", "under", "only", "if ", "provided", "condition"))
    ][:5]


def _extract_candidate_variables(text: str) -> list[str]:
    candidates: list[str] = []
    for token in str(text).replace("/", " ").replace("-", " ").split():
        cleaned = "".join(ch for ch in token if ch.isalnum() or ch == "_").strip()
        if len(cleaned) >= 4 and cleaned.lower() not in {"increase", "decrease", "higher", "lower", "change"}:
            candidates.append(cleaned)
    return list(dict.fromkeys(candidates))[:5]


def _missing_fields(payload: dict[str, list[str]]) -> list[str]:
    return [key for key, value in payload.items() if not value]


def _decision_state(
    *,
    status: str,
    gate: dict[str, Any],
    validation: dict[str, Any],
    negative_refs: list[str],
    missing_fields: list[str],
) -> str:
    gate_decision = str(gate.get("gate_decision", "")).strip().lower()
    if gate_decision in {"reject", "block"} or status.lower() == "rejected":
        return "block"
    if gate_decision == "revise" or status.lower() in {"revised", "deprecated"}:
        return "revise"
    if negative_refs:
        return "revise"
    low_scores = [
        float(validation.get(field, 1.0) or 0)
        for field in (
            "falsifiability_score",
            "testability_score",
            "mechanistic_coherence_score",
            "evidence_grounding_score",
        )
        if field in validation
    ]
    if any(score < 0.5 for score in low_scores) or len(missing_fields) >= 3:
        return "revise"
    if gate_decision == "accept" and len(missing_fields) <= 1:
        return "advance"
    return "observe"


def _theory_maturity(
    *,
    mechanism_chain: list[str],
    boundary_conditions: list[str],
    predictions: list[str],
    falsification_tests: list[str],
    counterfactual_predictions: list[str],
    missing_fields: list[str],
) -> str:
    if not mechanism_chain or not predictions:
        return "flat"
    if missing_fields:
        return "structured"
    if falsification_tests and boundary_conditions and counterfactual_predictions:
        return "predictive"
    return "structured"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key, "")).strip() or "unknown"
        counts[value] = counts.get(value, 0) + 1
    return counts


def _family_name(name: str) -> str:
    return str(name).split(":", 1)[0].strip() or "general"


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "hypothesis"


