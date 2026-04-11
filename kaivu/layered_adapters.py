from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class GeneralScientificAdapterLayer:
    layer_id: str = "adapter-layer::general_scientific"
    responsibilities: list[str] = field(
        default_factory=lambda: [
            "hypothesis lifecycle management",
            "evidence and uncertainty tracking",
            "experiment state governance",
            "failure memory reuse",
            "provenance and artifact registration",
            "reproducibility and quality-control gating",
        ]
    )
    universal_state_objects: list[str] = field(
        default_factory=lambda: [
            "research_program",
            "hypothesis_tree",
            "evidence_map",
            "experiment_graph",
            "failure_memory",
            "artifact_registry",
            "runtime_manifest",
        ]
    )
    universal_gates: list[str] = field(
        default_factory=lambda: [
            "claim_requires_evidence",
            "experiment_requires_protocol",
            "quality_failure_blocks_belief_upgrade",
            "negative_result_enters_memory",
            "external_execution_requires_approval",
        ]
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DisciplineAdapterLayer:
    discipline: str
    problem_types: list[str] = field(default_factory=list)
    data_modalities: list[str] = field(default_factory=list)
    experiment_families: list[str] = field(default_factory=list)
    quality_controls: list[str] = field(default_factory=list)
    failure_taxonomy: list[str] = field(default_factory=list)
    interpretation_rules: list[str] = field(default_factory=list)
    recommended_agents: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TaskAdapterLayer:
    task_id: str
    parent_discipline: str
    task_type: str
    workflow_stages: list[str] = field(default_factory=list)
    task_state_objects: list[str] = field(default_factory=list)
    metrics: list[str] = field(default_factory=list)
    scheduler_objectives: list[str] = field(default_factory=list)
    risk_controls: list[str] = field(default_factory=list)
    expected_artifacts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ToolchainAdapterLayer:
    toolchain_id: str
    task_id: str
    runtimes: list[str] = field(default_factory=list)
    storage: list[str] = field(default_factory=list)
    executors: list[str] = field(default_factory=list)
    evaluators: list[str] = field(default_factory=list)
    permission_requirements: list[str] = field(default_factory=list)
    reproducibility_requirements: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LayeredAdapterComposition:
    composition_id: str
    general: GeneralScientificAdapterLayer
    discipline: DisciplineAdapterLayer
    task: TaskAdapterLayer | None = None
    toolchain: ToolchainAdapterLayer | None = None
    inherited_gates: list[str] = field(default_factory=list)
    handoff_contract: dict[str, Any] = field(default_factory=dict)
    readiness_state: str = "ready"
    blocked_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "composition_id": self.composition_id,
            "readiness_state": self.readiness_state,
            "blocked_reasons": self.blocked_reasons,
            "general": self.general.to_dict(),
            "discipline": self.discipline.to_dict(),
            "task": self.task.to_dict() if self.task else None,
            "toolchain": self.toolchain.to_dict() if self.toolchain else None,
            "inherited_gates": self.inherited_gates,
            "handoff_contract": self.handoff_contract,
        }


def build_layered_adapter_summary(
    *,
    discipline: str,
    task_type: str = "",
    toolchain: str = "",
    available_tools: list[str] | None = None,
) -> dict[str, Any]:
    general = GeneralScientificAdapterLayer()
    discipline_layer = _discipline_layer(discipline)
    task_layer = _task_layer(discipline_layer.discipline, task_type)
    toolchain_layer = _toolchain_layer(task_layer, toolchain, available_tools or []) if task_layer else None
    blocked = _blocked_reasons(task_layer=task_layer, toolchain_layer=toolchain_layer)
    composition = LayeredAdapterComposition(
        composition_id="::".join(
            [
                "layered-adapter",
                _slugify(discipline_layer.discipline),
                _slugify(task_layer.task_type if task_layer else "general"),
                _slugify(toolchain_layer.toolchain_id if toolchain_layer else "unbound"),
            ]
        ),
        general=general,
        discipline=discipline_layer,
        task=task_layer,
        toolchain=toolchain_layer,
        inherited_gates=_dedupe(
            general.universal_gates
            + discipline_layer.quality_controls
            + (task_layer.risk_controls if task_layer else [])
            + (toolchain_layer.permission_requirements if toolchain_layer else [])
        ),
        handoff_contract=_handoff_contract(
            discipline_layer=discipline_layer,
            task_layer=task_layer,
            toolchain_layer=toolchain_layer,
        ),
        readiness_state="blocked" if blocked else "ready",
        blocked_reasons=blocked,
    )
    return {
        "interface_version": "layered_adapter_v1",
        "composition": composition.to_dict(),
        "layer_order": [
            "general_scientific",
            "discipline",
            "task",
            "toolchain",
        ],
        "design_rule": (
            "Core scientific state is shared; adapters only add discipline, task, "
            "and toolchain-specific contracts."
        ),
    }


