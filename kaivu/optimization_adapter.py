from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class TuningTrial:
    trial_id: str
    parameters: dict[str, Any]
    status: str = "planned"
    objective_value: float | None = None
    failure_reason: str = ""
    budget_units: float = 1.0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TuningPlan:
    plan_id: str
    experiment_id: str
    discipline: str
    objective_metric: str
    optimization_direction: str
    search_strategy: str
    search_space: dict[str, Any] = field(default_factory=dict)
    budget: dict[str, Any] = field(default_factory=dict)
    constraints: list[str] = field(default_factory=list)
    quality_gates: list[str] = field(default_factory=list)
    exploratory_trials: list[TuningTrial] = field(default_factory=list)
    confirmatory_protocol: dict[str, Any] = field(default_factory=dict)
    frozen_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["exploratory_trials"] = [trial.to_dict() for trial in self.exploratory_trials]
        return payload


@dataclass(slots=True)
class TuningResult:
    result_id: str
    plan_id: str
    best_trial_id: str = ""
    best_config: dict[str, Any] = field(default_factory=dict)
    failed_trials: list[dict[str, Any]] = field(default_factory=list)
    completed_trial_count: int = 0
    failed_trial_count: int = 0
    early_stop_reason: str = ""
    confirmatory_required: bool = True
    result_state: str = "planned"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_optimization_adapter_summary(
    *,
    topic: str,
    project_id: str = "",
    experiment_execution_loop_summary: dict[str, Any],
    discipline_adaptation_summary: dict[str, Any],
    max_trials: int = 8,
) -> dict[str, Any]:
    candidates = [
        item
        for item in experiment_execution_loop_summary.get("candidate_experiments", [])
        if isinstance(item, dict) and item.get("experiment_type") == "parameter_optimization"
    ]
    discipline = str(discipline_adaptation_summary.get("primary_discipline", "general_science")).strip()
    plans = [
        _build_tuning_plan(
            candidate=item,
            discipline=discipline,
            max_trials=max_trials,
        )
        for item in candidates[:6]
    ]
    simulated_results = [_simulate_result(plan) for plan in plans]
    return {
        "adapter_id": f"optimization-adapter::{_slugify(project_id or 'workspace')}::{_slugify(topic)}",
        "topic": topic,
        "project_id": project_id,
        "adapter_state": "ready" if plans else "no_parameter_optimization_candidates",
        "optimization_candidate_count": len(candidates),
        "plan_count": len(plans),
        "plans": [plan.to_dict() for plan in plans],
        "simulated_results": [result.to_dict() for result in simulated_results],
        "best_config_candidates": [
            result.best_config
            for result in simulated_results
            if result.best_config
        ][:6],
        "execution_boundary": {
            "adapter_role": "plan_and_record_optimization",
            "does_not_execute_heavy_jobs": True,
            "external_execution_targets": ["optuna", "ray_tune", "domain_lab_adapter", "run_manager"],
        },
    }


def _build_tuning_plan(*, candidate: dict[str, Any], discipline: str, max_trials: int) -> TuningPlan:
    experiment_id = str(candidate.get("experiment_id", "parameter-optimization")).strip()
    search_space = (
        candidate.get("search_space", {})
        if isinstance(candidate.get("search_space", {}), dict)
        else {}
    ) or _default_search_space(discipline)
    trials = [
        TuningTrial(
            trial_id=f"trial::{_slugify(experiment_id)}::{index + 1}",
            parameters=_sample_parameters(search_space, index),
            status="planned",
            budget_units=1.0,
            notes=["exploratory tuning trial; do not use test-set feedback"],
        )
        for index in range(max(1, min(max_trials, 24)))
    ]
    return TuningPlan(
        plan_id=f"tuning-plan::{_slugify(experiment_id)}",
        experiment_id=experiment_id,
        discipline=discipline,
        objective_metric=_objective_metric(discipline),
        optimization_direction=_optimization_direction(discipline),
        search_strategy=_search_strategy(search_space, discipline),
        search_space=search_space,
        budget={
            "max_trials": len(trials),
            "early_stopping": True,
            "confirmatory_repeats": 3 if discipline == "artificial_intelligence" else 2,
        },
        constraints=_constraints(discipline),
        quality_gates=[
            str(item).strip()
            for item in candidate.get("quality_gates", [])
            if str(item).strip()
        ],
        exploratory_trials=trials,
        confirmatory_protocol={
            "freeze_best_config_before_confirmatory_run": True,
            "freeze_data_or_material_split": True,
            "report_all_trials_including_failures": True,
            "separate_exploratory_from_confirmatory_claims": True,
        },
        frozen_fields=["objective_metric", "search_space", "budget", "validation_split_or_conditions"],
    )


