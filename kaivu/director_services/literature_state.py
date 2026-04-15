from __future__ import annotations

from typing import Any


def collect_citations(steps: list[Any]) -> list[dict[str, Any]]:
    citations: dict[str, dict[str, Any]] = {}
    for step in steps:
        library = step.state.scratchpad.get("citation_library", {})
        if not isinstance(library, dict):
            continue
        for key, value in library.items():
            if not isinstance(value, dict):
                continue
            if key not in citations:
                citations[key] = value
            else:
                merged = dict(citations[key])
                for field, item in value.items():
                    if item not in (None, "", [], {}):
                        merged[field] = item
                citations[key] = merged
    return list(citations.values())


def summarize_quality_grades(grades: list[str]) -> dict[str, Any]:
    if not grades:
        return {"dominant_grade": "unclear", "counts": {}}
    counts: dict[str, int] = {}
    for grade in grades:
        normalized = grade.strip().lower()
        if not normalized:
            continue
        counts[normalized] = counts.get(normalized, 0) + 1
    dominant = max(counts.items(), key=lambda item: item[1])[0] if counts else "unclear"
    return {"dominant_grade": dominant, "counts": counts}


def summarize_conflict_groups(conflict_groups: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    groups: list[dict[str, Any]] = []
    for group_name, items in conflict_groups.items():
        directions = {
            str(item.get("evidence_direction", "")).strip().lower()
            for item in items
            if str(item.get("evidence_direction", "")).strip()
        }
        strengths = [
            str(item.get("strength", "")).strip().lower()
            for item in items
            if str(item.get("strength", "")).strip()
        ]
        groups.append(
            {
                "conflict_group": group_name,
                "evidence_count": len(items),
                "directions": sorted(directions),
                "has_directional_conflict": len(directions) > 1,
                "strengths": strengths,
                "notes": [
                    str(item.get("conflict_note", "")).strip()
                    for item in items
                    if str(item.get("conflict_note", "")).strip()
                ][:5],
            }
        )
    return {
        "conflict_group_count": len(groups),
        "directional_conflict_count": len(
            [item for item in groups if item.get("has_directional_conflict")]
        ),
        "groups": groups[:10],
    }


def derive_literature_synthesis(steps: list[Any]) -> dict[str, Any]:
    consensus_findings: list[str] = []
    contested_questions: list[str] = []
    evidence_matrix: list[dict[str, Any]] = []
    evidence_gaps: list[str] = []
    for step in steps:
        parsed = step.parsed_output
        synthesis = parsed.get("literature_synthesis", {})
        if isinstance(synthesis, dict):
            consensus_findings.extend(
                str(item) for item in synthesis.get("consensus_findings", []) if str(item).strip()
            )
            contested_questions.extend(
                str(item) for item in synthesis.get("contested_questions", []) if str(item).strip()
            )
            for item in synthesis.get("evidence_matrix", []):
                if isinstance(item, dict):
                    evidence_matrix.append(item)
        evidence_gaps.extend(
            str(item) for item in parsed.get("evidence_gaps", []) if str(item).strip()
        )
    return {
        "consensus_findings": list(dict.fromkeys(consensus_findings))[:8],
        "contested_questions": list(dict.fromkeys(contested_questions))[:8],
        "evidence_matrix": evidence_matrix[:12],
        "evidence_gaps": list(dict.fromkeys(evidence_gaps))[:10],
    }


def derive_systematic_review_draft(steps: list[Any]) -> dict[str, Any]:
    review_question = ""
    review_protocol_version = ""
    study_types: list[str] = []
    inclusion_logic: list[str] = []
    exclusion_logic: list[str] = []
    screening_decisions: list[str] = []
    exclusion_reasons: list[str] = []
    evidence_balance: list[str] = []
    bias_hotspots: list[str] = []
    evidence_table_focus: list[str] = []
    evidence_table_records: list[str] = []
    review_protocol_gaps: list[str] = []
    quality_counts: dict[str, int] = {}
    screened_evidence_count = 0
    for step in steps:
        parsed = step.parsed_output
        systematic = parsed.get("systematic_review", {})
        if isinstance(systematic, dict):
            review_question = review_question or str(systematic.get("review_question", "")).strip()
            review_protocol_version = review_protocol_version or str(systematic.get("review_protocol_version", "")).strip()
            study_types.extend(str(item) for item in systematic.get("study_type_hierarchy", []) if str(item).strip())
            inclusion_logic.extend(str(item) for item in systematic.get("inclusion_logic", []) if str(item).strip())
            exclusion_logic.extend(str(item) for item in systematic.get("exclusion_logic", []) if str(item).strip())
            screening_decisions.extend(str(item) for item in systematic.get("screening_decisions", []) if str(item).strip())
            exclusion_reasons.extend(str(item) for item in systematic.get("exclusion_reasons", []) if str(item).strip())
            evidence_balance.extend(str(item) for item in systematic.get("evidence_balance", []) if str(item).strip())
            bias_hotspots.extend(str(item) for item in systematic.get("bias_hotspots", []) if str(item).strip())
            evidence_table_focus.extend(str(item) for item in systematic.get("evidence_table_focus", []) if str(item).strip())
            evidence_table_records.extend(str(item) for item in systematic.get("evidence_table_records", []) if str(item).strip())
            review_protocol_gaps.extend(str(item) for item in systematic.get("review_protocol_gaps", []) if str(item).strip())
        for item in parsed.get("evidence", []) if isinstance(parsed.get("evidence", []), list) else []:
            if not isinstance(item, dict):
                continue
            screened_evidence_count += 1
            study_type = str(item.get("study_type", "")).strip()
            quality_grade = str(item.get("quality_grade", "")).strip().lower()
            if study_type:
                study_types.append(study_type)
                screening_decisions.append(f"screened evidence from {study_type}")
            if quality_grade:
                quality_counts[quality_grade] = quality_counts.get(quality_grade, 0) + 1
            bias = str(item.get("bias_risk", "")).strip()
            if bias and bias.lower() in {"high", "medium", "unclear"}:
                bias_hotspots.append(f"{study_type or 'unknown study'} bias risk {bias.lower()}")
                exclusion_reasons.append(
                    f"downweight {study_type or 'unknown study'} because bias risk is {bias.lower()}"
                )
            conflict_group = str(item.get("conflict_group", "")).strip()
            if conflict_group:
                evidence_table_focus.append(f"conflict group {conflict_group}")
                evidence_table_records.append(
                    f"{study_type or 'unknown study'} -> conflict group {conflict_group}"
                )
    ordered_types = list(dict.fromkeys(study_types))
    balance_lines = list(dict.fromkeys(evidence_balance))
    if quality_counts:
        balance_lines.append(
            "quality counts: "
            + ", ".join(f"{key}={value}" for key, value in sorted(quality_counts.items()))
        )
    if not inclusion_logic:
        inclusion_logic = ["Prioritize primary evidence, direct measurements, and reproducible analyses."]
    if not exclusion_logic:
        exclusion_logic = ["Downweight weakly described, high-bias, or indirect evidence."]
    if not exclusion_reasons:
        exclusion_reasons = ["Exclude or downweight evidence with unclear methods, weak traceability, or high bias."]
    if not screening_decisions:
        screening_decisions = ["Screen studies by direct relevance, study quality, and traceable methodology."]
    if not evidence_table_focus and review_question:
        evidence_table_focus = [review_question]
    if not evidence_table_records and evidence_table_focus:
        evidence_table_records = [f"focus evidence table on {item}" for item in evidence_table_focus[:3]]
    if not review_question:
        review_protocol_gaps.append("review question is still underspecified")
    if not review_protocol_version:
        review_protocol_gaps.append("review protocol version has not been declared")
        review_protocol_version = "draft-v1"
    if not ordered_types:
        review_protocol_gaps.append("study hierarchy has not been stabilized")
    if screened_evidence_count < 3:
        review_protocol_gaps.append("evidence screening depth is still shallow")
    return {
        "review_question": review_question,
        "review_protocol_version": review_protocol_version,
        "study_type_hierarchy": ordered_types[:10],
        "inclusion_logic": list(dict.fromkeys(inclusion_logic))[:6],
        "exclusion_logic": list(dict.fromkeys(exclusion_logic))[:6],
        "screening_decisions": list(dict.fromkeys(screening_decisions))[:8],
        "exclusion_reasons": list(dict.fromkeys(exclusion_reasons))[:8],
        "evidence_balance": balance_lines[:8],
        "bias_hotspots": list(dict.fromkeys(bias_hotspots))[:8],
        "evidence_table_focus": list(dict.fromkeys(evidence_table_focus))[:8],
        "evidence_table_records": list(dict.fromkeys(evidence_table_records))[:10],
        "review_protocol_gaps": list(dict.fromkeys(review_protocol_gaps))[:8],
        "screened_evidence_count": screened_evidence_count,
        "study_type_counts": {item: study_types.count(item) for item in ordered_types[:10]},
    }


__all__ = [
    "collect_citations",
    "derive_literature_synthesis",
    "derive_systematic_review_draft",
    "summarize_conflict_groups",
    "summarize_quality_grades",
]
