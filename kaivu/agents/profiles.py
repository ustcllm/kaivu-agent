from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .stage_types import StageExecutionMode, StageSpec


@dataclass(slots=True)
class QualityGateSpec:
    """Declarative quality gate used to govern scientific stage transitions."""

    name: str
    stage: str
    criteria: list[str] = field(default_factory=list)
    severity: str = "blocking"
    failure_effect: str = "requires review before strong claim update"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DisciplineProfile:
    """Prompt-first description of how a discipline should reason inside Kaivu."""

    name: str
    display_name: str
    scientific_style: str = ""
    stage_prompts: dict[str, str] = field(default_factory=dict)
    quality_gates: list[QualityGateSpec] = field(default_factory=list)
    failure_taxonomy: list[str] = field(default_factory=list)
    preferred_capabilities: dict[str, list[str]] = field(default_factory=dict)
    evidence_conventions: list[str] = field(default_factory=list)
    decision_rubric: str = ""
    validators: list[str] = field(default_factory=list)
    validation_blockers: list[str] = field(default_factory=list)
    execution_contract: dict[str, Any] = field(default_factory=dict)
    interpretation_policy: dict[str, Any] = field(default_factory=dict)
    lifecycle_stages: list[StageSpec] = field(default_factory=list)

    def prompt_for_stage(self, stage: str) -> str:
        return self.stage_prompts.get(stage, "")

    def capabilities_for_stage(self, stage: str) -> list[str]:
        return list(self.preferred_capabilities.get(stage, []))

    def quality_gates_for_stage(self, stage: str) -> list[QualityGateSpec]:
        return [gate for gate in self.quality_gates if gate.stage == stage or gate.stage == "*"]

    def stage_spec(self, stage: str) -> StageSpec | None:
        for spec in self.lifecycle_stages:
            if spec.name == stage:
                return spec
        return None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_lifecycle_stages() -> list[StageSpec]:
    return [
        StageSpec(
            name="question",
            hook="frame_problem",
            goal="frame the research problem as a testable scientific objective",
            output_contract=["problem_statement", "scope", "constraints", "success_criteria", "unknowns"],
        ),
        StageSpec(
            name="literature_review",
            hook="build_literature_plan",
            goal="synthesize evidence, methods, assumptions, conflicts, and failed attempts from sources",
            output_contract=["review_digest", "claim_table", "method_table", "conflicts", "open_questions"],
            execution_mode=StageExecutionMode(capability_registry_driven=True),
            default_capabilities=["literature_search", "citation_resolution", "literature_wiki_query"],
        ),
        StageSpec(
            name="hypothesis_generation",
            hook="synthesize_hypotheses",
            goal="generate falsifiable hypotheses with assumptions, predictions, rivals, and minimum discriminative tests",
            output_contract=["hypotheses", "assumptions", "predictions", "rival_hypotheses", "validators"],
        ),
        StageSpec(
            name="hypothesis_validation",
            hook="validate_hypothesis",
            goal="validate novelty, feasibility, falsifiability, and evidence readiness",
            output_contract=["validator_set", "blocking_issues", "validation_boundary", "go_no_go"],
            execution_mode=StageExecutionMode(quality_gate_driven=True),
        ),
        StageSpec(
            name="experiment_design",
            hook="design_experiment",
            goal="design a test that can produce interpretable evidence with explicit quality gates",
            output_contract=["protocol", "variables", "controls", "quality_gates", "expected_artifacts"],
            execution_mode=StageExecutionMode(quality_gate_driven=True),
        ),
        StageSpec(
            name="execution_planning",
            hook="build_execution_plan",
            goal="prepare a safe handoff plan with required inputs, artifacts, and approval boundaries",
            output_contract=["handoff_target", "required_inputs", "approval_boundary", "artifact_contract"],
            execution_mode=StageExecutionMode(
                capability_registry_driven=True,
                runtime_policy_driven=True,
                executor_handoff_driven=True,
            ),
            default_capabilities=["executor_handoff"],
        ),
        StageSpec(
            name="quality_review",
            hook="define_quality_gates",
            goal="judge whether evidence is valid enough to update claims",
            output_contract=["quality_status", "blocking_issues", "evidence_reliability", "recommended_action"],
            execution_mode=StageExecutionMode(quality_gate_driven=True),
        ),
        StageSpec(
            name="analysis",
            hook="interpret_result",
            goal="analyze observations while preserving uncertainty, provenance, and alternative explanations",
            output_contract=["findings", "uncertainty", "alternative_explanations", "claim_updates"],
            execution_mode=StageExecutionMode(capability_registry_driven=True),
            default_capabilities=["python_analysis"],
        ),
        StageSpec(
            name="decision",
            hook="decide_next_action",
            goal="choose continue, revise, stop, replicate, or report based on evidence and value of information",
            output_contract=["decision", "rationale", "next_action", "memory_updates", "graph_updates"],
            execution_mode=StageExecutionMode(quality_gate_driven=True),
        ),
        StageSpec(
            name="memory_and_graph_update",
            hook="update_memory_and_graph",
            goal="write durable memory and graph updates for decisions, evidence, failures, and claim status",
            output_contract=["memory_items", "graph_facts", "claim_status_updates"],
            execution_mode=StageExecutionMode(capability_registry_driven=True, runtime_policy_driven=True),
            default_capabilities=["memory_write", "graph_update"],
        ),
        StageSpec(
            name="reporting",
            hook="build_reporting_plan",
            goal="produce a concise scientific report with claims, evidence, limitations, and next actions",
            output_contract=["summary", "evidence", "limitations", "next_steps"],
        ),
    ]


