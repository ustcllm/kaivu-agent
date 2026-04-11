from __future__ import annotations

from dataclasses import dataclass, field

from .model_registry import AgentModelConfig
from .structured_output import StructuredSchema


def _string_list_schema(description: str) -> dict:
    return {
        "type": "array",
        "description": description,
        "items": {"type": "string"},
    }


def _claim_schema(description: str) -> dict:
    return {
        "type": "array",
        "description": description,
        "items": {
            "type": "object",
            "properties": {
                "claim_id": {"type": "string"},
                "statement": {"type": "string"},
                "claim_type": {
                    "type": "string",
                    "description": "One of finding, hypothesis, method, risk, recommendation.",
                },
                "evidence_direction": {
                    "type": "string",
                    "description": "One of supports, weakens, mixed, contextual.",
                },
                "supports": _string_list_schema("Evidence ids supporting this claim."),
                "source_refs": _string_list_schema("DOIs, PMIDs, URLs, or file references."),
                "confidence": {"type": "string"},
                "boundary_conditions": _string_list_schema("Where this claim is expected to hold."),
                "failure_modes": _string_list_schema("What would invalidate or weaken this claim."),
            },
            "required": [
                "claim_id",
                "statement",
                "claim_type",
                "evidence_direction",
                "supports",
                "source_refs",
                "confidence",
                "boundary_conditions",
                "failure_modes",
            ],
            "additionalProperties": False,
        },
    }


def _evidence_schema() -> dict:
    return {
        "type": "array",
        "description": "Atomic evidence records that support, weaken, or contextualize claims.",
        "items": {
            "type": "object",
            "properties": {
                "evidence_id": {"type": "string"},
                "summary": {"type": "string"},
                "source_ref": {"type": "string"},
                "evidence_kind": {
                    "type": "string",
                    "description": "One of primary_study, review, preprint, dataset, analysis_run, observation, memory.",
                },
                "study_type": {"type": "string"},
                "model_system": {"type": "string"},
                "strength": {"type": "string"},
                "quality_grade": {
                    "type": "string",
                    "description": "One of high, moderate, low, very_low, unclear.",
                },
                "bias_risk": {
                    "type": "string",
                    "description": "One of low, medium, high, unclear.",
                },
                "relevance": {"type": "string"},
                "evidence_direction": {
                    "type": "string",
                    "description": "One of supports, weakens, mixed, contextual.",
                },
                "applicability": {"type": "string"},
                "conflict_group": {
                    "type": "string",
                    "description": "Shared label for evidence records that address the same contested question.",
                },
                "conflict_note": {
                    "type": "string",
                    "description": "Short explanation of why this evidence agrees or conflicts with nearby records.",
                },
                "limitations": _string_list_schema("Key caveats or limitations."),
            },
            "required": [
                "evidence_id",
                "summary",
                "source_ref",
                "evidence_kind",
                "study_type",
                "model_system",
                "strength",
                "quality_grade",
                "bias_risk",
                "relevance",
                "evidence_direction",
                "applicability",
                "conflict_group",
                "conflict_note",
                "limitations",
            ],
            "additionalProperties": False,
        },
    }


def _uncertainty_schema() -> dict:
    return {
        "type": "array",
        "description": "Unresolved uncertainties and open failure modes.",
        "items": {
            "type": "object",
            "properties": {
                "issue": {"type": "string"},
                "impact": {"type": "string"},
                "next_action": {"type": "string"},
            },
            "required": ["issue", "impact", "next_action"],
            "additionalProperties": False,
        },
    }


def _graph_references_schema() -> dict:
    return {
        "type": "object",
        "description": "Explicit typed graph nodes or edges consulted while producing this output.",
        "properties": {
            "node_refs": _string_list_schema("Typed graph node ids consulted."),
            "edge_refs": _string_list_schema("Typed graph edge ids consulted."),
            "usage_note": {"type": "string"},
        },
        "required": ["node_refs", "edge_refs", "usage_note"],
        "additionalProperties": False,
    }


def _stage_assessment_schema() -> dict:
    return {
        "type": "object",
        "description": "Explicit statement of where the investigation currently sits in the scientific workflow.",
        "properties": {
            "current_stage": {
                "type": "string",
                "description": "One of question, review, hypothesis, design, execute, analyze, decide, report.",
            },
            "next_stage": {
                "type": "string",
                "description": "The next recommended scientific stage.",
            },
            "stage_goal": {"type": "string"},
            "allowed_next_stages": _string_list_schema("Valid next stages from the current stage."),
            "missing_prerequisites": _string_list_schema("Scientific prerequisites still missing before advancing."),
            "stage_blockers": _string_list_schema("What is blocking progress to the next stage."),
        },
        "required": [
            "current_stage",
            "next_stage",
            "stage_goal",
            "allowed_next_stages",
            "missing_prerequisites",
            "stage_blockers",
        ],
        "additionalProperties": False,
    }


def _negative_results_schema() -> dict:
    return {
        "type": "array",
        "description": "Negative findings, failed attempts, or non-supporting results that should not be lost.",
        "items": {
            "type": "object",
            "properties": {
                "result": {"type": "string"},
                "why_it_failed_or_did_not_support": {"type": "string"},
                "implication": {"type": "string"},
                "affected_hypothesis_ids": _string_list_schema(
                    "Optional hypothesis ids directly weakened by this negative result."
                ),
            },
            "required": [
                "result",
                "why_it_failed_or_did_not_support",
                "implication",
                "affected_hypothesis_ids",
            ],
            "additionalProperties": False,
        },
    }


def _hypothesis_relations_schema() -> dict:
    return {
        "type": "array",
        "description": "Links between hypotheses such as parent-child, competing, or supporting relationships.",
        "items": {
            "type": "object",
            "properties": {
                "source_hypothesis_id": {"type": "string"},
                "target_hypothesis_id": {"type": "string"},
                "relation": {
                    "type": "string",
                    "description": "One of parent_of, child_of, competes_with, refines, depends_on.",
                },
                "note": {"type": "string"},
            },
            "required": ["source_hypothesis_id", "target_hypothesis_id", "relation", "note"],
            "additionalProperties": False,
        },
    }


def _causal_reasoning_schema() -> dict:
    return {
        "type": "object",
        "description": "Explicit causal assumptions, confounders, and alternative explanations.",
        "properties": {
            "causal_assumptions": _string_list_schema("Assumptions required for a causal interpretation."),
            "priority_confounders": _string_list_schema("Highest-priority confounders that could distort inference."),
            "alternative_explanations": _string_list_schema("Competing explanations that fit the current evidence."),
            "identification_strategy": {"type": "string"},
        },
        "required": [
            "causal_assumptions",
            "priority_confounders",
            "alternative_explanations",
            "identification_strategy",
        ],
        "additionalProperties": False,
    }


