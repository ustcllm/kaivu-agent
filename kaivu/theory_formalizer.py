from __future__ import annotations

from typing import Any


def build_theory_prediction_compiler_summary(
    *,
    topic: str,
    claim_graph: dict[str, Any],
    hypothesis_theory_summary: dict[str, Any],
    mechanism_reasoning_summary: dict[str, Any] | None = None,
    problem_reframer_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    theory_objects = _items(hypothesis_theory_summary.get("objects", []))
    mechanism_reasoning_summary = mechanism_reasoning_summary or {}
    problem_reframer_summary = problem_reframer_summary or {}
    compiled = [
        _compile_theory_object(
            topic=topic,
            item=item,
            mechanism_reasoning_summary=mechanism_reasoning_summary,
            problem_reframer_summary=problem_reframer_summary,
        )
        for item in theory_objects
    ]
    prediction_table = [
        prediction
        for item in compiled
        for prediction in item.get("observable_predictions", [])
        if isinstance(prediction, dict)
    ]
    discriminators = [
        item
        for theory in compiled
        for item in theory.get("discriminating_tests", [])
        if isinstance(item, dict)
    ]
    missing_counts: dict[str, int] = {}
    for item in compiled:
        for field in _strings(item.get("missing_formal_fields", [])):
            missing_counts[field] = missing_counts.get(field, 0) + 1
    return {
        "theory_prediction_compiler_id": f"theory-prediction-compiler::{_slugify(topic)}",
        "topic": topic,
        "compiled_theory_count": len(compiled),
        "prediction_count": len(prediction_table),
        "discriminating_test_count": len(discriminators),
        "formalization_readiness": "high" if compiled and not missing_counts else "medium" if compiled else "low",
        "missing_formal_field_counts": missing_counts,
        "compiled_theories": compiled,
        "prediction_table": prediction_table[:80],
        "discriminating_tests": discriminators[:80],
        "scheduler_constraints": _scheduler_constraints(compiled, problem_reframer_summary),
        "claim_graph_links": _claim_graph_links(compiled, claim_graph),
    }


def _compile_theory_object(
    *,
    topic: str,
    item: dict[str, Any],
    mechanism_reasoning_summary: dict[str, Any],
    problem_reframer_summary: dict[str, Any],
) -> dict[str, Any]:
    hypothesis_id = str(item.get("hypothesis_id", "")).strip()
    variables = _variables(item)
    mechanisms = _strings(item.get("mechanism_chain", []))
    assumptions = _strings(item.get("assumptions", []))
    boundaries = _strings(item.get("boundary_conditions", []))
    predictions = _strings(item.get("predictions", [])) or [f"{hypothesis_id or topic} should produce a measurable pattern"]
    falsification_tests = _strings(item.get("falsification_tests", []))
    counterfactuals = _strings(item.get("counterfactual_predictions", []))
    frame_type = str(problem_reframer_summary.get("selected_frame", {}).get("frame_type", "baseline")).strip()
    observable_predictions = [
        {
            "prediction_id": f"prediction::{_slugify(hypothesis_id or topic)}::{index}",
            "hypothesis_id": hypothesis_id,
            "observable": prediction,
            "variables": variables[:8],
            "expected_direction": _expected_direction(prediction),
            "boundary_conditions": boundaries[:8],
            "decision_threshold": _decision_threshold(topic, prediction, frame_type),
            "falsifies_if": _falsifies_if(prediction, falsification_tests),
        }
        for index, prediction in enumerate(predictions, start=1)
    ]
    discriminating_tests = _discriminating_tests(
        hypothesis_id=hypothesis_id,
        mechanisms=mechanisms,
        predictions=observable_predictions,
        counterfactuals=counterfactuals,
        mechanism_reasoning_summary=mechanism_reasoning_summary,
    )
    missing = []
    if not variables:
        missing.append("variables")
    if not mechanisms:
        missing.append("mechanism_chain")
    if not boundaries:
        missing.append("boundary_conditions")
    if not falsification_tests:
        missing.append("falsification_tests")
    if not discriminating_tests:
        missing.append("discriminating_tests")
    return {
        "compiled_theory_id": f"compiled-theory::{_slugify(hypothesis_id or topic)}",
        "hypothesis_id": hypothesis_id,
        "theory_family": str(item.get("theory_family", "general")).strip(),
        "formal_objects": {
            "variables": variables,
            "mechanism_chain": mechanisms,
            "assumptions": assumptions,
            "boundary_conditions": boundaries,
            "counterfactual_predictions": counterfactuals,
        },
        "observable_predictions": observable_predictions,
        "discriminating_tests": discriminating_tests,
        "missing_formal_fields": missing,
        "formal_state": "predictive" if not missing else "needs_formalization",
        "source_theory_object_id": str(item.get("theory_object_id", "")).strip(),
        "source_evidence_refs": _strings(item.get("evidence_refs", [])),
    }


def _variables(item: dict[str, Any]) -> list[dict[str, Any]]:
    values = _strings(item.get("measurable_variables", []))
    output: list[dict[str, Any]] = []
    for value in values:
        lowered = value.lower()
        role = "outcome"
        if any(token in lowered for token in ["dose", "temperature", "pressure", "input", "concentration", "parameter"]):
            role = "intervention"
        elif any(token in lowered for token in ["control", "baseline", "confound"]):
            role = "control"
        output.append({"name": value, "role": role, "measurement_state": "needs_unit_or_scale"})
    return output[:12]


def _expected_direction(prediction: str) -> str:
    text = prediction.lower()
    if any(token in text for token in ["increase", "higher", "improve", "enhance", "raise"]):
        return "increase"
    if any(token in text for token in ["decrease", "lower", "reduce", "suppress", "drop"]):
        return "decrease"
    if any(token in text for token in ["equal", "unchanged", "no change"]):
        return "no_change"
    return "pattern_match"


def _decision_threshold(topic: str, prediction: str, frame_type: str) -> str:
    text = f"{topic} {prediction}".lower()
    if "accuracy" in text or "benchmark" in text:
        return "predefine minimum effect over baseline and confidence interval before execution"
    if "yield" in text or "selectivity" in text or "conversion" in text:
        return "predefine minimum practical change and replicate count before execution"
    if frame_type == "operationalization":
        return "must include numeric threshold or categorical pass/fail rule before promotion"
    return "must be stated before experiment scheduling"


def _falsifies_if(prediction: str, falsification_tests: list[str]) -> str:
    if falsification_tests:
        return "; ".join(falsification_tests[:2])
    direction = _expected_direction(prediction)
    if direction == "increase":
        return "effect is absent, reversed, or explained by control/confounder"
    if direction == "decrease":
        return "effect is absent, reversed, or explained by control/confounder"
    return "observable pattern fails under the stated boundary conditions"


def _discriminating_tests(
    *,
    hypothesis_id: str,
    mechanisms: list[str],
    predictions: list[dict[str, Any]],
    counterfactuals: list[str],
    mechanism_reasoning_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    tests: list[dict[str, Any]] = []
    for index, prediction in enumerate(predictions[:4], start=1):
        tests.append(
            {
                "test_id": f"discriminator::{_slugify(hypothesis_id or 'hypothesis')}::{index}",
                "hypothesis_id": hypothesis_id,
                "target_prediction_id": prediction.get("prediction_id", ""),
                "test_logic": f"perturb the proposed mechanism and measure whether {prediction.get('observable', '')}",
                "required_controls": ["negative control", "positive or baseline control", "boundary-condition control"],
                "interpretation_rule": prediction.get("falsifies_if", ""),
            }
        )
    for index, counterfactual in enumerate(counterfactuals[:3], start=len(tests) + 1):
        tests.append(
            {
                "test_id": f"discriminator::{_slugify(hypothesis_id or 'hypothesis')}::{index}",
                "hypothesis_id": hypothesis_id,
                "target_prediction_id": "",
                "test_logic": counterfactual,
                "required_controls": ["rival mechanism control", "measurement artifact control"],
                "interpretation_rule": "different outcomes should separate rival mechanism families",
            }
        )
    competing = _strings(mechanism_reasoning_summary.get("competing_pairs", []))
    if competing and mechanisms:
        tests.append(
            {
                "test_id": f"discriminator::{_slugify(hypothesis_id or 'hypothesis')}::mechanism-pair",
                "hypothesis_id": hypothesis_id,
                "target_prediction_id": "",
                "test_logic": f"design a mechanism-pair discriminator for {competing[0]}",
                "required_controls": ["matched condition", "mechanism perturbation"],
                "interpretation_rule": "support the mechanism whose unique prediction survives controls",
            }
        )
    return tests[:8]


def _scheduler_constraints(compiled: list[dict[str, Any]], problem_reframer_summary: dict[str, Any]) -> list[str]:
    constraints = []
    for item in compiled[:6]:
        if item.get("missing_formal_fields"):
            constraints.append(
                f"do not promote {item.get('hypothesis_id', '')} until missing fields are formalized: {', '.join(_strings(item.get('missing_formal_fields', [])))}"
            )
        for test in _items(item.get("discriminating_tests", []))[:2]:
            constraints.append(f"prefer discriminating test: {test.get('test_id', '')}")
    constraints.extend(_strings(problem_reframer_summary.get("scheduler_constraints", []))[:4])
    return list(dict.fromkeys(constraints))[:12]


def _claim_graph_links(compiled: list[dict[str, Any]], claim_graph: dict[str, Any]) -> list[dict[str, Any]]:
    evidence_to_claims: dict[str, list[str]] = {}
    for edge in _items(claim_graph.get("edges", [])):
        relation = str(edge.get("relation", "")).strip()
        source = str(edge.get("source", "")).strip()
        target = str(edge.get("target", "")).strip()
        if not source or not target:
            continue
        if relation == "supported_by":
            evidence_to_claims.setdefault(target, []).append(source)
        elif relation == "supports":
            evidence_to_claims.setdefault(source, []).append(target)
    evidence_global_by_local = {
        str(item.get("evidence_id", "")).strip(): str(item.get("global_evidence_id", "")).strip()
        for item in _items(claim_graph.get("evidence", []))
        if str(item.get("evidence_id", "")).strip() and str(item.get("global_evidence_id", "")).strip()
    }
    links = []
    for item in compiled:
        hypothesis_id = str(item.get("hypothesis_id", "")).strip()
        evidence_refs = _strings(item.get("source_evidence_refs", []))
        claim_ids: list[str] = []
        for evidence_ref in evidence_refs:
            resolved_ref = evidence_global_by_local.get(evidence_ref, evidence_ref)
            claim_ids.extend(evidence_to_claims.get(resolved_ref, []))
        for claim_id in list(dict.fromkeys(claim_ids))[:6]:
            links.append({"source": hypothesis_id, "target": claim_id, "relation": "explains_or_predicts"})
    return links[:30]


def _items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value).strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "theory"