def list_builtin_layered_adapters() -> dict[str, Any]:
    disciplines = [
        "artificial_intelligence",
        "chemistry",
        "chemical_engineering",
        "physics",
        "mathematics",
    ]
    tasks = {
        "artificial_intelligence": ["kaggle_competition", "llm_fine_tuning", "benchmark_reproduction"],
        "chemistry": ["reaction_optimization", "molecular_property_screen"],
        "chemical_engineering": ["process_optimization", "scale_up_study"],
        "physics": ["simulation_study", "instrument_sweep"],
        "mathematics": ["theorem_proving", "counterexample_search"],
    }
    return {
        "disciplines": disciplines,
        "task_adapters": tasks,
        "composition_pattern": "Kaivu Core -> Discipline Adapter -> Task Adapter -> Toolchain Adapter",
    }


def _discipline_layer(discipline: str) -> DisciplineAdapterLayer:
    normalized = _normalize_discipline(discipline)
    if normalized == "artificial_intelligence":
        return DisciplineAdapterLayer(
            discipline=normalized,
            problem_types=["classification", "regression", "ranking", "generation", "representation_learning"],
            data_modalities=["tabular", "text", "image", "audio", "multimodal", "graph", "time_series"],
            experiment_families=["baseline", "ablation", "hyperparameter_search", "model_comparison", "scaling_study"],
            quality_controls=[
                "dataset_split_verified",
                "contamination_or_leakage_checked",
                "baseline_reproduced",
                "seed_variance_reviewed",
                "heldout_evaluation_preserved",
            ],
            failure_taxonomy=["data leakage", "benchmark contamination", "seed sensitivity", "overfitting", "irreproducible environment"],
            interpretation_rules=[
                "single-seed gains are weak evidence",
                "test-set reuse contaminates confirmatory evidence",
                "ablation conclusions require one controlled variable change",
            ],
            recommended_agents=["dataset_profiler", "evaluation_protocol_designer", "training_recipe_planner", "ablation_manager"],
        )
    if normalized == "chemistry":
        return DisciplineAdapterLayer(
            discipline=normalized,
            problem_types=["reaction_discovery", "condition_optimization", "mechanism_study", "property_screen"],
            data_modalities=["reaction_table", "spectra", "chromatogram", "molecular_structure", "lab_notebook"],
            experiment_families=["condition_screen", "control_experiment", "replicate", "mechanistic_probe"],
            quality_controls=["safety_review", "reagent_batch_recorded", "instrument_calibration", "blank_or_control_present"],
            failure_taxonomy=["side reaction", "contamination", "instrument drift", "workup loss", "batch effect"],
            interpretation_rules=[
                "instrument failure is not a negative scientific result",
                "single failed condition narrows a condition family before rejecting a mechanism",
                "replicated negative result can down-rank a mechanism branch",
            ],
            recommended_agents=["safety_reviewer", "protocol_writer", "analytical_quality_reviewer"],
        )
    if normalized == "chemical_engineering":
        return DisciplineAdapterLayer(
            discipline=normalized,
            problem_types=["process_design", "scale_up", "reactor_optimization", "separation_optimization"],
            data_modalities=["sensor_trace", "process_log", "simulation_output", "mass_balance_table"],
            experiment_families=["process_sweep", "simulation_screen", "pilot_run", "sensitivity_analysis"],
            quality_controls=["steady_state_verified", "sensor_calibration_verified", "mass_balance_closed", "shutdown_criteria_defined"],
            failure_taxonomy=["unstable steady state", "sensor drift", "mass balance mismatch", "control-loop instability"],
            interpretation_rules=[
                "mass-balance mismatch quarantines process performance claims",
                "unstable operation blocks performance interpretation",
                "scale-up failures update transferability assumptions",
            ],
            recommended_agents=["process_safety_reviewer", "mass_balance_reviewer", "simulation_reviewer"],
        )
    if normalized == "physics":
        return DisciplineAdapterLayer(
            discipline=normalized,
            problem_types=["parameter_estimation", "theory_test", "simulation", "instrument_measurement"],
            data_modalities=["raw_measurement", "calibrated_trace", "simulation_grid", "uncertainty_model"],
            experiment_families=["instrument_sweep", "simulation_sweep", "calibration_run", "background_measurement"],
            quality_controls=["calibration_reference_checked", "background_noise_characterized", "uncertainty_model_recorded"],
            failure_taxonomy=["calibration drift", "background contamination", "resolution limit", "model mismatch"],
            interpretation_rules=[
                "null result constrains only the measured parameter region",
                "calibration failure blocks theory update",
                "surprising anomalies require repeat and artifact checks",
            ],
            recommended_agents=["uncertainty_modeler", "instrument_quality_reviewer", "simulation_runner"],
        )
    if normalized == "mathematics":
        return DisciplineAdapterLayer(
            discipline=normalized,
            problem_types=["conjecture_generation", "proof_search", "counterexample_search", "formalization"],
            data_modalities=["definitions", "lemma_graph", "proof_attempt", "counterexample_candidate"],
            experiment_families=["proof_attempt", "counterexample_search", "formal_verification", "symbolic_search"],
            quality_controls=["assumptions_explicit", "proof_gaps_marked", "counterexamples_verified", "formal_status_recorded"],
            failure_taxonomy=["hidden assumption", "false lemma", "proof gap", "counterexample found", "unbounded search"],
            interpretation_rules=[
                "computational evidence is not proof",
                "verified counterexample rejects or narrows the conjecture",
                "failed proof paths should enter failed-attempt memory",
            ],
            recommended_agents=["formalizer", "proof_reviewer", "counterexample_searcher"],
        )
    return DisciplineAdapterLayer(
        discipline="general_science",
        problem_types=["hypothesis_test", "evidence_review", "experiment_planning"],
        data_modalities=["document", "table", "artifact"],
        experiment_families=["baseline", "control", "replicate", "comparison"],
        quality_controls=["protocol_recorded", "artifact_provenance_recorded", "quality_review_completed"],
        failure_taxonomy=["missing protocol", "missing artifact", "ambiguous interpretation"],
        interpretation_rules=["quality failure blocks strong claim updates"],
        recommended_agents=["scheduler", "quality_control_reviewer"],
    )