def _literature_synthesis_schema() -> dict:
    return {
        "type": "object",
        "description": "Higher-level synthesis of the literature beyond individual evidence snippets.",
        "properties": {
            "consensus_findings": _string_list_schema("Findings that appear broadly supported."),
            "contested_questions": _string_list_schema("Questions where the literature remains in conflict."),
            "evidence_matrix": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "supporting_evidence_ids": _string_list_schema("Evidence ids that support the proposition."),
                        "weakening_evidence_ids": _string_list_schema("Evidence ids that weaken the proposition."),
                        "overall_assessment": {"type": "string"},
                    },
                    "required": [
                        "question",
                        "supporting_evidence_ids",
                        "weakening_evidence_ids",
                        "overall_assessment",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["consensus_findings", "contested_questions", "evidence_matrix"],
        "additionalProperties": False,
    }


def _analysis_rigor_schema() -> dict:
    return {
        "type": "object",
        "description": "Statistical and analytical rigor checks for the current data plan.",
        "properties": {
            "power_analysis_notes": _string_list_schema("Notes about sample size, effect size, or power sufficiency."),
            "sensitivity_checks": _string_list_schema("Sensitivity analyses to test robustness."),
            "model_comparisons": _string_list_schema("Alternative models or estimators worth comparing."),
            "missing_data_strategy": {"type": "string"},
        },
        "required": [
            "power_analysis_notes",
            "sensitivity_checks",
            "model_comparisons",
            "missing_data_strategy",
        ],
        "additionalProperties": False,
    }


def _asset_registry_schema() -> dict:
    return {
        "type": "array",
        "description": "Research assets that should persist across runs such as datasets, protocols, reports, and plots.",
        "items": {
            "type": "object",
            "properties": {
                "asset_id": {"type": "string"},
                "asset_type": {"type": "string"},
                "label": {"type": "string"},
                "path_or_ref": {"type": "string"},
                "role": {"type": "string"},
                "parent_asset_id": {"type": "string"},
                "derived_from_asset_ids": _string_list_schema("Upstream assets this asset was derived from."),
                "governance_status": {"type": "string"},
                "lineage_note": {"type": "string"},
            },
            "required": ["asset_id", "asset_type", "label", "path_or_ref", "role"],
            "additionalProperties": False,
        },
    }


def _consensus_summary_schema() -> dict:
    return {
        "type": "object",
        "description": "Current consensus status across specialists.",
        "properties": {
            "consensus_status": {
                "type": "string",
                "description": "One of converged, partial, unresolved.",
            },
            "agreed_points": _string_list_schema("Points that appear stable across specialists."),
            "unresolved_points": _string_list_schema("Important disagreements that remain open."),
            "adjudication_basis": _string_list_schema("What evidence or logic drove the consensus state."),
        },
        "required": [
            "consensus_status",
            "agreed_points",
            "unresolved_points",
            "adjudication_basis",
        ],
        "additionalProperties": False,
    }


def _project_distill_schema() -> dict:
    return {
        "type": "object",
        "description": "Condensed project-level distill for future runs.",
        "properties": {
            "current_consensus": {"type": "string"},
            "failed_routes": _string_list_schema("Hypotheses, analyses, or designs that should not be repeated blindly."),
            "next_cycle_goals": _string_list_schema("The most valuable goals for the next research cycle."),
            "registry_updates": _string_list_schema("Assets or memories that should be updated after this run."),
        },
        "required": ["current_consensus", "failed_routes", "next_cycle_goals", "registry_updates"],
        "additionalProperties": False,
    }


def _experiment_economics_schema() -> dict:
    return {
        "type": "object",
        "description": "Cost, time, and information-gain framing for the next experiment choices.",
        "properties": {
            "cost_pressure": {"type": "string"},
            "time_pressure": {"type": "string"},
            "information_gain_pressure": {"type": "string"},
            "cheapest_discriminative_actions": _string_list_schema(
                "Actions that most cheaply separate competing explanations."
            ),
            "resource_risks": _string_list_schema("Resource or budget risks that could slow the project."),
            "defer_candidates": _string_list_schema("Actions worth postponing because they are expensive or low-yield."),
            "expected_information_gain": _string_list_schema("Why the chosen cheap actions are still scientifically discriminative."),
        },
        "required": [
            "cost_pressure",
            "time_pressure",
            "information_gain_pressure",
            "cheapest_discriminative_actions",
            "resource_risks",
            "defer_candidates",
            "expected_information_gain",
        ],
        "additionalProperties": False,
    }


def _lab_meeting_consensus_schema() -> dict:
    return {
        "type": "object",
        "description": "Group-style research discussion summary that clarifies debate, evidence needs, and next adjudication.",
        "properties": {
            "agenda_items": _string_list_schema("Open discussion items that still need deliberate resolution."),
            "position_summaries": _string_list_schema("Short summaries of the main positions on the table."),
            "evidence_needed_to_close": _string_list_schema(
                "Evidence or analyses still needed before the disagreement can close."
            ),
            "chair_recommendation": {"type": "string"},
            "decision_rule": {"type": "string"},
            "blocking_concerns": _string_list_schema("Concerns that prevent the meeting from declaring convergence."),
            "provisional_decisions": _string_list_schema("Temporary decisions the group can act on while uncertainty remains."),
            "consensus_summary": _consensus_summary_schema(),
        },
        "required": [
            "agenda_items",
            "position_summaries",
            "evidence_needed_to_close",
            "chair_recommendation",
            "decision_rule",
            "blocking_concerns",
            "provisional_decisions",
            "consensus_summary",
        ],
        "additionalProperties": False,
    }


def _research_plan_schema() -> dict:
    return {
        "type": "object",
        "description": "Forward-looking scientific research plan focused on information gain.",
        "properties": {
            "planning_horizon": {"type": "string"},
            "priority_questions": _string_list_schema("The most important scientific questions to resolve next."),
            "next_cycle_experiments": _string_list_schema("The highest-value next experiment or analysis cycles."),
            "decision_gates": _string_list_schema("Explicit conditions that would advance, pause, or stop a route."),
            "information_gain_priorities": _string_list_schema("Which actions would reduce uncertainty fastest."),
            "stop_conditions": _string_list_schema("Signals that should terminate a route or hypothesis family."),
            "strategy_memory_candidates": _string_list_schema("Reusable strategic lessons the planner wants to keep for future cycles."),
        },
        "required": [
            "planning_horizon",
            "priority_questions",
            "next_cycle_experiments",
            "decision_gates",
            "information_gain_priorities",
            "stop_conditions",
            "strategy_memory_candidates",
        ],
        "additionalProperties": False,
    }


def _discipline_adaptation_schema() -> dict:
    return {
        "type": "object",
        "description": "Discipline-specific execution requirements and artifact expectations.",
        "properties": {
            "primary_discipline": {"type": "string"},
            "secondary_disciplines": _string_list_schema("Secondary disciplines or methods that matter for this topic."),
            "adapter_requirements": _string_list_schema("Specialized execution requirements by discipline."),
            "discipline_specific_risks": _string_list_schema("Field-specific failure modes or blind spots."),
            "artifact_expectations": _string_list_schema("Expected artifacts such as spectra, checkpoints, proofs, plots, or calibration files."),
            "execution_modes": _string_list_schema("Dominant execution modes such as wet-lab, process, simulation, proof, or measurement."),
            "validation_norms": _string_list_schema("How this discipline usually validates a result before trusting it."),
            "artifact_governance_requirements": _string_list_schema("How artifacts in this discipline should be versioned, frozen, or reviewed."),
        },
        "required": [
            "primary_discipline",
            "secondary_disciplines",
            "adapter_requirements",
            "discipline_specific_risks",
            "artifact_expectations",
            "execution_modes",
            "validation_norms",
            "artifact_governance_requirements",
        ],
        "additionalProperties": False,
    }


def _autonomy_plan_schema() -> dict:
    return {
        "type": "object",
        "description": "Autonomous multi-cycle research control plan.",
        "properties": {
            "current_objective": {"type": "string"},
            "active_workstreams": _string_list_schema("Parallel workstreams the system should maintain."),
            "autonomous_next_actions": _string_list_schema("Actions the system should proactively take next."),
            "monitoring_signals": _string_list_schema("Signals that should trigger replanning."),
            "handoff_points": _string_list_schema("Moments that require human review or explicit approval."),
            "termination_conditions": _string_list_schema("Conditions that should stop or retire a route."),
        },
        "required": [
            "current_objective",
            "active_workstreams",
            "autonomous_next_actions",
            "monitoring_signals",
            "handoff_points",
            "termination_conditions",
        ],
        "additionalProperties": False,
    }


def _program_management_schema() -> dict:
    return {
        "type": "object",
        "description": "Long-horizon research program management across workstreams, milestones, and resource allocation.",
        "properties": {
            "program_objective": {"type": "string"},
            "primary_workstream": {"type": "string"},
            "secondary_workstreams": _string_list_schema("Parallel workstreams that support or hedge the primary route."),
            "milestones": _string_list_schema("Named milestones for the next research horizon."),
            "resource_allocations": _string_list_schema("How budget, time, and attention should be allocated across workstreams."),
            "portfolio_routes": _string_list_schema("Named route categories such as primary, hedge, paused, retired, or exploratory."),
            "review_cadence": {"type": "string"},
            "pivot_triggers": _string_list_schema("Signals that should trigger a program-level pivot."),
        },
        "required": [
            "program_objective",
            "primary_workstream",
            "secondary_workstreams",
            "milestones",
            "resource_allocations",
            "portfolio_routes",
            "review_cadence",
            "pivot_triggers",
        ],
        "additionalProperties": False,
    }


def _domain_playbook_schema() -> dict:
    return {
        "type": "array",
        "description": "Discipline-specific playbooks describing how this domain should be executed and validated.",
        "items": {
            "type": "object",
            "properties": {
                "discipline": {"type": "string"},
                "execution_pattern": {"type": "string"},
                "validation_pattern": {"type": "string"},
                "failure_modes": _string_list_schema("Common ways research in this domain breaks or misleads."),
                "required_artifacts": _string_list_schema("Artifacts that should exist before trusting conclusions in this domain."),
                "approval_expectations": _string_list_schema("Governance or approval expectations specific to this domain."),
            },
            "required": [
                "discipline",
                "execution_pattern",
                "validation_pattern",
                "failure_modes",
                "required_artifacts",
                "approval_expectations",
            ],
            "additionalProperties": False,
        },
    }


def _systematic_review_schema() -> dict:
    return {
        "type": "object",
        "description": "Systematic-review-style synthesis over the current literature base.",
        "properties": {
            "review_question": {"type": "string"},
            "review_protocol_version": {"type": "string"},
            "study_type_hierarchy": _string_list_schema("Ordered study hierarchy relevant to the question."),
            "inclusion_logic": _string_list_schema("What evidence was prioritized for inclusion."),
            "exclusion_logic": _string_list_schema("What evidence classes were deprioritized or excluded."),
            "screening_decisions": _string_list_schema("How studies were screened or bucketed during review."),
            "exclusion_reasons": _string_list_schema("Explicit reasons for excluding or downweighting evidence."),
            "evidence_balance": _string_list_schema("How the balance of evidence currently looks."),
            "bias_hotspots": _string_list_schema("Recurring methodological weaknesses across the literature."),
            "evidence_table_focus": _string_list_schema("Which questions or subquestions deserve explicit evidence-table treatment."),
            "evidence_table_records": _string_list_schema("Rows or slices that should appear in a formal evidence table."),
            "screening_records": _string_list_schema("Formal screening record identifiers or summaries."),
            "review_record_updates": _string_list_schema("Formal review record updates that should be logged this cycle."),
            "review_protocol_gaps": _string_list_schema("Where the current review process is still underspecified or weak."),
        },
        "required": [
            "review_question",
            "review_protocol_version",
            "study_type_hierarchy",
            "inclusion_logic",
            "exclusion_logic",
            "screening_decisions",
            "exclusion_reasons",
            "evidence_balance",
            "bias_hotspots",
            "evidence_table_focus",
            "evidence_table_records",
            "screening_records",
            "review_record_updates",
            "review_protocol_gaps",
        ],
        "additionalProperties": False,
    }


def _causal_model_schema() -> dict:
    return {
        "type": "object",
        "description": "Explicit causal model components and intervention priorities.",
        "properties": {
            "target_outcomes": _string_list_schema("Outcomes the research is trying to explain or control."),
            "interventions": _string_list_schema("Interventions or manipulations under consideration."),
            "mediators": _string_list_schema("Potential mediators between intervention and outcome."),
            "confounders": _string_list_schema("Variables that could confound causal inference."),
            "competing_mechanisms": _string_list_schema("Alternative mechanisms that could also explain the outcome pattern."),
            "counterfactual_queries": _string_list_schema("Counterfactual questions that would clarify the mechanism."),
            "eliminated_explanations": _string_list_schema("Explanations already partly ruled out by current evidence."),
            "identifiability_risks": _string_list_schema("Where causal identification remains weak or underdetermined."),
            "causal_edges": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string"},
                        "target": {"type": "string"},
                        "relation": {"type": "string"},
                        "confidence": {"type": "string"},
                    },
                    "required": ["source", "target", "relation", "confidence"],
                    "additionalProperties": False,
                },
            },
            "intervention_priorities": _string_list_schema("Interventions most likely to reduce causal uncertainty."),
            "mechanism_nodes": _string_list_schema("Mechanism-level explanatory units that should be tracked explicitly."),
            "mechanism_edges": _string_list_schema("Mechanism relationships such as activates, blocks, mediates, or constrains."),
            "counterfactual_experiments": _string_list_schema("Experiments that most cleanly distinguish competing counterfactual worlds."),
        },
        "required": [
            "target_outcomes",
            "interventions",
            "mediators",
            "confounders",
            "competing_mechanisms",
            "counterfactual_queries",
            "eliminated_explanations",
            "identifiability_risks",
            "causal_edges",
            "intervention_priorities",
            "mechanism_nodes",
            "mechanism_edges",
            "counterfactual_experiments",
        ],
        "additionalProperties": False,
    }


