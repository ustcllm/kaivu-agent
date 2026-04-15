from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class AITrainingScaffoldResult:
    scaffold_state: str
    root: str
    experiment_id: str
    created_files: list[str] = field(default_factory=list)
    run_command: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_ai_training_executor_scaffold(
    *,
    root: str | Path,
    experiment_id: str = "ai-exp-baseline-001",
    ai_agent_summary: dict[str, Any],
    overwrite: bool = False,
) -> AITrainingScaffoldResult:
    workspace = Path(root).resolve()
    experiment_root = workspace / "experiments" / _slugify(experiment_id)
    src_root = workspace / "src"
    created: list[str] = []
    warnings: list[str] = []
    experiment_root.mkdir(parents=True, exist_ok=True)
    src_root.mkdir(parents=True, exist_ok=True)

    evaluation = ai_agent_summary.get("evaluation_protocol", {})
    training = ai_agent_summary.get("training_recipe", {})
    dataset_profile = ai_agent_summary.get("dataset_profile", {})
    artifact_contract = ai_agent_summary.get("artifact_contract", {})
    baseline = training.get("baseline_recipe", {}) if isinstance(training, dict) else {}
    config = {
        "experiment_id": experiment_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": baseline.get("model", "simple_baseline"),
        "task_type": evaluation.get("task_type", ""),
        "metric": evaluation.get("primary_metric", ""),
        "metric_direction": evaluation.get("metric_direction", ""),
        "split_strategy": evaluation.get("split_strategy", {}),
        "dataset_path": dataset_profile.get("path", ""),
        "target_column": dataset_profile.get("target_column", ""),
        "id_column": dataset_profile.get("id_column", ""),
        "seed_policy": baseline.get("seed_policy", [42]),
        "artifact_contract": artifact_contract,
        "execution_boundary": "scaffold_only_until_approved",
    }
    created.extend(
        _write_json(experiment_root / "config.json", config, overwrite=overwrite, warnings=warnings)
    )
    created.extend(
        _write_json(
            experiment_root / "metrics.json",
            {
                "experiment_id": experiment_id,
                "status": "not_run",
                "metric": config["metric"],
                "score": None,
                "notes": ["metrics are populated after approved execution"],
            },
            overwrite=overwrite,
            warnings=warnings,
        )
    )
    created.extend(
        _write_json(
            experiment_root / "runtime_manifest.json",
            {
                "run_id": f"runtime::{_slugify(experiment_id)}::scaffold",
                "experiment_id": experiment_id,
                "status": "scaffold_created",
                "model": config["model"],
                "artifacts": ["config.json", "metrics.json", "runtime_manifest.json", "logs.txt"],
                "approval_required_before_execution": True,
                "created_at": config["created_at"],
            },
            overwrite=overwrite,
            warnings=warnings,
        )
    )
    created.extend(
        _write_text(
            experiment_root / "logs.txt",
            "AI training scaffold created. No training has been executed.\n",
            overwrite=overwrite,
            warnings=warnings,
        )
    )
    created.extend(
        _write_text(
            src_root / "train_baseline.py",
            _baseline_script(),
            overwrite=overwrite,
            warnings=warnings,
        )
    )
    return AITrainingScaffoldResult(
        scaffold_state="created" if created else "already_exists",
        root=str(workspace),
        experiment_id=experiment_id,
        created_files=created,
        run_command=[
            "python",
            "src/train_baseline.py",
            "--config",
            f"experiments/{_slugify(experiment_id)}/config.json",
        ],
        warnings=warnings,
    )