def build_general_science_profile() -> DisciplineProfile:
    return DisciplineProfile(
        name="general_science",
        display_name="General Science",
        scientific_style="Reason from evidence, uncertainty, rival hypotheses, and reproducible tests.",
        stage_prompts={},
        quality_gates=[
            QualityGateSpec(
                name="evidence_provenance_recorded",
                stage="*",
                criteria=["Claims must preserve source, observation, artifact, or memory provenance."],
            ),
            QualityGateSpec(
                name="quality_failure_blocks_strong_claim_update",
                stage="decision",
                criteria=["Weak or failed quality review cannot produce a strong support/reject claim update."],
            ),
        ],
        failure_taxonomy=[
            "protocol_failure",
            "quality_control_failure",
            "negative_result",
            "ambiguous_result",
            "execution_failure",
        ],
        preferred_capabilities={},
        evidence_conventions=["observation plus provenance plus quality status"],
        decision_rubric="Prefer the next action with clear information gain under cost, risk, and quality constraints.",
        lifecycle_stages=default_lifecycle_stages(),
    )


def build_ai_profile() -> DisciplineProfile:
    profile = build_general_science_profile()
    profile.name = "artificial_intelligence"
    profile.display_name = "Artificial Intelligence"
    profile.scientific_style = (
        "Reason about benchmark validity, leakage, baselines, ablations, seeds, compute budget, and reproducibility."
    )
    profile.stage_prompts.update(
        {
            "literature_review": (
                "Extract benchmark setting, dataset split, baseline strength, compute budget, code availability, "
                "reproducibility evidence, contamination risk, and missing ablations."
            ),
            "hypothesis_generation": (
                "Generate hypotheses over model architecture, data mixture, preprocessing, optimization, loss, "
                "evaluation, and scaling behavior."
            ),
            "analysis": (
                "Treat single-seed gains as weak evidence unless replicated. Separate exploratory tuning from confirmatory evaluation."
            ),
            "experiment_design": (
                "Use frozen splits, strong baselines, reproducible configs, per-seed variance, contamination checks, and ablation design."
            ),
            "execution_planning": (
                "Plan AI runs with frozen validation protocol, clear compute budget, recorded dependencies, seeds, search space, and stopping rule."
            ),
            "quality_review": (
                "Check leakage, baseline fairness, config snapshot, multi-seed variance, and whether the result is confirmatory or exploratory."
            ),
            "decision": (
                "Do not treat a single-seed improvement or exploratory tuning score as confirmatory evidence."
            ),
        }
    )
    profile.quality_gates.extend(
        [
            QualityGateSpec("dataset_leakage_check", "quality_review", ["Check target, train/test, temporal, group, and preprocessing leakage."]),
            QualityGateSpec("baseline_reproduction_check", "quality_review", ["Compare against a strong and reproducible baseline."]),
            QualityGateSpec("multi_seed_variance_check", "analysis", ["Estimate whether the result survives seed variance."]),
        ]
    )
    profile.failure_taxonomy.extend(["data_leakage", "seed_sensitivity", "benchmark_overfitting", "irreproducible_environment"])
    profile.validators.extend(
        [
            "benchmark_validity",
            "data_leakage_risk",
            "baseline_fairness",
            "reproducibility_readiness",
            "compute_feasibility",
        ]
    )
    profile.validation_blockers.extend(
        [
            "benchmark split or metric is not frozen",
            "baseline is too weak to support method-level claims",
            "contamination or leakage risk is unresolved",
        ]
    )
    profile.execution_contract = {
        "experiment_unit": "one reproducible training, evaluation, ablation, or benchmark run",
        "protocol_template": [
            "define benchmark, dataset split, baseline, metric, and compute budget",
            "freeze validation protocol before model selection",
            "separate exploratory tuning from confirmatory evaluation",
            "record search space, sampler, seeds, dependencies, and stopping rule",
        ],
        "measurement_contract": [
            "primary metric with direction",
            "secondary metrics",
            "per-seed results",
            "dataset split identifiers",
            "runtime and compute budget",
        ],
        "artifact_contract": [
            "config.json",
            "metrics.json",
            "seed_report",
            "environment_snapshot",
            "model_checkpoint_or_reference",
            "prediction_or_submission_file_when_applicable",
        ],
        "quality_gates": [
            "dataset_leakage_check",
            "baseline_reproduction_check",
            "configuration_snapshot_saved",
            "multi_seed_variance_check",
            "confirmatory_holdout_check",
        ],
        "safety_constraints": ["no hidden test-set tuning", "respect compute budget"],
        "failure_modes": ["data leakage", "seed sensitivity", "benchmark overfitting", "irreproducible environment"],
        "interpretation_boundaries": [
            "single-seed improvement is weak evidence until replicated",
            "exploratory tuning can rank configurations but cannot confirm a scientific claim",
            "baseline reproduction failure blocks method-level interpretation",
        ],
        "scheduler_rules": [
            "prefer cheap baselines and ablations before large training runs",
            "schedule confirmatory evaluation only after frozen validation selection",
            "prioritize reproducibility checks when variance is high",
        ],
        "handoff_target": "ai_training_runner",
    }
    profile.interpretation_policy = {
        "ai_specific_evidence": ["locked validation metric", "per-seed variance", "ablation delta", "contamination status"],
        "default_rule": "single-seed exploratory improvement can prioritize follow-up but cannot confirm a scientific claim",
        "claim_update_boundary": "benchmark reproduction and leakage checks must pass before model claims are strengthened",
    }
    profile.preferred_capabilities.update(
        {
            "analysis": ["data_read", "python_analysis"],
            "execution_planning": ["ai_training_execution", "executor_handoff"],
        }
    )
    return profile