def _simulate_result(plan: TuningPlan) -> TuningResult:
    # Deterministic placeholder scoring. Real execution adapters should replace this
    # with observed objective values from Optuna/Ray Tune/lab adapters.
    completed: list[TuningTrial] = []
    failed: list[TuningTrial] = []
    for index, trial in enumerate(plan.exploratory_trials):
        if index and index % 7 == 0:
            trial.status = "failed"
            trial.failure_reason = "simulated budget or quality gate failure"
            failed.append(trial)
            continue
        trial.status = "completed"
        trial.objective_value = round(1.0 / (index + 1) if plan.optimization_direction == "minimize" else 1.0 - 1.0 / (index + 2), 4)
        completed.append(trial)
    if not completed:
        return TuningResult(
            result_id=f"tuning-result::{_slugify(plan.plan_id)}",
            plan_id=plan.plan_id,
            failed_trials=[trial.to_dict() for trial in failed],
            failed_trial_count=len(failed),
            result_state="failed",
            early_stop_reason="no completed trials",
        )
    best = (
        min(completed, key=lambda item: item.objective_value or 0.0)
        if plan.optimization_direction == "minimize"
        else max(completed, key=lambda item: item.objective_value or 0.0)
    )
    return TuningResult(
        result_id=f"tuning-result::{_slugify(plan.plan_id)}",
        plan_id=plan.plan_id,
        best_trial_id=best.trial_id,
        best_config=best.parameters,
        failed_trials=[trial.to_dict() for trial in failed],
        completed_trial_count=len(completed),
        failed_trial_count=len(failed),
        early_stop_reason="not_triggered",
        confirmatory_required=True,
        result_state="exploratory_complete_requires_confirmation",
    )


def _sample_parameters(search_space: dict[str, Any], index: int) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for key, spec in search_space.items():
        if isinstance(spec, list) and spec:
            params[key] = spec[index % len(spec)]
        elif isinstance(spec, dict):
            params[key] = _sample_from_spec(spec, index)
        else:
            spec_text = str(spec)
            if "log_uniform" in spec_text:
                params[key] = [1e-5, 3e-5, 1e-4, 3e-4][index % 4]
            elif "categorical" in spec_text:
                params[key] = f"option_{index % 3}"
            elif "integer" in spec_text:
                params[key] = index + 1
            elif "bounded" in spec_text or "range" in spec_text:
                params[key] = round((index + 1) / 10.0, 3)
            else:
                params[key] = spec
    return params


def _sample_from_spec(spec: dict[str, Any], index: int) -> Any:
    values = spec.get("values")
    if isinstance(values, list) and values:
        return values[index % len(values)]
    low = spec.get("low")
    high = spec.get("high")
    if isinstance(low, (int, float)) and isinstance(high, (int, float)):
        fraction = ((index % 5) + 1) / 6.0
        return round(float(low) + (float(high) - float(low)) * fraction, 6)
    return spec.get("default", f"value_{index + 1}")


def _default_search_space(discipline: str) -> dict[str, Any]:
    if discipline == "artificial_intelligence":
        return {"learning_rate": "log_uniform", "batch_size": [16, 32, 64], "weight_decay": "log_uniform"}
    if discipline == "chemistry":
        return {"temperature": {"low": 20, "high": 120}, "solvent": ["A", "B", "C"], "reaction_time": {"low": 1, "high": 24}}
    if discipline == "chemical_engineering":
        return {"flow_rate": {"low": 0.1, "high": 10.0}, "pressure": {"low": 1, "high": 20}, "residence_time": {"low": 1, "high": 60}}
    if discipline == "physics":
        return {"field_strength": {"low": 0, "high": 10}, "temperature": {"low": 4, "high": 300}}
    if discipline == "mathematics":
        return {"construction_size": {"low": 2, "high": 12}, "counterexample_family": ["small", "sparse", "symmetric"]}
    return {"parameter": {"low": 0, "high": 1}}


def _objective_metric(discipline: str) -> str:
    return {
        "artificial_intelligence": "validation_metric",
        "chemistry": "yield_or_selectivity",
        "chemical_engineering": "throughput_quality_safety_score",
        "physics": "signal_to_noise_or_fit_quality",
        "mathematics": "counterexample_or_proof_progress_score",
    }.get(discipline, "objective_value")


def _optimization_direction(discipline: str) -> str:
    if discipline in {"mathematics"}:
        return "maximize"
    return "maximize"


def _search_strategy(search_space: dict[str, Any], discipline: str) -> str:
    if discipline == "artificial_intelligence":
        return "bayesian_or_hyperband_adapter"
    if len(search_space) <= 2:
        return "grid_or_factorial_sweep"
    return "bounded_sequential_design"


def _constraints(discipline: str) -> list[str]:
    common = [
        "record all trials, including failed trials",
        "do not use confirmatory/test evidence during exploratory tuning",
        "freeze best configuration before confirmatory evaluation",
    ]
    if discipline == "artificial_intelligence":
        return common + ["fixed validation split", "multi-seed repeat for top configurations", "dataset leakage check"]
    if discipline in {"chemistry", "chemical_engineering", "physics"}:
        return common + ["safety envelope must be explicit", "calibration/control checks required"]
    if discipline == "mathematics":
        return common + ["record failed proof attempts and counterexamples"]
    return common


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "optimization"