def _task_layer(discipline: str, task_type: str) -> TaskAdapterLayer | None:
    task = _slugify(task_type).replace("-", "_")
    if not task:
        return None
    if discipline == "artificial_intelligence" and task == "kaggle_competition":
        return TaskAdapterLayer(
            task_id="task-adapter::ai::kaggle_competition",
            parent_discipline=discipline,
            task_type=task,
            workflow_stages=[
                "read_competition",
                "profile_dataset",
                "design_validation",
                "build_baseline",
                "run_experiments",
                "ensemble_and_submit",
                "interpret_leaderboard",
                "distill_transfer_memory",
            ],
            task_state_objects=["competition_profile", "metric_profile", "validation_plan", "experiment_ledger", "submission_ledger"],
            metrics=["cross_validation_score", "public_leaderboard_score", "private_leaderboard_score", "shakeup_risk"],
            scheduler_objectives=["maximize reliable CV", "control public leaderboard overfit", "maximize model diversity per cost"],
            risk_controls=["leakage_detection_required", "submission_budget_governed", "public_lb_not_confirmatory"],
            expected_artifacts=["train_script", "oof_predictions", "test_predictions", "submission_csv", "leaderboard_record"],
        )
    if discipline == "artificial_intelligence" and task in {"llm_fine_tuning", "benchmark_reproduction"}:
        return TaskAdapterLayer(
            task_id=f"task-adapter::ai::{task}",
            parent_discipline=discipline,
            task_type=task,
            workflow_stages=[
                "define_benchmark",
                "audit_dataset",
                "build_training_recipe",
                "run_training",
                "evaluate_checkpoint",
                "run_ablations",
                "publish_reproduction_bundle",
            ],
            task_state_objects=["dataset_card", "training_recipe", "checkpoint_registry", "evaluation_report", "ablation_matrix"],
            metrics=["primary_benchmark_metric", "secondary_metrics", "cost", "variance_across_seeds"],
            scheduler_objectives=["maximize validated improvement", "minimize compute waste", "separate exploratory and confirmatory runs"],
            risk_controls=["benchmark_contamination_check", "heldout_set_preserved", "license_and_privacy_review"],
            expected_artifacts=["config", "checkpoint", "logs", "metrics", "model_card", "reproduction_script"],
        )
    if discipline == "chemistry" and task in {"reaction_optimization", "molecular_property_screen"}:
        return TaskAdapterLayer(
            task_id=f"task-adapter::chemistry::{task}",
            parent_discipline=discipline,
            task_type=task,
            workflow_stages=["define_reaction_family", "review_safety", "screen_conditions", "analyze_readout", "replicate_top_conditions"],
            task_state_objects=["reaction_space", "condition_matrix", "safety_envelope", "analytical_readout", "negative_condition_memory"],
            metrics=["yield", "selectivity", "purity", "reproducibility"],
            scheduler_objectives=["maximize information per safe run", "prioritize controls and replicates", "avoid repeated failed condition families"],
            risk_controls=["safety_review_required", "reagent_lot_tracking", "instrument_calibration_required"],
            expected_artifacts=["protocol", "condition_table", "spectra_refs", "yield_table", "safety_notes"],
        )
    if discipline == "chemical_engineering" and task in {"process_optimization", "scale_up_study"}:
        return TaskAdapterLayer(
            task_id=f"task-adapter::chemical_engineering::{task}",
            parent_discipline=discipline,
            task_type=task,
            workflow_stages=["define_process_window", "simulate_or_screen", "verify_steady_state", "collect_process_trace", "close_balances"],
            task_state_objects=["process_flow", "operating_window", "sensor_map", "mass_energy_balance", "scaleup_risk_register"],
            metrics=["conversion", "throughput", "energy_use", "mass_balance_closure", "safety_margin"],
            scheduler_objectives=["maximize value of information per cost", "respect safety envelope", "prioritize stable operating regions"],
            risk_controls=["shutdown_criteria_required", "steady_state_required", "mass_balance_required"],
            expected_artifacts=["process_trace", "sensor_log", "balance_report", "simulation_config"],
        )
    if discipline == "physics" and task in {"simulation_study", "instrument_sweep"}:
        return TaskAdapterLayer(
            task_id=f"task-adapter::physics::{task}",
            parent_discipline=discipline,
            task_type=task,
            workflow_stages=["define_observable", "calibrate_or_initialize", "run_sweep", "estimate_uncertainty", "compare_theory"],
            task_state_objects=["theory_prediction", "sweep_plan", "calibration_record", "uncertainty_model", "anomaly_log"],
            metrics=["fit_error", "uncertainty", "signal_to_noise", "parameter_constraint"],
            scheduler_objectives=["maximize theory discrimination", "repeat anomalies", "control calibration cost"],
            risk_controls=["calibration_required", "background_required", "uncertainty_model_required"],
            expected_artifacts=["raw_measurements", "calibrated_data", "fit_report", "simulation_config"],
        )
    if discipline == "mathematics" and task in {"theorem_proving", "counterexample_search"}:
        return TaskAdapterLayer(
            task_id=f"task-adapter::mathematics::{task}",
            parent_discipline=discipline,
            task_type=task,
            workflow_stages=["state_conjecture", "decompose_lemmas", "search_counterexamples", "attempt_proof", "formal_or_peer_review"],
            task_state_objects=["definition_registry", "lemma_graph", "proof_attempt_log", "counterexample_set", "formal_status"],
            metrics=["proof_gap_count", "counterexample_status", "lemma_dependency_depth", "formalization_coverage"],
            scheduler_objectives=["find counterexamples early", "reduce proof gaps", "formalize stable proof paths"],
            risk_controls=["assumptions_explicit", "heuristic_not_marked_as_proof", "counterexample_verification_required"],
            expected_artifacts=["proof_log", "lemma_graph", "counterexample_candidates", "formal_file"],
        )
    return TaskAdapterLayer(
        task_id=f"task-adapter::{discipline}::{task}",
        parent_discipline=discipline,
        task_type=task,
        workflow_stages=["define_task", "plan_protocol", "execute_or_handoff", "review_quality", "interpret_and_record"],
        task_state_objects=["task_profile", "protocol", "quality_review", "artifact_refs"],
        metrics=["primary_outcome", "quality_status", "cost"],
        scheduler_objectives=["maximize information gain", "minimize avoidable risk"],
        risk_controls=["quality_review_required"],
        expected_artifacts=["protocol", "run_record", "observation_record"],
    )