def build_chemistry_profile() -> DisciplineProfile:
    profile = build_general_science_profile()
    profile.name = "chemistry"
    profile.display_name = "Chemistry"
    profile.scientific_style = (
        "Reason about reaction conditions, safety, characterization, yield, selectivity, controls, and mechanism uncertainty."
    )
    profile.stage_prompts.update(
        {
            "experiment_design": "Design controlled reaction, synthesis, characterization, or condition-screen tests with explicit safety and readout boundaries.",
            "analysis": "Interpret yield, conversion, selectivity, spectra, chromatograms, replicate status, and workup or instrument quality before mechanism updates.",
        }
    )
    profile.validators.extend(["safety_feasibility", "synthetic_accessibility", "condition_space_plausibility", "analytical_readout_readiness"])
    profile.failure_taxonomy.extend(["reagent degradation", "side reaction", "instrument drift", "workup loss", "batch effect"])
    profile.quality_gates.extend(
        [
            QualityGateSpec("safety_review_check", "execution_planning", ["Safety envelope must be reviewed before execution."]),
            QualityGateSpec("reagent_batch_recorded", "quality_review", ["Reagent lots and batches must be recorded."]),
            QualityGateSpec("instrument_calibration", "quality_review", ["Analytical instruments must have calibration status."]),
            QualityGateSpec("replicate_or_control_present", "quality_review", ["Replicate, blank, or positive control should be present when needed."]),
        ]
    )
    profile.execution_contract = {
        "experiment_unit": "one controlled reaction, synthesis, characterization, or condition-screen run",
        "protocol_template": [
            "define reagent lots, stoichiometry, solvent, catalyst, temperature, and time",
            "freeze safety envelope before execution",
            "include blank, positive control, or replicate where needed",
            "record quench, workup, purification, and analytical method",
        ],
        "measurement_contract": ["yield or conversion", "selectivity", "spectral or chromatographic evidence", "replicate count"],
        "artifact_contract": ["lab_notebook_entry", "reagent_lot_table", "spectra_or_chromatogram_refs", "yield_table"],
        "quality_gates": ["safety_review_check", "reagent_batch_recorded", "instrument_calibration", "replicate_or_control_present"],
        "safety_constraints": ["stay inside approved safety envelope", "flag hazardous reagent, pressure, or thermal conditions"],
        "failure_modes": ["reagent degradation", "side reaction", "instrument drift", "workup loss", "batch effect"],
        "interpretation_boundaries": [
            "single failed condition narrows a condition family but does not reject a mechanism",
            "instrument or workup failure is quality-control failure before negative scientific evidence",
        ],
        "scheduler_rules": [
            "prefer low-hazard microscale screens before expensive or hazardous runs",
            "prioritize replicate confirmation before mechanism belief upgrade",
        ],
        "handoff_target": "domain_lab_adapter",
    }
    profile.interpretation_policy = {
        "chemistry_specific_evidence": ["yield or conversion", "selectivity", "spectra or chromatograms", "replicate/control status"],
        "default_rule": "single failed condition narrows a condition family but does not reject a mechanism",
        "quality_boundary": "instrument, workup, or reagent failures are quality-control failures before scientific negative evidence",
    }
    return profile


