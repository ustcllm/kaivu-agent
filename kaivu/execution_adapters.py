from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ExecutionAdapterSpec:
    adapter_id: str
    discipline: str
    adapter_type: str
    supported_experiment_types: list[str] = field(default_factory=list)
    execution_boundary: str = "plan_only"
    required_inputs: list[str] = field(default_factory=list)
    produced_artifacts: list[str] = field(default_factory=list)
    quality_gates: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExecutionPackage:
    package_id: str
    experiment_id: str
    adapter_id: str
    discipline: str
    package_state: str
    execution_mode: str
    protocol_requirements: list[str] = field(default_factory=list)
    run_configuration: dict[str, Any] = field(default_factory=dict)
    quality_gates: list[str] = field(default_factory=list)
    expected_artifacts: list[str] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)
    tuning_plan_id: str = ""
    handoff_target: str = "run_manager"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_execution_adapter_registry_summary(
    *,
    topic: str,
    project_id: str = "",
    experiment_execution_loop_summary: dict[str, Any],
    optimization_adapter_summary: dict[str, Any],
    discipline_adaptation_summary: dict[str, Any],
    discipline_adapter_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    primary = str(discipline_adaptation_summary.get("primary_discipline", "general_science")).strip()
    adapters = _adapter_specs()
    selected = _select_adapter(primary, adapters)
    packages = _build_packages(
        adapter=selected,
        experiment_execution_loop_summary=experiment_execution_loop_summary,
        optimization_adapter_summary=optimization_adapter_summary,
        discipline_adapter_summary=discipline_adapter_summary or {},
        discipline=primary,
    )
    package_dicts = [item.to_dict() for item in packages]
    ready_count = len([item for item in package_dicts if item.get("package_state") == "ready_for_handoff"])
    blocked_count = len([item for item in package_dicts if item.get("package_state") != "ready_for_handoff"])
    return {
        "registry_id": f"execution-adapter-registry::{_slugify(project_id or 'workspace')}::{_slugify(topic)}",
        "topic": topic,
        "project_id": project_id,
        "primary_discipline": primary,
        "registry_state": "ready" if packages else "no_scheduled_experiments",
        "selected_adapter_id": selected.adapter_id,
        "adapter_count": len(adapters),
        "adapters": [item.to_dict() for item in adapters],
        "execution_package_count": len(package_dicts),
        "ready_package_count": ready_count,
        "blocked_package_count": blocked_count,
        "execution_packages": package_dicts,
        "discipline_adapter_id": str(
            (discipline_adapter_summary or {}).get("adapter_id", "")
        ).strip(),
        "handoff_policy": {
            "safe_default": "plan_only_until_explicit_execution_approval",
            "external_jobs_require": ["approved protocol", "budget", "environment", "operator"],
            "result_return_contract": [
                "experiment_run",
                "observation_records",
                "quality_control_review",
                "interpretation_record",
                "artifact_records",
            ],
        },
    }


def _build_packages(
    *,
    adapter: ExecutionAdapterSpec,
    experiment_execution_loop_summary: dict[str, Any],
    optimization_adapter_summary: dict[str, Any],
    discipline_adapter_summary: dict[str, Any],
    discipline: str,
) -> list[ExecutionPackage]:
    tuning_by_experiment = {
        str(plan.get("experiment_id", "")).strip(): plan
        for plan in optimization_adapter_summary.get("plans", [])
        if isinstance(plan, dict) and str(plan.get("experiment_id", "")).strip()
    }
    discipline_bindings = {
        str(binding.get("experiment_id", "")).strip(): binding
        for binding in discipline_adapter_summary.get("bindings", [])
        if isinstance(binding, dict) and str(binding.get("experiment_id", "")).strip()
    }
    packages: list[ExecutionPackage] = []
    for item in experiment_execution_loop_summary.get("execution_queue", []) if isinstance(experiment_execution_loop_summary.get("execution_queue", []), list) else []:
        if not isinstance(item, dict):
            continue
        experiment_id = str(item.get("experiment_id", "")).strip()
        if not experiment_id:
            continue
        action = str(item.get("action", "")).strip()
        experiment_type = action.removeprefix("schedule_") if action else "unknown"
        tuning_plan = tuning_by_experiment.get(experiment_id, {})
        discipline_binding = discipline_bindings.get(experiment_id, {})
        blocked = []
        required = [
            str(req).strip()
            for req in item.get("required_before_execution", [])
            if str(req).strip()
        ]
        required.extend(
            str(req).strip()
            for req in discipline_binding.get("required_before_handoff", [])
            if str(req).strip()
        )
        if experiment_type not in adapter.supported_experiment_types and "parameter_optimization" != experiment_type:
            blocked.append(f"adapter {adapter.adapter_id} does not explicitly support {experiment_type}")
        if str(discipline_binding.get("readiness_state", "")).strip() == "blocked":
            blocked.extend(
                str(reason).strip()
                for reason in discipline_binding.get("blocked_reasons", [])
                if str(reason).strip()
            )
        if "approved protocol" in adapter.required_inputs and "protocol_version_recorded" not in required:
            required.append("protocol_version_recorded")
        package_state = "blocked" if blocked else "ready_for_handoff"
        packages.append(
            ExecutionPackage(
                package_id=f"execution-package::{_slugify(experiment_id)}",
                experiment_id=experiment_id,
                adapter_id=adapter.adapter_id,
                discipline=discipline,
                package_state=package_state,
                execution_mode=_execution_mode(experiment_type, discipline),
                protocol_requirements=list(dict.fromkeys(required + adapter.required_inputs))[:14],
                run_configuration=_run_configuration(
                    experiment_type=experiment_type,
                    discipline=discipline,
                    tuning_plan=tuning_plan,
                    discipline_binding=discipline_binding,
                ),
                quality_gates=list(
                    dict.fromkeys(
                        item.get("required_before_execution", [])
                        + adapter.quality_gates
                        + [
                            str(gate).strip()
                            for gate in discipline_binding.get("quality_gates", [])
                            if str(gate).strip()
                        ]
                    )
                )[:20],
                expected_artifacts=list(
                    dict.fromkeys(
                        adapter.produced_artifacts
                        + [
                            str(artifact).strip()
                            for artifact in discipline_binding.get("artifact_requirements", [])
                            if str(artifact).strip()
                        ]
                    )
                )[:20],
                blocked_reasons=blocked,
                tuning_plan_id=str(tuning_plan.get("plan_id", "")).strip(),
                handoff_target=_handoff_target(experiment_type, discipline),
            )
        )
    return packages[:20]


def _adapter_specs() -> list[ExecutionAdapterSpec]:
    return [
        ExecutionAdapterSpec(
            adapter_id="adapter::artificial_intelligence_training",
            discipline="artificial_intelligence",
            adapter_type="ai_training",
            supported_experiment_types=[
                "parameter_optimization",
                "discriminative_experiment",
                "control_or_ablation",
                "reproducibility_check",
                "ai_baseline",
                "ai_ablation",
                "ai_leakage_audit",
                "ai_protocol_repair",
                "ai_research_planning",
            ],
            required_inputs=["approved protocol", "frozen dataset split", "compute budget", "environment snapshot"],
            produced_artifacts=["config.json", "metrics.json", "model_checkpoint_ref", "seed_report"],
            quality_gates=["dataset_leakage_check", "configuration_snapshot_saved", "multi_seed_top_config_check"],
        ),
        ExecutionAdapterSpec(
            adapter_id="adapter::chemistry_condition",
            discipline="chemistry",
            adapter_type="wet_lab_plan",
            supported_experiment_types=[
                "parameter_optimization",
                "discriminative_experiment",
                "reproducibility_check",
            ],
            required_inputs=["approved protocol", "materials list", "safety envelope", "measurement plan"],
            produced_artifacts=["lab_notebook_entry", "spectra_or_chromatogram_refs", "yield_table"],
            quality_gates=["instrument_calibration", "reagent_batch_recorded", "safety_review_check"],
        ),
        ExecutionAdapterSpec(
            adapter_id="adapter::chemical_engineering_process",
            discipline="chemical_engineering",
            adapter_type="process_run_plan",
            supported_experiment_types=[
                "parameter_optimization",
                "discriminative_experiment",
                "reproducibility_check",
            ],
            required_inputs=["approved protocol", "process limits", "sensor calibration", "shutdown criteria"],
            produced_artifacts=["process_trace", "sensor_log", "mass_balance_report"],
            quality_gates=["process_conditions_stable", "sensor_calibration_verified", "mass_balance_reviewed"],
        ),
        ExecutionAdapterSpec(
            adapter_id="adapter::physics_parameter_sweep",
            discipline="physics",
            adapter_type="instrument_run_plan",
            supported_experiment_types=[
                "parameter_optimization",
                "discriminative_experiment",
                "reproducibility_check",
            ],
            required_inputs=["approved protocol", "instrument settings", "calibration reference", "uncertainty model"],
            produced_artifacts=["instrument_log", "raw_measurements", "calibration_report"],
            quality_gates=["instrument_alignment_verified", "calibration_reference_checked", "background_noise_characterized"],
        ),
        ExecutionAdapterSpec(
            adapter_id="adapter::mathematics_search",
            discipline="mathematics",
            adapter_type="proof_or_counterexample_search",
            supported_experiment_types=[
                "parameter_optimization",
                "discriminative_experiment",
                "control_or_ablation",
                "reproducibility_check",
            ],
            required_inputs=["formal assumptions", "search bounds", "proof state snapshot"],
            produced_artifacts=["proof_attempt_log", "counterexample_candidates", "lemma_dependency_graph"],
            quality_gates=["assumptions_explicit", "edge_cases_reviewed", "proof_gaps_marked"],
        ),
        ExecutionAdapterSpec(
            adapter_id="adapter::general_science_plan",
            discipline="general_science",
            adapter_type="plan_only",
            supported_experiment_types=[
                "discriminative_experiment",
                "parameter_optimization",
                "reproducibility_check",
                "evidence_quality_repair",
                "evidence_resolution",
            ],
            required_inputs=["approved protocol", "measurement plan", "quality gates"],
            produced_artifacts=["run_record", "observation_record", "quality_control_review"],
            quality_gates=["protocol_version_recorded", "artifact_provenance_recorded"],
        ),
    ]


def _select_adapter(discipline: str, adapters: list[ExecutionAdapterSpec]) -> ExecutionAdapterSpec:
    for adapter in adapters:
        if adapter.discipline == discipline:
            return adapter
    return next(adapter for adapter in adapters if adapter.discipline == "general_science")


def _execution_mode(experiment_type: str, discipline: str) -> str:
    if experiment_type == "parameter_optimization":
        return {
            "artificial_intelligence": "external_hpo_runner",
            "chemistry": "bounded_condition_screen",
            "chemical_engineering": "process_parameter_sweep",
            "physics": "instrument_parameter_sweep",
            "mathematics": "bounded_search",
        }.get(discipline, "parameter_sweep")
    if discipline == "artificial_intelligence" and experiment_type in {
        "ai_baseline",
        "ai_ablation",
        "ai_leakage_audit",
        "ai_protocol_repair",
        "ai_research_planning",
    }:
        return "single_or_batched_experiment_run"
    if experiment_type in {"evidence_quality_repair", "evidence_resolution"}:
        return "review_workflow"
    return "single_or_batched_experiment_run"


def _run_configuration(
    *,
    experiment_type: str,
    discipline: str,
    tuning_plan: dict[str, Any],
    discipline_binding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = {
        "experiment_type": experiment_type,
        "discipline": discipline,
        "execution_boundary": "plan_only",
        "requires_explicit_approval_to_execute": True,
    }
    if tuning_plan:
        config.update(
            {
                "tuning_plan_id": tuning_plan.get("plan_id", ""),
                "search_strategy": tuning_plan.get("search_strategy", ""),
                "objective_metric": tuning_plan.get("objective_metric", ""),
                "trial_count": len(tuning_plan.get("exploratory_trials", [])),
                "confirmatory_protocol": tuning_plan.get("confirmatory_protocol", {}),
            }
        )
    if discipline_binding:
        config["discipline_adapter_binding_id"] = discipline_binding.get("binding_id", "")
        config["measurement_requirements"] = discipline_binding.get("measurement_requirements", [])
        config["lifecycle_stages"] = discipline_binding.get("lifecycle_stages", [])
        config["safety_constraints"] = discipline_binding.get("safety_constraints", [])
        config["failure_modes_to_watch"] = discipline_binding.get("failure_modes_to_watch", [])
        config["interpretation_boundaries"] = discipline_binding.get("interpretation_boundaries", [])
        config["backpropagation_rules"] = discipline_binding.get("backpropagation_rules", [])
        config["scheduler_rules"] = discipline_binding.get("scheduler_rules", [])
        config["handoff_payload_extensions"] = discipline_binding.get("handoff_payload_extensions", {})
    return config


def _handoff_target(experiment_type: str, discipline: str) -> str:
    if experiment_type == "parameter_optimization":
        return "optimization_adapter"
    if discipline == "artificial_intelligence":
        return "ai_training_runner"
    if discipline in {"chemistry", "chemical_engineering", "physics"}:
        return "domain_lab_adapter"
    if discipline == "mathematics":
        return "proof_search_adapter"
    return "run_manager"


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "execution"