def _toolchain_layer(
    task_layer: TaskAdapterLayer,
    toolchain: str,
    available_tools: list[str],
) -> ToolchainAdapterLayer:
    requested = _slugify(toolchain).replace("-", "_") or "default"
    discipline = task_layer.parent_discipline
    task = task_layer.task_type
    if discipline == "artificial_intelligence":
        expected = ["python", "sklearn", "pytorch", "lightgbm", "huggingface", "mlflow", "wandb"]
        executors = ["local_python_runner", "notebook_runner", "training_executor"]
        evaluators = ["metric_runner", "leakage_detector", "ablation_comparator"]
    elif discipline == "chemistry":
        expected = ["rdkit", "eln", "lims", "instrument_adapter", "spectra_parser"]
        executors = ["lab_handoff_executor", "simulation_or_screening_executor"]
        evaluators = ["analytical_quality_reviewer", "safety_reviewer"]
    elif discipline == "chemical_engineering":
        expected = ["python", "aspen", "comsol", "historian", "process_simulator"]
        executors = ["simulation_runner", "process_handoff_executor"]
        evaluators = ["mass_balance_checker", "process_safety_reviewer"]
    elif discipline == "physics":
        expected = ["python", "numpy", "scipy", "instrument_adapter", "simulation_runner"]
        executors = ["simulation_runner", "instrument_handoff_executor"]
        evaluators = ["uncertainty_evaluator", "calibration_reviewer"]
    elif discipline == "mathematics":
        expected = ["lean", "coq", "isabelle", "sympy", "sage"]
        executors = ["proof_checker", "symbolic_search_runner"]
        evaluators = ["proof_gap_reviewer", "counterexample_verifier"]
    else:
        expected = ["python", "artifact_store"]
        executors = ["generic_executor"]
        evaluators = ["quality_reviewer"]
    matched = [
        item
        for item in expected
        if item in requested or any(item in tool.lower() for tool in available_tools)
    ]
    return ToolchainAdapterLayer(
        toolchain_id=f"toolchain-adapter::{discipline}::{task}::{requested}",
        task_id=task_layer.task_id,
        runtimes=matched or expected[:3],
        storage=["artifact_registry", "runtime_manifest_store", "provenance_graph"],
        executors=executors,
        evaluators=evaluators,
        permission_requirements=[
            "runtime_manifest_required",
            "workspace_boundary_required",
            "high_risk_execution_review_required",
        ],
        reproducibility_requirements=[
            "config_snapshot",
            "environment_snapshot",
            "seed_or_calibration_policy",
            "artifact_hashes",
        ],
    )