def _mechanism_map_schema() -> dict:
    return {
        "type": "array",
        "description": "Mechanism-centered scientific objects connecting hypotheses to plausible explanatory pathways.",
        "items": {
            "type": "object",
            "properties": {
                "mechanism_id": {"type": "string"},
                "label": {"type": "string"},
                "family": {"type": "string"},
                "supports_hypothesis_ids": _string_list_schema("Hypotheses this mechanism supports."),
                "competes_with": _string_list_schema("Mechanisms that directly compete with this one."),
                "status": {"type": "string"},
                "evidence_ref_ids": _string_list_schema("Evidence ids that currently support this mechanism."),
                "challenge_signals": _string_list_schema("Signals, failures, or counterevidence challenging this mechanism."),
                "revive_conditions": _string_list_schema("What new evidence would justify reviving this mechanism if weakened."),
            },
            "required": [
                "mechanism_id",
                "label",
                "family",
                "supports_hypothesis_ids",
                "competes_with",
                "status",
                "evidence_ref_ids",
                "challenge_signals",
                "revive_conditions",
            ],
            "additionalProperties": False,
        },
    }


def _counterfactual_plan_schema() -> dict:
    return {
        "type": "object",
        "description": "Counterfactual experiment framing for discriminating mechanisms or hypothesis families.",
        "properties": {
            "target_contrast": {"type": "string"},
            "if_true_predictions": _string_list_schema("Predictions if the favored mechanism or hypothesis is true."),
            "if_false_predictions": _string_list_schema("Predictions if the favored mechanism or hypothesis is false."),
            "discriminative_experiments": _string_list_schema("Experiments that sharply separate the competing worlds."),
        },
        "required": ["target_contrast", "if_true_predictions", "if_false_predictions", "discriminative_experiments"],
        "additionalProperties": False,
    }