def build_chemical_engineering_profile() -> DisciplineProfile:
    profile = build_general_science_profile()
    profile.name = "chemical_engineering"
    profile.display_name = "Chemical Engineering"
    profile.scientific_style = "Reason about process windows, steady state, controls, sensor validity, safety, and mass/energy balance."
    profile.failure_taxonomy.extend(["process instability", "sensor drift", "mass balance mismatch", "unsafe excursion", "scale-up artifact"])
    profile.quality_gates.extend(
        [
            QualityGateSpec("sensor_calibration_verified", "quality_review", ["Sensor calibration status must be verified."]),
            QualityGateSpec("steady_state_verified", "quality_review", ["Steady-state criteria must be checked before process interpretation."]),
            QualityGateSpec("mass_balance_reviewed", "quality_review", ["Mass balance closure must be reviewed."]),
            QualityGateSpec("shutdown_criteria_defined", "execution_planning", ["Unsafe excursions require explicit shutdown criteria."]),
        ]
    )
    profile.execution_contract = {
        "experiment_unit": "one process run, simulation, or operating-window sweep",
        "protocol_template": [
            "define process flow, operating window, control variables, and shutdown criteria",
            "record sensor map, residence time, and steady-state criteria",
            "include mass and energy balance checks",
        ],
        "measurement_contract": ["conversion", "selectivity", "throughput", "energy use", "mass balance closure", "sensor trace"],
        "artifact_contract": ["process_trace", "sensor_log", "mass_balance_report", "process_limits_record"],
        "quality_gates": ["sensor_calibration_verified", "steady_state_verified", "mass_balance_reviewed", "shutdown_criteria_defined"],
        "safety_constraints": ["respect pressure, temperature, and process limits", "require shutdown path for unsafe excursions"],
        "failure_modes": ["sensor drift", "unstable steady state", "mass balance mismatch", "scale-up artifact"],
        "interpretation_boundaries": [
            "unstable operation blocks process performance interpretation",
            "mass-balance mismatch quarantines performance claims",
        ],
        "scheduler_rules": [
            "prefer simulation or low-throughput process windows before high-risk pilot runs",
            "favor experiments with clear shutdown criteria and high information gain per cost",
        ],
        "handoff_target": "domain_lab_adapter",
    }
    profile.interpretation_policy = {
        "claim_effect": "process instability or mass-balance failure quarantines performance claims before mechanism updates",
    }
    return profile