def build_ai_training_handoff_package(
    *,
    scaffold: AITrainingScaffoldResult,
    experiment_id: str,
) -> dict[str, Any]:
    return {
        "package_id": f"execution-package::{_slugify(experiment_id)}",
        "experiment_id": experiment_id,
        "adapter_id": "adapter::artificial_intelligence_training",
        "discipline": "artificial_intelligence",
        "package_state": "ready_for_handoff" if scaffold.scaffold_state in {"created", "already_exists"} else "blocked",
        "execution_mode": "single_or_batched_experiment_run",
        "protocol_requirements": [
            "freeze_evaluation_protocol",
            "configuration_snapshot_saved",
            "approval_required_before_execution",
        ],
        "run_configuration": {
            "local_python_script": "src/train_baseline.py",
            "args": scaffold.run_command[2:],
            "scaffold_root": scaffold.root,
            "experiment_id": experiment_id,
        },
        "quality_gates": [
            "dataset_split_verified",
            "contamination_or_leakage_checked",
            "configuration_snapshot_saved",
        ],
        "expected_artifacts": [
            f"experiments/{_slugify(experiment_id)}/config.json",
            f"experiments/{_slugify(experiment_id)}/metrics.json",
            f"experiments/{_slugify(experiment_id)}/runtime_manifest.json",
            f"experiments/{_slugify(experiment_id)}/logs.txt",
        ],
        "handoff_target": "ai_training_runner",
    }


def _write_json(path: Path, payload: dict[str, Any], *, overwrite: bool, warnings: list[str]) -> list[str]:
    if path.exists() and not overwrite:
        warnings.append(f"skipped existing file: {path}")
        return []
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return [str(path)]


def _write_text(path: Path, text: str, *, overwrite: bool, warnings: list[str]) -> list[str]:
    if path.exists() and not overwrite:
        warnings.append(f"skipped existing file: {path}")
        return []
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return [str(path)]


def _baseline_script() -> str:
    return """from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Kaivu AI baseline training scaffold.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    config_path = Path(args.config).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    experiment_root = config_path.parent
    metrics = {
        "experiment_id": config.get("experiment_id", ""),
        "status": "scaffold_run_only",
        "metric": config.get("metric", ""),
        "score": None,
        "model": config.get("model", ""),
        "dataset_path": config.get("dataset_path", ""),
        "notes": [
            "This scaffold validates the execution path but does not train a model yet.",
            "Replace this script with a real sklearn/PyTorch/LightGBM runner after approval.",
        ],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (experiment_root / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps({"handoff_payload": _handoff_payload(config, metrics)}, ensure_ascii=False))


def _handoff_payload(config: dict, metrics: dict) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    experiment_id = str(config.get("experiment_id", "ai-exp-baseline-001"))
    run_id = f"run::ai-training-scaffold::{experiment_id}"
    return {
        "experiment_run": {
            "run_id": run_id,
            "experiment_id": experiment_id,
            "protocol_id": f"protocol::{experiment_id}",
            "status": "completed",
            "operator": "ai_training_scaffold",
            "started_at": now,
            "ended_at": now,
            "approval_status": "approved",
            "approval_note": "scaffold execution only; no real model training",
            "configuration_snapshot": config,
            "environment_snapshot": {"executor": "ai_training_scaffold"},
        },
        "observation_records": [
            {
                "observation_id": f"observation::{run_id}::metrics",
                "run_id": run_id,
                "observation_type": "ai_training_scaffold_metrics",
                "raw_values": metrics,
                "summary": "AI training scaffold produced metrics template.",
                "files": ["metrics.json"],
                "timestamp": now,
            }
        ],
        "quality_control_review": {
            "review_id": f"qc::{run_id}",
            "run_id": run_id,
            "quality_control_status": "warning",
            "issues": ["real training not implemented in scaffold"],
            "quality_control_checks_run": ["configuration_snapshot_saved"],
            "usable_for_interpretation": False,
            "recommended_action": "replace scaffold with approved real training runner",
        },
        "interpretation_record": {
            "interpretation_id": f"interpretation::{run_id}",
            "run_id": run_id,
            "negative_result": False,
            "confidence": "low",
            "next_decision": "implement_real_training_runner",
        },
        "research_asset_records": [
            {
                "asset_id": f"asset::{experiment_id}::metrics",
                "asset_type": "metrics",
                "label": "AI scaffold metrics",
                "path_or_reference": "metrics.json",
                "role": "execution_template",
                "experiment_id": experiment_id,
                "run_id": run_id,
                "discipline": "artificial_intelligence",
                "governance_status": "scaffold_only",
                "is_frozen": False,
            }
        ],
    }


if __name__ == "__main__":
    main()
"""


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value).strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "ai-experiment"