def _hypothesis_family_actions_schema() -> dict:
    return {
        "type": "array",
        "description": "Family-level lifecycle recommendations for groups of related hypotheses.",
        "items": {
            "type": "object",
            "properties": {
                "family": {"type": "string"},
                "action": {"type": "string"},
                "reason": {"type": "string"},
                "affected_hypothesis_ids": _string_list_schema("Hypotheses in this family affected by the action."),
            },
            "required": ["family", "action", "reason", "affected_hypothesis_ids"],
            "additionalProperties": False,
        },
    }


def _hypothesis_validation_schema() -> dict:
    return {
        "type": "array",
        "description": "Validator scores and recommendations for candidate scientific hypotheses.",
        "items": {
            "type": "object",
            "properties": {
                "hypothesis_id": {"type": "string"},
                "novelty_score": {"type": "number"},
                "falsifiability_score": {"type": "number"},
                "testability_score": {"type": "number"},
                "mechanistic_coherence_score": {"type": "number"},
                "evidence_grounding_score": {"type": "number"},
                "confounder_risk_score": {"type": "number"},
                "resource_feasibility_score": {"type": "number"},
                "overall_recommendation": {"type": "string"},
                "validator_notes": _string_list_schema("Reasons or suggested revisions from the validators."),
            },
            "required": [
                "hypothesis_id",
                "novelty_score",
                "falsifiability_score",
                "testability_score",
                "mechanistic_coherence_score",
                "evidence_grounding_score",
                "confounder_risk_score",
                "resource_feasibility_score",
                "overall_recommendation",
                "validator_notes",
            ],
            "additionalProperties": False,
        },
    }


def _hypothesis_gate_schema() -> dict:
    return {
        "type": "array",
        "description": "Gate decision for each hypothesis after validation.",
        "items": {
            "type": "object",
            "properties": {
                "hypothesis_id": {"type": "string"},
                "gate_decision": {"type": "string"},
                "reason": {"type": "string"},
                "required_follow_up": _string_list_schema("Actions required before the hypothesis can advance."),
            },
            "required": ["hypothesis_id", "gate_decision", "reason", "required_follow_up"],
            "additionalProperties": False,
        },
    }


def _experiment_specification_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "experiment_id": {"type": "string"},
            "title": {"type": "string"},
            "discipline": {"type": "string"},
            "goal": {"type": "string"},
            "decision_type": {"type": "string"},
            "success_criteria": _string_list_schema("Conditions that would count as a successful run."),
            "failure_criteria": _string_list_schema("Conditions that would invalidate or fail the run."),
        },
        "required": [
            "experiment_id",
            "title",
            "discipline",
            "goal",
            "decision_type",
            "success_criteria",
            "failure_criteria",
        ],
        "additionalProperties": False,
    }


def _experimental_protocol_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "protocol_id": {"type": "string"},
            "experiment_id": {"type": "string"},
            "version": {"type": "string"},
            "inputs": _string_list_schema("Inputs, materials, datasets, or assumptions required."),
            "controls": _string_list_schema("Required controls or baselines."),
            "steps": _string_list_schema("Execution steps."),
            "measurement_plan": _string_list_schema("How outputs will be measured."),
            "quality_control_checks": _string_list_schema("Checks required before trusting the run."),
        },
        "required": [
            "protocol_id",
            "experiment_id",
            "version",
            "inputs",
            "controls",
            "steps",
            "measurement_plan",
            "quality_control_checks",
        ],
        "additionalProperties": False,
    }


def _experiment_run_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "run_id": {"type": "string"},
            "experiment_id": {"type": "string"},
            "protocol_id": {"type": "string"},
            "status": {"type": "string"},
            "operator": {"type": "string"},
            "configuration_snapshot": {"type": "object"},
            "environment_snapshot": {"type": "object"},
        },
        "required": [
            "run_id",
            "experiment_id",
            "protocol_id",
            "status",
            "operator",
            "configuration_snapshot",
            "environment_snapshot",
        ],
        "additionalProperties": False,
    }


def _observation_records_schema() -> dict:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "observation_id": {"type": "string"},
                "run_id": {"type": "string"},
                "observation_type": {"type": "string"},
                "summary": {"type": "string"},
                "files": _string_list_schema("Files or artifacts generated by the run."),
                "notes": _string_list_schema("Important notes from the run."),
            },
            "required": ["observation_id", "run_id", "observation_type", "summary", "files", "notes"],
            "additionalProperties": False,
        },
    }


def _quality_control_review_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "review_id": {"type": "string"},
            "run_id": {"type": "string"},
            "quality_control_status": {"type": "string"},
            "issues": _string_list_schema("Problems that affect trust in the run."),
            "possible_artifacts": _string_list_schema("Artifacts that may explain the result."),
            "protocol_deviations": _string_list_schema("Where the actual run diverged from the protocol."),
            "quality_control_checks_run": _string_list_schema("Checks actually reviewed."),
            "missing_quality_control_checks": _string_list_schema("Checks that should have run but did not."),
            "affected_outputs": _string_list_schema("Outputs contaminated by the quality issue."),
            "repeat_required": {"type": "boolean"},
            "blocking_severity": {"type": "string"},
            "evidence_reliability": {"type": "string"},
            "usable_for_interpretation": {"type": "boolean"},
            "recommended_action": {"type": "string"},
        },
        "required": [
            "review_id",
            "run_id",
            "quality_control_status",
            "issues",
            "possible_artifacts",
            "protocol_deviations",
            "quality_control_checks_run",
            "missing_quality_control_checks",
            "affected_outputs",
            "repeat_required",
            "blocking_severity",
            "evidence_reliability",
            "usable_for_interpretation",
            "recommended_action",
        ],
        "additionalProperties": False,
    }


