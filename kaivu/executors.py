from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

from .graph import ProvenanceEvent, ProvenanceFact, ResearchGraphRegistry
from .run_handoff import normalize_run_handoff_payload


@dataclass(slots=True)
class ExecutorSpec:
    executor_id: str
    executor_type: str
    supported_handoff_targets: list[str] = field(default_factory=list)
    supported_execution_modes: list[str] = field(default_factory=list)
    safety_boundary: str = "dry_run_or_explicit_local_only"
    requires_explicit_approval: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExecutorRunResult:
    executor_id: str
    package_id: str
    experiment_id: str
    execution_state: str
    normalized_bundle: dict[str, Any] = field(default_factory=dict)
    raw_result: dict[str, Any] = field(default_factory=dict)
    provenance_fact_ids: list[str] = field(default_factory=list)
    provenance_event_ids: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ScientificExecutorRegistry:
    def __init__(self, *, cwd: str | Path, graph_registry: ResearchGraphRegistry | None = None) -> None:
        self.cwd = Path(cwd).resolve()
        self.graph_registry = graph_registry
        self.executors = {
            "dry_run": ExecutorSpec(
                executor_id="executor::dry_run",
                executor_type="dry_run",
                supported_handoff_targets=[
                    "run_manager",
                    "optimization_adapter",
                    "ai_training_runner",
                    "domain_lab_adapter",
                    "proof_search_adapter",
                ],
                supported_execution_modes=["*"],
                requires_explicit_approval=False,
            ),
            "local_python": ExecutorSpec(
                executor_id="executor::local_python",
                executor_type="local_python",
                supported_handoff_targets=[
                    "ai_training_runner",
                    "optimization_adapter",
                    "proof_search_adapter",
                    "run_manager",
                ],
                supported_execution_modes=[
                    "external_hpo_runner",
                    "bounded_search",
                    "single_or_batched_experiment_run",
                    "review_workflow",
                ],
                safety_boundary="workspace_local_python_script_only",
                requires_explicit_approval=True,
            ),
        }

    def describe(self) -> dict[str, Any]:
        return {
            "executor_registry_id": "scientific-executor-registry",
            "executor_count": len(self.executors),
            "executors": [item.to_dict() for item in self.executors.values()],
            "safety_policy": {
                "default_executor": "dry_run",
                "local_python_requires_workspace_script": True,
                "local_python_does_not_use_shell": True,
                "instrument_control_not_supported_in_v1": True,
            },
        }

    async def execute(
        self,
        *,
        package: dict[str, Any],
        contract: dict[str, Any],
        executor_type: str = "dry_run",
        executor_config: dict[str, Any] | None = None,
        project_id: str = "",
        topic: str = "",
    ) -> ExecutorRunResult:
        executor_config = executor_config or {}
        executor = self.executors.get(executor_type)
        if executor is None:
            return self._error_result(package, executor_type, [f"unknown executor_type: {executor_type}"])
        compatibility_errors = self._compatibility_errors(package, executor)
        if compatibility_errors:
            return self._error_result(package, executor.executor_id, compatibility_errors)
        if executor_type == "local_python":
            payload, raw_result, errors = await self._run_local_python(
                package=package,
                executor_config=executor_config,
            )
        else:
            payload, raw_result, errors = self._run_dry(package=package, contract=contract)
        if errors:
            return self._error_result(package, executor.executor_id, errors, raw_result=raw_result)
        bundle = normalize_run_handoff_payload(contract=contract, payload=payload)
        fact_ids, event_ids = self.persist_execution_facts(
            bundle=bundle,
            package=package,
            executor=executor,
            project_id=project_id,
            topic=topic,
        )
        return ExecutorRunResult(
            executor_id=executor.executor_id,
            package_id=str(package.get("package_id", "")),
            experiment_id=str(package.get("experiment_id", "")),
            execution_state="completed" if bundle.get("validation_state") == "valid" else "completed_with_validation_errors",
            normalized_bundle=bundle,
            raw_result=raw_result,
            provenance_fact_ids=fact_ids,
            provenance_event_ids=event_ids,
            errors=bundle.get("validation_errors", []) if isinstance(bundle.get("validation_errors", []), list) else [],
        )

    def persist_execution_facts(
        self,
        *,
        bundle: dict[str, Any],
        package: dict[str, Any],
        executor: ExecutorSpec,
        project_id: str = "",
        topic: str = "",
    ) -> tuple[list[str], list[str]]:
        if self.graph_registry is None:
            return [], []
        fact_ids: list[str] = []
        event_ids: list[str] = []

        def save_fact(
            fact_type: str,
            subject_id: str,
            predicate: str,
            *,
            object_id: str = "",
            value: Any = None,
            status: str = "active",
            source_refs: list[str] | None = None,
            metadata: dict[str, Any] | None = None,
        ) -> None:
            if not subject_id or not predicate:
                return
            fact_id = "::".join(
                [
                    "fact",
                    fact_type,
                    _slugify(subject_id)[:120],
                    _slugify(predicate)[:80],
                    _slugify(object_id or json.dumps(value, ensure_ascii=False)[:120]),
                ]
            )
            self.graph_registry.save_fact(
                ProvenanceFact(
                    fact_id=fact_id,
                    fact_type=fact_type,
                    subject_id=subject_id,
                    predicate=predicate,
                    object_id=object_id,
                    value=value,
                    project_id=project_id,
                    topic=topic,
                    source_refs=source_refs or [],
                    produced_by=executor.executor_id,
                    status=status,
                    metadata=metadata or {},
                )
            )
            fact_ids.append(fact_id)

        run = bundle.get("experiment_run", {}) if isinstance(bundle.get("experiment_run", {}), dict) else {}
        run_id = str(run.get("run_id", "")).strip()
        experiment_id = str(run.get("experiment_id", "")).strip() or str(package.get("experiment_id", "")).strip()
        save_fact("experiment", experiment_id, "executed_as", object_id=run_id, value=run, status=str(run.get("status", "completed")))
        save_fact("experiment_run", run_id, "returned_bundle", object_id=str(bundle.get("bundle_id", "")), value=bundle, status=str(run.get("status", "completed")))
        for observation in bundle.get("observation_records", []) if isinstance(bundle.get("observation_records", []), list) else []:
            if not isinstance(observation, dict):
                continue
            observation_id = str(observation.get("observation_id", "")).strip()
            save_fact("observation", observation_id, "observed_in_run", object_id=run_id, value=observation, source_refs=_strings(observation.get("files", [])))
        qc = bundle.get("quality_control_review", {}) if isinstance(bundle.get("quality_control_review", {}), dict) else {}
        save_fact("quality_control", str(qc.get("review_id", "")).strip(), "reviews_run", object_id=run_id, value=qc, status=str(qc.get("quality_control_status", "")))
        interpretation = bundle.get("interpretation_record", {}) if isinstance(bundle.get("interpretation_record", {}), dict) else {}
        save_fact("interpretation", str(interpretation.get("interpretation_id", "")).strip(), "interprets_run", object_id=run_id, value=interpretation, status=str(interpretation.get("confidence", "medium")))
        for asset in bundle.get("research_asset_records", []) if isinstance(bundle.get("research_asset_records", []), list) else []:
            if not isinstance(asset, dict):
                continue
            asset_id = str(asset.get("asset_id", "")).strip()
            save_fact("artifact", asset_id, "produced_by_run", object_id=run_id, value=asset, source_refs=[str(asset.get("path_or_reference", "")).strip()])
        event_id = f"event::executor_run_completed::{_slugify(run_id or experiment_id)}::{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        self.graph_registry.save_event(
            ProvenanceEvent(
                event_id=event_id,
                event_type="executor_run_completed",
                fact_ids=fact_ids,
                project_id=project_id,
                topic=topic,
                actor=executor.executor_id,
                action="execute_package",
                metadata={
                    "package_id": package.get("package_id", ""),
                    "experiment_id": experiment_id,
                    "bundle_id": bundle.get("bundle_id", ""),
                    "validation_state": bundle.get("validation_state", ""),
                },
            )
        )
        event_ids.append(event_id)
        return fact_ids, event_ids

    def _run_dry(self, *, package: dict[str, Any], contract: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
        now = datetime.now(timezone.utc).isoformat()
        experiment_id = str(package.get("experiment_id", "")).strip()
        package_id = str(package.get("package_id", "")).strip()
        run_id = f"run::dry::{_slugify(package_id or experiment_id)}"
        quality_gates = [
            str(item).strip()
            for item in package.get("quality_gates", [])
            if str(item).strip()
        ] if isinstance(package.get("quality_gates", []), list) else []
        payload = {
            "experiment_run": {
                "run_id": run_id,
                "experiment_id": experiment_id,
                "protocol_id": f"protocol::{_slugify(experiment_id)}",
                "status": "completed",
                "operator": "scientific_executor_registry.dry_run",
                "started_at": now,
                "ended_at": now,
                "approval_status": "approved",
                "approval_note": "dry run does not operate external instruments or heavy jobs",
                "configuration_snapshot": package.get("run_configuration", {}) if isinstance(package.get("run_configuration", {}), dict) else {},
                "environment_snapshot": {"executor": "dry_run", "python": sys.version.split()[0]},
            },
            "observation_records": [
                {
                    "observation_id": f"observation::{_slugify(run_id)}::summary",
                    "observation_type": "dry_run_summary",
                    "summary": f"Dry run validated execution package {package_id or experiment_id}.",
                    "raw_values": {
                        "package_state": package.get("package_state", ""),
                        "execution_mode": package.get("execution_mode", ""),
                        "handoff_target": package.get("handoff_target", ""),
                    },
                    "timestamp": now,
                }
            ],
            "quality_control_review": {
                "review_id": f"qc::{_slugify(run_id)}",
                "quality_control_status": "passed",
                "quality_control_checks_run": quality_gates,
                "evidence_reliability": "medium",
                "usable_for_interpretation": True,
                "recommended_action": "ready_for_real_executor_or_result_import",
            },
            "interpretation_record": {
                "interpretation_id": f"interpretation::{_slugify(run_id)}",
                "negative_result": False,
                "confidence": "medium",
                "next_decision": "handoff_to_real_executor_when_approved",
            },
            "research_asset_records": [
                {
                    "asset_id": f"asset::dry-run::{_slugify(package_id or experiment_id)}",
                    "asset_type": "executor_trace",
                    "label": "dry run executor trace",
                    "path_or_reference": f"executor://dry_run/{package_id or experiment_id}",
                    "role": "execution_trace",
                    "experiment_id": experiment_id,
                    "run_id": run_id,
                    "governance_status": "dry_run_only",
                    "is_frozen": True,
                    "metadata": {"contract_id": contract.get("contract_id", "")},
                }
            ],
        }
        return payload, {"executor": "dry_run", "package_id": package_id}, []

    async def _run_local_python(
        self,
        *,
        package: dict[str, Any],
        executor_config: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
        script = str(executor_config.get("script_path") or package.get("run_configuration", {}).get("local_python_script", "")).strip()
        if not script:
            return {}, {}, ["local_python executor requires script_path or run_configuration.local_python_script"]
        script_path = (self.cwd / script).resolve()
        try:
            script_path.relative_to(self.cwd)
        except ValueError:
            return {}, {}, ["local_python script must be inside workspace"]
        if not script_path.exists() or script_path.suffix != ".py":
            return {}, {}, ["local_python script must exist and end with .py"]
        timeout = float(executor_config.get("timeout", 60))
        args = [str(arg) for arg in executor_config.get("args", [])] if isinstance(executor_config.get("args", []), list) else []
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(script_path),
            *args,
            cwd=str(self.cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        raw = {
            "returncode": proc.returncode,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
            "script_path": str(script_path),
        }
        if proc.returncode != 0:
            return {}, raw, [f"local_python exited with code {proc.returncode}"]
        payload = _extract_handoff_payload(raw["stdout"])
        if not payload:
            return {}, raw, ["local_python stdout must contain JSON handoff payload"]
        return payload, raw, []

    def _compatibility_errors(self, package: dict[str, Any], executor: ExecutorSpec) -> list[str]:
        handoff_target = str(package.get("handoff_target", "")).strip()
        execution_mode = str(package.get("execution_mode", "")).strip()
        errors: list[str] = []
        if executor.supported_handoff_targets and handoff_target and handoff_target not in executor.supported_handoff_targets:
            errors.append(f"{executor.executor_id} does not support handoff_target={handoff_target}")
        if (
            executor.supported_execution_modes
            and "*" not in executor.supported_execution_modes
            and execution_mode
            and execution_mode not in executor.supported_execution_modes
        ):
            errors.append(f"{executor.executor_id} does not support execution_mode={execution_mode}")
        return errors

    @staticmethod
    def _error_result(
        package: dict[str, Any],
        executor_id: str,
        errors: list[str],
        *,
        raw_result: dict[str, Any] | None = None,
    ) -> ExecutorRunResult:
        return ExecutorRunResult(
            executor_id=executor_id,
            package_id=str(package.get("package_id", "")),
            experiment_id=str(package.get("experiment_id", "")),
            execution_state="failed",
            raw_result=raw_result or {},
            errors=errors,
        )


def _extract_handoff_payload(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    if not text:
        return {}
    candidates = [text]
    candidates.extend(line.strip() for line in text.splitlines() if line.strip().startswith("{"))
    for candidate in reversed(candidates):
        try:
            payload = json.loads(candidate)
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload.get("handoff_payload", payload) if isinstance(payload.get("handoff_payload", payload), dict) else {}
    return {}


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "executor"