def _handoff_contract(
    *,
    discipline_layer: DisciplineAdapterLayer,
    task_layer: TaskAdapterLayer | None,
    toolchain_layer: ToolchainAdapterLayer | None,
) -> dict[str, Any]:
    return {
        "discipline_payload": {
            "discipline": discipline_layer.discipline,
            "problem_types": discipline_layer.problem_types,
            "data_modalities": discipline_layer.data_modalities,
            "quality_controls": discipline_layer.quality_controls,
            "failure_taxonomy": discipline_layer.failure_taxonomy,
        },
        "task_payload": task_layer.to_dict() if task_layer else {},
        "toolchain_payload": toolchain_layer.to_dict() if toolchain_layer else {},
        "minimum_required_before_execution": _dedupe(
            [
                "hypothesis_id",
                "protocol_or_task_plan",
                "quality_control_plan",
                "artifact_output_plan",
                *(task_layer.risk_controls if task_layer else []),
                *(toolchain_layer.permission_requirements if toolchain_layer else []),
            ]
        ),
    }


def _blocked_reasons(
    *,
    task_layer: TaskAdapterLayer | None,
    toolchain_layer: ToolchainAdapterLayer | None,
) -> list[str]:
    reasons: list[str] = []
    if task_layer is None:
        reasons.append("task_adapter_not_selected")
    if task_layer is not None and toolchain_layer is None:
        reasons.append("toolchain_adapter_not_bound")
    return reasons


def _normalize_discipline(value: str) -> str:
    lowered = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "ai": "artificial_intelligence",
        "machine_learning": "artificial_intelligence",
        "chemical": "chemistry",
        "chem": "chemistry",
        "chem_eng": "chemical_engineering",
        "chemical_engineer": "chemical_engineering",
        "math": "mathematics",
    }
    return aliases.get(lowered, lowered or "general_science")


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys([str(item).strip() for item in values if str(item).strip()]))


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value).strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-")
