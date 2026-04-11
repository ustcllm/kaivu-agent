from __future__ import annotations

from typing import Any


def build_discipline_toolchain_binding_summary(
    *,
    topic: str,
    discipline_adapter_summary: dict[str, Any],
    experiment_execution_loop_summary: dict[str, Any],
    execution_adapter_registry_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    primary = str(
        discipline_adapter_summary.get("primary_discipline", "")
        or discipline_adapter_summary.get("selected_adapter_id", "")
        or "general_science"
    ).strip().lower()
    candidates = _items(experiment_execution_loop_summary.get("candidate_experiments", []))
    packages = _items((execution_adapter_registry_summary or {}).get("execution_packages", []))
    expected = _expected_toolchain(primary)
    present_text = " ".join(
        [
            topic,
            str(discipline_adapter_summary),
            str(experiment_execution_loop_summary),
            str(execution_adapter_registry_summary or {}),
        ]
    ).lower()
    bindings: list[dict[str, Any]] = []
    missing_required: list[str] = []
    for role, tools in expected.items():
        matched = [tool for tool in tools if tool.lower() in present_text]
        required = role in {"primary_runtime", "data_or_artifact_store", "quality_control"}
        if required and not matched:
            missing_required.append(role)
        bindings.append(
            {
                "binding_role": role,
                "expected_tools": tools,
                "matched_tools": matched,
                "binding_state": "bound" if matched else "needs_configuration",
                "required": required,
            }
        )
    readiness = "high" if not missing_required else "medium" if len(missing_required) <= 1 else "low"
    return {
        "discipline_toolchain_binding_id": f"discipline-toolchain::{_slugify(topic)}",
        "topic": topic,
        "primary_discipline": primary,
        "candidate_count": len(candidates),
        "execution_package_count": len(packages),
        "binding_readiness": readiness,
        "bindings": bindings,
        "missing_required_bindings": missing_required,
        "toolchain_constraints": _toolchain_constraints(primary, missing_required),
        "handoff_requirements": [
            "executor package must name the concrete runtime or instrument adapter",
            "artifacts must be written to a governed data store with provenance ids",
            "quality-control reviewer must verify discipline-native checks before belief update",
        ],
    }


def _expected_toolchain(primary: str) -> dict[str, list[str]]:
    if "chemical_engineering" in primary or ("chem" in primary and "engineering" in primary):
        return {
            "primary_runtime": ["aspen", "gproms", "comsol", "opc", "python"],
            "data_or_artifact_store": ["lims", "historian", "mlflow", "artifact"],
            "quality_control": ["mass balance", "energy balance", "sensitivity"],
            "safety_layer": ["hazop", "msds", "process safety"],
        }
    if "chem" in primary:
        return {
            "primary_runtime": ["rdkit", "openbabel", "orca", "gaussian", "instrument"],
            "data_or_artifact_store": ["eln", "lims", "spectra", "artifact"],
            "quality_control": ["purity", "calibration", "blank", "replicate"],
            "safety_layer": ["msds", "hazard", "ppe"],
        }
    if "artificial" in primary or primary == "ai":
        return {
            "primary_runtime": ["python", "pytorch", "tensorflow", "jax", "sklearn"],
            "data_or_artifact_store": ["dataset", "checkpoint", "mlflow", "wandb"],
            "quality_control": ["seed", "split", "baseline", "ablation"],
            "safety_layer": ["privacy", "license", "model card"],
        }
    if "physics" in primary:
        return {
            "primary_runtime": ["python", "numpy", "scipy", "ase", "qutip", "instrument"],
            "data_or_artifact_store": ["raw data", "calibration", "artifact"],
            "quality_control": ["calibration", "uncertainty", "control", "replicate"],
            "safety_layer": ["laser", "radiation", "cryogenic", "electrical"],
        }
    if "math" in primary:
        return {
            "primary_runtime": ["sympy", "sage", "lean", "coq", "isabelle"],
            "data_or_artifact_store": ["proof", "lemma", "notebook", "artifact"],
            "quality_control": ["formal proof", "counterexample", "assumption"],
            "safety_layer": ["scope control", "human proof review"],
        }
    return {
        "primary_runtime": ["python", "notebook"],
        "data_or_artifact_store": ["artifact", "dataset"],
        "quality_control": ["control", "reproducibility"],
        "safety_layer": ["human approval"],
    }


def _toolchain_constraints(primary: str, missing: list[str]) -> list[str]:
    constraints = [f"bind {item.replace('_', ' ')} before real execution" for item in missing]
    if "chem" in primary or "physics" in primary:
        constraints.append("physical experiment execution requires safety and instrument adapter approval")
    if "math" in primary:
        constraints.append("claim promotion requires proof object or explicit conjecture status")
    return constraints[:10]


def _items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value).strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "toolchain"