def build_physics_profile() -> DisciplineProfile:
    profile = build_general_science_profile()
    profile.name = "physics"
    profile.display_name = "Physics"
    profile.scientific_style = "Reason about observables, calibration, uncertainty, background, parameter regions, simulations, and theory updates."
    profile.failure_taxonomy.extend(["calibration drift", "background contamination", "thermal drift", "resolution limit", "model mismatch"])
    profile.quality_gates.extend(
        [
            QualityGateSpec("instrument_alignment_verified", "quality_review", ["Instrument alignment must be verified."]),
            QualityGateSpec("calibration_reference_checked", "quality_review", ["Calibration reference must be checked."]),
            QualityGateSpec("background_noise_characterized", "quality_review", ["Background and noise must be characterized."]),
            QualityGateSpec("uncertainty_model_recorded", "analysis", ["Uncertainty model must be recorded before theory update."]),
        ]
    )
    profile.execution_contract = {
        "experiment_unit": "one calibrated measurement, simulation, or parameter sweep",
        "protocol_template": [
            "define observable, theoretical prediction, sweep range, and resolution",
            "record calibration reference, background, and uncertainty model",
            "include repeat points and drift checks",
        ],
        "measurement_contract": ["raw measurements", "calibrated measurements", "uncertainty estimate", "background or noise characterization"],
        "artifact_contract": ["instrument_log", "raw_measurements", "calibration_report", "uncertainty_model"],
        "quality_gates": ["instrument_alignment_verified", "calibration_reference_checked", "background_noise_characterized", "uncertainty_model_recorded"],
        "safety_constraints": ["respect instrument operating limits", "flag radiation, cryogenic, laser, or high-voltage risks"],
        "failure_modes": ["calibration drift", "background contamination", "thermal drift", "resolution limit", "model mismatch"],
        "interpretation_boundaries": [
            "calibration failure blocks theory update",
            "null result constrains only the measured parameter region and sensitivity level",
        ],
        "scheduler_rules": [
            "schedule calibration and background checks before high-cost sweeps",
            "repeat surprising anomalies before strong theory revision",
        ],
        "handoff_target": "domain_lab_adapter",
    }
    profile.interpretation_policy = {
        "physics_specific_evidence": ["calibrated measurement", "background/noise estimate", "uncertainty model", "parameter region"],
        "default_rule": "calibration failure blocks theory update",
        "claim_update_boundary": "null results constrain only measured parameter regions and sensitivity levels",
    }
    return profile


