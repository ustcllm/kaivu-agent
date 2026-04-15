from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .layered_adapters import build_layered_adapter_summary


@dataclass(slots=True)
class DisciplineAdapterSpec:
    adapter_id: str
    discipline: str
    adapter_family: str
    protocol_templates: dict[str, list[str]] = field(default_factory=dict)
    measurement_contract: list[str] = field(default_factory=list)
    artifact_contract: list[str] = field(default_factory=list)
    lifecycle_stages: list[str] = field(default_factory=list)
    quality_gates: list[str] = field(default_factory=list)
    safety_constraints: list[str] = field(default_factory=list)
    failure_modes: list[str] = field(default_factory=list)
    interpretation_boundaries: list[str] = field(default_factory=list)
    backpropagation_rules: list[str] = field(default_factory=list)
    scheduler_rules: list[str] = field(default_factory=list)
    recommended_agents: list[str] = field(default_factory=list)
    external_targets: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DisciplineAdapterBinding:
    binding_id: str
    experiment_id: str
    adapter_id: str
    discipline: str
    experiment_type: str
    readiness_state: str
    selected_protocol_template: list[str] = field(default_factory=list)
    required_before_handoff: list[str] = field(default_factory=list)
    measurement_requirements: list[str] = field(default_factory=list)
    artifact_requirements: list[str] = field(default_factory=list)
    lifecycle_stages: list[str] = field(default_factory=list)
    quality_gates: list[str] = field(default_factory=list)
    safety_constraints: list[str] = field(default_factory=list)
    failure_modes_to_watch: list[str] = field(default_factory=list)
    interpretation_boundaries: list[str] = field(default_factory=list)
    backpropagation_rules: list[str] = field(default_factory=list)
    scheduler_rules: list[str] = field(default_factory=list)
    handoff_payload_extensions: dict[str, Any] = field(default_factory=dict)
    blocked_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_discipline_adapter_summary(
    *,
    topic: str,
    project_id: str = "",
    discipline_adaptation_summary: dict[str, Any],
    experiment_execution_loop_summary: dict[str, Any],
    optimization_adapter_summary: dict[str, Any] | None = None,
    evidence_review_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    specs = _adapter_specs()
    primary = str(
        discipline_adaptation_summary.get("primary_discipline", "general_science")
    ).strip() or "general_science"
    selected = _select_adapter(primary, specs)
    bindings = _build_bindings(
        adapter=selected,
        experiment_execution_loop_summary=experiment_execution_loop_summary,
        optimization_adapter_summary=optimization_adapter_summary or {},
        evidence_review_summary=evidence_review_summary or {},
    )
    binding_dicts = [item.to_dict() for item in bindings]
    blocked_count = len([item for item in binding_dicts if item.get("readiness_state") != "ready"])
    primary_task = _infer_primary_task(
        experiment_execution_loop_summary=experiment_execution_loop_summary,
        optimization_adapter_summary=optimization_adapter_summary or {},
    )
    layered = build_layered_adapter_summary(
        discipline=primary,
        task_type=primary_task,
        toolchain="default",
        available_tools=selected.external_targets,
    )
    return {
        "adapter_id": f"discipline-adapter::{_slugify(project_id or 'workspace')}::{_slugify(topic)}",
        "interface_version": "discipline_adapter",
        "layered_interface_version": "layered_adapter_v1",
        "topic": topic,
        "project_id": project_id,
        "primary_discipline": primary,
        "secondary_disciplines": [
            str(item).strip()
            for item in discipline_adaptation_summary.get("secondary_disciplines", [])
            if str(item).strip()
        ][:6]
        if isinstance(discipline_adaptation_summary.get("secondary_disciplines", []), list)
        else [],
        "adapter_state": "ready" if binding_dicts and blocked_count == 0 else (
            "partially_blocked" if binding_dicts else "no_execution_bindings"
        ),
        "selected_adapter_id": selected.adapter_id,
        "selected_adapter": selected.to_dict(),
        "layered_adapter_summary": layered,
        "available_adapter_count": len(specs),
        "available_adapters": [item.to_dict() for item in specs],
        "binding_count": len(binding_dicts),
        "blocked_binding_count": blocked_count,
        "bindings": binding_dicts,
        "role": (
            "translate scientific decisions into discipline-specific protocol, "
            "measurement, artifact, quality, safety, and backpropagation contracts"
        ),
        "execution_boundary": {
            "mode": "plan_and_handoff_only",
            "does_not_operate_instruments_or_heavy_jobs": True,
            "requires_explicit_execution_approval": True,
        },
        "handoff_contract_extensions": {
            "experiment_run.discipline_payload": "discipline-specific parameters and environment",
            "observation_records.discipline_payload": "measurement units, instrument/model metadata, raw refs",
            "quality_control_review.discipline_payload": "discipline quality gate evidence",
            "interpretation_record.discipline_payload": "domain interpretation and failure taxonomy",
            "research_asset_records.discipline": "owning discipline for provenance and permissions",
        },
    }


def _build_bindings(
    *,
    adapter: DisciplineAdapterSpec,
    experiment_execution_loop_summary: dict[str, Any],
    optimization_adapter_summary: dict[str, Any],
    evidence_review_summary: dict[str, Any],
) -> list[DisciplineAdapterBinding]:
    tuning_by_experiment = {
        str(plan.get("experiment_id", "")).strip(): plan
        for plan in optimization_adapter_summary.get("plans", [])
        if isinstance(plan, dict) and str(plan.get("experiment_id", "")).strip()
    }
    evidence_state = str(evidence_review_summary.get("review_state", "")).strip()
    bindings: list[DisciplineAdapterBinding] = []
    queue = experiment_execution_loop_summary.get("execution_queue", [])
    for item in queue if isinstance(queue, list) else []:
        if not isinstance(item, dict):
            continue
        experiment_id = str(item.get("experiment_id", "")).strip()
        if not experiment_id:
            continue
        experiment_type = _experiment_type(item)
        required = _string_list(item.get("required_before_execution", []))
        blockers = _string_list(item.get("blocked_reasons", []))
        if evidence_state in {"blocked", "needs_human_review", "not_ready"}:
            blockers.append(f"evidence_review_state={evidence_state}")
        template = adapter.protocol_templates.get(
            experiment_type,
            adapter.protocol_templates.get("default", []),
        )
        tuning_plan = tuning_by_experiment.get(experiment_id, {})
        extensions = {
            "discipline": adapter.discipline,
            "experiment_type": experiment_type,
            "adapter_family": adapter.adapter_family,
            "parameter_optimization": bool(tuning_plan),
            "tuning_plan_id": str(tuning_plan.get("plan_id", "")).strip(),
            "expected_failure_taxonomy": adapter.failure_modes,
            "lifecycle_stages": adapter.lifecycle_stages,
            "interpretation_boundaries": adapter.interpretation_boundaries,
            "scheduler_rules": adapter.scheduler_rules,
        }
        bindings.append(
            DisciplineAdapterBinding(
                binding_id=f"discipline-binding::{_slugify(experiment_id)}",
                experiment_id=experiment_id,
                adapter_id=adapter.adapter_id,
                discipline=adapter.discipline,
                experiment_type=experiment_type,
                readiness_state="blocked" if blockers else "ready",
                selected_protocol_template=list(template),
                required_before_handoff=_dedupe(required + template),
                measurement_requirements=adapter.measurement_contract,
                artifact_requirements=adapter.artifact_contract,
                lifecycle_stages=adapter.lifecycle_stages,
                quality_gates=_dedupe(_string_list(item.get("quality_gates", [])) + adapter.quality_gates),
                safety_constraints=adapter.safety_constraints,
                failure_modes_to_watch=adapter.failure_modes,
                interpretation_boundaries=adapter.interpretation_boundaries,
                backpropagation_rules=adapter.backpropagation_rules,
                scheduler_rules=adapter.scheduler_rules,
                handoff_payload_extensions=extensions,
                blocked_reasons=_dedupe(blockers),
            )
        )
    return bindings[:20]


def _adapter_specs() -> list[DisciplineAdapterSpec]:
    return [
        DisciplineAdapterSpec(
            adapter_id="discipline-adapter::artificial_intelligence",
            discipline="artificial_intelligence",
            adapter_family="model_training_and_evaluation",
            protocol_templates={
                "parameter_optimization": [
                    "freeze dataset split and benchmark definition",
                    "separate exploratory tuning from final confirmatory evaluation",
                    "record search space, sampler, seed policy, and stopping rule",
                ],
                "control_or_ablation": [
                    "define single-factor ablation matrix",
                    "hold data, budget, and preprocessing constant",
                    "compare against locked baseline and random seeds",
                ],
                "default": [
                    "define benchmark, baseline, metric, and compute budget",
                    "record environment and dependency snapshot",
                ],
            },
            measurement_contract=[
                "primary metric with direction",
                "secondary metrics and confidence intervals",
                "per-seed results",
                "dataset split identifiers",
            ],
            artifact_contract=[
                "config.json",
                "metrics.json",
                "seed_report",
                "environment_snapshot",
                "model_checkpoint_or_reference",
            ],
            lifecycle_stages=[
                "define benchmark and baseline",
                "freeze data split",
                "exploratory tuning",
                "multi-seed replication",
                "confirmatory holdout evaluation",
                "statistical comparison and error analysis",
            ],
            quality_gates=[
                "dataset_leakage_check",
                "baseline_reproduction_check",
                "multi_seed_variance_check",
                "confirmatory_holdout_check",
            ],
            safety_constraints=["no hidden test-set tuning", "respect compute budget"],
            failure_modes=["data leakage", "seed sensitivity", "benchmark overfitting", "irreproducible environment"],
            interpretation_boundaries=[
                "exploratory tuning can prioritize configurations but cannot confirm the scientific claim",
                "single-seed improvement is weak evidence until replicated",
                "baseline reproduction failure blocks method-level interpretation",
                "test-set reuse converts positive evidence into contaminated evidence",
            ],
            backpropagation_rules=[
                "negative tuning result weakens only the tested configuration family",
                "quality failure quarantines metrics until rerun",
                "successful exploratory result requires confirmatory run before belief upgrade",
            ],
            scheduler_rules=[
                "prefer cheap ablations before large training runs",
                "schedule confirmatory evaluation only after frozen validation selection",
                "prioritize reproducibility checks when variance is high",
            ],
            recommended_agents=["benchmark_designer", "optimization_adapter", "reproducibility_reviewer"],
            external_targets=["optuna", "ray_tune", "local_training_runner"],
        ),
        DisciplineAdapterSpec(
            adapter_id="discipline-adapter::chemistry",
            discipline="chemistry",
            adapter_family="wet_lab_condition_screen",
            protocol_templates={
                "parameter_optimization": [
                    "define reagent lots, stoichiometry bounds, solvent, catalyst, temperature, and time",
                    "include blank, positive control, and replicate conditions",
                    "record quench, workup, and analytical method",
                ],
                "default": [
                    "freeze materials list and safety envelope",
                    "define analytical readout and calibration method",
                ],
            },
            measurement_contract=["yield or conversion", "selectivity", "spectral/chromatographic evidence", "replicate count"],
            artifact_contract=["lab_notebook_entry", "reagent_lot_table", "spectra_or_chromatogram_refs", "yield_table"],
            lifecycle_stages=[
                "define reaction and condition family",
                "safety and materials review",
                "small-scale condition run",
                "quench, workup, and sampling",
                "analytical characterization",
                "replicate or control confirmation",
            ],
            quality_gates=["safety_review_check", "reagent_batch_recorded", "instrument_calibration", "replicate_or_control_present"],
            safety_constraints=["stay inside approved safety envelope", "flag hazardous reagent or pressure conditions"],
            failure_modes=["reagent degradation", "side reaction", "instrument drift", "workup loss", "batch effect"],
            interpretation_boundaries=[
                "single failed condition narrows the condition family but does not reject the mechanism",
                "instrument or workup failure is a quality-control failure before it is a negative result",
                "side-product evidence may generate a competing mechanism rather than only a failed attempt",
                "replicated negative result can challenge the mechanism branch",
            ],
            backpropagation_rules=[
                "failed condition updates condition-family memory, not the whole mechanism by default",
                "instrument failure creates quality-control failure rather than scientific negative result",
                "replicated negative result can down-rank the mechanism branch",
            ],
            scheduler_rules=[
                "prefer low-hazard microscale screens before expensive or hazardous runs",
                "schedule controls when a condition family has only positive-looking results",
                "prioritize replicate confirmation before mechanism belief upgrade",
            ],
            recommended_agents=["safety_reviewer", "protocol_writer", "analytical_quality_reviewer"],
            external_targets=["electronic_lab_notebook", "lab_operator"],
        ),
        DisciplineAdapterSpec(
            adapter_id="discipline-adapter::chemical_engineering",
            discipline="chemical_engineering",
            adapter_family="process_parameter_sweep",
            protocol_templates={
                "parameter_optimization": [
                    "define operating window, control variables, and shutdown criteria",
                    "record steady-state criteria and residence time",
                    "include mass and energy balance checks",
                ],
                "default": [
                    "freeze process flow diagram and sensor map",
                    "define process limits and alarms",
                ],
            },
            measurement_contract=["conversion", "selectivity", "throughput", "energy use", "mass balance closure", "sensor trace"],
            artifact_contract=["process_trace", "sensor_log", "mass_balance_report", "process_limits_record"],
            lifecycle_stages=[
                "define process flow and operating window",
                "calibrate sensors and safety interlocks",
                "ramp to operating condition",
                "verify steady state",
                "collect process trace and samples",
                "close mass and energy balances",
            ],
            quality_gates=["sensor_calibration_verified", "steady_state_verified", "mass_balance_reviewed", "shutdown_criteria_defined"],
            safety_constraints=["respect pressure/temperature/process limits", "require shutdown path for unsafe excursions"],
            failure_modes=["sensor drift", "unstable steady state", "mass balance mismatch", "scale-up artifact", "control-loop instability"],
            interpretation_boundaries=[
                "unstable operation blocks process performance interpretation",
                "mass-balance mismatch quarantines yield, selectivity, and throughput claims",
                "scale-up artifact should update transferability assumptions rather than base chemistry alone",
                "safety excursion turns the run into governance evidence before scientific evidence",
            ],
            backpropagation_rules=[
                "process instability blocks interpretation until steady state is re-established",
                "mass-balance failure quarantines performance claims",
                "scale-dependent failures should update transferability assumptions",
            ],
            scheduler_rules=[
                "prefer simulation or low-throughput process windows before high-risk pilot runs",
                "schedule sensor calibration repair before repeating unstable runs",
                "favor experiments with clear shutdown criteria and expected information gain per cost",
            ],
            recommended_agents=["process_safety_reviewer", "mass_balance_reviewer", "scheduler"],
            external_targets=["process_simulator", "pilot_rig_operator"],
        ),
        DisciplineAdapterSpec(
            adapter_id="discipline-adapter::physics",
            discipline="physics",
            adapter_family="instrument_measurement_and_sweep",
            protocol_templates={
                "parameter_optimization": [
                    "define sweep variable, range, resolution, and dwell time",
                    "record calibration, background, and uncertainty model",
                    "include repeat points and drift checks",
                ],
                "default": [
                    "define instrument configuration and measurement uncertainty",
                    "record calibration reference and environmental conditions",
                ],
            },
            measurement_contract=["raw measurements", "calibrated measurements", "uncertainty estimate", "background/noise characterization"],
            artifact_contract=["instrument_log", "raw_measurements", "calibration_report", "uncertainty_model"],
            lifecycle_stages=[
                "define observable and theoretical prediction",
                "configure instrument and calibration reference",
                "measure background and noise floor",
                "run parameter sweep",
                "repeat drift and calibration checks",
                "fit model with uncertainty analysis",
            ],
            quality_gates=["instrument_alignment_verified", "calibration_reference_checked", "background_noise_characterized", "uncertainty_model_recorded"],
            safety_constraints=["respect instrument operating limits", "flag radiation/cryogenic/high-voltage risks when present"],
            failure_modes=["calibration drift", "background contamination", "thermal drift", "resolution limit", "model mismatch"],
            interpretation_boundaries=[
                "calibration failure blocks theory update",
                "null result constrains only the measured parameter region and sensitivity level",
                "repeatable anomaly should create a discriminative follow-up experiment",
                "model mismatch should distinguish instrument artifact from theory failure",
            ],
            backpropagation_rules=[
                "calibration failure creates quality-control failure before theory update",
                "repeatable anomaly creates candidate discriminative experiment",
                "null result updates parameter region constraints",
            ],
            scheduler_rules=[
                "schedule calibration and background checks before high-cost sweeps",
                "prioritize parameter regions with maximal theory discrimination",
                "repeat surprising anomalies before creating strong theory revisions",
            ],
            recommended_agents=["instrument_quality_reviewer", "uncertainty_modeler", "scheduler"],
            external_targets=["instrument_control_system", "simulation_runner"],
        ),
        DisciplineAdapterSpec(
            adapter_id="discipline-adapter::mathematics",
            discipline="mathematics",
            adapter_family="proof_search_and_counterexample",
            protocol_templates={
                "parameter_optimization": [
                    "define search space, bounds, invariants, and pruning rule",
                    "separate heuristic exploration from proof obligation",
                    "record counterexample filters and proof gaps",
                ],
                "default": [
                    "state assumptions and target theorem precisely",
                    "track lemma dependencies and edge cases",
                ],
            },
            measurement_contract=["proof state", "lemma dependency status", "counterexample candidates", "search bounds"],
            artifact_contract=["proof_attempt_log", "counterexample_candidates", "lemma_dependency_graph", "formal_assumptions"],
            lifecycle_stages=[
                "state conjecture and assumptions",
                "decompose into lemmas",
                "search proof strategy",
                "search counterexamples and boundary cases",
                "mark proof gaps",
                "formal or peer review",
            ],
            quality_gates=["assumptions_explicit", "edge_cases_reviewed", "proof_gaps_marked", "counterexamples_verified"],
            safety_constraints=["do not treat heuristic evidence as proof", "mark unverified lemmas explicitly"],
            failure_modes=["hidden assumption", "false lemma", "unbounded search", "counterexample found", "proof gap"],
            interpretation_boundaries=[
                "computational evidence can prioritize a conjecture but cannot prove it",
                "proof gap keeps the hypothesis pending rather than supported",
                "verified counterexample rejects or narrows the conjecture immediately",
                "failed proof path should not be retried without a new lemma or assumption change",
            ],
            backpropagation_rules=[
                "counterexample rejects or narrows the conjecture immediately",
                "proof gap keeps hypothesis pending rather than supported",
                "failed proof attempt becomes reusable failed-attempt memory",
            ],
            scheduler_rules=[
                "prioritize counterexample search before expensive proof elaboration",
                "schedule formalization when a proof path appears stable",
                "branch to weaker conjectures when boundary cases fail",
            ],
            recommended_agents=["formalizer", "counterexample_searcher", "proof_reviewer"],
            external_targets=["lean_or_coq_optional", "symbolic_search_runner"],
        ),
        DisciplineAdapterSpec(
            adapter_id="discipline-adapter::general_science",
            discipline="general_science",
            adapter_family="generic_plan_and_quality_contract",
            protocol_templates={
                "default": [
                    "define hypothesis, protocol, measurement, quality gates, and result interpretation plan",
                    "record artifacts and provenance for every run",
                ],
            },
            measurement_contract=["primary outcome", "quality-control status", "artifact references"],
            artifact_contract=["run_record", "observation_record", "quality_control_review"],
            lifecycle_stages=[
                "define hypothesis and protocol",
                "prepare measurement and quality plan",
                "execute approved run",
                "record observations and artifacts",
                "review quality and interpret result",
            ],
            quality_gates=["protocol_version_recorded", "artifact_provenance_recorded"],
            safety_constraints=["require human approval for real-world execution"],
            failure_modes=["missing protocol", "missing artifact", "ambiguous interpretation"],
            interpretation_boundaries=[
                "quality failure blocks strong claim updates",
                "ambiguous observation should schedule clarification rather than belief update",
            ],
            backpropagation_rules=["failed or negative runs must update memory and claim graph"],
            scheduler_rules=[
                "repair protocol and artifact gaps before scheduling expensive follow-up experiments",
                "prefer lower-cost discriminative tests when uncertainty is high",
            ],
            recommended_agents=["scheduler", "quality_control_reviewer"],
            external_targets=["run_manager"],
        ),
    ]


def _select_adapter(discipline: str, specs: list[DisciplineAdapterSpec]) -> DisciplineAdapterSpec:
    for item in specs:
        if item.discipline == discipline:
            return item
    return next(item for item in specs if item.discipline == "general_science")


def _experiment_type(item: dict[str, Any]) -> str:
    action = str(item.get("action", "")).strip()
    if action.startswith("schedule_"):
        return action.removeprefix("schedule_")
    return str(item.get("experiment_type", "")).strip() or "default"


def _infer_primary_task(
    *,
    experiment_execution_loop_summary: dict[str, Any],
    optimization_adapter_summary: dict[str, Any],
) -> str:
    queue = experiment_execution_loop_summary.get("execution_queue", [])
    if isinstance(queue, list):
        for item in queue:
            if isinstance(item, dict):
                experiment_type = _experiment_type(item)
                if experiment_type and experiment_type != "default":
                    return experiment_type
    plans = optimization_adapter_summary.get("plans", [])
    if isinstance(plans, list) and plans:
        return "parameter_optimization"
    return "general"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys([str(item).strip() for item in values if str(item).strip()]))


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "discipline-adapter"


