from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..layered_adapters import build_layered_adapter_summary
from .ablation import build_ablation_plan
from .artifact_registry import build_ai_artifact_contract
from .contamination import build_contamination_risk_report
from .dataset_profiler import build_dataset_profile
from .evaluation_protocol import build_evaluation_protocol
from .models import AIResearchWorkflowInput, AIResearchWorkflowResult
from .training_recipe import build_training_recipe


class AIResearchWorkflow:
    def __init__(self, *, cwd: str | Path) -> None:
        self.cwd = Path(cwd).resolve()

    def run(self, data: AIResearchWorkflowInput | dict[str, Any]) -> AIResearchWorkflowResult:
        request = data if isinstance(data, AIResearchWorkflowInput) else AIResearchWorkflowInput(**data)
        output_dir = request.resolved_output_dir(self.cwd)
        output_dir.mkdir(parents=True, exist_ok=True)

        dataset_path = _resolve_optional_path(self.cwd, request.dataset_path)
        problem_profile = self._build_problem_profile(request)
        dataset_profile = build_dataset_profile(
            dataset_path=str(dataset_path) if dataset_path else None,
            target_column=request.target_column,
            id_column=request.id_column,
        )
        contamination_risk_report = build_contamination_risk_report(
            dataset_profile=dataset_profile,
            target_column=request.target_column,
            id_column=request.id_column,
            task_type=request.task_type,
        )
        evaluation_protocol = build_evaluation_protocol(
            research_question=request.research_question,
            dataset_profile=dataset_profile,
            contamination_risk_report=contamination_risk_report,
            task_type=request.task_type,
            metric=request.metric,
            metric_direction=request.metric_direction,
        )
        training_recipe = build_training_recipe(
            dataset_profile=dataset_profile,
            evaluation_protocol=evaluation_protocol,
            available_compute=request.available_compute,
            candidate_models=request.candidate_models,
        )
        ablation_plan = build_ablation_plan(
            training_recipe=training_recipe,
            evaluation_protocol=evaluation_protocol,
        )
        artifact_contract = build_ai_artifact_contract(
            project_id=request.project_id,
            evaluation_protocol=evaluation_protocol,
            training_recipe=training_recipe,
        )
        next_actions = self._build_next_actions(
            dataset_profile=dataset_profile,
            contamination_risk_report=contamination_risk_report,
            evaluation_protocol=evaluation_protocol,
            training_recipe=training_recipe,
        )
        result = AIResearchWorkflowResult(
            problem_profile=problem_profile,
            dataset_profile=dataset_profile,
            contamination_risk_report=contamination_risk_report,
            evaluation_protocol=evaluation_protocol,
            training_recipe=training_recipe,
            ablation_plan=ablation_plan,
            artifact_contract=artifact_contract,
            next_actions=next_actions,
            output_dir=str(output_dir),
        )
        self._write_outputs(output_dir, result)
        return result

    def _build_problem_profile(self, request: AIResearchWorkflowInput) -> dict[str, Any]:
        task_type = request.task_type or "unspecified_ai_task"
        layered_adapter = build_layered_adapter_summary(
            discipline="artificial_intelligence",
            task_type=task_type if task_type != "unspecified_ai_task" else "benchmark_reproduction",
            toolchain="python",
            available_tools=["python"],
        )
        return {
            "profile_state": "draft",
            "research_question": request.research_question,
            "project_id": request.project_id,
            "discipline": "artificial_intelligence",
            "task_type": task_type,
            "target_column": request.target_column,
            "id_column": request.id_column,
            "metric": request.metric,
            "metric_direction": request.metric_direction,
            "available_compute": request.available_compute,
            "candidate_models": request.candidate_models,
            "research_context": request.research_context,
            "literature_context": request.literature_context,
            "benchmark_context": request.benchmark_context,
            "repo_context": request.repo_context,
            "prior_memory_context": request.prior_memory_context,
            "layered_adapter_summary": layered_adapter,
            "core_scientific_framing": {
                "hypothesis_unit": "model, data, feature, training, or evaluation change",
                "experiment_unit": "one reproducible training/evaluation run",
                "evidence_unit": "metric plus artifact provenance plus quality-control status",
                "failure_unit": "negative result, invalid run, leakage finding, or irreproducible configuration",
            },
        }

    def _build_next_actions(
        self,
        *,
        dataset_profile: dict[str, Any],
        contamination_risk_report: dict[str, Any],
        evaluation_protocol: dict[str, Any],
        training_recipe: dict[str, Any],
    ) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        if dataset_profile.get("profile_state") != "profiled":
            actions.append(
                {
                    "action": "provide_or_fix_dataset_path",
                    "priority": "high",
                    "reason": "dataset profile is required before trustworthy AI experiments",
                }
            )
        if contamination_risk_report.get("overall_risk") in {"medium", "high"}:
            actions.append(
                {
                    "action": "run_contamination_and_leakage_audit",
                    "priority": "high",
                    "reason": "contamination or leakage can invalidate AI research claims",
                }
            )
        actions.append(
            {
                "action": "freeze_evaluation_protocol",
                "priority": "high",
                "reason": f"baseline and ablations should use {evaluation_protocol.get('split_strategy', {}).get('method', 'a locked split')}",
            }
        )
        actions.append(
            {
                "action": "run_reproducible_baseline",
                "priority": "high",
                "reason": f"first baseline model: {training_recipe.get('baseline_recipe', {}).get('model', 'baseline')}",
            }
        )
        actions.append(
            {
                "action": "schedule_controlled_ablation",
                "priority": "medium",
                "reason": "AI research conclusions require one-factor-at-a-time comparisons",
            }
        )
        return actions

    def _write_outputs(self, output_dir: Path, result: AIResearchWorkflowResult) -> None:
        payload = result.to_dict()
        (output_dir / "ai_research_workflow_result.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        for key, value in payload.items():
            if isinstance(value, (dict, list)):
                (output_dir / f"{key}.json").write_text(
                    json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
                    encoding="utf-8",
                )


def _resolve_optional_path(cwd: Path, raw_path: str | None) -> Path | None:
    if not raw_path:
        return None
    path = Path(raw_path)
    return path.resolve() if path.is_absolute() else (cwd / path).resolve()