def build_mathematics_profile() -> DisciplineProfile:
    profile = build_general_science_profile()
    profile.name = "mathematics"
    profile.display_name = "Mathematics"
    profile.scientific_style = "Reason about conjectures, definitions, lemmas, proof obligations, counterexamples, and formalization readiness."
    profile.validators = [
        "definition_precision",
        "assumption_explicitness",
        "proof_consistency",
        "counterexample_search_readiness",
        "formalization_feasibility",
    ]
    profile.validation_blockers = [
        "statement is not precise enough to prove or refute",
        "hidden assumptions are unresolved",
        "known counterexample already invalidates the conjecture",
    ]
    profile.failure_taxonomy.extend(["hidden assumption", "false lemma", "unbounded search", "counterexample found", "proof gap"])
    profile.preferred_capabilities.update({"execution_planning": ["proof_checking", "counterexample_search", "executor_handoff"]})
    profile.quality_gates.extend(
        [
            QualityGateSpec("assumptions_explicit", "hypothesis_validation", ["Definitions and assumptions must be explicit."]),
            QualityGateSpec("edge_cases_reviewed", "hypothesis_validation", ["Boundary cases should be reviewed."]),
            QualityGateSpec("proof_gaps_marked", "analysis", ["Proof gaps must be marked and cannot be treated as proof."]),
            QualityGateSpec("counterexamples_verified", "analysis", ["Counterexamples must be verified before rejecting or narrowing a conjecture."]),
        ]
    )
    profile.execution_contract = {
        "experiment_unit": "one proof attempt, formalization step, search run, or counterexample test",
        "protocol_template": [
            "state conjecture, assumptions, definitions, and target theorem precisely",
            "decompose into lemmas and proof obligations",
            "search proof strategies and counterexamples separately",
            "mark proof gaps and hidden assumptions explicitly",
        ],
        "measurement_contract": ["proof state", "lemma dependency status", "counterexample candidates", "search bounds"],
        "artifact_contract": ["proof_attempt_log", "counterexample_candidates", "lemma_dependency_graph", "formal_assumptions"],
        "quality_gates": ["assumptions_explicit", "edge_cases_reviewed", "proof_gaps_marked", "counterexamples_verified"],
        "safety_constraints": ["do not treat heuristic evidence as proof", "mark unverified lemmas explicitly"],
        "failure_modes": ["hidden assumption", "false lemma", "unbounded search", "counterexample found", "proof gap"],
        "interpretation_boundaries": [
            "computational evidence can prioritize a conjecture but cannot prove it",
            "verified counterexample rejects or narrows the conjecture immediately",
        ],
        "scheduler_rules": [
            "prioritize counterexample search before expensive proof elaboration",
            "branch to weaker conjectures when boundary cases fail",
        ],
        "handoff_target": "proof_search_adapter",
    }
    profile.interpretation_policy = {
        "mathematics_specific_evidence": ["proof step", "lemma dependency", "counterexample", "formal proof state"],
        "default_rule": "heuristic or computational evidence can guide search but cannot prove the conjecture",
        "claim_update_boundary": "verified counterexample rejects or narrows the conjecture immediately",
    }
    return profile


def build_kaggle_profile() -> DisciplineProfile:
    profile = build_ai_profile()
    profile.name = "kaggle_competition"
    profile.display_name = "Kaggle Competition"
    profile.stage_prompts.update(
        {
            "question": (
                "Read the competition as part of problem definition. Extract objective, official metric, metric direction, "
                "target column, id column, submission format, rules, external data policy, timeline, and unknowns."
            ),
            "literature_review": (
                "Extend literature review with Kaggle intelligence: official pages, discussions, notebooks, baselines, "
                "winner writeups, CV schemes, and known leakage traps."
            ),
            "experiment_design": (
                "Design a Kaggle experiment with frozen CV, OOF predictions where useful, leakage audit, sample-submission "
                "schema validation, and submission dry-run."
            ),
        }
    )
    profile.quality_gates.extend(
        [
            QualityGateSpec("sample_submission_schema_validity", "quality_review", ["Submission columns and row count must match sample submission."]),
            QualityGateSpec("leaderboard_overfit_guard", "decision", ["Public leaderboard cannot be the only validation signal."]),
            QualityGateSpec("rule_compliance_check", "execution_planning", ["External data and submission behavior must satisfy competition rules."]),
        ]
    )
    profile.failure_taxonomy.extend(["leaderboard_overfit", "submission_schema_error", "public_private_leaderboard_gap"])
    profile.preferred_capabilities.update(
        {
            "execution_planning": ["kaggle_submission_dry_run", "ai_training_execution", "executor_handoff"],
            "quality_review": ["kaggle_submission_dry_run"],
        }
    )
    return profile


def build_profile(name: str) -> DisciplineProfile:
    normalized = name.strip().lower()
    if normalized in {"ai", "artificial_intelligence"}:
        return build_ai_profile()
    if normalized in {"kaggle", "kaggle_competition"}:
        return build_kaggle_profile()
    if normalized == "chemistry":
        return build_chemistry_profile()
    if normalized == "chemical_engineering":
        return build_chemical_engineering_profile()
    if normalized == "physics":
        return build_physics_profile()
    if normalized in {"mathematics", "math"}:
        return build_mathematics_profile()
    profile = build_general_science_profile()
    profile.name = normalized or "general_science"
    profile.display_name = profile.name.replace("_", " ").title()
    return profile


def available_discipline_profiles() -> list[str]:
    return [
        "general_science",
        "artificial_intelligence",
        "kaggle_competition",
        "chemistry",
        "chemical_engineering",
        "physics",
        "mathematics",
    ]
