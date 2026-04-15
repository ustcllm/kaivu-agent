from __future__ import annotations

from ..quality_control import QualityControlCheckDefinition, QualityControlChecklist


def mathematics_quality_control_checklist() -> QualityControlChecklist:
    return QualityControlChecklist(
        discipline="mathematics",
        checks=[
            QualityControlCheckDefinition(
                check_id="assumptions_explicit",
                title="Assumptions made explicit",
                rationale="A proof or conjecture assessment is uninterpretable if assumptions are implicit.",
                severity_if_failed="high",
            ),
            QualityControlCheckDefinition(
                check_id="edge_cases_reviewed",
                title="Edge cases reviewed",
                rationale="Boundary cases often carry the real failure mode of a mathematical argument.",
            ),
            QualityControlCheckDefinition(
                check_id="lemma_dependencies_tracked",
                title="Lemma dependencies tracked",
                rationale="Missing dependencies make later verification fragile.",
            ),
            QualityControlCheckDefinition(
                check_id="counterexample_search_documented",
                title="Counterexample search documented",
                rationale="A positive argument is much weaker if no systematic counterexample search was attempted.",
                required=False,
            ),
            QualityControlCheckDefinition(
                check_id="proof_gaps_marked",
                title="Proof gaps marked explicitly",
                rationale="Unmarked proof gaps can be mistaken for established results.",
                severity_if_failed="high",
            ),
        ],
    )