def _interpretation_record_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "interpretation_id": {"type": "string"},
            "run_id": {"type": "string"},
            "supported_hypothesis_ids": _string_list_schema("Hypotheses supported by the run."),
            "weakened_hypothesis_ids": _string_list_schema("Hypotheses weakened by the run."),
            "inconclusive_hypothesis_ids": _string_list_schema("Hypotheses that remain unresolved."),
            "negative_result": {"type": "boolean"},
            "claim_updates": _string_list_schema("What claims should be updated based on the run."),
            "confidence": {"type": "string"},
            "next_decision": {"type": "string"},
        },
        "required": [
            "interpretation_id",
            "run_id",
            "supported_hypothesis_ids",
            "weakened_hypothesis_ids",
            "inconclusive_hypothesis_ids",
            "negative_result",
            "claim_updates",
            "confidence",
            "next_decision",
        ],
        "additionalProperties": False,
    }


COMMON_FIELDS = {
    "claims": _claim_schema("Structured claims produced by this specialist."),
    "evidence": _evidence_schema(),
    "graph_references": _graph_references_schema(),
    "uncertainties": _uncertainty_schema(),
    "negative_results": _negative_results_schema(),
    "stage_assessment": _stage_assessment_schema(),
    "confidence": {"type": "string", "description": "One of low, medium, high."},
    "open_questions": _string_list_schema("Important unanswered questions."),
}


@dataclass(slots=True)
class SpecialistProfile:
    name: str
    system_prompt: str
    output_schema: StructuredSchema
    model_config: AgentModelConfig
    allow_web_search: bool = False
    tool_names: list[str] = field(default_factory=list)


DEFAULT_SCIENCE_PROFILES: dict[str, SpecialistProfile] = {
    "research_planner": SpecialistProfile(
        name="research_planner",
        tool_names=["search_memory", "query_typed_graph", "record_observation", "read_file"],
        system_prompt=(
            "You are a scientific research planner. Build a multi-cycle plan that maximizes information gain, "
            "clarifies decision gates, identifies stop conditions, and adapts the workflow to the relevant scientific disciplines."
        ),
        output_schema=StructuredSchema(
            name="research_planning",
            description="Long-horizon scientific planning and discipline adaptation.",
            schema={
                "type": "object",
                "properties": {
                    "research_plan": _research_plan_schema(),
                    "autonomy_plan": _autonomy_plan_schema(),
                    "systematic_review": _systematic_review_schema(),
                    "program_management": _program_management_schema(),
                    "domain_playbooks": _domain_playbook_schema(),
                    "discipline_adaptation": _discipline_adaptation_schema(),
                    "causal_reasoning": _causal_reasoning_schema(),
                    "causal_model": _causal_model_schema(),
                    "mechanism_map": _mechanism_map_schema(),
                    "consensus_summary": _consensus_summary_schema(),
                    "asset_registry": _asset_registry_schema(),
                    **COMMON_FIELDS,
                },
                "required": [
                    "research_plan",
                    "autonomy_plan",
                    "systematic_review",
                    "program_management",
                    "domain_playbooks",
                    "discipline_adaptation",
                    "causal_reasoning",
                    "causal_model",
                    "mechanism_map",
                    "consensus_summary",
                    "asset_registry",
                    "claims",
                    "evidence",
                    "uncertainties",
                    "confidence",
                    "open_questions",
                ],
                "additionalProperties": False,
            },
        ),
        model_config=AgentModelConfig(
            model="gpt-5",
            reasoning_effort="high",
            max_output_tokens=2000,
        ),
    ),
    "literature_reviewer": SpecialistProfile(
        name="literature_reviewer",
        allow_web_search=True,
        tool_names=[
            "record_observation",
            "pubmed_search",
            "arxiv_search",
            "crossref_search",
            "resolve_citation",
            "ingest_literature_source",
            "query_literature_wiki",
            "lint_literature_workspace",
            "search_memory",
            "read_file",
        ],
        system_prompt=(
            "You are a literature review agent for scientific research. "
            "Prioritize primary sources and separate claim statements from evidence records. "
            "Every important finding should trace back to explicit sources and caveats. "
            "Maintain the literature wiki as a persistent synthesis layer with paper pages, review pages, "
            "formal review records, and controversy tracking."
        ),
        output_schema=StructuredSchema(
            name="literature_review",
            description="Structured literature survey output with claim-evidence links.",
            schema={
                "type": "object",
                "properties": {
                    "research_goal": {"type": "string"},
                    "evidence_gaps": _string_list_schema("Important missing evidence."),
                    "representative_sources": _string_list_schema("Citations or URLs for representative sources."),
                    "literature_synthesis": _literature_synthesis_schema(),
                    "systematic_review": _systematic_review_schema(),
                    "citations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "doi": {"type": "string"},
                                "url": {"type": "string"},
                                "source_type": {"type": "string"},
                                "summary": {"type": "string"},
                            },
                            "required": ["title", "doi", "url", "source_type", "summary"],
                            "additionalProperties": False,
                        },
                    },
                    **COMMON_FIELDS,
                },
                "required": [
                    "research_goal",
                    "evidence_gaps",
                    "representative_sources",
                    "literature_synthesis",
                    "systematic_review",
                    "citations",
                    "claims",
                    "evidence",
                    "uncertainties",
                    "confidence",
                    "open_questions",
                ],
                "additionalProperties": False,
            },
        ),
        model_config=AgentModelConfig(
            model="gpt-5",
            reasoning_effort="high",
            max_output_tokens=2200,
            allow_web_search=True,
        ),
    ),
    "data_curator": SpecialistProfile(
        name="data_curator",
        tool_names=["read_file", "read_table", "record_observation", "search_memory"],
        system_prompt=(
            "You are a data curator agent. Organize files, datasets, variables, units, and data quality issues. "
            "Treat dataset inventory and quality risks as evidence-backed claims."
        ),
        output_schema=StructuredSchema(
            name="data_inventory",
            description="Inventory of available data assets with quality evidence.",
            schema={
                "type": "object",
                "properties": {
                    "available_assets": _string_list_schema("Files, datasets, or sources available."),
                    "key_variables": _string_list_schema("Variables likely relevant to the research question."),
                    "quality_risks": _string_list_schema("Missingness, bias, unclear units, or integrity risks."),
                    "recommended_preprocessing": _string_list_schema("Minimal preprocessing steps."),
                    "asset_registry": _asset_registry_schema(),
                    **COMMON_FIELDS,
                },
                "required": [
                    "available_assets",
                    "key_variables",
                    "quality_risks",
                    "recommended_preprocessing",
                    "asset_registry",
                    "claims",
                    "evidence",
                    "uncertainties",
                    "confidence",
                    "open_questions",
                ],
                "additionalProperties": False,
            },
        ),
        model_config=AgentModelConfig(
            model="gpt-5-mini",
            reasoning_effort="medium",
            max_output_tokens=1600,
        ),
    ),
    "hypothesis_generator": SpecialistProfile(
        name="hypothesis_generator",
        tool_names=["record_observation", "search_memory", "review_memory", "query_typed_graph"],
        system_prompt=(
            "You are a hypothesis generation agent. Turn evidence summaries into falsifiable hypotheses. "
            "Mark each hypothesis as a claim and keep assumptions and failure conditions explicit. "
            "After generating hypotheses, act like an internal review panel and score novelty, falsifiability, testability, "
            "mechanistic coherence, evidence grounding, confounder exposure, and resource feasibility before recommending accept, revise, or reject. "
            "Whenever possible, phrase hypotheses as theory objects with boundary conditions, observable variables, and counterfactual predictions."
        ),
        output_schema=StructuredSchema(
            name="hypothesis_set",
            description="Ranked scientific hypotheses with explicit evidence links.",
            schema={
                "type": "object",
                "properties": {
                    "hypotheses": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "hypothesis_id": {"type": "string"},
                                "version": {"type": "string"},
                                "mechanism": {"type": "string"},
                                "prediction": {"type": "string"},
                                "falsifiability_test": {"type": "string"},
                                "boundary_conditions": _string_list_schema("Conditions where the hypothesis should hold."),
                                "measurable_variables": _string_list_schema("Variables or readouts that make the prediction observable."),
                                "counterfactual_predictions": _string_list_schema("Expected observations if the hypothesis is false or a competitor is true."),
                                "discriminating_experiments": _string_list_schema("Experiments that separate this hypothesis from competitors."),
                                "status": {
                                    "type": "string",
                                    "description": "One of active, revised, deprecated, rejected.",
                                },
                                "assumptions": _string_list_schema("Key assumptions"),
                                "failure_conditions": _string_list_schema("What would falsify or weaken the hypothesis"),
                            },
                            "required": [
                                "name",
                                "hypothesis_id",
                                "version",
                                "mechanism",
                                "prediction",
                                "falsifiability_test",
                                "status",
                                "assumptions",
                                "failure_conditions",
                            ],
                            "additionalProperties": False,
                        },
                    },
                    "hypothesis_relations": _hypothesis_relations_schema(),
                    "mechanism_map": _mechanism_map_schema(),
                    "hypothesis_validations": _hypothesis_validation_schema(),
                    "hypothesis_gates": _hypothesis_gate_schema(),
                    **COMMON_FIELDS,
                },
                "required": [
                    "hypotheses",
                    "hypothesis_relations",
                    "mechanism_map",
                    "hypothesis_validations",
                    "hypothesis_gates",
                    "claims",
                    "evidence",
                    "uncertainties",
                    "confidence",
                    "open_questions",
                ],
                "additionalProperties": False,
            },
        ),
        model_config=AgentModelConfig(
            model="gpt-5",
            reasoning_effort="high",
            max_output_tokens=1800,
        ),
    ),
    "experiment_designer": SpecialistProfile(
        name="experiment_designer",
        tool_names=["record_observation", "python_exec", "search_memory", "query_typed_graph", "query_literature_wiki"],
        system_prompt=(
            "You are an experiment design agent. Design experiments that discriminate between competing hypotheses. "
            "Expose confounders, endpoints, and sample assumptions as auditable claims. "
            "Before proposing a new experiment, inspect the typed research graph for prior tests, challenges, "
            "supporting evidence, and failed routes so you do not repeat weak or already-invalidated designs. "
            "Consult literature review and controversy pages to design experiments that close the most important disputes."
        ),
        output_schema=StructuredSchema(
            name="experiment_plan",
            description="Actionable experiment design with rationale and risks.",
            schema={
                "type": "object",
                "properties": {
                    "primary_experiment": {"type": "string"},
                    "controls": _string_list_schema("Necessary controls"),
                    "measurements": _string_list_schema("Primary endpoints and readouts"),
                    "confounders": _string_list_schema("Likely confounders"),
                    "protocol_outline": _string_list_schema("Minimal viable protocol steps"),
                    "causal_reasoning": _causal_reasoning_schema(),
                    "counterfactual_experiment_plan": _counterfactual_plan_schema(),
                    **COMMON_FIELDS,
                },
                "required": [
                    "primary_experiment",
                    "controls",
                    "measurements",
                    "confounders",
                    "protocol_outline",
                    "causal_reasoning",
                    "counterfactual_experiment_plan",
                    "claims",
                    "evidence",
                    "uncertainties",
                    "confidence",
                    "open_questions",
                ],
                "additionalProperties": False,
            },
        ),
        model_config=AgentModelConfig(
            model="gpt-5",
            reasoning_effort="high",
            max_output_tokens=2000,
        ),
    ),
    "run_manager": SpecialistProfile(
        name="run_manager",
        tool_names=["record_observation", "write_file", "save_memory", "search_memory", "query_typed_graph"],
        system_prompt=(
            "You are an experiment run management agent. Convert an approved design into an executable run plan, "
            "capture the run state, and record the observations and assets that should persist. "
            "Before launching a new run plan, inspect the typed research graph for earlier protocols, runs, "
            "artifacts, and challenged routes so the execution plan reuses valid lineage and avoids repeated mistakes."
        ),
        output_schema=StructuredSchema(
            name="experiment_run_bundle",
            description="Executable run bundle with experiment specification, protocol, run metadata, and observations.",
            schema={
                "type": "object",
                "properties": {
                    "experiment_specification": _experiment_specification_schema(),
                    "experimental_protocol": _experimental_protocol_schema(),
                    "experiment_run": _experiment_run_schema(),
                    "observation_records": _observation_records_schema(),
                    "asset_registry": _asset_registry_schema(),
                    **COMMON_FIELDS,
                },
                "required": [
                    "experiment_specification",
                    "experimental_protocol",
                    "experiment_run",
                    "observation_records",
                    "asset_registry",
                    "claims",
                    "evidence",
                    "uncertainties",
                    "confidence",
                    "open_questions",
                ],
                "additionalProperties": False,
            },
        ),
        model_config=AgentModelConfig(
            model="gpt-5",
            reasoning_effort="medium",
            max_output_tokens=1900,
        ),
    ),
    "quality_control_reviewer": SpecialistProfile(
        name="quality_control_reviewer",
        tool_names=["record_observation", "search_memory", "query_typed_graph", "review_memory"],
        system_prompt=(
            "You are a quality control reviewer for scientific experiments and computational runs. "
            "Judge whether the run can be trusted, identify execution artifacts, and state clearly whether interpretation should proceed. "
            "Use the typed research graph to compare this run against prior failures, quality issues, repeated artifacts, "
            "and superseded execution paths before deciding whether the result is usable."
        ),
        output_schema=StructuredSchema(
            name="quality_control_review",
            description="Structured quality control review for an experimental or computational run.",
            schema={
                "type": "object",
                "properties": {
                    "quality_control_review": _quality_control_review_schema(),
                    "asset_registry": _asset_registry_schema(),
                    **COMMON_FIELDS,
                },
                "required": [
                    "quality_control_review",
                    "asset_registry",
                    "claims",
                    "evidence",
                    "uncertainties",
                    "confidence",
                    "open_questions",
                ],
                "additionalProperties": False,
            },
        ),
        model_config=AgentModelConfig(
            model="gpt-5",
            reasoning_effort="high",
            max_output_tokens=1800,
        ),
    ),
    "result_interpreter": SpecialistProfile(
        name="result_interpreter",
        tool_names=["record_observation", "search_memory", "query_typed_graph", "review_memory"],
        system_prompt=(
            "You are a scientific result interpretation agent. Interpret only quality-controlled outputs, map results onto hypotheses, "
            "and distinguish genuine negative results from execution or measurement failures. "
            "Use the typed research graph to compare the current run against prior supporting, challenging, and tested relationships "
            "before deciding what this result changes."
        ),
        output_schema=StructuredSchema(
            name="interpretation_bundle",
            description="Interpretation of a run and its implications for hypotheses and future work.",
            schema={
                "type": "object",
                "properties": {
                    "interpretation_record": _interpretation_record_schema(),
                    "consensus_summary": _consensus_summary_schema(),
                    **COMMON_FIELDS,
                },
                "required": [
                    "interpretation_record",
                    "consensus_summary",
                    "claims",
                    "evidence",
                    "uncertainties",
                    "confidence",
                    "open_questions",
                ],
                "additionalProperties": False,
            },
        ),
        model_config=AgentModelConfig(
            model="gpt-5",
            reasoning_effort="high",
            max_output_tokens=1800,
        ),
    ),
    "belief_updater": SpecialistProfile(
        name="belief_updater",
        tool_names=["save_memory", "review_memory", "search_memory", "query_typed_graph", "record_observation"],
        system_prompt=(
            "You are a scientific belief update agent. Update hypothesis states, memory, and the next-cycle plan "
            "based on interpreted results and quality control outcomes."
        ),
        output_schema=StructuredSchema(
            name="belief_update_bundle",
            description="Persistent updates to hypotheses, memory, and next-step decisions after a run.",
            schema={
                "type": "object",
                "properties": {
                    "hypothesis_relations": _hypothesis_relations_schema(),
                    "hypothesis_family_actions": _hypothesis_family_actions_schema(),
                    "consensus_summary": _consensus_summary_schema(),
                    "project_distill": _project_distill_schema(),
                    "asset_registry_updates": _asset_registry_schema(),
                    **COMMON_FIELDS,
                },
                "required": [
                    "hypothesis_relations",
                    "hypothesis_family_actions",
                    "consensus_summary",
                    "project_distill",
                    "asset_registry_updates",
                    "claims",
                    "evidence",
                    "uncertainties",
                    "confidence",
                    "open_questions",
                ],
                "additionalProperties": False,
            },
        ),
        model_config=AgentModelConfig(
            model="gpt-5",
            reasoning_effort="high",
            max_output_tokens=1800,
        ),
    ),
    "data_analyst": SpecialistProfile(
        name="data_analyst",
        tool_names=[
            "python_exec",
            "read_file",
            "read_table",
            "basic_table_stats",
            "plot_csv",
            "record_observation",
            "search_memory",
        ],
        system_prompt=(
            "You are a scientific data analysis agent. Use the data tools when tabular files are available. "
            "Treat planned analyses and diagnostics as reproducible, evidence-backed decisions."
        ),
        output_schema=StructuredSchema(
            name="analysis_plan",
            description="Scientific data analysis plan with evidence and robustness logic.",
            schema={
                "type": "object",
                "properties": {
                    "analysis_steps": _string_list_schema("Ordered analysis steps"),
                    "statistical_tests": _string_list_schema("Suggested tests or models"),
                    "plots": _string_list_schema("Plots to generate"),
                    "robustness_checks": _string_list_schema("Sanity checks and robustness checks"),
                    "analysis_rigor": _analysis_rigor_schema(),
                    **COMMON_FIELDS,
                },
                "required": [
                    "analysis_steps",
                    "statistical_tests",
                    "plots",
                    "robustness_checks",
                    "analysis_rigor",
                    "claims",
                    "evidence",
                    "uncertainties",
                    "confidence",
                    "open_questions",
                ],
                "additionalProperties": False,
            },
        ),
        model_config=AgentModelConfig(
            model="gpt-5",
            reasoning_effort="medium",
            max_output_tokens=1800,
        ),
    ),
    "experiment_economist": SpecialistProfile(
        name="experiment_economist",
        tool_names=["search_memory", "query_typed_graph", "query_literature_wiki", "record_observation"],
        system_prompt=(
            "You are an experiment economics specialist. Optimize the next experimental or analytical cycle "
            "for information gain per unit cost, time, and operational risk. Be explicit about what should be deferred. "
            "Use the typed research graph to inspect prior tested routes, repeated failures, governed assets, and lineage "
            "before recommending what is cheapest, safest, and most discriminative to do next. "
            "Use review and controversy pages to avoid paying for experiments that do not close meaningful uncertainty."
        ),
        output_schema=StructuredSchema(
            name="experiment_economics_bundle",
            description="Information-gain-aware cost and time framing for next-step experimental choices.",
            schema={
                "type": "object",
                "properties": {
                    "experiment_economics": _experiment_economics_schema(),
                    **COMMON_FIELDS,
                },
                "required": [
                    "experiment_economics",
                    "claims",
                    "evidence",
                    "uncertainties",
                    "confidence",
                    "open_questions",
                ],
                "additionalProperties": False,
            },
        ),
        model_config=AgentModelConfig(
            model="gpt-5",
            reasoning_effort="high",
            max_output_tokens=1600,
        ),
    ),
    "critic": SpecialistProfile(
        name="critic",
        tool_names=["record_observation", "search_memory", "query_typed_graph", "review_memory"],
        system_prompt=(
            "You are a scientific critic agent. Stress-test claims, look for confounders, alternative explanations, "
            "overclaiming, reproducibility risks, and missing controls. Your output should focus on why a claim may fail."
        ),
        output_schema=StructuredSchema(
            name="critical_review",
            description="Structured critique of the current research plan.",
            schema={
                "type": "object",
                "properties": {
                    "major_risks": _string_list_schema("Major scientific or methodological risks"),
                    "alternative_explanations": _string_list_schema("Competing explanations"),
                    "missing_controls": _string_list_schema("Missing controls or validations"),
                    "overclaims": _string_list_schema("Claims that are not yet justified"),
                    "causal_reasoning": _causal_reasoning_schema(),
                    **COMMON_FIELDS,
                },
                "required": [
                    "major_risks",
                    "alternative_explanations",
                    "missing_controls",
                    "overclaims",
                    "causal_reasoning",
                    "claims",
                    "evidence",
                    "uncertainties",
                    "confidence",
                    "open_questions",
                ],
                "additionalProperties": False,
            },
        ),
        model_config=AgentModelConfig(
            model="gpt-5",
            reasoning_effort="high",
            max_output_tokens=1800,
        ),
    ),
    "safety_ethics_reviewer": SpecialistProfile(
        name="safety_ethics_reviewer",
        tool_names=["record_observation", "search_memory"],
        system_prompt=(
            "You are a safety and ethics review agent for scientific work. "
            "Assess biosafety, clinical risk, dual-use concerns, privacy, and consent implications conservatively."
        ),
        output_schema=StructuredSchema(
            name="safety_ethics_review",
            description="Structured safety and ethics review.",
            schema={
                "type": "object",
                "properties": {
                    "risk_areas": _string_list_schema("Potential safety, ethics, or governance risks"),
                    "mitigations": _string_list_schema("Specific mitigations"),
                    "approval_needs": _string_list_schema("Reviews, approvals, or governance checks that may be needed"),
                    **COMMON_FIELDS,
                },
                "required": [
                    "risk_areas",
                    "mitigations",
                    "approval_needs",
                    "claims",
                    "evidence",
                    "uncertainties",
                    "confidence",
                    "open_questions",
                ],
                "additionalProperties": False,
            },
        ),
        model_config=AgentModelConfig(
            model="gpt-5",
            reasoning_effort="medium",
            max_output_tokens=1600,
        ),
    ),
    "lab_meeting_moderator": SpecialistProfile(
        name="lab_meeting_moderator",
        tool_names=["search_memory", "query_typed_graph", "query_literature_wiki", "record_observation", "review_memory"],
        system_prompt=(
            "You are a lab meeting moderator for a scientific team. Clarify the competing positions, isolate what evidence "
            "would actually close disagreement, and recommend the narrowest agenda for the next adjudication round. "
            "Use controversy pages, review pages, and graph evidence to separate evidence disputes from interpretation disputes."
        ),
        output_schema=StructuredSchema(
            name="lab_meeting_consensus_bundle",
            description="Structured group-style consensus and disagreement framing.",
            schema={
                "type": "object",
                "properties": {
                    "lab_meeting_consensus": _lab_meeting_consensus_schema(),
                    **COMMON_FIELDS,
                },
                "required": [
                    "lab_meeting_consensus",
                    "claims",
                    "evidence",
                    "uncertainties",
                    "confidence",
                    "open_questions",
                ],
                "additionalProperties": False,
            },
        ),
        model_config=AgentModelConfig(
            model="gpt-5",
            reasoning_effort="high",
            max_output_tokens=1700,
        ),
    ),
    "conflict_resolver": SpecialistProfile(
        name="conflict_resolver",
        tool_names=["record_observation", "search_memory"],
        system_prompt=(
            "You are a conflict resolution agent for scientific deliberation. "
            "Compare supporting and opposing specialist claims, identify where they truly conflict, "
            "and produce the narrowest set of disagreements that still matter for the next decision."
        ),
        output_schema=StructuredSchema(
            name="conflict_resolution",
            description="Resolution of cross-agent conflicts and remaining disagreements.",
            schema={
                "type": "object",
                "properties": {
                    "resolved_conflicts": _string_list_schema("Conflicts resolved by weighing evidence."),
                    "remaining_disagreements": _string_list_schema("Still-open disagreements worth human attention."),
                    "adjudication_logic": _string_list_schema("How the conflicts were weighed and resolved."),
                    "consensus_summary": _consensus_summary_schema(),
                    **COMMON_FIELDS,
                },
                "required": [
                    "resolved_conflicts",
                    "remaining_disagreements",
                    "adjudication_logic",
                    "consensus_summary",
                    "claims",
                    "evidence",
                    "uncertainties",
                    "confidence",
                    "open_questions",
                ],
                "additionalProperties": False,
            },
        ),
        model_config=AgentModelConfig(
            model="gpt-5",
            reasoning_effort="high",
            max_output_tokens=1800,
        ),
    ),
    "coordinator": SpecialistProfile(
        name="coordinator",
        tool_names=["record_observation", "write_file", "save_memory", "search_memory", "query_typed_graph", "query_literature_wiki", "review_memory"],
        system_prompt=(
            "You are the principal investigator agent coordinating a scientific workflow. "
            "Synthesize evidence, hypotheses, experiments, analysis, critique, and safety considerations "
            "into a practical next-step plan. Do not present a recommendation without tracing it back to evidence. "
            "Consult the typed research graph to ground recommendations in prior tested routes, challenged hypotheses, "
            "governed assets, and superseded or still-active lineages. Use literature review and controversy pages when deciding what disagreement matters most."
        ),
        output_schema=StructuredSchema(
            name="research_strategy",
            description="Integrated research strategy with evidence-backed decisions.",
            schema={
                "type": "object",
                "properties": {
                    "executive_summary": {"type": "string"},
                    "recommended_hypothesis": {"type": "string"},
                    "next_experiment": {"type": "string"},
                    "analysis_plan": _string_list_schema("Planned analyses"),
                    "decision_points": _string_list_schema("Key go/no-go decision points"),
                    "consensus_summary": _consensus_summary_schema(),
                    "project_distill": _project_distill_schema(),
                    "asset_registry_updates": _asset_registry_schema(),
                    **COMMON_FIELDS,
                },
                "required": [
                    "executive_summary",
                    "recommended_hypothesis",
                    "next_experiment",
                    "analysis_plan",
                    "decision_points",
                    "consensus_summary",
                    "project_distill",
                    "asset_registry_updates",
                    "claims",
                    "evidence",
                    "uncertainties",
                    "confidence",
                    "open_questions",
                ],
                "additionalProperties": False,
            },
        ),
        model_config=AgentModelConfig(
            model="gpt-5",
            reasoning_effort="high",
            max_output_tokens=2200,
        ),
    ),
    "report_writer": SpecialistProfile(
        name="report_writer",
        tool_names=["write_file", "search_memory"],
        system_prompt=(
            "You are a scientific report writer. Summarize specialist outputs into a concise research memo. "
            "Keep evidence links visible and separate current facts from open hypotheses."
        ),
        output_schema=StructuredSchema(
            name="research_report",
            description="Human-readable structured report sections.",
            schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "key_findings": _string_list_schema("Top findings"),
                    "recommended_next_steps": _string_list_schema("Actionable next steps"),
                    "references_to_check": _string_list_schema("Important references or source leads to verify"),
                    **COMMON_FIELDS,
                },
                "required": [
                    "title",
                    "summary",
                    "key_findings",
                    "recommended_next_steps",
                    "references_to_check",
                    "claims",
                    "evidence",
                    "uncertainties",
                    "confidence",
                    "open_questions",
                ],
                "additionalProperties": False,
            },
        ),
        model_config=AgentModelConfig(
            model="gpt-5-mini",
            reasoning_effort="low",
            max_output_tokens=1400,
        ),
    ),
}
