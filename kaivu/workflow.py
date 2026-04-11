from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys
from typing import Any

from .agents import SubagentRuntime, SubagentSpec
from .ai_research import (
    AIResearchWorkflow,
    AIResearchWorkflowInput,
    augment_experiment_execution_loop_with_ai,
)
from .assets import build_unified_asset_summary
from .autonomous_controller import build_autonomous_controller_summary
from .anomaly_detector import build_anomaly_surprise_detector_summary
from .campaign_planner import build_research_campaign_plan_summary
from .credit_ledger import build_scientific_credit_responsibility_ledger_summary
from .decision_engine import build_scientific_decision_summary
from .context_policy import build_scientific_context_policy_summary
from .discipline_adapters import build_discipline_adapter_summary
from .discipline_toolchains import build_discipline_toolchain_binding_summary
from .evidence_review import build_evidence_review_summary
from .evaluation_harness import build_kaivu_evaluation_harness_summary
from .event_ledger import ResearchEventLedger, build_workflow_events
from .executors import ScientificExecutorRegistry
from .experiment_backpropagation import (
    apply_backpropagation_to_claim_graph,
    build_backpropagation_memory_items,
    build_executor_belief_backpropagation_summary,
    persist_run_handoff_bundle,
)
from .experiment_scheduler import build_experiment_execution_loop_summary
from .execution_adapters import build_execution_adapter_registry_summary
from .experiments import ExperimentRegistry
from .graph import (
    ProvenanceEvent,
    ProvenanceFact,
    ResearchGraphEdge,
    ResearchGraphNode,
    ResearchGraphRegistry,
    ResearchGraphSnapshot,
)
from .hypotheses import build_hypothesis_theory_summary
from .mcp import MCPRegistry
from .model import ModelBackend
from .model_registry import AgentModelConfig, ModelRegistry
from .memory import MemoryManager
from .literature_policy import decide_literature_ingest_policy
from .permissions import PermissionPolicy
from .optimization_adapter import build_optimization_adapter_summary
from .problem_reframer import build_scientific_problem_reframer_summary
from .profiles import DEFAULT_SCIENCE_PROFILES, SpecialistProfile
from .prompts import PromptBuilder
from .reporting import render_markdown_report, write_markdown_report
from .research_program import ResearchProgram, ResearchProgramRegistry, build_research_program_from_state
from .run_handoff import build_run_handoff_contract_summary
from .runtime.workspace import ResearchWorkspaceLayout
from .risk_permissions import build_experiment_risk_permission_summary
from .route_scheduler import build_research_route_scheduler_summary
from .scheduler_judge import SchedulerLLMJudge, apply_scheduler_judgment_to_summary
from .scientific_kernel import (
    build_benchmark_case_suite_summary,
    build_scientific_evaluation_benchmark_summary,
    build_counterfactual_experiment_summary,
    build_failure_reuse_engine_summary,
    build_literature_claim_compiler_summary,
    build_memory_conflict_version_graph_summary,
    build_memory_governance_loop_summary,
    build_model_reliability_layer_summary,
    build_next_cycle_decision_directives_summary,
    build_research_state_machine_summary,
    build_research_operating_system_summary,
    build_reproducibility_kernel_summary,
    build_discipline_native_kernel_summary,
    build_lab_meeting_protocol_summary,
    build_scheduler_search_kernel_summary,
    build_scientific_error_taxonomy_summary,
    build_scientific_kernel_state_summary,
    build_scientific_object_store_summary,
    build_scientific_debate_protocol_summary,
    build_scientific_release_gate_summary,
    build_uncertainty_ledger_summary,
    build_unified_provenance_graph_summary,
    build_value_of_information_summary,
)
from .skills.runtime import SkillRuntime
from .state import AgentState
from .theory_formalizer import build_theory_prediction_compiler_summary
from .structured_output import (
    StructuredSchema,
    parse_structured_output,
    repair_instruction,
    salvage_structured_output,
    schema_instruction,
)
from .tools import ToolRegistry


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _context_string(context: dict[str, Any], key: str) -> str:
    value = context.get(key)
    return str(value).strip() if value is not None else ""


def _context_list(context: dict[str, Any], key: str) -> list[str]:
    value = context.get(key)
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _context_dict(context: dict[str, Any], key: str) -> dict[str, Any]:
    value = context.get(key)
    return value if isinstance(value, dict) else {}


@dataclass(slots=True)
class WorkflowStepResult:
    profile_name: str
    raw_output: str
    parsed_output: dict[str, Any]
    state: AgentState
    model_meta: dict[str, Any]


@dataclass(slots=True)
class WorkflowRunResult:
    topic: str
    steps: list[WorkflowStepResult]
    claim_graph: dict[str, Any]
    research_state: dict[str, Any]
    run_manifest: dict[str, Any]
    final_report: str
    report_path: str


STAGE_ORDER = [
    "question",
    "review",
    "hypothesis",
    "design",
    "execute",
    "analyze",
    "decide",
    "report",
]

ALLOWED_STAGE_NEXT: dict[str, list[str]] = {
    "question": ["review"],
    "review": ["hypothesis"],
    "hypothesis": ["design"],
    "design": ["execute", "analyze"],
    "execute": ["analyze"],
    "analyze": ["hypothesis", "design", "decide"],
    "decide": ["design", "report"],
    "report": [],
}


class ScientificWorkflow:
    def __init__(
        self,
        *,
        cwd: str | Path,
        model_name: str = "gpt-5",
        base_url: str = "https://api.openai.com/v1/responses",
        permission_policy: PermissionPolicy | None = None,
        tools: ToolRegistry | None = None,
        report_path: str | Path | None = None,
        dynamic_routing: bool = True,
        skill_runtime: SkillRuntime | None = None,
        mcp_registry: MCPRegistry | None = None,
        model_registry: ModelRegistry | None = None,
        collaboration_context: dict[str, str] | None = None,
    ) -> None:
        self.cwd = Path(cwd).resolve()
        self.model_name = model_name
        self.base_url = base_url
        self.permission_policy = permission_policy or PermissionPolicy()
        self.tools = tools
        self.report_path = (
            Path(report_path).resolve()
            if report_path
            else self.cwd / "reports" / "scientific_report.md"
        )
        self.repair_attempts = 2
        self.dynamic_routing = dynamic_routing
        self.skill_runtime = skill_runtime
        self.mcp_registry = mcp_registry
        self.model_registry = model_registry or ModelRegistry(
            default_model=model_name,
            default_base_url=base_url,
        )
        self.collaboration_context = collaboration_context or {}
        self.prompt_builder = PromptBuilder()
        self.workspace_layout = ResearchWorkspaceLayout.for_context(
            self.cwd,
            discipline=str(self.collaboration_context.get("discipline", "")).strip()
            or str(self.collaboration_context.get("primary_discipline", "")).strip(),
            project_id=str(self.collaboration_context.get("project_id", "")).strip(),
            group_id=str(self.collaboration_context.get("group_id", "")).strip(),
            user_id=str(self.collaboration_context.get("user_id", "")).strip(),
        )
        self.workspace_layout.ensure()
        self.graph_registry = ResearchGraphRegistry(self.workspace_layout.state_root / "graph")
        self.event_ledger = ResearchEventLedger(self.workspace_layout.state_root / "events")
        self.experiment_registry = ExperimentRegistry(self.workspace_layout.state_root / "experiments")
        self.research_program_registry = ResearchProgramRegistry(self.workspace_layout.state_root / "programs")
        self.executor_registry = ScientificExecutorRegistry(
            cwd=self.cwd,
            graph_registry=self.graph_registry,
        )
        self.subagent_runtime = SubagentRuntime(
            cwd=self.cwd,
            permission_policy=self.permission_policy,
            memory_manager=MemoryManager(
                self.cwd,
                memory_root=self.workspace_layout.memory_root,
                state_root=self.workspace_layout.state_root,
            ),
            memory_root=self.workspace_layout.memory_root,
            state_root=self.workspace_layout.state_root,
        )

    async def run(
        self,
        topic: str,
        *,
        tools: ToolRegistry,
        profiles: list[SpecialistProfile] | None = None,
    ) -> WorkflowRunResult:
        steps: list[WorkflowStepResult] = []
        project_id = str(self.collaboration_context.get("project_id", "")).strip()
        prior_program = self.research_program_registry.latest_program(project_id=project_id, topic=topic)
        if prior_program:
            self.collaboration_context["research_program_context"] = {
                "program_id": prior_program.get("program_id", ""),
                "status": prior_program.get("status", ""),
                "objective_contract": prior_program.get("objective_contract", {}),
                "control_actions": prior_program.get("control_actions", [])[:10]
                if isinstance(prior_program.get("control_actions", []), list)
                else [],
                "failed_attempt_recall": prior_program.get("failed_attempt_recall", {}),
                "experiment_portfolio": prior_program.get("experiment_portfolio", {}),
                "report_release_policy": prior_program.get("report_release_policy", {}),
                "rival_hypothesis_reasoning": prior_program.get("rival_hypothesis_reasoning", {}),
            }
        graph_history_summary = self.graph_registry.summarize(project_id=project_id, topic=topic)
        self.collaboration_context["typed_research_graph_history"] = graph_history_summary
        self.collaboration_context["typed_research_graph_query"] = self._build_typed_graph_query_context(topic)

        if profiles is not None:
            for profile in profiles:
                step = await self._run_profile(topic, profile, tools, steps)
                steps.append(step)
        elif self.dynamic_routing:
            await self._run_dynamic_workflow(topic, tools, steps)
        else:
            for profile in self._build_profile_sequence(topic):
                step = await self._run_profile(topic, profile, tools, steps)
                steps.append(step)

        claim_graph = self._build_claim_graph(steps)
        self._apply_hypothesis_status_updates(steps, claim_graph)
        execution_records = self._collect_execution_records(steps)
        usage_summary = self._collect_usage_summary(steps)
        run_manifest = self._derive_run_manifest(
            topic=topic,
            steps=steps,
            execution_records=execution_records,
            usage_summary=usage_summary,
        )
        research_state = self._derive_research_state(
            topic,
            steps,
            claim_graph=claim_graph,
            run_manifest=run_manifest,
        )
        await self._apply_scheduler_llm_judgment(
            topic=topic,
            research_state=research_state,
            claim_graph=claim_graph,
        )
        claim_graph["hypothesis_tree"] = research_state.get("hypothesis_tree_summary", {})
        claim_graph["asset_registry_summary"] = research_state.get("asset_registry_summary", {})
        claim_graph["asset_graph_summary"] = research_state.get("asset_graph_summary", {})
        claim_graph["unified_asset_summary"] = research_state.get("unified_asset_summary", {})
        claim_graph["consensus_state"] = research_state.get("consensus_state", {})
        claim_graph["consensus_state_machine"] = research_state.get("consensus_state_machine", {})
        claim_graph["research_plan_summary"] = research_state.get("research_plan_summary", {})
        claim_graph["literature_synthesis"] = research_state.get("literature_synthesis", {})
        claim_graph["systematic_review_summary"] = research_state.get("systematic_review_summary", {})
        claim_graph["ai_research_workflow_summary"] = research_state.get("ai_research_workflow_summary", {})
        claim_graph["ai_evaluation_protocol"] = research_state.get("ai_evaluation_protocol", {})
        claim_graph["ai_training_recipe"] = research_state.get("ai_training_recipe", {})
        claim_graph["ai_ablation_plan"] = research_state.get("ai_ablation_plan", {})
        claim_graph["workspace_layout_summary"] = research_state.get("workspace_layout_summary", {})
        claim_graph["causal_graph_summary"] = research_state.get("causal_graph_summary", {})
        claim_graph["discipline_adaptation_summary"] = research_state.get("discipline_adaptation_summary", {})
        claim_graph["autonomy_summary"] = research_state.get("autonomy_summary", {})
        claim_graph["autonomous_controller_summary"] = research_state.get(
            "autonomous_controller_summary", {}
        )
        claim_graph["execution_cycle_summary"] = research_state.get("execution_cycle_summary", {})
        claim_graph["termination_strategy_summary"] = research_state.get("termination_strategy_summary", {})
        claim_graph["experiment_governance_summary"] = research_state.get("experiment_governance_summary", {})
        claim_graph["experiment_execution_loop_summary"] = research_state.get(
            "experiment_execution_loop_summary", {}
        )
        claim_graph["optimization_adapter_summary"] = research_state.get(
            "optimization_adapter_summary", {}
        )
        claim_graph["discipline_adapter_summary"] = research_state.get(
            "discipline_adapter_summary", {}
        )
        claim_graph["execution_adapter_registry_summary"] = research_state.get(
            "execution_adapter_registry_summary", {}
        )
        claim_graph["run_handoff_contract_summary"] = research_state.get(
            "run_handoff_contract_summary", {}
        )
        claim_graph["discipline_toolchain_binding_summary"] = research_state.get(
            "discipline_toolchain_binding_summary", {}
        )
        claim_graph["experiment_risk_permission_summary"] = research_state.get(
            "experiment_risk_permission_summary", {}
        )
        claim_graph["experiment_economics_summary"] = research_state.get("experiment_economics_summary", {})
        claim_graph["lab_meeting_consensus_summary"] = research_state.get("lab_meeting_consensus_summary", {})
        claim_graph["agent_stance_continuity_summary"] = research_state.get(
            "agent_stance_continuity_summary", {}
        )
        claim_graph["theoretical_hypothesis_tree_summary"] = research_state.get("theoretical_hypothesis_tree_summary", {})
        claim_graph["mechanism_reasoning_summary"] = research_state.get("mechanism_reasoning_summary", {})
        claim_graph["hypothesis_family_lifecycle_summary"] = research_state.get("hypothesis_family_lifecycle_summary", {})
        claim_graph["failure_intelligence_summary"] = research_state.get("failure_intelligence_summary", {})
        claim_graph["evaluation_summary"] = research_state.get("evaluation_summary", {})
        claim_graph["graph_reference_summary"] = research_state.get("graph_reference_summary", {})
        claim_graph["route_temperature_summary"] = research_state.get("route_temperature_summary", {})
        claim_graph["graph_learning_summary"] = research_state.get("graph_learning_summary", {})
        claim_graph["human_governance_checkpoint_summary"] = research_state.get(
            "human_governance_checkpoint_summary", {}
        )
        claim_graph["benchmark_harness_summary"] = research_state.get(
            "benchmark_harness_summary", {}
        )
        claim_graph["kaivu_evaluation_harness_summary"] = research_state.get(
            "kaivu_evaluation_harness_summary", {}
        )
        claim_graph["program_management_summary"] = research_state.get(
            "program_management_summary", {}
        )
        claim_graph["domain_playbook_summary"] = research_state.get(
            "domain_playbook_summary", {}
        )
        claim_graph["hypothesis_validation_summary"] = research_state.get(
            "hypothesis_validation_summary", {}
        )
        claim_graph["hypothesis_gate_summary"] = research_state.get(
            "hypothesis_gate_summary", {}
        )
        claim_graph["hypothesis_theory_summary"] = research_state.get(
            "hypothesis_theory_summary", {}
        )
        claim_graph["scientific_problem_reframer_summary"] = research_state.get(
            "scientific_problem_reframer_summary", {}
        )
        claim_graph["theory_prediction_compiler_summary"] = research_state.get(
            "theory_prediction_compiler_summary", {}
        )
        claim_graph["anomaly_surprise_detector_summary"] = research_state.get(
            "anomaly_surprise_detector_summary", {}
        )
        claim_graph["scientific_credit_responsibility_ledger_summary"] = research_state.get(
            "scientific_credit_responsibility_ledger_summary", {}
        )
        claim_graph["mechanism_family_lifecycle_summary"] = research_state.get(
            "mechanism_family_lifecycle_summary", {}
        )
        claim_graph["artifact_provenance_summary"] = research_state.get(
            "artifact_provenance_summary", {}
        )
        claim_graph["program_portfolio_summary"] = research_state.get(
            "program_portfolio_summary", {}
        )
        claim_graph["formal_review_record_summary"] = research_state.get(
            "formal_review_record_summary", {}
        )
        claim_graph["literature_ingest_policy_summary"] = research_state.get(
            "literature_ingest_policy_summary", {}
        )
        claim_graph["evidence_review_summary"] = research_state.get(
            "evidence_review_summary", {}
        )
        claim_graph["research_route_search_summary"] = research_state.get(
            "research_route_search_summary", {}
        )
        claim_graph["scientific_decision_summary"] = research_state.get(
            "scientific_decision_summary", {}
        )
        claim_graph["scientific_object_store_summary"] = research_state.get(
            "scientific_object_store_summary", {}
        )
        claim_graph["research_state_machine_summary"] = research_state.get(
            "research_state_machine_summary", {}
        )
        claim_graph["uncertainty_ledger_summary"] = research_state.get(
            "uncertainty_ledger_summary", {}
        )
        claim_graph["value_of_information_summary"] = research_state.get(
            "value_of_information_summary", {}
        )
        claim_graph["counterfactual_experiment_summary"] = research_state.get(
            "counterfactual_experiment_summary", {}
        )
        claim_graph["reproducibility_kernel_summary"] = research_state.get(
            "reproducibility_kernel_summary", {}
        )
        claim_graph["scientific_debate_protocol_summary"] = research_state.get(
            "scientific_debate_protocol_summary", {}
        )
        claim_graph["failure_reuse_engine_summary"] = research_state.get(
            "failure_reuse_engine_summary", {}
        )
        claim_graph["literature_claim_compiler_summary"] = research_state.get(
            "literature_claim_compiler_summary", {}
        )
        claim_graph["model_reliability_layer_summary"] = research_state.get(
            "model_reliability_layer_summary", {}
        )
        claim_graph["benchmark_case_suite_summary"] = research_state.get(
            "benchmark_case_suite_summary", {}
        )
        claim_graph["scientific_context_policy_summary"] = research_state.get(
            "scientific_context_policy_summary", {}
        )
        claim_graph["memory_governance_loop_summary"] = research_state.get(
            "memory_governance_loop_summary", {}
        )
        claim_graph["scheduler_search_kernel_summary"] = research_state.get(
            "scheduler_search_kernel_summary", {}
        )
        claim_graph["research_campaign_plan_summary"] = research_state.get(
            "research_campaign_plan_summary", {}
        )
        if isinstance(claim_graph["research_campaign_plan_summary"], dict):
            claim_graph["route_selector_summary"] = claim_graph["research_campaign_plan_summary"].get(
                "route_selector_summary",
                {},
            )
        claim_graph["graph_semantics"] = {
            "canonical_fact_source": "provenance_facts",
            "canonical_state_source": "research_state",
            "claim_graph_scope": ["claims", "hypotheses", "evidence", "experiments", "negative_results", "relations"],
            "research_context_overlay": "read-only compatibility context for downstream summarizers",
        }
        claim_graph["lab_meeting_protocol_summary"] = research_state.get(
            "lab_meeting_protocol_summary", {}
        )
        claim_graph["unified_provenance_graph_summary"] = research_state.get(
            "unified_provenance_graph_summary", {}
        )
        claim_graph["discipline_native_kernel_summary"] = research_state.get(
            "discipline_native_kernel_summary", {}
        )
        claim_graph["next_cycle_decision_directives_summary"] = research_state.get(
            "next_cycle_decision_directives_summary", {}
        )
        claim_graph["scientific_kernel_state_summary"] = research_state.get(
            "scientific_kernel_state_summary", {}
        )
        claim_graph["research_operating_system_summary"] = research_state.get(
            "research_operating_system_summary", {}
        )
        claim_graph["research_program_summary"] = research_state.get(
            "research_program_summary", {}
        )
        claim_graph["scientific_error_taxonomy_summary"] = research_state.get(
            "scientific_error_taxonomy_summary", {}
        )
        claim_graph["scientific_release_gate_summary"] = research_state.get(
            "scientific_release_gate_summary", {}
        )
        claim_graph["memory_conflict_version_graph_summary"] = research_state.get(
            "memory_conflict_version_graph_summary", {}
        )
        claim_graph["typed_research_graph_history"] = graph_history_summary
        typed_research_graph_summary = self._sync_typed_research_graph(
            topic=topic,
            steps=steps,
            claim_graph=claim_graph,
            research_state=research_state,
            run_manifest=run_manifest,
        )
        claim_graph["typed_research_graph_summary"] = typed_research_graph_summary
        provenance_claim_graph = self._build_claim_graph_from_provenance_replay(topic)
        provenance_merge_summary = self._merge_provenance_claim_graph(
            claim_graph,
            provenance_claim_graph,
        )
        claim_graph["provenance_claim_graph"] = provenance_claim_graph
        claim_graph["provenance_merge_summary"] = provenance_merge_summary
        claim_graph["source_of_truth_policy"] = {
            "primary_fact_source": "provenance_facts",
            "legacy_step_outputs": "used_as_fact_inputs_until_full_migration",
            "derived_claim_graph_overlay": provenance_merge_summary,
        }
        research_state["typed_research_graph_summary"] = typed_research_graph_summary
        research_state["typed_research_graph_history"] = graph_history_summary
        research_state["provenance_replay_summary"] = provenance_claim_graph.get("replay_summary", {})
        research_state["provenance_merge_summary"] = provenance_merge_summary
        research_state["source_of_truth_policy"] = claim_graph["source_of_truth_policy"]
        executor_run_summary = await self._execute_ready_packages(
            topic=topic,
            research_state=research_state,
        )
        research_state["executor_run_summary"] = executor_run_summary
        claim_graph["executor_run_summary"] = executor_run_summary
        executor_belief_backpropagation_summary = build_executor_belief_backpropagation_summary(
            topic=topic,
            executor_run_summary=executor_run_summary,
            claim_graph=claim_graph,
            research_state=research_state,
        )
        research_state["executor_belief_backpropagation_summary"] = executor_belief_backpropagation_summary
        claim_graph["executor_belief_backpropagation_summary"] = executor_belief_backpropagation_summary
        executor_backpropagation_records = [
            run.get("backpropagation_record", {})
            for run in executor_run_summary.get("runs", [])
            if isinstance(run, dict) and isinstance(run.get("backpropagation_record", {}), dict) and run.get("backpropagation_record", {})
        ] if isinstance(executor_run_summary.get("runs", []), list) else []
        for backpropagation_record in executor_backpropagation_records:
            claim_graph = apply_backpropagation_to_claim_graph(
                claim_graph=claim_graph,
                backpropagation_record=backpropagation_record,
            )
        if executor_backpropagation_records:
            research_state["executor_backpropagation_records"] = executor_backpropagation_records
            claim_graph["executor_backpropagation_records"] = executor_backpropagation_records
        research_state["anomaly_surprise_detector_summary"] = build_anomaly_surprise_detector_summary(
            topic=topic,
            research_state=research_state,
            claim_graph=claim_graph,
        )
        claim_graph["anomaly_surprise_detector_summary"] = research_state["anomaly_surprise_detector_summary"]
        research_state["scientific_credit_responsibility_ledger_summary"] = build_scientific_credit_responsibility_ledger_summary(
            topic=topic,
            research_state=research_state,
            run_manifest=run_manifest,
        )
        claim_graph["scientific_credit_responsibility_ledger_summary"] = research_state[
            "scientific_credit_responsibility_ledger_summary"
        ]
        if executor_belief_backpropagation_summary.get("scheduler_feedback"):
            research_state["experiment_risk_permission_summary"] = build_experiment_risk_permission_summary(
                topic=topic,
                experiment_execution_loop_summary=research_state.get("experiment_execution_loop_summary", {}),
                discipline_toolchain_binding_summary=research_state.get("discipline_toolchain_binding_summary", {}),
                human_governance_checkpoint_summary=research_state.get("human_governance_checkpoint_summary", {}),
                executor_run_summary=executor_run_summary,
            )
            claim_graph["experiment_risk_permission_summary"] = research_state["experiment_risk_permission_summary"]
        if executor_run_summary.get("run_count"):
            provenance_claim_graph = self._build_claim_graph_from_provenance_replay(topic)
            provenance_merge_summary = self._merge_provenance_claim_graph(
                claim_graph,
                provenance_claim_graph,
            )
            claim_graph["provenance_claim_graph"] = provenance_claim_graph
            claim_graph["provenance_merge_summary"] = provenance_merge_summary
            research_state["provenance_replay_summary"] = provenance_claim_graph.get("replay_summary", {})
            research_state["provenance_merge_summary"] = provenance_merge_summary
        research_state["benchmark_case_suite_summary"] = build_benchmark_case_suite_summary(
            topic=topic,
            research_state=research_state,
            claim_graph=claim_graph,
            run_manifest=run_manifest,
        )
        claim_graph["benchmark_case_suite_summary"] = research_state["benchmark_case_suite_summary"]
        scientific_evaluation_benchmark_summary = build_scientific_evaluation_benchmark_summary(
            topic=topic,
            research_state=research_state,
            claim_graph=claim_graph,
        )
        research_state["benchmark_case_suite_summary"] = {
            **research_state["benchmark_case_suite_summary"],
            "benchmark_version": "current",
            "scientific_evaluation_benchmark_summary": scientific_evaluation_benchmark_summary,
            "scientific_evaluation_tasks": scientific_evaluation_benchmark_summary.get("tasks", []),
            "scientific_evaluation_benchmark_state": scientific_evaluation_benchmark_summary.get("benchmark_state", ""),
            "average_task_quality_score": scientific_evaluation_benchmark_summary.get("average_quality_score", 0),
        }
        claim_graph["benchmark_case_suite_summary"] = research_state["benchmark_case_suite_summary"]
        research_state["scientific_evaluation_system_summary"] = ScientificWorkflow._derive_scientific_evaluation_system_summary(
            topic=topic,
            benchmark_harness_summary=research_state.get("benchmark_harness_summary", {}),
            benchmark_case_suite_summary=research_state.get("benchmark_case_suite_summary", {}),
            kaivu_evaluation_harness_summary=research_state.get("kaivu_evaluation_harness_summary", {}),
            evaluation_summary=research_state.get("evaluation_summary", {}),
        )
        claim_graph["scientific_evaluation_system_summary"] = research_state["scientific_evaluation_system_summary"]
        research_state["workflow_control_summary"] = ScientificWorkflow._derive_workflow_control_summary(
            topic=topic,
            current_stage=str(research_state.get("current_stage", "")),
            recommended_next_stage=str(research_state.get("recommended_next_stage", "")),
            claim_graph=claim_graph,
            systematic_review_summary=research_state.get("systematic_review_summary", {}),
            evidence_review_summary=research_state.get("evidence_review_summary", {}),
            hypothesis_system_summary=research_state.get("hypothesis_system_summary", {}),
            scientific_decision_summary=research_state.get("scientific_decision_summary", {}),
            experiment_execution_loop_summary=research_state.get("experiment_execution_loop_summary", {}),
            research_campaign_plan_summary=research_state.get("research_campaign_plan_summary", {}),
            scientific_evaluation_system_summary=research_state.get("scientific_evaluation_system_summary", {}),
            stage_validation={
                "allowed_next_stages": research_state.get("allowed_next_stages", []),
                "missing_prerequisites": research_state.get("missing_prerequisites", []),
                "invalid_transitions": research_state.get("invalid_transitions", []),
            },
        )
        claim_graph["workflow_control_summary"] = research_state["workflow_control_summary"]
        research_state["scientific_error_taxonomy_summary"] = build_scientific_error_taxonomy_summary(
            topic=topic,
            research_state=research_state,
            claim_graph=claim_graph,
        )
        claim_graph["scientific_error_taxonomy_summary"] = research_state["scientific_error_taxonomy_summary"]
        research_state["scientific_release_gate_summary"] = build_scientific_release_gate_summary(
            topic=topic,
            research_state=research_state,
        )
        claim_graph["scientific_release_gate_summary"] = research_state["scientific_release_gate_summary"]
        reliability_state = {
            key: value
            for key, value in research_state.items()
            if key.endswith("_summary") or key in {"topic", "current_stage", "recommended_next_stage", "blockers"}
        }
        research_state["scientific_kernel_state_summary"] = build_scientific_kernel_state_summary(
            topic=topic,
            project_id=project_id,
            summaries=reliability_state,
        )
        claim_graph["scientific_kernel_state_summary"] = research_state["scientific_kernel_state_summary"]
        self._capture_negative_result_memories(steps)
        self._sync_hypothesis_memories(claim_graph)
        self._apply_conflict_memory_updates(steps, claim_graph)
        self._sync_project_distill_memory(research_state)
        self._sync_execution_cycle_memories(steps, research_state)
        self._sync_belief_update_memories(research_state)
        self._sync_research_strategy_memories(research_state)
        self._sync_agent_stance_memories(research_state)
        self._sync_literature_workspace(topic, steps, research_state)
        self._sync_graph_memory_distill(research_state)
        ledger_events = build_workflow_events(
            topic=topic,
            project_id=project_id,
            user_id=str(self.collaboration_context.get("user_id", "")),
            group_id=str(self.collaboration_context.get("group_id", "")),
            run_manifest=run_manifest,
            claim_graph=claim_graph,
            research_state=research_state,
        )
        ledger_path = self.event_ledger.append_many(ledger_events)
        event_ledger_summary = self.event_ledger.summarize(project_id=project_id, topic=topic)
        event_ledger_summary["events_written"] = len(ledger_events)
        event_ledger_summary["ledger_path"] = str(ledger_path) if ledger_path is not None else ""
        research_state["event_ledger_summary"] = event_ledger_summary
        claim_graph["event_ledger_summary"] = event_ledger_summary
        rendered = render_markdown_report(
            topic,
            [
                {
                    "profile_name": step.profile_name,
                    "raw_output": step.raw_output,
                    "parsed_output": step.parsed_output,
                    "model_meta": step.model_meta,
                }
                for step in steps
            ],
            citations=self._collect_citations(steps),
            execution_records=execution_records,
            usage_summary=usage_summary,
            claim_graph=claim_graph,
            research_state=research_state,
            run_manifest=run_manifest,
        )
        saved_path = write_markdown_report(self.report_path, rendered)
        run_manifest["artifacts"] = [
            (
                {
                    **item,
                    "path": str(saved_path),
                    "exists": True,
                }
                if item.get("kind") == "report"
                else item
            )
            for item in run_manifest.get("artifacts", [])
        ]
        return WorkflowRunResult(
            topic=topic,
            steps=steps,
            claim_graph=claim_graph,
            research_state=research_state,
            run_manifest=run_manifest,
            final_report=rendered,
            report_path=str(saved_path),
        )

    async def _run_dynamic_workflow(
        self, topic: str, tools: ToolRegistry, steps: list[WorkflowStepResult]
    ) -> None:
        remaining = [
            "data_curator",
            "hypothesis_generator",
            "experiment_designer",
            "experiment_economist",
            "run_manager",
            "quality_control_reviewer",
            "result_interpreter",
            "belief_updater",
            "data_analyst",
            "critic",
            "lab_meeting_moderator",
            "safety_ethics_reviewer",
            "conflict_resolver",
        ]
        planner_step = await self._run_profile(
            topic, DEFAULT_SCIENCE_PROFILES["research_planner"], tools, steps
        )
        steps.append(planner_step)
        await self._apply_mid_run_control(topic, tools, steps, remaining, trigger_step=planner_step)
        if self._mid_run_control_should_stop():
            await self._run_controlled_tail(topic, tools, steps)
            return
        literature_step = await self._run_profile(
            topic, DEFAULT_SCIENCE_PROFILES["literature_reviewer"], tools, steps
        )
        steps.append(literature_step)
        await self._apply_mid_run_control(topic, tools, steps, remaining, trigger_step=literature_step)
        if self._mid_run_control_should_stop():
            await self._run_controlled_tail(topic, tools, steps)
            return

        topic_lower = topic.lower()
        if any(
            token in topic_lower
            for token in ["csv", "xlsx", "table", "dataset", "data", "file"]
        ):
            initial_profiles = [
                DEFAULT_SCIENCE_PROFILES[name]
                for name in ["data_curator", "data_analyst"]
                if name in remaining
            ]
            for step in await self._run_profiles_batch(topic, initial_profiles, tools, steps):
                steps.append(step)
                if step.profile_name in remaining:
                    remaining.remove(step.profile_name)
                await self._apply_mid_run_control(topic, tools, steps, remaining, trigger_step=step)
                if self._mid_run_control_should_stop():
                    await self._run_controlled_tail(topic, tools, steps)
                    return

        while remaining:
            blocked_profiles = self._mid_run_control_blocked_profiles()
            if blocked_profiles:
                remaining[:] = [name for name in remaining if name not in blocked_profiles]
                if not remaining:
                    break
            next_names = await self._route_next_profiles(topic, steps, remaining)
            if not next_names:
                break
            batch_profiles = [
                DEFAULT_SCIENCE_PROFILES[name] for name in next_names if name in remaining
            ]
            if not batch_profiles:
                break
            for step in await self._run_profiles_batch(topic, batch_profiles, tools, steps):
                steps.append(step)
                if step.profile_name in remaining:
                    remaining.remove(step.profile_name)
                await self._apply_mid_run_control(topic, tools, steps, remaining, trigger_step=step)
                if self._mid_run_control_should_stop():
                    await self._run_controlled_tail(topic, tools, steps)
                    return

        termination_strategy = ScientificWorkflow._derive_routing_termination_strategy(steps)
        blocked_after_routing = {
            str(item).strip()
            for item in termination_strategy.get("blocked_specialists", [])
            if str(item).strip()
        }
        for fallback in [
            "hypothesis_generator",
            "experiment_designer",
            "experiment_economist",
            "run_manager",
            "quality_control_reviewer",
            "result_interpreter",
            "belief_updater",
            "critic",
            "lab_meeting_moderator",
            "safety_ethics_reviewer",
            "conflict_resolver",
            "data_curator",
            "data_analyst",
        ]:
            if fallback in remaining and fallback not in blocked_after_routing:
                step = await self._run_profile(topic, DEFAULT_SCIENCE_PROFILES[fallback], tools, steps)
                steps.append(step)
                remaining.remove(fallback)
                await self._apply_mid_run_control(topic, tools, steps, remaining, trigger_step=step)
                if self._mid_run_control_should_stop():
                    await self._run_controlled_tail(topic, tools, steps)
                    return
        if self._needs_conflict_resolution(steps) and "conflict_resolver" not in [step.profile_name for step in steps]:
            step = await self._run_profile(
                topic, DEFAULT_SCIENCE_PROFILES["conflict_resolver"], tools, steps
            )
            steps.append(step)
        await self._run_controlled_tail(topic, tools, steps)

    async def _run_controlled_tail(
        self,
        topic: str,
        tools: ToolRegistry,
        steps: list[WorkflowStepResult],
    ) -> None:
        completed = {step.profile_name for step in steps}
        for tail in ["coordinator", "report_writer"]:
            if tail in completed:
                continue
            step = await self._run_profile(
                topic, DEFAULT_SCIENCE_PROFILES[tail], tools, steps
            )
            steps.append(step)

    async def _apply_mid_run_control(
        self,
        topic: str,
        tools: ToolRegistry,
        steps: list[WorkflowStepResult],
        remaining: list[str],
        *,
        trigger_step: WorkflowStepResult,
    ) -> None:
        control = self._mid_run_control_decision(trigger_step=trigger_step, steps=steps, remaining=remaining)
        self._record_mid_run_control(control)
        self._emit_runtime_event(
            "workflow.mid_run_control.evaluated",
            actor="mid_run_controller",
            payload=control,
        )
        self._apply_mid_run_control_directives(control)
        if control.get("action") != "insert_specialists":
            return
        next_names = [
            str(name).strip()
            for name in control.get("insert_specialists", [])
            if str(name).strip() in remaining
        ][:2]
        if not next_names:
            return
        for name in next_names:
            step = await self._run_profile(topic, DEFAULT_SCIENCE_PROFILES[name], tools, steps)
            steps.append(step)
            if name in remaining:
                remaining.remove(name)
            inserted_control = self._mid_run_control_decision(trigger_step=step, steps=steps, remaining=remaining)
            self._record_mid_run_control(inserted_control)
            self._emit_runtime_event(
                "workflow.mid_run_control.evaluated",
                actor="mid_run_controller",
                payload=inserted_control,
            )

    def _record_mid_run_control(self, control: dict[str, Any]) -> None:
        decisions = self.collaboration_context.setdefault("_mid_run_control_decisions", [])
        if isinstance(decisions, list):
            decisions.append(control)

    def _apply_mid_run_control_directives(self, control: dict[str, Any]) -> None:
        directives = control.get("control_directives", {})
        if not isinstance(directives, dict):
            return
        state = self.collaboration_context.setdefault(
            "_mid_run_control_state",
            {
                "paused_workstreams": [],
                "required_evidence_repairs": [],
                "hypothesis_rollbacks": [],
                "scheduler_overrides": [],
                "terminated_routes": [],
                "blocked_profiles": [],
                "stop_reasons": [],
            },
        )
        if not isinstance(state, dict):
            return

        def extend_unique(key: str, values: list[Any]) -> None:
            bucket = state.setdefault(key, [])
            if not isinstance(bucket, list):
                return
            for value in values:
                if value and value not in bucket:
                    bucket.append(value)

        extend_unique("paused_workstreams", directives.get("pause_workstreams", []) if isinstance(directives.get("pause_workstreams", []), list) else [])
        extend_unique("required_evidence_repairs", directives.get("require_evidence", []) if isinstance(directives.get("require_evidence", []), list) else [])
        extend_unique("hypothesis_rollbacks", directives.get("rollback_hypotheses", []) if isinstance(directives.get("rollback_hypotheses", []), list) else [])
        extend_unique("scheduler_overrides", directives.get("scheduler_overrides", []) if isinstance(directives.get("scheduler_overrides", []), list) else [])
        extend_unique("terminated_routes", directives.get("terminate_routes", []) if isinstance(directives.get("terminate_routes", []), list) else [])
        extend_unique("blocked_profiles", directives.get("blocked_profiles", []) if isinstance(directives.get("blocked_profiles", []), list) else [])
        if directives.get("stop_routing"):
            state["stop_routing"] = True
            extend_unique("stop_reasons", [str(reason) for reason in control.get("reasons", []) if str(reason).strip()])

    def _mid_run_control_should_stop(self) -> bool:
        state = self.collaboration_context.get("_mid_run_control_state", {})
        return isinstance(state, dict) and bool(state.get("stop_routing"))

    def _mid_run_control_blocked_profiles(self) -> set[str]:
        state = self.collaboration_context.get("_mid_run_control_state", {})
        if not isinstance(state, dict):
            return set()
        blocked = state.get("blocked_profiles", [])
        if not isinstance(blocked, list):
            return set()
        return {str(name).strip() for name in blocked if str(name).strip()}

    def _mid_run_control_summary(self) -> dict[str, Any]:
        decisions = self.collaboration_context.get("_mid_run_control_decisions", [])
        if not isinstance(decisions, list):
            decisions = []
        state = self.collaboration_context.get("_mid_run_control_state", {})
        if not isinstance(state, dict):
            state = {}
        inserted_count = len(
            [
                item
                for item in decisions
                if isinstance(item, dict) and item.get("action") == "insert_specialists"
            ]
        )
        hard_control_count = len(
            [
                item
                for item in decisions
                if isinstance(item, dict)
                and item.get("action")
                in {"pause_workflow", "require_evidence", "rollback_hypothesis", "reorder_experiments", "terminate_route"}
            ]
        )
        return {
            "decision_count": len(decisions),
            "inserted_count": inserted_count,
            "hard_control_count": hard_control_count,
            "stop_routing": bool(state.get("stop_routing")),
            "paused_workstreams": state.get("paused_workstreams", []) if isinstance(state.get("paused_workstreams", []), list) else [],
            "required_evidence_repairs": state.get("required_evidence_repairs", []) if isinstance(state.get("required_evidence_repairs", []), list) else [],
            "hypothesis_rollbacks": state.get("hypothesis_rollbacks", []) if isinstance(state.get("hypothesis_rollbacks", []), list) else [],
            "scheduler_overrides": state.get("scheduler_overrides", []) if isinstance(state.get("scheduler_overrides", []), list) else [],
            "terminated_routes": state.get("terminated_routes", []) if isinstance(state.get("terminated_routes", []), list) else [],
            "blocked_profiles": state.get("blocked_profiles", []) if isinstance(state.get("blocked_profiles", []), list) else [],
            "stop_reasons": state.get("stop_reasons", []) if isinstance(state.get("stop_reasons", []), list) else [],
            "decisions": decisions[-50:],
        }

    @staticmethod
    def _mid_run_control_decision(
        *,
        trigger_step: WorkflowStepResult,
        steps: list[WorkflowStepResult],
        remaining: list[str],
    ) -> dict[str, Any]:
        parsed = trigger_step.parsed_output if isinstance(trigger_step.parsed_output, dict) else {}
        reasons: list[str] = []
        preferred: list[str] = []
        directives: dict[str, Any] = {
            "pause_workstreams": [],
            "require_evidence": [],
            "rollback_hypotheses": [],
            "scheduler_overrides": [],
            "terminate_routes": [],
            "blocked_profiles": [],
            "stop_routing": False,
        }
        if "schema_parse_error" in parsed or parsed.get("_repair_note"):
            reasons.append("structured output was repaired or failed parsing")
            preferred.extend(["critic", "coordinator"])
        if str(parsed.get("confidence", "")).strip().lower() == "low":
            reasons.append("agent reported low confidence")
            preferred.extend(["critic", "lab_meeting_moderator"])
        if trigger_step.profile_name == "literature_reviewer":
            systematic = parsed.get("systematic_review", {}) if isinstance(parsed.get("systematic_review", {}), dict) else {}
            claims = parsed.get("claims", []) if isinstance(parsed.get("claims", []), list) else []
            evidence = parsed.get("evidence", []) if isinstance(parsed.get("evidence", []), list) else []
            if systematic.get("review_protocol_gaps") or (claims and not evidence):
                reasons.append("literature review has protocol gaps or unsupported claims")
                preferred.extend(["critic", "hypothesis_generator"])
                directives["pause_workstreams"].append("downstream_experiment_execution")
                directives["require_evidence"].append("repair literature protocol gaps before expensive design or execution")
                directives["blocked_profiles"].extend(["experiment_designer", "run_manager"])
                directives["scheduler_overrides"].append(
                    {
                        "override": "prioritize_evidence_repair",
                        "reason": "literature evidence is not decision-ready",
                    }
                )
        if trigger_step.profile_name == "hypothesis_generator":
            validations = parsed.get("hypothesis_validations", []) if isinstance(parsed.get("hypothesis_validations", []), list) else []
            gates = parsed.get("hypothesis_gates", []) if isinstance(parsed.get("hypothesis_gates", []), list) else []
            if any(
                isinstance(item, dict)
                and (
                    float(item.get("falsifiability_score", 1) or 0) < 0.5
                    or float(item.get("testability_score", 1) or 0) < 0.5
                )
                for item in validations
            ):
                reasons.append("hypothesis validator found weak falsifiability or testability")
                preferred.extend(["critic", "experiment_designer"])
                directives["rollback_hypotheses"].extend(
                    [
                        str(item.get("hypothesis_id", "")).strip()
                        for item in validations
                        if isinstance(item, dict)
                        and str(item.get("hypothesis_id", "")).strip()
                        and (
                            float(item.get("falsifiability_score", 1) or 0) < 0.5
                            or float(item.get("testability_score", 1) or 0) < 0.5
                        )
                    ]
                )
                directives["scheduler_overrides"].append(
                    {
                        "override": "design_discriminative_or_falsification_test_first",
                        "reason": "weak validators should be repaired before portfolio expansion",
                    }
                )
            if any(isinstance(item, dict) and str(item.get("gate_decision", "")).lower() in {"reject", "block"} for item in gates):
                reasons.append("hypothesis gate blocked a candidate")
                preferred.extend(["lab_meeting_moderator", "critic"])
                directives["terminate_routes"].extend(
                    [
                        str(item.get("hypothesis_id", "")).strip()
                        for item in gates
                        if isinstance(item, dict)
                        and str(item.get("hypothesis_id", "")).strip()
                        and str(item.get("gate_decision", "")).lower() in {"reject", "block"}
                    ]
                )
        if trigger_step.profile_name == "experiment_designer":
            experiment_spec = parsed.get("experiment_specification", {}) if isinstance(parsed.get("experiment_specification", {}), dict) else {}
            controls = experiment_spec.get("controls", []) if isinstance(experiment_spec.get("controls", []), list) else []
            quality_gates = experiment_spec.get("quality_control_checks", []) if isinstance(experiment_spec.get("quality_control_checks", []), list) else []
            if not controls or not quality_gates:
                reasons.append("experiment design is missing controls or quality gates")
                preferred.extend(["quality_control_reviewer", "safety_ethics_reviewer"])
                directives["pause_workstreams"].append("experiment_execution")
                directives["blocked_profiles"].append("run_manager")
                directives["scheduler_overrides"].append(
                    {
                        "override": "insert_quality_gate_repair_before_execution",
                        "reason": "controls or quality gates are missing",
                    }
                )
        if trigger_step.profile_name == "run_manager":
            run = parsed.get("experiment_run", {}) if isinstance(parsed.get("experiment_run", {}), dict) else {}
            if str(run.get("status", "")).lower() in {"failed", "error", "blocked"}:
                reasons.append("experiment run failed or was blocked")
                preferred.extend(["quality_control_reviewer", "belief_updater"])
                directives["pause_workstreams"].append("experiment_execution")
                directives["scheduler_overrides"].append(
                    {
                        "override": "quarantine_failed_run_and_schedule_repair",
                        "run_id": str(run.get("run_id", "")).strip(),
                    }
                )
        if trigger_step.profile_name == "quality_control_reviewer":
            review = parsed.get("quality_control_review", {}) if isinstance(parsed.get("quality_control_review", {}), dict) else {}
            if str(review.get("quality_control_status", "")).lower() in {"failed", "warning"} or review.get("repeat_required"):
                reasons.append("quality control requires repeat or repair")
                preferred.extend(["result_interpreter", "experiment_designer"])
                directives["pause_workstreams"].append("belief_update")
                directives["scheduler_overrides"].append(
                    {
                        "override": "repeat_or_repair_before_interpretation",
                        "review_id": str(review.get("review_id", "")).strip(),
                    }
                )
        negative_results = parsed.get("negative_results", []) if isinstance(parsed.get("negative_results", []), list) else []
        if negative_results:
            reasons.append("negative results appeared mid-run")
            preferred.extend(["belief_updater", "lab_meeting_moderator", "critic"])
            affected = [
                str(hypothesis_id).strip()
                for item in negative_results
                if isinstance(item, dict)
                for hypothesis_id in (
                    item.get("affected_hypothesis_ids", [])
                    if isinstance(item.get("affected_hypothesis_ids", []), list)
                    else []
                )
                if str(hypothesis_id).strip()
            ]
            directives["rollback_hypotheses"].extend(affected)
            directives["scheduler_overrides"].append(
                {
                    "override": "cool_or_redesign_negative_route",
                    "affected_hypothesis_ids": affected,
                }
            )
        repeated_repairs = len(
            [
                step
                for step in steps
                if isinstance(step.parsed_output, dict)
                and ("schema_parse_error" in step.parsed_output or step.parsed_output.get("_repair_note"))
            ]
        )
        if repeated_repairs >= 3:
            reasons.append("too many repaired or failed structured outputs in one run")
            preferred.extend(["coordinator", "report_writer"])
            directives["pause_workstreams"].append("workflow_reliability")
            directives["stop_routing"] = True
        if directives["terminate_routes"]:
            directives["stop_routing"] = True
        available = [name for name in dict.fromkeys(preferred) if name in remaining]
        hard_action = "continue"
        if directives["terminate_routes"]:
            hard_action = "terminate_route"
        elif directives["stop_routing"] or directives["pause_workstreams"]:
            hard_action = "pause_workflow"
        elif directives["require_evidence"]:
            hard_action = "require_evidence"
        elif directives["rollback_hypotheses"]:
            hard_action = "rollback_hypothesis"
        elif directives["scheduler_overrides"]:
            hard_action = "reorder_experiments"
        return {
            "trigger_profile": trigger_step.profile_name,
            "action": "insert_specialists" if available and reasons else hard_action,
            "insert_specialists": available[:2],
            "reasons": reasons[:8],
            "control_directives": directives,
            "remaining_count": len(remaining),
            "completed_count": len(steps),
        }

    async def _run_profile(
        self,
        topic: str,
        profile: SpecialistProfile,
        tools: ToolRegistry,
        prior_steps: list[WorkflowStepResult],
    ) -> WorkflowStepResult:
        if self._is_profile_blocked_by_mid_run_control(profile.name):
            step = self._blocked_profile_step(profile.name)
            self._emit_runtime_event(
                "specialist.step.skipped",
                actor=profile.name,
                payload=self._runtime_step_payload(step, len(prior_steps) + 1),
            )
            return step
        self._emit_runtime_event(
            "specialist.step.started",
            actor=profile.name,
            payload={
                "profile_name": profile.name,
                "prior_step_count": len(prior_steps),
                "requested_tools": profile.tool_names,
            },
        )
        resolved_model_config = self.model_registry.resolve_for_agent(
            profile.name,
            profile.model_config,
        )
        skill_selection = (
            self.skill_runtime.select_for_query(topic)
            if self.skill_runtime is not None
            else None
        )
        filtered_tools = tools.subset(profile.tool_names)
        if skill_selection is not None and skill_selection.allowed_tools:
            profile_allowed = set(tool.name for tool in filtered_tools.all())
            runtime_allowed = set(skill_selection.allowed_tools)
            keep = sorted(profile_allowed.intersection(runtime_allowed))
            if keep:
                filtered_tools = filtered_tools.subset(keep)

        backend: ModelBackend = self.model_registry.build_backend(
            resolved_model_config,
            allow_web_search_override=profile.allow_web_search,
        )
        subagent = await self.subagent_runtime.run_subagent(
            SubagentSpec(
                name=profile.name,
                model=backend,
                tools=filtered_tools,
                    system_prompt=profile.system_prompt,
                    task_prompt=self._build_prompt(topic, profile, prior_steps),
                    skill_prompt=skill_selection.prompt_block if skill_selection is not None else "",
                    workflow_state=self._build_workflow_state(topic, prior_steps),
                schema_instruction=schema_instruction(profile.output_schema),
                mcp_instructions=self._build_mcp_instructions(topic),
                safety_policy=(
                    "Distinguish evidence from speculation. Do not overstate causal claims. "
                    "Flag uncertainty explicitly."
                ),
                memory_namespace=profile.name,
                collaboration_context=self.collaboration_context,
            )
        )
        parsed, used_model_config = await self._parse_and_maybe_escalate(
            topic=topic,
            profile=profile,
            tools=filtered_tools,
            prior_steps=prior_steps,
            raw_text=subagent.result.final_text,
            initial_model_config=resolved_model_config,
            initial_state=subagent.result.state,
        )
        step = WorkflowStepResult(
            profile_name=profile.name,
            raw_output=parsed.pop("_raw_output", subagent.result.final_text),
            parsed_output=parsed,
            state=parsed.pop("_state", subagent.result.state),
            model_meta=self._build_model_meta(used_model_config),
        )
        self._emit_runtime_event(
            "specialist.step.completed",
            actor=profile.name,
            payload=self._runtime_step_payload(step, len(prior_steps) + 1),
        )
        return step

    async def _run_profiles_batch(
        self,
        topic: str,
        profiles: list[SpecialistProfile],
        tools: ToolRegistry,
        prior_steps: list[WorkflowStepResult],
    ) -> list[WorkflowStepResult]:
        if not profiles:
            return []
        output_steps: list[WorkflowStepResult] = []
        runnable_profiles: list[SpecialistProfile] = []
        for profile in profiles:
            if self._is_profile_blocked_by_mid_run_control(profile.name):
                step = self._blocked_profile_step(profile.name)
                self._emit_runtime_event(
                    "specialist.step.skipped",
                    actor=profile.name,
                    payload=self._runtime_step_payload(step, len(prior_steps) + len(output_steps) + 1),
                )
                output_steps.append(step)
            else:
                runnable_profiles.append(profile)
        profiles = runnable_profiles
        if not profiles:
            return output_steps
        specs: list[tuple[SpecialistProfile, SubagentSpec]] = []
        workflow_state = self._build_workflow_state(topic, prior_steps)
        mcp_instructions = self._build_mcp_instructions(topic)
        for profile in profiles:
            self._emit_runtime_event(
                "specialist.step.started",
                actor=profile.name,
                payload={
                    "profile_name": profile.name,
                    "prior_step_count": len(prior_steps),
                    "requested_tools": profile.tool_names,
                    "batched": True,
                },
            )
            resolved_model_config = self.model_registry.resolve_for_agent(
                profile.name,
                profile.model_config,
            )
            skill_selection = (
                self.skill_runtime.select_for_query(topic)
                if self.skill_runtime is not None
                else None
            )
            filtered_tools = tools.subset(profile.tool_names)
            if skill_selection is not None and skill_selection.allowed_tools:
                profile_allowed = set(tool.name for tool in filtered_tools.all())
                runtime_allowed = set(skill_selection.allowed_tools)
                keep = sorted(profile_allowed.intersection(runtime_allowed))
                if keep:
                    filtered_tools = filtered_tools.subset(keep)
            backend: ModelBackend = self.model_registry.build_backend(
                resolved_model_config,
                allow_web_search_override=profile.allow_web_search,
            )
            specs.append(
                (
                    profile,
                    resolved_model_config,
                    SubagentSpec(
                        name=profile.name,
                        model=backend,
                        tools=filtered_tools,
                        system_prompt=profile.system_prompt,
                        task_prompt=self._build_prompt(topic, profile, prior_steps),
                        skill_prompt=(
                            skill_selection.prompt_block if skill_selection is not None else ""
                        ),
                        workflow_state=workflow_state,
                        schema_instruction=schema_instruction(profile.output_schema),
                        mcp_instructions=mcp_instructions,
                        safety_policy=(
                            "Distinguish evidence from speculation. Do not overstate causal claims. "
                            "Flag uncertainty explicitly."
                        ),
                        memory_namespace=profile.name,
                        collaboration_context=self.collaboration_context,
                    ),
                )
            )
        results = await self.subagent_runtime.run_subagents([spec for _, _, spec in specs])
        for (profile, resolved_model_config, _), subagent in zip(specs, results, strict=False):
            parsed, used_model_config = await self._parse_and_maybe_escalate(
                topic=topic,
                profile=profile,
                tools=tools.subset(profile.tool_names),
                prior_steps=prior_steps,
                raw_text=subagent.result.final_text,
                initial_model_config=resolved_model_config,
                initial_state=subagent.result.state,
            )
            step = WorkflowStepResult(
                profile_name=profile.name,
                raw_output=parsed.pop("_raw_output", subagent.result.final_text),
                parsed_output=parsed,
                state=parsed.pop("_state", subagent.result.state),
                model_meta=self._build_model_meta(used_model_config),
            )
            self._emit_runtime_event(
                "specialist.step.completed",
                actor=profile.name,
                payload=self._runtime_step_payload(step, len(prior_steps) + len(output_steps) + 1),
            )
            output_steps.append(step)
        return output_steps

    def _is_profile_blocked_by_mid_run_control(self, profile_name: str) -> bool:
        if profile_name in {"coordinator", "report_writer", "critic", "lab_meeting_moderator"}:
            return False
        return profile_name in self._mid_run_control_blocked_profiles()

    def _blocked_profile_step(self, profile_name: str) -> WorkflowStepResult:
        state = AgentState(cwd=self.cwd)
        state.scratchpad["mid_run_control_skipped"] = True
        return WorkflowStepResult(
            profile_name=profile_name,
            raw_output="Skipped by mid-run controller.",
            parsed_output={
                "stage_assessment": {
                    "current_stage": "decide",
                    "next_stage": "report",
                    "stage_blockers": ["mid-run controller blocked this specialist"],
                },
                "mid_run_control_skip": {
                    "profile_name": profile_name,
                    "reason": "blocked by active mid-run control directives",
                },
            },
            state=state,
            model_meta={"model": "mid_run_controller", "provider": "workflow", "skipped": True},
        )

    def _emit_runtime_event(self, event_type: str, *, actor: str = "workflow", payload: dict[str, Any] | None = None) -> None:
        stream = getattr(self, "runtime_event_stream", None)
        if stream is None or not hasattr(stream, "emit"):
            return
        try:
            stream.emit(
                event_type,
                actor=actor,
                project_id=str(self.collaboration_context.get("project_id", "")),
                user_id=str(self.collaboration_context.get("user_id", "")),
                group_id=str(self.collaboration_context.get("group_id", "")),
                payload=payload or {},
            )
        except Exception:
            return

    @staticmethod
    def _runtime_step_payload(step: WorkflowStepResult, step_index: int) -> dict[str, Any]:
        usage = step.state.scratchpad.get("model_usage_totals", {})
        usage_totals = usage if isinstance(usage, dict) else {}
        return {
            "step_index": step_index,
            "profile_name": step.profile_name,
            "model_meta": step.model_meta,
            "parsed_keys": sorted(str(key) for key in step.parsed_output.keys()),
            "raw_output_preview": step.raw_output[:800],
            "usage_summary": {
                "input_tokens": int(usage_totals.get("input_tokens", 0) or 0),
                "output_tokens": int(usage_totals.get("output_tokens", 0) or 0),
                "total_tokens": int(usage_totals.get("total_tokens", 0) or 0),
                "estimated_cost_usd": round(float(usage_totals.get("estimated_cost_usd", 0.0) or 0.0), 6),
                "rounds": int(usage_totals.get("rounds", 0) or 0),
            },
            "tool_record_count": len(
                step.state.scratchpad.get("execution_records", [])
                if isinstance(step.state.scratchpad.get("execution_records", []), list)
                else []
            ),
        }

    @staticmethod
    def _compose_system_prompt(base_prompt: str, skill_prompt: str) -> str:
        if not skill_prompt:
            return base_prompt
        return f"{base_prompt}\n\n{skill_prompt}"

    def _build_workflow_state(self, topic: str, prior_steps: list[WorkflowStepResult]) -> str:
        graph_context = self._build_typed_graph_query_context(topic)
        if not prior_steps:
            lines = ["No prior specialist outputs yet."]
        else:
            lines = ["Prior specialist outputs:"]
            for step in prior_steps:
                lines.append(f"[{step.profile_name}]")
                lines.append(json.dumps(step.parsed_output, ensure_ascii=False, indent=2))
        if graph_context:
            lines.extend(["", "Typed research graph query context:", json.dumps(graph_context, ensure_ascii=False, indent=2)])
        stance_context = self._build_agent_stance_query_context(topic)
        if stance_context:
            lines.extend(
                [
                    "",
                    "Agent role memory and stance continuity context:",
                    json.dumps(stance_context, ensure_ascii=False, indent=2),
                    (
                        "Preserve role continuity: if your stance changes, state what new evidence, "
                        "failed attempt, or boundary condition caused the change."
                    ),
                ]
            )
        mid_run_control = self._mid_run_control_summary()
        has_active_control = bool(
            mid_run_control.get("decision_count")
            or mid_run_control.get("stop_routing")
            or mid_run_control.get("paused_workstreams")
            or mid_run_control.get("required_evidence_repairs")
            or mid_run_control.get("hypothesis_rollbacks")
            or mid_run_control.get("scheduler_overrides")
            or mid_run_control.get("terminated_routes")
            or mid_run_control.get("blocked_profiles")
        )
        if has_active_control:
            lines.extend(
                [
                    "",
                    "Active mid-run control directives:",
                    json.dumps(
                        {
                            "stop_routing": mid_run_control.get("stop_routing", False),
                            "paused_workstreams": mid_run_control.get("paused_workstreams", []),
                            "required_evidence_repairs": mid_run_control.get("required_evidence_repairs", []),
                            "hypothesis_rollbacks": mid_run_control.get("hypothesis_rollbacks", []),
                            "scheduler_overrides": mid_run_control.get("scheduler_overrides", []),
                            "terminated_routes": mid_run_control.get("terminated_routes", []),
                            "blocked_profiles": mid_run_control.get("blocked_profiles", []),
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    (
                        "Treat these directives as hard workflow constraints unless your role is explicitly "
                        "to review, repair, or document them."
                    ),
                ]
            )
        return "\n".join(lines)

    def _build_typed_graph_query_context(self, topic: str) -> dict[str, Any]:
        project_id = str(self.collaboration_context.get("project_id", "")).strip()
        if not project_id:
            return {}
        summary = self.graph_registry.summarize(project_id=project_id, topic=topic)
        nodes = self.graph_registry.load_nodes(project_id=project_id, topic=topic)
        edges = self.graph_registry.load_edges(project_id=project_id, topic=topic)
        facts = self.graph_registry.load_facts(project_id=project_id, topic=topic)
        replay = self.graph_registry.replay_facts(project_id=project_id, topic=topic)
        interesting_nodes = [
            item
            for item in nodes
            if isinstance(item, dict)
            and str(item.get("node_type", "")).strip()
            in {
                "hypothesis",
                "negative_result",
                "claim",
                "evidence",
                "specialist_reference",
                "dataset",
                "checkpoint",
                "spectrum",
                "notebook",
                "figure",
                "proof_note",
                "artifact",
            }
        ][:12]
        interesting_edges = [
            item
            for item in edges
            if isinstance(item, dict)
            and str(item.get("relation", "")).strip()
            in {"challenges", "supports", "tests", "updates", "supersedes", "consulted", "produced_by", "consumed_by"}
        ][:16]
        return {
            "summary": summary,
            "focus_nodes": interesting_nodes,
            "focus_edges": interesting_edges,
            "source_of_truth": "provenance_facts" if summary.get("graph_is_fact_backed") else "typed_graph_nodes_edges",
            "focus_facts": [
                item
                for item in facts
                if isinstance(item, dict)
                and str(item.get("fact_type", "")).strip()
                in {
                    "claim",
                    "hypothesis",
                    "evidence",
                    "negative_result",
                    "experiment",
                    "decision",
                    "agent_stance",
                }
            ][:20],
            "replay_summary": {
                "fact_count": replay.get("fact_count", 0),
                "claim_count": replay.get("claim_count", 0),
                "hypothesis_count": replay.get("hypothesis_count", 0),
                "evidence_count": replay.get("evidence_count", 0),
                "experiment_count": replay.get("experiment_count", 0),
            },
        }

    async def _apply_scheduler_llm_judgment(
        self,
        *,
        topic: str,
        research_state: dict[str, Any],
        claim_graph: dict[str, Any],
    ) -> None:
        scheduler = research_state.get("experiment_execution_loop_summary", {})
        campaign_plan = research_state.get("research_campaign_plan_summary", {})
        has_experiment_candidates = isinstance(scheduler, dict) and bool(scheduler.get("candidate_experiments"))
        route_selector = campaign_plan.get("route_selector_summary", {}) if isinstance(campaign_plan, dict) else {}
        has_route_candidates = isinstance(route_selector, dict) and bool(route_selector.get("route_nodes"))
        has_campaign_candidates = isinstance(campaign_plan, dict) and bool(campaign_plan.get("multi_step_route_plan"))
        if not (has_experiment_candidates or has_route_candidates or has_campaign_candidates):
            return
        policy = self.collaboration_context.get("scheduler_llm_judge", {})
        policy = policy if isinstance(policy, dict) else {}
        mode = str(policy.get("mode", "llm")).strip().lower()
        enabled = bool(policy.get("enabled", True))
        model_backend: ModelBackend | None = None
        if enabled and mode == "llm":
            try:
                model_backend = self.model_registry.build_backend(
                    AgentModelConfig(
                        model=str(policy.get("model", self.model_name)).strip() or self.model_name,
                        reasoning_effort=str(policy.get("reasoning_effort", "medium")).strip() or "medium",
                        max_output_tokens=int(policy.get("max_output_tokens", 1400) or 1400),
                        allow_web_search=bool(policy.get("allow_web_search", False)),
                        base_url=str(policy.get("base_url", self.base_url)).strip() or self.base_url,
                    ),
                    allow_web_search_override=bool(policy.get("allow_web_search", False)),
                )
            except Exception:
                model_backend = None
        judge = SchedulerLLMJudge(model_backend)
        research_context = self._build_scheduler_judge_context(research_state, claim_graph)
        updated_scheduler = scheduler
        if has_experiment_candidates:
            judgment = await judge.review_candidates(
                topic=topic,
                scheduler_type="experiment",
                scheduler_summary=scheduler,
                research_context=research_context,
                max_candidates=int(policy.get("max_candidates", 12) or 12),
            )
            updated_scheduler = apply_scheduler_judgment_to_summary(
                scheduler,
                judgment,
                adjustment_weight=float(policy.get("adjustment_weight", 1.0) or 1.0),
            )
            updated_scheduler["llm_judge_default"] = mode == "llm"
            research_state["experiment_execution_loop_summary"] = updated_scheduler
            if isinstance(research_state.get("scheduler_search_kernel_summary", {}), dict):
                research_state["scheduler_search_kernel_summary"] = build_scheduler_search_kernel_summary(
                    topic=topic,
                    experiment_execution_loop_summary=updated_scheduler,
                    value_of_information_summary=research_state.get("value_of_information_summary", {}),
                    uncertainty_ledger_summary=research_state.get("uncertainty_ledger_summary", {}),
                    research_campaign_plan_summary=campaign_plan if isinstance(campaign_plan, dict) else {},
                    route_selector_summary=route_selector_summary if isinstance(route_selector_summary, dict) else {},
                )
        route_selector_summary = {}
        campaign_plan = research_state.get("research_campaign_plan_summary", {})
        if isinstance(campaign_plan, dict):
            route_selector_summary = (
                campaign_plan.get("route_selector_summary", {})
                if isinstance(campaign_plan.get("route_selector_summary", {}), dict)
                else {}
            )
        if isinstance(campaign_plan, dict):
            route_selector_summary = build_research_route_scheduler_summary(
                topic=topic,
                research_state=research_state,
                claim_graph=claim_graph,
                scheduler_memory_context=research_state.get("scheduler_memory_context", {}),
            )
            route_judgment = await judge.review_candidates(
                topic=topic,
                scheduler_type="route",
                scheduler_summary=self._route_scheduler_as_judge_summary(route_selector_summary),
                research_context=research_context,
                max_candidates=int(policy.get("max_route_candidates", policy.get("max_candidates", 12)) or 12),
            )
            route_selector_summary = self._apply_route_judgment_to_summary(
                route_selector_summary,
                route_judgment,
                adjustment_weight=float(policy.get("adjustment_weight", 1.0) or 1.0),
                llm_default=mode == "llm",
            )
        if isinstance(research_state.get("research_campaign_plan_summary", {}), dict):
            research_state["research_campaign_plan_summary"] = build_research_campaign_plan_summary(
                topic=topic,
                research_state=research_state,
                claim_graph=claim_graph,
                scheduler_memory_context=research_state.get("scheduler_memory_context", {}),
                route_scheduler_summary=route_selector_summary,
            )
            campaign_judgment = await judge.review_candidates(
                topic=topic,
                scheduler_type="campaign",
                scheduler_summary=self._campaign_plan_as_judge_summary(research_state["research_campaign_plan_summary"]),
                research_context=research_context,
                max_candidates=int(policy.get("max_campaign_steps", policy.get("max_candidates", 12)) or 12),
            )
            research_state["research_campaign_plan_summary"] = self._apply_campaign_judgment_to_summary(
                research_state["research_campaign_plan_summary"],
                campaign_judgment,
                adjustment_weight=float(policy.get("adjustment_weight", 1.0) or 1.0),
                llm_default=mode == "llm",
            )
            if isinstance(research_state.get("scheduler_search_kernel_summary", {}), dict):
                research_state["scheduler_search_kernel_summary"] = build_scheduler_search_kernel_summary(
                    topic=topic,
                    experiment_execution_loop_summary=updated_scheduler
                    if isinstance(updated_scheduler, dict)
                    else research_state.get("experiment_execution_loop_summary", {}),
                    value_of_information_summary=research_state.get("value_of_information_summary", {}),
                    uncertainty_ledger_summary=research_state.get("uncertainty_ledger_summary", {}),
                    research_campaign_plan_summary=research_state["research_campaign_plan_summary"],
                    route_selector_summary=route_selector_summary,
                )

    @staticmethod
    def _route_scheduler_as_judge_summary(route_scheduler: dict[str, Any]) -> dict[str, Any]:
        candidates = []
        for node in route_scheduler.get("route_nodes", []) if isinstance(route_scheduler.get("route_nodes", []), list) else []:
            if not isinstance(node, dict):
                continue
            candidates.append(
                {
                    "experiment_id": str(node.get("node_id", "")).strip(),
                    "title": str(node.get("action", "")).strip(),
                    "experiment_type": "research_route",
                    "objective": str(node.get("selection_reason", "")).strip(),
                    "selection_score": node.get("selection_score", 0),
                    "information_gain_score": node.get("value_estimate", 0),
                    "risk_score": max(0.0, 1.0 - float(node.get("exploration_bonus", 0) or 0)),
                    "gate_state": "ready_to_schedule",
                }
            )
        return {
            **route_scheduler,
            "candidate_experiments": candidates,
            "top_experiment_id": route_scheduler.get("best_route_node_id", ""),
        }

    @staticmethod
    def _campaign_plan_as_judge_summary(campaign_plan: dict[str, Any]) -> dict[str, Any]:
        candidates = []
        for item in campaign_plan.get("multi_step_route_plan", []) if isinstance(campaign_plan.get("multi_step_route_plan", []), list) else []:
            if not isinstance(item, dict):
                continue
            step_id = f"campaign-step::{item.get('step_index', '')}::{item.get('route_action', '')}"
            candidates.append(
                {
                    "experiment_id": step_id,
                    "title": str(item.get("route_action", "")).strip(),
                    "experiment_type": "campaign_step",
                    "objective": str(item.get("goal", "")).strip(),
                    "selection_score": max(1.0, 8.0 - float(item.get("step_index", 1) or 1)),
                    "information_gain_score": max(1.0, 6.0 - float(item.get("step_index", 1) or 1) * 0.5),
                    "risk_score": 2.0 if item.get("route_action") in {"schedule_experiment", "run_reproducibility_check"} else 1.0,
                    "quality_gates": item.get("exit_criteria", []),
                    "gate_state": "ready_to_schedule",
                }
            )
        return {
            **campaign_plan,
            "candidate_experiments": candidates,
            "top_experiment_id": candidates[0]["experiment_id"] if candidates else "",
        }

    @staticmethod
    def _apply_route_judgment_to_summary(
        route_scheduler: dict[str, Any],
        judgment: dict[str, Any],
        *,
        adjustment_weight: float,
        llm_default: bool,
    ) -> dict[str, Any]:
        updated = dict(route_scheduler)
        ranked = {
            str(item.get("experiment_id", "")).strip(): item
            for item in judgment.get("ranked_candidates", [])
            if isinstance(item, dict) and str(item.get("experiment_id", "")).strip()
        } if isinstance(judgment.get("ranked_candidates", []), list) else {}
        blocked = {
            str(item.get("experiment_id", "")).strip()
            for item in judgment.get("blocked_candidates", [])
            if isinstance(item, dict) and str(item.get("experiment_id", "")).strip()
        } if isinstance(judgment.get("blocked_candidates", []), list) else set()
        nodes = []
        for node in route_scheduler.get("route_nodes", []) if isinstance(route_scheduler.get("route_nodes", []), list) else []:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("node_id", "")).strip()
            item = dict(node)
            review = ranked.get(node_id, {})
            base = _safe_float(item.get("selection_score", 0))
            adjustment = _safe_float(review.get("score_adjustment", 0)) * adjustment_weight
            item["llm_judgment"] = review
            item["llm_recommended_action"] = "block" if node_id in blocked else str(review.get("recommended_action", "schedule")).strip() or "schedule"
            item["llm_rationale"] = str(review.get("rationale", "")).strip()
            item["judge_adjusted_selection_score"] = round(base + adjustment, 3)
            nodes.append(item)
        nodes.sort(key=lambda item: _safe_float(item.get("judge_adjusted_selection_score", item.get("selection_score", 0))), reverse=True)
        best = next((item for item in nodes if item.get("llm_recommended_action") != "block"), nodes[0] if nodes else {})
        updated["route_nodes"] = nodes[:40]
        updated["best_action"] = str(best.get("action", ""))
        updated["best_route_node_id"] = str(best.get("node_id", ""))
        updated["best_selection_reason"] = str(best.get("llm_rationale", "")) or str(best.get("selection_reason", ""))
        updated["llm_judgment"] = judgment
        updated["llm_judge_state"] = str(judgment.get("judge_state", ""))
        updated["llm_judge_mode"] = str(judgment.get("judge_mode", ""))
        updated["llm_judge_default"] = llm_default
        return updated

    @staticmethod
    def _apply_campaign_judgment_to_summary(
        campaign_plan: dict[str, Any],
        judgment: dict[str, Any],
        *,
        adjustment_weight: float,
        llm_default: bool,
    ) -> dict[str, Any]:
        updated = dict(campaign_plan)
        ranked = {
            str(item.get("experiment_id", "")).strip(): item
            for item in judgment.get("ranked_candidates", [])
            if isinstance(item, dict) and str(item.get("experiment_id", "")).strip()
        } if isinstance(judgment.get("ranked_candidates", []), list) else {}
        steps = []
        for step in campaign_plan.get("multi_step_route_plan", []) if isinstance(campaign_plan.get("multi_step_route_plan", []), list) else []:
            if not isinstance(step, dict):
                continue
            step_id = f"campaign-step::{step.get('step_index', '')}::{step.get('route_action', '')}"
            review = ranked.get(step_id, {})
            item = dict(step)
            item["llm_judgment"] = review
            item["llm_recommended_action"] = str(review.get("recommended_action", "schedule")).strip() or "schedule"
            item["llm_rationale"] = str(review.get("rationale", "")).strip()
            item["judge_adjusted_priority"] = round(
                max(1.0, 8.0 - _safe_float(step.get("step_index", 1))) + _safe_float(review.get("score_adjustment", 0)) * adjustment_weight,
                3,
            )
            steps.append(item)
        next_step = next((item for item in steps if item.get("llm_recommended_action") != "block"), steps[0] if steps else {})
        updated["multi_step_route_plan"] = steps
        updated["next_campaign_decision"] = str(next_step.get("route_action", "")) or updated.get("next_campaign_decision", "")
        updated["llm_judgment"] = judgment
        updated["llm_judge_state"] = str(judgment.get("judge_state", ""))
        updated["llm_judge_mode"] = str(judgment.get("judge_mode", ""))
        updated["llm_judge_default"] = llm_default
        updated["scheduler_constraints"] = list(
            dict.fromkeys(
                ScientificWorkflow._strings(updated.get("scheduler_constraints", []))
                + [
                    f"LLM judge: {item.get('route_action', '')} -> {item.get('llm_recommended_action', '')}: {item.get('llm_rationale', '')}"
                    for item in steps[:5]
                    if str(item.get("llm_rationale", "")).strip()
                ]
            )
        )[:12]
        return updated

    def _build_scheduler_judge_context(
        self,
        research_state: dict[str, Any],
        claim_graph: dict[str, Any],
    ) -> dict[str, Any]:
        discipline_adapter = research_state.get("discipline_adapter_summary", {})
        bindings = discipline_adapter.get("bindings", []) if isinstance(discipline_adapter, dict) and isinstance(discipline_adapter.get("bindings", []), list) else []
        return {
            "current_stage": research_state.get("current_stage", ""),
            "recommended_next_stage": research_state.get("recommended_next_stage", ""),
            "active_hypotheses": claim_graph.get("hypotheses", []) if isinstance(claim_graph.get("hypotheses", []), list) else [],
            "mechanism_family_lifecycle_summary": research_state.get("mechanism_family_lifecycle_summary", {}),
            "evidence_conflicts": research_state.get("conflict_attribution", {}).get("groups", [])
            if isinstance(research_state.get("conflict_attribution", {}), dict)
            else [],
            "failed_attempts": research_state.get("negative_result_summary", [])
            + research_state.get("failure_intelligence_summary", {}).get("avoid_repeat_routes", [])
            if isinstance(research_state.get("negative_result_summary", []), list)
            and isinstance(research_state.get("failure_intelligence_summary", {}), dict)
            else [],
            "discipline_constraints": [
                str(rule).strip()
                for binding in bindings[:8]
                if isinstance(binding, dict)
                for rule in (
                    binding.get("scheduler_rules", [])
                    if isinstance(binding.get("scheduler_rules", []), list)
                    else []
                )
                if str(rule).strip()
            ],
            "budget_constraints": research_state.get("experiment_economics_summary", {}),
        }

    def _derive_scheduler_memory_context(
        self,
        *,
        topic: str,
        failure_intelligence_summary: dict[str, Any],
        agent_stance_continuity_summary: dict[str, Any],
        project_distill: dict[str, Any],
    ) -> dict[str, Any]:
        project_id = str(self.collaboration_context.get("project_id", "")).strip()
        group_id = str(self.collaboration_context.get("group_id", "")).strip()
        manager = self.subagent_runtime.memory_manager
        query = f"{topic} failed route experiment scheduler stance objection"
        memory_records = manager.search_memories(
            query,
            max_results=8,
            project_id=project_id or None,
            group_id=group_id or None,
            scopes=["project", "group", "agent"],
        )
        memory_signals = [
            {
                "title": record.title,
                "summary": record.summary,
                "scope": record.scope,
                "kind": record.kind,
                "tags": record.tags,
                "path": str(record.path),
            }
            for record in memory_records
        ]
        avoid_repeat_routes = (
            [
                str(item).strip()
                for item in failure_intelligence_summary.get("avoid_repeat_routes", [])
                if str(item).strip()
            ]
            if isinstance(failure_intelligence_summary.get("avoid_repeat_routes", []), list)
            else []
        )
        distill_failed_routes = (
            [
                str(item).strip()
                for item in project_distill.get("failed_routes", [])
                if str(item).strip()
            ]
            if isinstance(project_distill.get("failed_routes", []), list)
            else []
        )
        prior_program = (
            self.collaboration_context.get("research_program_context", {})
            if isinstance(self.collaboration_context.get("research_program_context", {}), dict)
            else {}
        )
        prior_failed_recall = (
            prior_program.get("failed_attempt_recall", {})
            if isinstance(prior_program.get("failed_attempt_recall", {}), dict)
            else {}
        )
        prior_repeat_warnings = [
            str(item.get("required_change", "") or item.get("negative_result_id", "")).strip()
            for item in prior_failed_recall.get("repeat_risk_warnings", [])
            if isinstance(item, dict)
            and str(item.get("required_change", "") or item.get("negative_result_id", "")).strip()
        ] if isinstance(prior_failed_recall.get("repeat_risk_warnings", []), list) else []
        failed_routes = list(
            dict.fromkeys(
                avoid_repeat_routes
                + distill_failed_routes
                + prior_repeat_warnings
                + [
                    str(item.get("title", "")).strip()
                    for item in memory_signals
                    if item.get("kind") == "warning"
                    or any(
                        tag in item.get("tags", [])
                        for tag in ["failed-route", "failed-attempt", "negative-result"]
                    )
                ]
            )
        )[:12]
        standing_objections = list(
            dict.fromkeys(
                [
                    str(item).strip()
                    for item in agent_stance_continuity_summary.get("standing_objections", [])
                    if str(item).strip()
                ] if isinstance(agent_stance_continuity_summary.get("standing_objections", []), list) else []
            )
        )[:12]
        successful_routes = [
            str(item.get("title", "")).strip()
            for item in memory_signals
            if "successful-route" in item.get("tags", []) or "validated" in item.get("tags", [])
        ][:8]
        return {
            "topic": topic,
            "project_id": project_id,
            "group_id": group_id,
            "memory_signal_count": len(memory_signals),
            "memory_signals": memory_signals,
            "failed_routes": failed_routes,
            "successful_routes": successful_routes,
            "standing_objections": standing_objections,
            "prior_research_program": prior_program,
            "policy": "scheduler must not repeat failed routes without changed conditions and must address standing objections",
        }

    def _build_agent_stance_query_context(self, topic: str) -> dict[str, Any]:
        project_id = str(self.collaboration_context.get("project_id", "")).strip()
        if not project_id:
            return {}
        facts = [
            item
            for item in self.graph_registry.load_facts(project_id=project_id, topic=topic)
            if isinstance(item, dict)
            and str(item.get("fact_type", "")).strip() == "agent_stance"
            and str(item.get("predicate", "")).strip() == "holds_position"
            and str(item.get("status", "active")).strip() == "active"
        ]
        if not facts:
            return {}
        by_agent: dict[str, list[dict[str, Any]]] = {}
        for fact in facts:
            agent = str(fact.get("produced_by", "")).strip()
            value = fact.get("value", {}) if isinstance(fact.get("value", {}), dict) else {}
            if not agent:
                agent = str(value.get("agent", "")).strip()
            if not agent:
                continue
            by_agent.setdefault(agent, []).append(fact)
        records: list[dict[str, Any]] = []
        for agent, agent_facts in sorted(by_agent.items()):
            agent_facts.sort(
                key=lambda item: str(
                    item.get("metadata", {}).get("recorded_at", "")
                    if isinstance(item.get("metadata", {}), dict)
                    else ""
                )
            )
            recent = agent_facts[-1]
            value = recent.get("value", {}) if isinstance(recent.get("value", {}), dict) else {}
            metadata = recent.get("metadata", {}) if isinstance(recent.get("metadata", {}), dict) else {}
            records.append(
                {
                    "agent": agent,
                    "last_position": str(
                        value.get("current_position", "")
                        or value.get("position", "")
                        or value.get("consensus_status", "")
                    ).strip(),
                    "stance_label": str(value.get("stance_label", "")).strip(),
                    "continuity_state": str(value.get("continuity_state", "")).strip(),
                    "change_type": str(value.get("change_type", "")).strip(),
                    "open_questions": value.get("open_questions", [])[:4]
                    if isinstance(value.get("open_questions", []), list)
                    else [],
                    "blocking_concerns": value.get("blocking_concerns", [])[:4]
                    if isinstance(value.get("blocking_concerns", []), list)
                    else [],
                    "source_refs": recent.get("source_refs", [])[:6]
                    if isinstance(recent.get("source_refs", []), list)
                    else [],
                    "recorded_at": str(metadata.get("recorded_at", "")).strip(),
                }
            )
        return {
            "project_id": project_id,
            "topic": topic,
            "prior_role_memory_count": len(records),
            "prior_stances": records[:12],
            "instruction": "Use these as role memory, not as settled truth; update stance only with explicit reason.",
        }

    async def _parse_result(
        self, profile: SpecialistProfile, raw_text: str
    ) -> dict[str, Any]:
        try:
            return parse_structured_output(raw_text, profile.output_schema)
        except Exception as exc:
            try:
                salvaged = salvage_structured_output(raw_text, profile.output_schema)
                salvaged["_repair_note"] = "locally-salvaged-from-partial-json"
                return salvaged
            except Exception:
                pass
            return await self._repair_structured_output(profile, raw_text, str(exc))

    async def _parse_and_maybe_escalate(
        self,
        *,
        topic: str,
        profile: SpecialistProfile,
        tools: ToolRegistry,
        prior_steps: list[WorkflowStepResult],
        raw_text: str,
        initial_model_config: AgentModelConfig,
        initial_state: AgentState,
    ) -> tuple[dict[str, Any], AgentModelConfig]:
        parsed = await self._parse_result(profile, raw_text)
        if not self._should_escalate_result(parsed):
            parsed["_raw_output"] = raw_text
            parsed["_state"] = initial_state
            return parsed, initial_model_config

        escalated_config = self.model_registry.escalate_config(initial_model_config)
        if escalated_config == initial_model_config:
            parsed["_raw_output"] = raw_text
            parsed["_state"] = initial_state
            return parsed, initial_model_config

        retry_backend = self.model_registry.build_backend(
            escalated_config,
            allow_web_search_override=profile.allow_web_search,
        )
        retry_subagent = await self.subagent_runtime.run_subagent(
            SubagentSpec(
                name=profile.name,
                model=retry_backend,
                tools=tools,
                system_prompt=profile.system_prompt,
                task_prompt=self._build_prompt(topic, profile, prior_steps),
                workflow_state=self._build_workflow_state(topic, prior_steps),
                schema_instruction=schema_instruction(profile.output_schema),
                mcp_instructions=self._build_mcp_instructions(topic),
                safety_policy=(
                    "Distinguish evidence from speculation. Do not overstate causal claims. "
                    "Flag uncertainty explicitly."
                ),
                memory_namespace=profile.name,
                collaboration_context=self.collaboration_context,
            )
        )
        reparsed = await self._parse_result(profile, retry_subagent.result.final_text)
        reparsed["_raw_output"] = retry_subagent.result.final_text
        reparsed["_state"] = retry_subagent.result.state
        reparsed["_escalated_from"] = self._build_model_meta(initial_model_config)
        return reparsed, escalated_config

    async def _repair_structured_output(
        self,
        profile: SpecialistProfile,
        raw_text: str,
        error_message: str,
    ) -> dict[str, Any]:
        current_error = error_message
        current_raw = raw_text
        for _ in range(self.repair_attempts):
            backend: ModelBackend = self.model_registry.build_backend(
                AgentModelConfig(
                    model=self.model_name,
                    reasoning_effort="medium",
                    max_output_tokens=1400,
                    allow_web_search=False,
                    base_url=self.base_url,
                ),
                allow_web_search_override=False,
            )
            repair_agent = ScientificAgent(
                model=backend,
                tools=ToolRegistry([]),
                cwd=self.cwd,
                system_prompt=(
                    "You repair scientific workflow outputs into valid JSON that matches a required schema."
                ),
                permission_policy=self.permission_policy,
                max_turns=3,
            )
            repair_prompt = repair_instruction(
                profile.output_schema, current_raw, current_error
            )
            repair_result = await repair_agent.run(repair_prompt)
            current_raw = repair_result.final_text
            try:
                repaired = parse_structured_output(current_raw, profile.output_schema)
                repaired["_repair_note"] = "auto-repaired-from-invalid-json"
                return repaired
            except Exception as exc:
                current_error = str(exc)
        return {"schema_parse_error": current_error, "raw_text": current_raw}

    @staticmethod
    def _collect_citations(steps: list[WorkflowStepResult]) -> list[dict[str, Any]]:
        citations: dict[str, dict[str, Any]] = {}
        for step in steps:
            library = step.state.scratchpad.get("citation_library", {})
            if not isinstance(library, dict):
                continue
            for key, value in library.items():
                if key not in citations:
                    citations[key] = value
                else:
                    merged = dict(citations[key])
                    for field, item in value.items():
                        if item not in (None, "", [], {}):
                            merged[field] = item
                    citations[key] = merged
        return list(citations.values())

    @staticmethod
    def _build_prompt(
        topic: str, profile: SpecialistProfile, prior_steps: list[WorkflowStepResult]
    ) -> str:
        sections = [
            f"Research topic: {topic}",
            f"Current role: {profile.name}",
            schema_instruction(profile.output_schema),
        ]
        if prior_steps:
            sections.append("Previous specialist outputs (JSON):")
            for step in prior_steps:
                sections.append(f"[{step.profile_name}]")
                sections.append(json.dumps(step.parsed_output, ensure_ascii=False, indent=2))
        return "\n\n".join(sections)

    def _build_mcp_instructions(self, topic: str) -> str:
        if self.mcp_registry is None:
            return ""
        return self.mcp_registry.build_prompt_instructions(topic)

    @staticmethod
    def _build_claim_graph(steps: list[WorkflowStepResult]) -> dict[str, Any]:
        claim_nodes: list[dict[str, Any]] = []
        evidence_nodes: list[dict[str, Any]] = []
        edges: list[dict[str, str]] = []
        hypothesis_nodes: list[dict[str, Any]] = []
        hypothesis_relations: list[dict[str, Any]] = []
        negative_result_nodes: list[dict[str, Any]] = []
        negative_result_links: list[dict[str, Any]] = []
        asset_registry: list[dict[str, Any]] = []
        claim_id_map: dict[tuple[str, str], str] = {}
        evidence_id_map: dict[tuple[str, str], str] = {}
        hypothesis_id_map: dict[tuple[str, str], str] = {}

        for step in steps:
            parsed = step.parsed_output
            raw_evidence = parsed.get("evidence", [])
            for index, item in enumerate(raw_evidence):
                if not isinstance(item, dict):
                    continue
                local_id = str(item.get("evidence_id") or f"e{index + 1}")
                global_id = f"{step.profile_name}::{local_id}"
                evidence_id_map[(step.profile_name, local_id)] = global_id
                node = dict(item)
                node["global_evidence_id"] = global_id
                node["profile_name"] = step.profile_name
                evidence_nodes.append(node)

            raw_claims = parsed.get("claims", [])
            for index, item in enumerate(raw_claims):
                if not isinstance(item, dict):
                    continue
                local_id = str(item.get("claim_id") or f"c{index + 1}")
                global_id = f"{step.profile_name}::{local_id}"
                claim_id_map[(step.profile_name, local_id)] = global_id
                node = dict(item)
                node["global_claim_id"] = global_id
                node["profile_name"] = step.profile_name
                claim_nodes.append(node)

            raw_hypotheses = parsed.get("hypotheses", [])
            for index, item in enumerate(raw_hypotheses):
                if not isinstance(item, dict):
                    continue
                local_id = str(item.get("hypothesis_id") or f"h{index + 1}")
                global_id = f"{step.profile_name}::{local_id}"
                hypothesis_id_map[(step.profile_name, local_id)] = global_id
                node = dict(item)
                node["global_hypothesis_id"] = global_id
                node["profile_name"] = step.profile_name
                hypothesis_nodes.append(node)

            raw_negative_results = parsed.get("negative_results", [])
            for index, item in enumerate(raw_negative_results):
                if not isinstance(item, dict):
                    continue
                global_id = f"{step.profile_name}::negative::{index + 1}"
                node = dict(item)
                node["global_negative_result_id"] = global_id
                node["profile_name"] = step.profile_name
                negative_result_nodes.append(node)

            raw_assets = parsed.get("asset_registry", []) or parsed.get("asset_registry_updates", [])
            for item in raw_assets if isinstance(raw_assets, list) else []:
                if not isinstance(item, dict):
                    continue
                node = dict(item)
                node["profile_name"] = step.profile_name
                asset_registry.append(node)

        for step in steps:
            raw_claims = step.parsed_output.get("claims", [])
            for index, item in enumerate(raw_claims):
                if not isinstance(item, dict):
                    continue
                local_id = str(item.get("claim_id") or f"c{index + 1}")
                source_id = claim_id_map.get((step.profile_name, local_id))
                if source_id is None:
                    continue
                for support in item.get("supports", []):
                    target_id = evidence_id_map.get((step.profile_name, str(support)))
                    if target_id is None:
                        for (_, evidence_local), mapped in evidence_id_map.items():
                            if evidence_local == str(support):
                                target_id = mapped
                                break
                    if target_id is not None:
                        edges.append(
                            {
                                "source": source_id,
                                "target": target_id,
                                "relation": "supported_by",
                            }
                        )

            raw_relations = step.parsed_output.get("hypothesis_relations", [])
            for item in raw_relations if isinstance(raw_relations, list) else []:
                if not isinstance(item, dict):
                    continue
                source_local = str(item.get("source_hypothesis_id", "")).strip()
                target_local = str(item.get("target_hypothesis_id", "")).strip()
                if not source_local or not target_local:
                    continue
                source_id = hypothesis_id_map.get((step.profile_name, source_local))
                target_id = hypothesis_id_map.get((step.profile_name, target_local))
                if source_id is None:
                    for (_, local_id), mapped in hypothesis_id_map.items():
                        if local_id == source_local:
                            source_id = mapped
                            break
                if target_id is None:
                    for (_, local_id), mapped in hypothesis_id_map.items():
                        if local_id == target_local:
                            target_id = mapped
                            break
                if source_id and target_id:
                    hypothesis_relations.append(
                        {
                            "source": source_id,
                            "target": target_id,
                            "relation": str(item.get("relation", "related_to")).strip() or "related_to",
                            "note": str(item.get("note", "")).strip(),
                            "profile_name": step.profile_name,
                        }
                    )

        negative_result_links = ScientificWorkflow._build_negative_result_links(
            steps,
            hypothesis_id_map,
            hypothesis_nodes,
            negative_result_nodes,
        )

        return {
            "claims": claim_nodes,
            "evidence": evidence_nodes,
            "hypotheses": hypothesis_nodes,
            "hypothesis_relations": hypothesis_relations,
            "negative_results": negative_result_nodes,
            "negative_result_links": negative_result_links,
            "asset_registry": asset_registry,
            "edges": edges,
        }

    def _derive_ai_research_workflow_summary(
        self,
        *,
        topic: str,
        literature_synthesis: dict[str, Any],
        systematic_review_summary: dict[str, Any],
        evidence_review_summary: dict[str, Any],
        discipline_adaptation_summary: dict[str, Any],
        project_distill: dict[str, Any],
        failure_intelligence_summary: dict[str, Any],
    ) -> dict[str, Any]:
        if not self._should_run_ai_research_workflow(topic, discipline_adaptation_summary):
            return {
                "workflow_state": "not_applicable",
                "reason": "input was not classified as artificial intelligence research",
            }
        try:
            request = AIResearchWorkflowInput(
                research_question=topic,
                dataset_path=_context_string(self.collaboration_context, "dataset_path"),
                target_column=_context_string(self.collaboration_context, "target_column"),
                id_column=_context_string(self.collaboration_context, "id_column"),
                task_type=self._infer_ai_task_type(topic),
                metric=_context_string(self.collaboration_context, "metric"),
                metric_direction=_context_string(self.collaboration_context, "metric_direction"),
                available_compute=_context_string(self.collaboration_context, "available_compute") or "local_cpu",
                candidate_models=_context_list(self.collaboration_context, "candidate_models"),
                project_id=str(self.collaboration_context.get("project_id", "")).strip(),
                output_dir=str(self.workspace_layout.state_root / "ai_research" / self._slugify_text(topic)),
                research_context={
                    "topic": topic,
                    "mode": str(self.collaboration_context.get("ai_research_mode", "guided")).strip() or "guided",
                    "discipline_adaptation_summary": discipline_adaptation_summary,
                    "evidence_review_summary": evidence_review_summary,
                    "project_distill": project_distill,
                    "failure_intelligence_summary": failure_intelligence_summary,
                },
                literature_context={
                    "literature_synthesis": literature_synthesis,
                    "systematic_review_summary": systematic_review_summary,
                },
                benchmark_context=_context_dict(self.collaboration_context, "benchmark_context"),
                repo_context=_context_dict(self.collaboration_context, "repo_context"),
                prior_memory_context={
                    "research_program_context": self.collaboration_context.get("research_program_context", {}),
                    "scheduler_memory_context": self.collaboration_context.get("scheduler_memory_context", {}),
                },
            )
            result = AIResearchWorkflow(cwd=self.cwd).run(request).to_dict()
            result["workflow_state"] = "planned"
            result["automation_mode"] = str(self.collaboration_context.get("ai_research_mode", "guided")).strip() or "guided"
            result["auto_trigger"] = True
            return result
        except Exception as exc:
            return {
                "workflow_state": "failed",
                "error": str(exc),
                "auto_trigger": True,
            }

    def _should_run_ai_research_workflow(
        self,
        topic: str,
        discipline_adaptation_summary: dict[str, Any],
    ) -> bool:
        mode = str(self.collaboration_context.get("ai_research_mode", "auto")).strip().lower()
        if mode in {"off", "disabled", "false", "0"}:
            return False
        if mode in {"on", "guided", "autonomous", "observe"}:
            return True
        explicit = str(self.collaboration_context.get("discipline", "")).strip().lower()
        task_type = str(self.collaboration_context.get("task_type", "")).strip().lower()
        primary = str(discipline_adaptation_summary.get("primary_discipline", "")).strip().lower()
        if explicit in {"ai", "artificial_intelligence", "machine_learning"}:
            return True
        if primary == "artificial_intelligence":
            return True
        if task_type in {
            "kaggle_competition",
            "llm_fine_tuning",
            "benchmark_reproduction",
            "model_comparison",
            "ablation_study",
        }:
            return True
        if any(key in self.collaboration_context for key in ("dataset_path", "target_column", "metric", "candidate_models")):
            return True
        lowered = topic.lower()
        return any(
            token in lowered
            for token in (
                "kaggle",
                "benchmark",
                "dataset",
                "classification",
                "regression",
                "training",
                "fine-tuning",
                "finetune",
                "llm",
                "machine learning",
                "deep learning",
                "model evaluation",
                "ablation",
            )
        )

    def _infer_ai_task_type(self, topic: str) -> str:
        explicit = str(self.collaboration_context.get("task_type", "")).strip()
        if explicit:
            return explicit
        lowered = topic.lower()
        if "kaggle" in lowered:
            return "kaggle_competition"
        if "fine-tuning" in lowered or "finetune" in lowered or "fine tune" in lowered:
            return "llm_fine_tuning"
        if "reproduce" in lowered or "reproduction" in lowered or "benchmark" in lowered:
            return "benchmark_reproduction"
        if "ablation" in lowered:
            return "ablation_study"
        if "classification" in lowered:
            return "classification"
        if "regression" in lowered:
            return "regression"
        return "benchmark_reproduction"

    def _derive_research_state(
        self,
        topic: str,
        steps: list[WorkflowStepResult],
        *,
        claim_graph: dict[str, Any],
        run_manifest: dict[str, Any],
    ) -> dict[str, Any]:
        stage_counts: dict[str, int] = {}
        blockers: list[str] = []
        open_questions: list[str] = []
        active_hypotheses: list[dict[str, Any]] = []
        negative_results: list[dict[str, Any]] = []
        evidence_strengths: list[str] = []
        evidence_quality_grades: list[str] = []
        conflict_groups: dict[str, list[dict[str, Any]]] = {}
        experiment_runs: list[dict[str, Any]] = []
        quality_control_reviews: list[dict[str, Any]] = []
        interpretation_records: list[dict[str, Any]] = []

        for step in steps:
            parsed = step.parsed_output
            stage = parsed.get("stage_assessment", {})
            if isinstance(stage, dict):
                current = str(stage.get("current_stage", "")).strip()
                if current:
                    stage_counts[current] = stage_counts.get(current, 0) + 1
                for blocker in stage.get("stage_blockers", []) if isinstance(stage.get("stage_blockers", []), list) else []:
                    if blocker:
                        blockers.append(str(blocker))
            for question in parsed.get("open_questions", []) if isinstance(parsed.get("open_questions", []), list) else []:
                if question:
                    open_questions.append(str(question))
            for item in parsed.get("hypotheses", []) if isinstance(parsed.get("hypotheses", []), list) else []:
                if isinstance(item, dict):
                    active_hypotheses.append(item)
            for item in parsed.get("negative_results", []) if isinstance(parsed.get("negative_results", []), list) else []:
                if isinstance(item, dict):
                    negative_results.append(item)
            for evidence in parsed.get("evidence", []) if isinstance(parsed.get("evidence", []), list) else []:
                if isinstance(evidence, dict):
                    strength = str(evidence.get("strength", "")).strip()
                    if strength:
                        evidence_strengths.append(strength)
                    quality_grade = str(evidence.get("quality_grade", "")).strip().lower()
                    if quality_grade:
                        evidence_quality_grades.append(quality_grade)
                    conflict_group = str(evidence.get("conflict_group", "")).strip()
                    if conflict_group:
                        conflict_groups.setdefault(conflict_group, []).append(evidence)
            run_payload = parsed.get("experiment_run", {})
            if isinstance(run_payload, dict) and run_payload:
                experiment_runs.append(run_payload)
            quality_payload = parsed.get("quality_control_review", {})
            if isinstance(quality_payload, dict) and quality_payload:
                quality_control_reviews.append(quality_payload)
            interpretation_payload = parsed.get("interpretation_record", {})
            if isinstance(interpretation_payload, dict) and interpretation_payload:
                interpretation_records.append(interpretation_payload)

        stage_validation = ScientificWorkflow._validate_stage_progression(steps)
        current_stage = stage_validation["current_stage"]
        next_stage = stage_validation["recommended_next_stage"]
        blockers.extend(stage_validation.get("blockers", []))

        if len(negative_results) >= 2:
            if current_stage in {"design", "analyze", "decide", "report"}:
                next_stage = "hypothesis"
            else:
                next_stage = "design"
            blockers.append("Repeated negative results require redesign or hypothesis revision.")
        elif len(negative_results) == 1 and current_stage in {"analyze", "decide"}:
            next_stage = "design"
            blockers.append("A negative result suggests the current design should be revisited.")

        evidence_summary = "mixed"
        if evidence_strengths:
            if all(item.lower() == "high" for item in evidence_strengths):
                evidence_summary = "strong"
            elif all(item.lower() in {"medium", "high"} for item in evidence_strengths):
                evidence_summary = "moderate"
            else:
                evidence_summary = "mixed"

        quality_summary = ScientificWorkflow._summarize_quality_grades(evidence_quality_grades)
        conflict_summary = ScientificWorkflow._summarize_conflict_groups(conflict_groups)
        literature_synthesis = ScientificWorkflow._derive_literature_synthesis(steps)
        systematic_review_summary = ScientificWorkflow._derive_systematic_review_draft(steps)
        causal_reasoning = ScientificWorkflow._derive_causal_reasoning(steps)
        analysis_rigor = ScientificWorkflow._derive_analysis_rigor(steps)
        consensus_state = ScientificWorkflow._derive_consensus_state(steps)
        autonomy_summary = ScientificWorkflow._derive_autonomy_summary(
            topic=topic,
            steps=steps,
            stage_validation=stage_validation,
        )
        research_plan_summary = ScientificWorkflow._derive_research_plan_summary(
            topic=topic,
            steps=steps,
            stage_validation=stage_validation,
        )
        causal_graph_summary = ScientificWorkflow._derive_causal_graph_summary(
            steps=steps,
            claim_graph=claim_graph,
        )
        discipline_adaptation_summary = ScientificWorkflow._derive_discipline_adaptation_summary(
            topic=topic,
            steps=steps,
            claim_graph=claim_graph,
        )
        hypothesis_tree = ScientificWorkflow._derive_hypothesis_tree(claim_graph)
        asset_registry_summary = ScientificWorkflow._summarize_asset_registry(
            claim_graph.get("asset_registry", []),
            run_manifest,
        )
        asset_graph_summary = ScientificWorkflow._derive_asset_graph_summary(
            claim_graph=claim_graph,
            run_manifest=run_manifest,
        )
        consensus_state_machine = ScientificWorkflow._derive_consensus_state_machine(
            consensus_state=consensus_state,
            conflict_summary=conflict_summary,
            stage_validation=stage_validation,
            negative_results=negative_results,
        )
        execution_cycle_summary = ScientificWorkflow._derive_execution_cycle_summary(
            experiment_runs=experiment_runs,
            quality_control_reviews=quality_control_reviews,
            interpretation_records=interpretation_records,
        )
        belief_update_summary = ScientificWorkflow._derive_belief_update_summary(
            steps=steps,
            claim_graph=claim_graph,
        )
        experiment_governance_summary = ScientificWorkflow._derive_experiment_governance_summary(
            experiment_runs=experiment_runs,
            quality_control_reviews=quality_control_reviews,
            interpretation_records=interpretation_records,
            claim_graph=claim_graph,
        )
        failure_intelligence_summary = ScientificWorkflow._derive_failure_intelligence_summary(
            steps=steps,
            claim_graph=claim_graph,
            execution_cycle_summary=execution_cycle_summary,
        )
        experiment_economics_summary = ScientificWorkflow._derive_experiment_economics_summary(
            topic=topic,
            steps=steps,
            research_plan_summary=research_plan_summary,
            discipline_adaptation_summary=discipline_adaptation_summary,
            execution_cycle_summary=execution_cycle_summary,
            failure_intelligence_summary=failure_intelligence_summary,
        )
        lab_meeting_consensus_summary = ScientificWorkflow._derive_lab_meeting_consensus_summary(
            steps=steps,
            consensus_state=consensus_state,
            consensus_state_machine=consensus_state_machine,
            failure_intelligence_summary=failure_intelligence_summary,
        )
        agent_stance_continuity_summary = self._derive_agent_stance_continuity_summary(
            topic=topic,
            steps=steps,
            lab_meeting_consensus_summary=lab_meeting_consensus_summary,
        )
        theoretical_hypothesis_tree_summary = (
            ScientificWorkflow._derive_theoretical_hypothesis_tree_summary(
                claim_graph=claim_graph,
                hypothesis_tree=hypothesis_tree,
                discipline_adaptation_summary=discipline_adaptation_summary,
            )
        )
        mechanism_reasoning_summary = ScientificWorkflow._derive_mechanism_reasoning_summary(
            steps=steps,
            causal_graph_summary=causal_graph_summary,
        )
        hypothesis_family_lifecycle_summary = ScientificWorkflow._derive_hypothesis_family_lifecycle_summary(
            steps=steps,
            theoretical_hypothesis_tree_summary=theoretical_hypothesis_tree_summary,
        )
        program_management_summary = ScientificWorkflow._derive_program_management_summary(
            topic=topic,
            steps=steps,
            research_plan_summary=research_plan_summary,
            autonomy_summary=autonomy_summary,
            route_temperature_summary={},
        )
        domain_playbook_summary = ScientificWorkflow._derive_domain_playbook_summary(
            topic=topic,
            steps=steps,
            discipline_adaptation_summary=discipline_adaptation_summary,
        )
        hypothesis_validation_summary = ScientificWorkflow._derive_hypothesis_validation_summary(
            steps=steps,
            claim_graph=claim_graph,
        )
        hypothesis_gate_summary = ScientificWorkflow._derive_hypothesis_gate_summary(
            steps=steps,
            hypothesis_validation_summary=hypothesis_validation_summary,
        )
        hypothesis_theory_summary = build_hypothesis_theory_summary(
            claim_graph=claim_graph,
            steps=steps,
            causal_graph_summary=causal_graph_summary,
        )
        mid_run_control_summary = self._mid_run_control_summary()
        scheduler_memory_context = self._derive_scheduler_memory_context(
            topic=topic,
            failure_intelligence_summary=failure_intelligence_summary,
            agent_stance_continuity_summary=agent_stance_continuity_summary,
            project_distill={},
        )
        graph_reference_summary = ScientificWorkflow._derive_graph_reference_summary(steps)
        evaluation_history_summary = (
            self.collaboration_context.get("evaluation_history_summary", {})
            if isinstance(self.collaboration_context.get("evaluation_history_summary", {}), dict)
            else {}
        )
        typed_research_graph_history = (
            self.collaboration_context.get("typed_research_graph_history", {})
            if isinstance(self.collaboration_context.get("typed_research_graph_history", {}), dict)
            else {}
        )
        route_temperature_summary = ScientificWorkflow._derive_route_temperature_summary(
            claim_graph=claim_graph,
            failure_intelligence_summary=failure_intelligence_summary,
            graph_reference_summary=graph_reference_summary,
            typed_research_graph_history=typed_research_graph_history,
            evaluation_history_summary=evaluation_history_summary,
            theoretical_hypothesis_tree_summary=theoretical_hypothesis_tree_summary,
        )
        program_management_summary = ScientificWorkflow._derive_program_management_summary(
            topic=topic,
            steps=steps,
            research_plan_summary=research_plan_summary,
            autonomy_summary=autonomy_summary,
            route_temperature_summary=route_temperature_summary,
        )
        graph_learning_summary = ScientificWorkflow._derive_graph_learning_summary(
            typed_research_graph_history=typed_research_graph_history,
            graph_reference_summary=graph_reference_summary,
            failure_intelligence_summary=failure_intelligence_summary,
            evaluation_history_summary=evaluation_history_summary,
        )
        mechanism_family_lifecycle_summary = (
            ScientificWorkflow._derive_mechanism_family_lifecycle_summary(
                steps=steps,
                mechanism_reasoning_summary=mechanism_reasoning_summary,
            )
        )
        artifact_provenance_summary = ScientificWorkflow._derive_artifact_provenance_summary(
            claim_graph=claim_graph,
            run_manifest=run_manifest,
            asset_graph_summary=asset_graph_summary,
        )
        program_portfolio_summary = ScientificWorkflow._derive_program_portfolio_summary(
            program_management_summary=program_management_summary,
            route_temperature_summary=route_temperature_summary,
            experiment_economics_summary=experiment_economics_summary,
            termination_strategy_summary={},
        )
        formal_review_record_summary = ScientificWorkflow._derive_formal_review_record_summary(
            systematic_review_summary=systematic_review_summary,
        )
        literature_ingest_policy_summary = decide_literature_ingest_policy(
            source_type=str(self.collaboration_context.get("literature_source_type", "paper")).strip() or "paper",
            title=topic,
            target_scope=str(self.collaboration_context.get("literature_target_scope", "project")).strip() or "project",
            user_mode=str(self.collaboration_context.get("literature_ingest_mode", "auto")).strip() or "auto",
            impact_level=str(self.collaboration_context.get("literature_impact_level", "medium")).strip() or "medium",
            conflict_level=str(conflict_summary.get("conflict_level", "low")).strip()
            if isinstance(conflict_summary, dict)
            else "low",
            confidence=str(quality_summary.get("overall_quality", "medium")).strip()
            if isinstance(quality_summary, dict)
            else "medium",
            group_role=str(self.collaboration_context.get("group_role", "")).strip(),
        ).to_dict()
        evidence_review_summary = build_evidence_review_summary(
            topic=topic,
            project_id=str(self.collaboration_context.get("project_id", "")).strip(),
            literature_synthesis=literature_synthesis,
            systematic_review_summary=systematic_review_summary,
            literature_quality_summary=quality_summary,
            conflict_attribution=conflict_summary,
            formal_review_record_summary=formal_review_record_summary,
            claim_graph=claim_graph,
        )
        systematic_review_summary = ScientificWorkflow._derive_systematic_review_summary(
            topic=topic,
            systematic_review_summary=systematic_review_summary,
            literature_synthesis=literature_synthesis,
            evidence_review_summary=evidence_review_summary,
            claim_graph=claim_graph,
        )
        problem_reframer_seed_state = {
            "current_stage": current_stage,
            "recommended_next_stage": next_stage,
            "systematic_review_summary": systematic_review_summary,
            "evidence_review_summary": evidence_review_summary,
            "conflict_attribution": conflict_summary,
            "hypothesis_validation_summary": hypothesis_validation_summary,
            "hypothesis_gate_summary": hypothesis_gate_summary,
        }
        scientific_problem_reframer_summary = build_scientific_problem_reframer_summary(
            topic=topic,
            research_state=problem_reframer_seed_state,
            claim_graph=claim_graph,
        )
        theory_prediction_compiler_summary = build_theory_prediction_compiler_summary(
            topic=topic,
            claim_graph=claim_graph,
            hypothesis_theory_summary=hypothesis_theory_summary,
            mechanism_reasoning_summary=mechanism_reasoning_summary,
            problem_reframer_summary=scientific_problem_reframer_summary,
        )
        evaluation_summary = ScientificWorkflow._derive_evaluation_summary(
            claim_graph=claim_graph,
            literature_quality_summary=quality_summary,
            consensus_state_machine=consensus_state_machine,
            execution_cycle_summary=execution_cycle_summary,
            failure_intelligence_summary=failure_intelligence_summary,
            theoretical_hypothesis_tree_summary=theoretical_hypothesis_tree_summary,
            systematic_review_summary=systematic_review_summary,
            causal_graph_summary=causal_graph_summary,
            asset_graph_summary=asset_graph_summary,
            graph_reference_summary=graph_reference_summary,
            typed_research_graph_history=typed_research_graph_history,
            evaluation_history_summary=evaluation_history_summary,
            route_temperature_summary=route_temperature_summary,
            graph_learning_summary=graph_learning_summary,
        )
        human_governance_checkpoint_summary = (
            ScientificWorkflow._derive_human_governance_checkpoint_summary(
                topic=topic,
                termination_strategy_summary={},
                lab_meeting_consensus_summary=lab_meeting_consensus_summary,
                experiment_governance_summary=experiment_governance_summary,
                experiment_economics_summary=experiment_economics_summary,
                consensus_state_machine=consensus_state_machine,
                evaluation_summary=evaluation_summary,
            )
        )
        project_distill = ScientificWorkflow._derive_project_distill(
            topic=topic,
            steps=steps,
            literature_synthesis=literature_synthesis,
            causal_reasoning=causal_reasoning,
            analysis_rigor=analysis_rigor,
            consensus_state=consensus_state,
            asset_registry_summary=asset_registry_summary,
            experiment_economics_summary=experiment_economics_summary,
            lab_meeting_consensus_summary=lab_meeting_consensus_summary,
        )
        scheduler_memory_context = self._derive_scheduler_memory_context(
            topic=topic,
            failure_intelligence_summary=failure_intelligence_summary,
            agent_stance_continuity_summary=agent_stance_continuity_summary,
            project_distill=project_distill,
        )
        termination_strategy_summary = ScientificWorkflow._derive_termination_strategy_summary(
            topic=topic,
            claim_graph=claim_graph,
            research_plan_summary=research_plan_summary,
            autonomy_summary=autonomy_summary,
            consensus_state_machine=consensus_state_machine,
            negative_results=negative_results,
            execution_cycle_summary=execution_cycle_summary,
            belief_update_summary=belief_update_summary,
            experiment_economics_summary=experiment_economics_summary,
            lab_meeting_consensus_summary=lab_meeting_consensus_summary,
        )
        program_portfolio_summary = ScientificWorkflow._derive_program_portfolio_summary(
            program_management_summary=program_management_summary,
            route_temperature_summary=route_temperature_summary,
            experiment_economics_summary=experiment_economics_summary,
            termination_strategy_summary=termination_strategy_summary,
        )
        human_governance_checkpoint_summary = (
            ScientificWorkflow._derive_human_governance_checkpoint_summary(
                topic=topic,
                termination_strategy_summary=termination_strategy_summary,
                lab_meeting_consensus_summary=lab_meeting_consensus_summary,
                experiment_governance_summary=experiment_governance_summary,
                experiment_economics_summary=experiment_economics_summary,
                consensus_state_machine=consensus_state_machine,
                evaluation_summary=evaluation_summary,
            )
        )
        benchmark_harness_summary = ScientificWorkflow._derive_benchmark_harness_summary(
            topic=topic,
            evaluation_summary=evaluation_summary,
            systematic_review_summary=systematic_review_summary,
            execution_cycle_summary=execution_cycle_summary,
            asset_graph_summary=asset_graph_summary,
            graph_reference_summary=graph_reference_summary,
            route_temperature_summary=route_temperature_summary,
            typed_research_graph_history=typed_research_graph_history,
            mechanism_reasoning_summary=mechanism_reasoning_summary,
            hypothesis_family_lifecycle_summary=hypothesis_family_lifecycle_summary,
            human_governance_checkpoint_summary=human_governance_checkpoint_summary,
        )
        research_route_search_summary = ScientificWorkflow._derive_research_route_search_summary(
            topic=topic,
            research_plan_summary=research_plan_summary,
            autonomy_summary=autonomy_summary,
            systematic_review_summary=systematic_review_summary,
            experiment_governance_summary=experiment_governance_summary,
            experiment_economics_summary=experiment_economics_summary,
            failure_intelligence_summary=failure_intelligence_summary,
            route_temperature_summary=route_temperature_summary,
            evaluation_summary=evaluation_summary,
            human_governance_checkpoint_summary=human_governance_checkpoint_summary,
            benchmark_harness_summary=benchmark_harness_summary,
            hypothesis_validation_summary=hypothesis_validation_summary,
            typed_research_graph_history=typed_research_graph_history,
        )
        scientific_decision_summary = build_scientific_decision_summary(
            topic=topic,
            hypothesis_theory_summary=hypothesis_theory_summary,
            research_route_search_summary=research_route_search_summary,
            experiment_economics_summary=experiment_economics_summary,
            failure_intelligence_summary=failure_intelligence_summary,
            systematic_review_summary=systematic_review_summary,
            evidence_review_summary=evidence_review_summary,
            human_governance_checkpoint_summary=human_governance_checkpoint_summary,
            lab_meeting_consensus_summary=lab_meeting_consensus_summary,
            termination_strategy_summary=termination_strategy_summary,
        )
        ai_research_workflow_summary = self._derive_ai_research_workflow_summary(
            topic=topic,
            literature_synthesis=literature_synthesis,
            systematic_review_summary=systematic_review_summary,
            evidence_review_summary=evidence_review_summary,
            discipline_adaptation_summary=discipline_adaptation_summary,
            project_distill=project_distill,
            failure_intelligence_summary=failure_intelligence_summary,
        )
        experiment_execution_loop_summary = build_experiment_execution_loop_summary(
            topic=topic,
            project_id=str(self.collaboration_context.get("project_id", "")).strip(),
            hypothesis_theory_summary=hypothesis_theory_summary,
            scientific_decision_summary=scientific_decision_summary,
            research_plan_summary=research_plan_summary,
            experiment_economics_summary=experiment_economics_summary,
            evidence_review_summary=evidence_review_summary,
            failure_intelligence_summary=failure_intelligence_summary,
            experiment_governance_summary=experiment_governance_summary,
            execution_cycle_summary=execution_cycle_summary,
            discipline_adaptation_summary=discipline_adaptation_summary,
            hypothesis_validation_summary=hypothesis_validation_summary,
            hypothesis_gate_summary=hypothesis_gate_summary,
            mid_run_control_summary=mid_run_control_summary,
            scheduler_memory_context=scheduler_memory_context,
        )
        experiment_execution_loop_summary = augment_experiment_execution_loop_with_ai(
            experiment_execution_loop_summary,
            ai_research_workflow_summary=ai_research_workflow_summary,
        )
        optimization_adapter_summary = build_optimization_adapter_summary(
            topic=topic,
            project_id=str(self.collaboration_context.get("project_id", "")).strip(),
            experiment_execution_loop_summary=experiment_execution_loop_summary,
            discipline_adaptation_summary=discipline_adaptation_summary,
        )
        discipline_adapter_summary = build_discipline_adapter_summary(
            topic=topic,
            project_id=str(self.collaboration_context.get("project_id", "")).strip(),
            discipline_adaptation_summary=discipline_adaptation_summary,
            experiment_execution_loop_summary=experiment_execution_loop_summary,
            optimization_adapter_summary=optimization_adapter_summary,
            evidence_review_summary=evidence_review_summary,
        )
        experiment_execution_loop_summary = build_experiment_execution_loop_summary(
            topic=topic,
            project_id=str(self.collaboration_context.get("project_id", "")).strip(),
            hypothesis_theory_summary=hypothesis_theory_summary,
            scientific_decision_summary=scientific_decision_summary,
            research_plan_summary=research_plan_summary,
            experiment_economics_summary=experiment_economics_summary,
            evidence_review_summary=evidence_review_summary,
            failure_intelligence_summary=failure_intelligence_summary,
            experiment_governance_summary=experiment_governance_summary,
            execution_cycle_summary=execution_cycle_summary,
            discipline_adaptation_summary=discipline_adaptation_summary,
            hypothesis_validation_summary=hypothesis_validation_summary,
            hypothesis_gate_summary=hypothesis_gate_summary,
            discipline_adapter_summary=discipline_adapter_summary,
            mid_run_control_summary=mid_run_control_summary,
            scheduler_memory_context=scheduler_memory_context,
        )
        experiment_execution_loop_summary = augment_experiment_execution_loop_with_ai(
            experiment_execution_loop_summary,
            ai_research_workflow_summary=ai_research_workflow_summary,
        )
        optimization_adapter_summary = build_optimization_adapter_summary(
            topic=topic,
            project_id=str(self.collaboration_context.get("project_id", "")).strip(),
            experiment_execution_loop_summary=experiment_execution_loop_summary,
            discipline_adaptation_summary=discipline_adaptation_summary,
        )
        discipline_adapter_summary = build_discipline_adapter_summary(
            topic=topic,
            project_id=str(self.collaboration_context.get("project_id", "")).strip(),
            discipline_adaptation_summary=discipline_adaptation_summary,
            experiment_execution_loop_summary=experiment_execution_loop_summary,
            optimization_adapter_summary=optimization_adapter_summary,
            evidence_review_summary=evidence_review_summary,
        )
        execution_adapter_registry_summary = build_execution_adapter_registry_summary(
            topic=topic,
            project_id=str(self.collaboration_context.get("project_id", "")).strip(),
            experiment_execution_loop_summary=experiment_execution_loop_summary,
            optimization_adapter_summary=optimization_adapter_summary,
            discipline_adaptation_summary=discipline_adaptation_summary,
            discipline_adapter_summary=discipline_adapter_summary,
        )
        run_handoff_contract_summary = build_run_handoff_contract_summary(
            topic=topic,
            project_id=str(self.collaboration_context.get("project_id", "")).strip(),
            execution_adapter_registry_summary=execution_adapter_registry_summary,
        )
        discipline_toolchain_binding_summary = build_discipline_toolchain_binding_summary(
            topic=topic,
            discipline_adapter_summary=discipline_adapter_summary,
            experiment_execution_loop_summary=experiment_execution_loop_summary,
            execution_adapter_registry_summary=execution_adapter_registry_summary,
        )
        experiment_risk_permission_summary = build_experiment_risk_permission_summary(
            topic=topic,
            experiment_execution_loop_summary=experiment_execution_loop_summary,
            discipline_toolchain_binding_summary=discipline_toolchain_binding_summary,
            human_governance_checkpoint_summary=human_governance_checkpoint_summary,
        )
        autonomous_controller_summary = build_autonomous_controller_summary(
            topic=topic,
            project_id=str(self.collaboration_context.get("project_id", "")).strip(),
            stage_machine=stage_validation,
            autonomy_summary=autonomy_summary,
            scientific_decision_summary=scientific_decision_summary,
            evidence_review_summary=evidence_review_summary,
            experiment_governance_summary=experiment_governance_summary,
            experiment_execution_loop_summary=experiment_execution_loop_summary,
            termination_strategy_summary=termination_strategy_summary,
            human_governance_checkpoint_summary=human_governance_checkpoint_summary,
            evaluation_summary=evaluation_summary,
            run_manifest=run_manifest,
            mid_run_control_summary=mid_run_control_summary,
        )
        kaivu_evaluation_harness_summary = (
            build_kaivu_evaluation_harness_summary(
                topic=topic,
                project_id=str(self.collaboration_context.get("project_id", "")).strip(),
                evaluation_summary=evaluation_summary,
                benchmark_harness_summary=benchmark_harness_summary,
                hypothesis_validation_summary=hypothesis_validation_summary,
                evidence_review_summary=evidence_review_summary,
                discipline_adapter_summary=discipline_adapter_summary,
                experiment_execution_loop_summary=experiment_execution_loop_summary,
                execution_adapter_registry_summary=execution_adapter_registry_summary,
                run_handoff_contract_summary=run_handoff_contract_summary,
                autonomous_controller_summary=autonomous_controller_summary,
                failure_intelligence_summary=failure_intelligence_summary,
                graph_learning_summary=graph_learning_summary,
                mid_run_control_summary=mid_run_control_summary,
                agent_stance_continuity_summary=agent_stance_continuity_summary,
            )
        )
        unified_asset_summary = build_unified_asset_summary(
            topic=topic,
            project_id=str(self.collaboration_context.get("project_id", "")).strip(),
            claim_graph=claim_graph,
            run_manifest=run_manifest,
            hypothesis_theory_summary=hypothesis_theory_summary,
            scientific_decision_summary=scientific_decision_summary,
            systematic_review_summary=systematic_review_summary,
            evidence_review_summary=evidence_review_summary,
            autonomous_controller_summary=autonomous_controller_summary,
            experiment_execution_loop_summary=experiment_execution_loop_summary,
            optimization_adapter_summary=optimization_adapter_summary,
            discipline_adapter_summary=discipline_adapter_summary,
            execution_adapter_registry_summary=execution_adapter_registry_summary,
            run_handoff_contract_summary=run_handoff_contract_summary,
            kaivu_evaluation_harness_summary=kaivu_evaluation_harness_summary,
            causal_graph_summary=causal_graph_summary,
        )
        kernel_state = {
            "topic": topic,
            "workspace_layout_summary": self.workspace_layout.to_dict(),
            "current_stage": current_stage,
            "recommended_next_stage": next_stage,
            "blockers": list(dict.fromkeys(blockers))[:10],
            "open_questions": open_questions[:10],
            "systematic_review_summary": systematic_review_summary,
            "evidence_review_summary": evidence_review_summary,
            "hypothesis_validation_summary": hypothesis_validation_summary,
            "hypothesis_gate_summary": hypothesis_gate_summary,
            "scientific_problem_reframer_summary": scientific_problem_reframer_summary,
            "theory_prediction_compiler_summary": theory_prediction_compiler_summary,
            "literature_ingest_policy_summary": literature_ingest_policy_summary,
            "ai_research_workflow_summary": ai_research_workflow_summary,
            "experiment_execution_loop_summary": experiment_execution_loop_summary,
            "discipline_adapter_summary": discipline_adapter_summary,
            "discipline_toolchain_binding_summary": discipline_toolchain_binding_summary,
            "experiment_risk_permission_summary": experiment_risk_permission_summary,
            "scientific_decision_summary": scientific_decision_summary,
            "kaivu_evaluation_harness_summary": kaivu_evaluation_harness_summary,
            "human_governance_checkpoint_summary": human_governance_checkpoint_summary,
        }
        scientific_object_store_summary = build_scientific_object_store_summary(
            topic=topic,
            project_id=str(self.collaboration_context.get("project_id", "")).strip(),
            claim_graph=claim_graph,
            research_state=kernel_state,
            run_manifest=run_manifest,
        )
        research_state_machine_summary = build_research_state_machine_summary(
            topic=topic,
            research_state=kernel_state,
            object_store_summary=scientific_object_store_summary,
        )
        uncertainty_ledger_summary = build_uncertainty_ledger_summary(
            topic=topic,
            research_state=kernel_state,
            claim_graph=claim_graph,
        )
        value_of_information_summary = build_value_of_information_summary(
            topic=topic,
            experiment_execution_loop_summary=experiment_execution_loop_summary,
            uncertainty_ledger_summary=uncertainty_ledger_summary,
        )
        counterfactual_experiment_summary = build_counterfactual_experiment_summary(
            topic=topic,
            claim_graph=claim_graph,
            uncertainty_ledger_summary=uncertainty_ledger_summary,
        )
        reproducibility_kernel_summary = build_reproducibility_kernel_summary(
            topic=topic,
            run_manifest=run_manifest,
            research_state=kernel_state,
        )
        scientific_debate_protocol_summary = build_scientific_debate_protocol_summary(
            topic=topic,
            research_state=kernel_state,
            claim_graph=claim_graph,
        )
        failure_reuse_engine_summary = build_failure_reuse_engine_summary(
            topic=topic,
            claim_graph=claim_graph,
            experiment_execution_loop_summary=experiment_execution_loop_summary,
        )
        literature_claim_compiler_summary = build_literature_claim_compiler_summary(
            topic=topic,
            claim_graph=claim_graph,
            systematic_review_summary=systematic_review_summary,
        )
        model_reliability_layer_summary = build_model_reliability_layer_summary(
            topic=topic,
            run_manifest=run_manifest,
            research_state=kernel_state,
        )
        extended_kernel_state = {
            **kernel_state,
            "scientific_object_store_summary": scientific_object_store_summary,
            "reproducibility_kernel_summary": reproducibility_kernel_summary,
            "scientific_debate_protocol_summary": scientific_debate_protocol_summary,
            "failure_reuse_engine_summary": failure_reuse_engine_summary,
            "literature_claim_compiler_summary": literature_claim_compiler_summary,
            "model_reliability_layer_summary": model_reliability_layer_summary,
            "scientific_problem_reframer_summary": scientific_problem_reframer_summary,
            "theory_prediction_compiler_summary": theory_prediction_compiler_summary,
            "literature_ingest_policy_summary": literature_ingest_policy_summary,
            "ai_research_workflow_summary": ai_research_workflow_summary,
            "run_handoff_contract_summary": run_handoff_contract_summary,
            "discipline_toolchain_binding_summary": discipline_toolchain_binding_summary,
            "experiment_risk_permission_summary": experiment_risk_permission_summary,
            "project_distill": project_distill,
        }
        benchmark_case_suite_summary = build_benchmark_case_suite_summary(
            topic=topic,
            research_state=extended_kernel_state,
            claim_graph=claim_graph,
            run_manifest=run_manifest,
        )
        anomaly_surprise_detector_summary = build_anomaly_surprise_detector_summary(
            topic=topic,
            research_state=extended_kernel_state,
            claim_graph=claim_graph,
        )
        scientific_credit_responsibility_ledger_summary = build_scientific_credit_responsibility_ledger_summary(
            topic=topic,
            research_state=extended_kernel_state,
            run_manifest=run_manifest,
        )
        scientific_evaluation_benchmark_summary = build_scientific_evaluation_benchmark_summary(
            topic=topic,
            research_state={
                **extended_kernel_state,
                "benchmark_case_suite_summary": benchmark_case_suite_summary,
                "anomaly_surprise_detector_summary": anomaly_surprise_detector_summary,
                "scientific_credit_responsibility_ledger_summary": scientific_credit_responsibility_ledger_summary,
            },
            claim_graph=claim_graph,
        )
        benchmark_case_suite_summary = {
            **benchmark_case_suite_summary,
            "benchmark_version": "current",
            "scientific_evaluation_benchmark_summary": scientific_evaluation_benchmark_summary,
            "scientific_evaluation_tasks": scientific_evaluation_benchmark_summary.get("tasks", []),
            "scientific_evaluation_benchmark_state": scientific_evaluation_benchmark_summary.get("benchmark_state", ""),
            "average_task_quality_score": scientific_evaluation_benchmark_summary.get("average_quality_score", 0),
        }
        scientific_context_policy_summary = build_scientific_context_policy_summary(
            topic=topic,
            research_state={
                **extended_kernel_state,
                "benchmark_case_suite_summary": benchmark_case_suite_summary,
                "anomaly_surprise_detector_summary": anomaly_surprise_detector_summary,
            },
            claim_graph=claim_graph,
            scheduler_memory_context=scheduler_memory_context,
        )
        route_scheduler_summary = build_research_route_scheduler_summary(
            topic=topic,
            research_state={
                **extended_kernel_state,
                "benchmark_case_suite_summary": benchmark_case_suite_summary,
                "scientific_context_policy_summary": scientific_context_policy_summary,
                "anomaly_surprise_detector_summary": anomaly_surprise_detector_summary,
            },
            claim_graph=claim_graph,
            scheduler_memory_context=scheduler_memory_context,
        )
        research_campaign_plan_summary = build_research_campaign_plan_summary(
            topic=topic,
            research_state={
                **extended_kernel_state,
                "benchmark_case_suite_summary": benchmark_case_suite_summary,
                "scientific_context_policy_summary": scientific_context_policy_summary,
                "route_selector_summary": route_scheduler_summary,
            },
            claim_graph=claim_graph,
            scheduler_memory_context=scheduler_memory_context,
            route_scheduler_summary=route_scheduler_summary,
        )
        memory_governance_loop_summary = build_memory_governance_loop_summary(
            topic=topic,
            research_state=extended_kernel_state,
            claim_graph=claim_graph,
            object_store_summary=scientific_object_store_summary,
        )
        scheduler_search_kernel_summary = build_scheduler_search_kernel_summary(
            topic=topic,
            experiment_execution_loop_summary=experiment_execution_loop_summary,
            value_of_information_summary=value_of_information_summary,
            uncertainty_ledger_summary=uncertainty_ledger_summary,
            research_campaign_plan_summary=research_campaign_plan_summary,
            route_selector_summary=research_campaign_plan_summary.get("route_selector_summary", {})
            if isinstance(research_campaign_plan_summary, dict)
            else {},
        )
        lab_meeting_protocol_summary = build_lab_meeting_protocol_summary(
            topic=topic,
            research_state=extended_kernel_state,
            claim_graph=claim_graph,
        )
        unified_provenance_graph_summary = build_unified_provenance_graph_summary(
            topic=topic,
            object_store_summary=scientific_object_store_summary,
            run_manifest=run_manifest,
            research_state=extended_kernel_state,
        )
        discipline_native_kernel_summary = build_discipline_native_kernel_summary(
            topic=topic,
            discipline_adapter_summary=discipline_adapter_summary,
            experiment_execution_loop_summary=experiment_execution_loop_summary,
        )
        next_cycle_decision_directives_summary = build_next_cycle_decision_directives_summary(
            topic=topic,
            benchmark_case_suite_summary=benchmark_case_suite_summary,
            memory_governance_loop_summary=memory_governance_loop_summary,
            scheduler_search_kernel_summary=scheduler_search_kernel_summary,
            lab_meeting_protocol_summary=lab_meeting_protocol_summary,
            unified_provenance_graph_summary=unified_provenance_graph_summary,
            discipline_native_kernel_summary=discipline_native_kernel_summary,
        )
        reliability_state = {
            **extended_kernel_state,
            "benchmark_case_suite_summary": benchmark_case_suite_summary,
            "scientific_context_policy_summary": scientific_context_policy_summary,
            "anomaly_surprise_detector_summary": anomaly_surprise_detector_summary,
            "scientific_credit_responsibility_ledger_summary": scientific_credit_responsibility_ledger_summary,
            "research_campaign_plan_summary": research_campaign_plan_summary,
            "memory_governance_loop_summary": memory_governance_loop_summary,
            "scheduler_search_kernel_summary": scheduler_search_kernel_summary,
            "lab_meeting_protocol_summary": lab_meeting_protocol_summary,
            "unified_provenance_graph_summary": unified_provenance_graph_summary,
            "discipline_native_kernel_summary": discipline_native_kernel_summary,
            "next_cycle_decision_directives_summary": next_cycle_decision_directives_summary,
        }
        scientific_error_taxonomy_summary = build_scientific_error_taxonomy_summary(
            topic=topic,
            research_state=reliability_state,
            claim_graph=claim_graph,
        )
        reliability_state["scientific_error_taxonomy_summary"] = scientific_error_taxonomy_summary
        scientific_release_gate_summary = build_scientific_release_gate_summary(
            topic=topic,
            research_state=reliability_state,
        )
        reliability_state["scientific_release_gate_summary"] = scientific_release_gate_summary
        memory_conflict_version_graph_summary = build_memory_conflict_version_graph_summary(
            topic=topic,
            research_state=reliability_state,
            claim_graph=claim_graph,
        )
        reliability_state["memory_conflict_version_graph_summary"] = memory_conflict_version_graph_summary
        hypothesis_system_summary = ScientificWorkflow._derive_hypothesis_system_summary(
            topic=topic,
            hypothesis_tree_summary=hypothesis_tree,
            theoretical_hypothesis_tree_summary=theoretical_hypothesis_tree_summary,
            hypothesis_theory_summary=hypothesis_theory_summary,
            hypothesis_validation_summary=hypothesis_validation_summary,
            hypothesis_gate_summary=hypothesis_gate_summary,
            mechanism_family_lifecycle_summary=mechanism_family_lifecycle_summary,
            theory_prediction_compiler_summary=theory_prediction_compiler_summary,
        )
        scientific_evaluation_system_summary = ScientificWorkflow._derive_scientific_evaluation_system_summary(
            topic=topic,
            benchmark_harness_summary=benchmark_harness_summary,
            benchmark_case_suite_summary=benchmark_case_suite_summary,
            kaivu_evaluation_harness_summary=kaivu_evaluation_harness_summary,
            evaluation_summary=evaluation_summary,
        )
        workflow_control_summary = ScientificWorkflow._derive_workflow_control_summary(
            topic=topic,
            current_stage=current_stage,
            recommended_next_stage=next_stage,
            claim_graph=claim_graph,
            systematic_review_summary=systematic_review_summary,
            evidence_review_summary=evidence_review_summary,
            hypothesis_system_summary=hypothesis_system_summary,
            scientific_decision_summary=scientific_decision_summary,
            experiment_execution_loop_summary=experiment_execution_loop_summary,
            research_campaign_plan_summary=research_campaign_plan_summary,
            scientific_evaluation_system_summary=scientific_evaluation_system_summary,
            stage_validation=stage_validation,
        )
        reliability_state["hypothesis_system_summary"] = hypothesis_system_summary
        reliability_state["scientific_evaluation_system_summary"] = scientific_evaluation_system_summary
        reliability_state["workflow_control_summary"] = workflow_control_summary
        research_operating_system_summary = build_research_operating_system_summary(
            topic=topic,
            project_id=str(self.collaboration_context.get("project_id", "")).strip(),
            research_state=reliability_state,
            claim_graph=claim_graph,
            run_manifest=run_manifest,
        )
        reliability_state["research_operating_system_summary"] = research_operating_system_summary
        research_program_summary = build_research_program_from_state(
            topic=topic,
            project_id=str(self.collaboration_context.get("project_id", "")).strip(),
            research_state=reliability_state,
            claim_graph=claim_graph,
            run_manifest=run_manifest,
        )
        reliability_state["research_program_summary"] = research_program_summary
        self.research_program_registry.save_program(
            ResearchProgram(
                program_id=str(research_program_summary.get("program_id", "")),
                topic=topic,
                project_id=str(self.collaboration_context.get("project_id", "")).strip(),
                status=str(research_program_summary.get("status", "active")),
                objective_contract=research_program_summary.get("objective_contract", {}),
                hypothesis_lifecycle=research_program_summary.get("hypothesis_lifecycle", {}),
                evidence_map=research_program_summary.get("evidence_map", {}),
                resource_economics=research_program_summary.get("resource_economics", {}),
                autonomy_policy=research_program_summary.get("autonomy_policy", {}),
                provenance_policy=research_program_summary.get("provenance_policy", {}),
                meeting_governance=research_program_summary.get("meeting_governance", {}),
                evaluation_contract=research_program_summary.get("evaluation_contract", {}),
                failed_attempt_recall=research_program_summary.get("failed_attempt_recall", {}),
                experiment_portfolio=research_program_summary.get("experiment_portfolio", {}),
                report_release_policy=research_program_summary.get("report_release_policy", {}),
                control_actions=research_program_summary.get("control_actions", []),
                updated_at=str(research_program_summary.get("updated_at", "")),
            )
        )
        scientific_kernel_state_summary = build_scientific_kernel_state_summary(
            topic=topic,
            project_id=str(self.collaboration_context.get("project_id", "")).strip(),
            summaries=reliability_state,
        )

        return {
            "topic": topic,
            "current_stage": current_stage,
            "recommended_next_stage": next_stage,
            "stage_counts": stage_counts,
            "allowed_next_stages": stage_validation.get("allowed_next_stages", []),
            "missing_prerequisites": stage_validation.get("missing_prerequisites", []),
            "invalid_transitions": stage_validation.get("invalid_transitions", []),
            "blockers": list(dict.fromkeys(blockers))[:10],
            "open_questions": open_questions[:10],
            "active_hypothesis_count": len([item for item in active_hypotheses if str(item.get("status", "active")) != "rejected"]),
            "negative_result_count": len(negative_results),
            "negative_result_summary": [
                str(item.get("result", "")).strip()
                for item in negative_results[:5]
                if isinstance(item, dict) and str(item.get("result", "")).strip()
            ],
            "challenged_hypothesis_ids": sorted(
                {
                    hypothesis_id
                    for item in negative_results
                    if isinstance(item, dict)
                    for hypothesis_id in (
                        item.get("affected_hypothesis_ids", [])
                        if isinstance(item.get("affected_hypothesis_ids", []), list)
                        else []
                    )
                    if str(hypothesis_id).strip()
                }
            )[:10],
            "hypothesis_status_counts": {
                status: len(
                    [
                        item
                        for item in active_hypotheses
                        if str(item.get("status", "active")).strip().lower() == status
                    ]
                )
                for status in ["active", "revised", "deprecated", "rejected"]
            },
            "evidence_strength_summary": evidence_summary,
            "literature_quality_summary": quality_summary,
            "conflict_attribution": conflict_summary,
            "literature_synthesis": literature_synthesis,
            "systematic_review_summary": systematic_review_summary,
            "causal_reasoning": causal_reasoning,
            "causal_graph_summary": causal_graph_summary,
            "autonomy_summary": autonomy_summary,
            "autonomous_controller_summary": autonomous_controller_summary,
            "analysis_rigor": analysis_rigor,
            "consensus_state": consensus_state,
            "consensus_state_machine": consensus_state_machine,
            "research_plan_summary": research_plan_summary,
            "discipline_adaptation_summary": discipline_adaptation_summary,
            "hypothesis_tree_summary": hypothesis_tree,
            "asset_registry_summary": asset_registry_summary,
            "asset_graph_summary": asset_graph_summary,
            "unified_asset_summary": unified_asset_summary,
            "belief_update_summary": belief_update_summary,
            "experiment_governance_summary": experiment_governance_summary,
            "experiment_execution_loop_summary": experiment_execution_loop_summary,
            "scheduler_memory_context": scheduler_memory_context,
            "optimization_adapter_summary": optimization_adapter_summary,
            "discipline_adapter_summary": discipline_adapter_summary,
            "execution_adapter_registry_summary": execution_adapter_registry_summary,
            "run_handoff_contract_summary": run_handoff_contract_summary,
            "discipline_toolchain_binding_summary": discipline_toolchain_binding_summary,
            "experiment_risk_permission_summary": experiment_risk_permission_summary,
            "experiment_economics_summary": experiment_economics_summary,
            "lab_meeting_consensus_summary": lab_meeting_consensus_summary,
            "agent_stance_continuity_summary": agent_stance_continuity_summary,
            "theoretical_hypothesis_tree_summary": theoretical_hypothesis_tree_summary,
            "mechanism_reasoning_summary": mechanism_reasoning_summary,
            "hypothesis_family_lifecycle_summary": hypothesis_family_lifecycle_summary,
            "failure_intelligence_summary": failure_intelligence_summary,
            "evaluation_summary": evaluation_summary,
            "graph_reference_summary": graph_reference_summary,
            "route_temperature_summary": route_temperature_summary,
            "graph_learning_summary": graph_learning_summary,
            "human_governance_checkpoint_summary": human_governance_checkpoint_summary,
            "benchmark_harness_summary": benchmark_harness_summary,
            "kaivu_evaluation_harness_summary": kaivu_evaluation_harness_summary,
            "program_management_summary": program_management_summary,
            "domain_playbook_summary": domain_playbook_summary,
            "hypothesis_validation_summary": hypothesis_validation_summary,
            "hypothesis_gate_summary": hypothesis_gate_summary,
            "hypothesis_theory_summary": hypothesis_theory_summary,
            "hypothesis_system_summary": hypothesis_system_summary,
            "scientific_problem_reframer_summary": scientific_problem_reframer_summary,
            "theory_prediction_compiler_summary": theory_prediction_compiler_summary,
            "literature_ingest_policy_summary": literature_ingest_policy_summary,
            "ai_research_workflow_summary": ai_research_workflow_summary,
            "ai_dataset_profile": ai_research_workflow_summary.get("dataset_profile", {})
            if isinstance(ai_research_workflow_summary, dict)
            else {},
            "ai_contamination_risk_report": ai_research_workflow_summary.get("contamination_risk_report", {})
            if isinstance(ai_research_workflow_summary, dict)
            else {},
            "ai_evaluation_protocol": ai_research_workflow_summary.get("evaluation_protocol", {})
            if isinstance(ai_research_workflow_summary, dict)
            else {},
            "ai_training_recipe": ai_research_workflow_summary.get("training_recipe", {})
            if isinstance(ai_research_workflow_summary, dict)
            else {},
            "ai_ablation_plan": ai_research_workflow_summary.get("ablation_plan", {})
            if isinstance(ai_research_workflow_summary, dict)
            else {},
            "ai_artifact_contract": ai_research_workflow_summary.get("artifact_contract", {})
            if isinstance(ai_research_workflow_summary, dict)
            else {},
            "anomaly_surprise_detector_summary": anomaly_surprise_detector_summary,
            "scientific_credit_responsibility_ledger_summary": scientific_credit_responsibility_ledger_summary,
            "mechanism_family_lifecycle_summary": mechanism_family_lifecycle_summary,
            "artifact_provenance_summary": artifact_provenance_summary,
            "program_portfolio_summary": program_portfolio_summary,
            "formal_review_record_summary": formal_review_record_summary,
            "evidence_review_summary": evidence_review_summary,
            "research_route_search_summary": research_route_search_summary,
            "scientific_decision_summary": scientific_decision_summary,
            "scientific_object_store_summary": scientific_object_store_summary,
            "research_state_machine_summary": research_state_machine_summary,
            "uncertainty_ledger_summary": uncertainty_ledger_summary,
            "value_of_information_summary": value_of_information_summary,
            "counterfactual_experiment_summary": counterfactual_experiment_summary,
            "reproducibility_kernel_summary": reproducibility_kernel_summary,
            "scientific_debate_protocol_summary": scientific_debate_protocol_summary,
            "failure_reuse_engine_summary": failure_reuse_engine_summary,
            "literature_claim_compiler_summary": literature_claim_compiler_summary,
            "model_reliability_layer_summary": model_reliability_layer_summary,
            "benchmark_case_suite_summary": benchmark_case_suite_summary,
            "scientific_evaluation_system_summary": scientific_evaluation_system_summary,
            "scientific_context_policy_summary": scientific_context_policy_summary,
            "anomaly_surprise_detector_summary": anomaly_surprise_detector_summary,
            "scientific_credit_responsibility_ledger_summary": scientific_credit_responsibility_ledger_summary,
            "research_campaign_plan_summary": research_campaign_plan_summary,
            "route_selector_summary": research_campaign_plan_summary.get("route_selector_summary", {})
            if isinstance(research_campaign_plan_summary, dict)
            else {},
            "memory_governance_loop_summary": memory_governance_loop_summary,
            "scheduler_search_kernel_summary": scheduler_search_kernel_summary,
            "lab_meeting_protocol_summary": lab_meeting_protocol_summary,
            "unified_provenance_graph_summary": unified_provenance_graph_summary,
            "discipline_native_kernel_summary": discipline_native_kernel_summary,
            "next_cycle_decision_directives_summary": next_cycle_decision_directives_summary,
            "scientific_kernel_state_summary": scientific_kernel_state_summary,
            "workflow_control_summary": workflow_control_summary,
            "scientific_error_taxonomy_summary": scientific_error_taxonomy_summary,
            "scientific_release_gate_summary": scientific_release_gate_summary,
            "memory_conflict_version_graph_summary": memory_conflict_version_graph_summary,
            "research_operating_system_summary": research_operating_system_summary,
            "research_program_summary": research_program_summary,
            "project_distill": project_distill,
            "execution_cycle_summary": execution_cycle_summary,
            "termination_strategy_summary": termination_strategy_summary,
            "stage_machine": stage_validation,
            "mid_run_control_summary": mid_run_control_summary,
            "run_manifest_summary": {
                "tool_count": len(run_manifest.get("tools_used", [])),
                "model_count": len(run_manifest.get("models_used", [])),
                "artifact_count": len(run_manifest.get("artifacts", [])),
                "input_file_count": len(run_manifest.get("input_files", [])),
            },
        }

    def _build_profile_sequence(self, topic: str) -> list[SpecialistProfile]:
        sequence = [
            DEFAULT_SCIENCE_PROFILES["research_planner"],
            DEFAULT_SCIENCE_PROFILES["literature_reviewer"],
        ]
        remaining = [
            "data_curator",
            "hypothesis_generator",
            "experiment_designer",
            "experiment_economist",
            "run_manager",
            "quality_control_reviewer",
            "result_interpreter",
            "belief_updater",
            "data_analyst",
            "critic",
            "lab_meeting_moderator",
            "safety_ethics_reviewer",
            "conflict_resolver",
        ]
        topic_lower = topic.lower()
        if any(
            token in topic_lower
            for token in ["csv", "xlsx", "table", "dataset", "data", "file"]
        ):
            for name in ["data_curator", "data_analyst"]:
                if name in remaining:
                    sequence.append(DEFAULT_SCIENCE_PROFILES[name])
                    remaining.remove(name)
        sequence.extend(DEFAULT_SCIENCE_PROFILES[name] for name in remaining)
        sequence.append(DEFAULT_SCIENCE_PROFILES["coordinator"])
        sequence.append(DEFAULT_SCIENCE_PROFILES["report_writer"])
        return sequence

    @staticmethod
    def _validate_stage_progression(steps: list[WorkflowStepResult]) -> dict[str, Any]:
        stage_sequence: list[str] = []
        invalid_transitions: list[str] = []
        blockers: list[str] = []
        open_questions: list[str] = []
        have_evidence = False
        have_hypothesis = False
        have_design = False
        have_execution = False
        have_analysis = False
        have_decision = False

        for step in steps:
            parsed = step.parsed_output
            if parsed.get("evidence"):
                have_evidence = True
            if parsed.get("hypotheses"):
                have_hypothesis = True
            stage = parsed.get("stage_assessment", {})
            if not isinstance(stage, dict):
                continue
            current_stage = str(stage.get("current_stage", "")).strip().lower()
            next_stage = str(stage.get("next_stage", "")).strip().lower()
            if current_stage:
                stage_sequence.append(current_stage)
                if current_stage == "design":
                    have_design = True
                elif current_stage == "execute":
                    have_execution = True
                elif current_stage == "analyze":
                    have_analysis = True
                elif current_stage == "decide":
                    have_decision = True
            if current_stage and next_stage:
                allowed_next = ALLOWED_STAGE_NEXT.get(current_stage, [])
                if next_stage not in allowed_next and next_stage != current_stage:
                    invalid_transitions.append(f"{current_stage}->{next_stage}")
            for item in stage.get("stage_blockers", []):
                if item:
                    blockers.append(str(item))
            for item in stage.get("missing_prerequisites", []):
                if item:
                    blockers.append(str(item))

        current_stage = stage_sequence[-1] if stage_sequence else "question"
        allowed_next_stages = ALLOWED_STAGE_NEXT.get(current_stage, [])
        missing_prerequisites: list[str] = []
        if current_stage in {"review", "hypothesis", "design", "execute", "analyze", "decide", "report"} and not have_evidence:
            missing_prerequisites.append("No explicit evidence records have been captured yet.")
        if current_stage in {"design", "execute", "analyze", "decide", "report"} and not have_hypothesis:
            missing_prerequisites.append("No explicit hypothesis set is available for downstream stages.")
        if current_stage in {"execute", "analyze", "decide", "report"} and not have_design:
            missing_prerequisites.append("No experimental or analytical design has been recorded.")
        if current_stage in {"analyze", "decide", "report"} and not (have_execution or have_analysis):
            missing_prerequisites.append("No execution or analysis stage has been recorded.")
        if current_stage == "report" and not have_decision:
            missing_prerequisites.append("Reporting is premature because no decision stage has been captured.")

        recommended_next_stage = allowed_next_stages[0] if allowed_next_stages else current_stage
        if missing_prerequisites:
            if not have_hypothesis:
                recommended_next_stage = "hypothesis"
            elif not have_design:
                recommended_next_stage = "design"
            elif not have_execution:
                recommended_next_stage = "execute"
            elif not have_analysis:
                recommended_next_stage = "analyze"
            else:
                recommended_next_stage = current_stage
        elif current_stage == "design" and have_execution:
            recommended_next_stage = "analyze"
        elif current_stage == "analyze" and have_decision:
            recommended_next_stage = "report"

        if invalid_transitions:
            blockers.append("Some specialist outputs proposed invalid stage transitions.")

        return {
            "stage_sequence": stage_sequence,
            "current_stage": current_stage,
            "allowed_next_stages": allowed_next_stages,
            "recommended_next_stage": recommended_next_stage,
            "missing_prerequisites": list(dict.fromkeys(missing_prerequisites)),
            "invalid_transitions": list(dict.fromkeys(invalid_transitions)),
            "blockers": list(dict.fromkeys(blockers)),
        }

    @staticmethod
    def _summarize_quality_grades(grades: list[str]) -> dict[str, Any]:
        if not grades:
            return {"dominant_grade": "unclear", "counts": {}}
        counts: dict[str, int] = {}
        for grade in grades:
            normalized = grade.strip().lower()
            if not normalized:
                continue
            counts[normalized] = counts.get(normalized, 0) + 1
        dominant = max(counts.items(), key=lambda item: item[1])[0] if counts else "unclear"
        return {"dominant_grade": dominant, "counts": counts}

    @staticmethod
    def _summarize_conflict_groups(
        conflict_groups: dict[str, list[dict[str, Any]]]
    ) -> dict[str, Any]:
        groups: list[dict[str, Any]] = []
        for group_name, items in conflict_groups.items():
            directions = {
                str(item.get("evidence_direction", "")).strip().lower()
                for item in items
                if str(item.get("evidence_direction", "")).strip()
            }
            strengths = [
                str(item.get("strength", "")).strip().lower()
                for item in items
                if str(item.get("strength", "")).strip()
            ]
            groups.append(
                {
                    "conflict_group": group_name,
                    "evidence_count": len(items),
                    "directions": sorted(directions),
                    "has_directional_conflict": len(directions) > 1,
                    "strengths": strengths,
                    "notes": [
                        str(item.get("conflict_note", "")).strip()
                        for item in items
                        if str(item.get("conflict_note", "")).strip()
                    ][:5],
                }
            )
        return {
            "conflict_group_count": len(groups),
            "directional_conflict_count": len(
                [item for item in groups if item.get("has_directional_conflict")]
            ),
            "groups": groups[:10],
        }

    @staticmethod
    def _derive_literature_synthesis(steps: list[WorkflowStepResult]) -> dict[str, Any]:
        consensus_findings: list[str] = []
        contested_questions: list[str] = []
        evidence_matrix: list[dict[str, Any]] = []
        evidence_gaps: list[str] = []
        for step in steps:
            parsed = step.parsed_output
            synthesis = parsed.get("literature_synthesis", {})
            if isinstance(synthesis, dict):
                consensus_findings.extend(
                    str(item) for item in synthesis.get("consensus_findings", []) if str(item).strip()
                )
                contested_questions.extend(
                    str(item) for item in synthesis.get("contested_questions", []) if str(item).strip()
                )
                for item in synthesis.get("evidence_matrix", []):
                    if isinstance(item, dict):
                        evidence_matrix.append(item)
            evidence_gaps.extend(
                str(item) for item in parsed.get("evidence_gaps", []) if str(item).strip()
            )
        return {
            "consensus_findings": list(dict.fromkeys(consensus_findings))[:8],
            "contested_questions": list(dict.fromkeys(contested_questions))[:8],
            "evidence_matrix": evidence_matrix[:12],
            "evidence_gaps": list(dict.fromkeys(evidence_gaps))[:10],
        }

    @staticmethod
    def _derive_systematic_review_draft(steps: list[WorkflowStepResult]) -> dict[str, Any]:
        review_question = ""
        review_protocol_version = ""
        study_types: list[str] = []
        inclusion_logic: list[str] = []
        exclusion_logic: list[str] = []
        screening_decisions: list[str] = []
        exclusion_reasons: list[str] = []
        evidence_balance: list[str] = []
        bias_hotspots: list[str] = []
        evidence_table_focus: list[str] = []
        evidence_table_records: list[str] = []
        review_protocol_gaps: list[str] = []
        quality_counts: dict[str, int] = {}
        screened_evidence_count = 0
        for step in steps:
            parsed = step.parsed_output
            systematic = parsed.get("systematic_review", {})
            if isinstance(systematic, dict):
                review_question = review_question or str(systematic.get("review_question", "")).strip()
                review_protocol_version = review_protocol_version or str(systematic.get("review_protocol_version", "")).strip()
                study_types.extend(
                    str(item) for item in systematic.get("study_type_hierarchy", []) if str(item).strip()
                )
                inclusion_logic.extend(
                    str(item) for item in systematic.get("inclusion_logic", []) if str(item).strip()
                )
                exclusion_logic.extend(
                    str(item) for item in systematic.get("exclusion_logic", []) if str(item).strip()
                )
                screening_decisions.extend(
                    str(item) for item in systematic.get("screening_decisions", []) if str(item).strip()
                )
                exclusion_reasons.extend(
                    str(item) for item in systematic.get("exclusion_reasons", []) if str(item).strip()
                )
                evidence_balance.extend(
                    str(item) for item in systematic.get("evidence_balance", []) if str(item).strip()
                )
                bias_hotspots.extend(
                    str(item) for item in systematic.get("bias_hotspots", []) if str(item).strip()
                )
                evidence_table_focus.extend(
                    str(item) for item in systematic.get("evidence_table_focus", []) if str(item).strip()
                )
                evidence_table_records.extend(
                    str(item) for item in systematic.get("evidence_table_records", []) if str(item).strip()
                )
                review_protocol_gaps.extend(
                    str(item) for item in systematic.get("review_protocol_gaps", []) if str(item).strip()
                )
            for item in parsed.get("evidence", []) if isinstance(parsed.get("evidence", []), list) else []:
                if not isinstance(item, dict):
                    continue
                screened_evidence_count += 1
                study_type = str(item.get("study_type", "")).strip()
                quality_grade = str(item.get("quality_grade", "")).strip().lower()
                if study_type:
                    study_types.append(study_type)
                    screening_decisions.append(f"screened evidence from {study_type}")
                if quality_grade:
                    quality_counts[quality_grade] = quality_counts.get(quality_grade, 0) + 1
                bias = str(item.get("bias_risk", "")).strip()
                if bias and bias.lower() in {"high", "medium", "unclear"}:
                    bias_hotspots.append(
                        f"{study_type or 'unknown study'} bias risk {bias.lower()}"
                    )
                    exclusion_reasons.append(
                        f"downweight {study_type or 'unknown study'} because bias risk is {bias.lower()}"
                    )
                conflict_group = str(item.get("conflict_group", "")).strip()
                if conflict_group:
                    evidence_table_focus.append(f"conflict group {conflict_group}")
                    evidence_table_records.append(
                        f"{study_type or 'unknown study'} -> conflict group {conflict_group}"
                    )
        ordered_types = list(dict.fromkeys(study_types))
        balance_lines = list(dict.fromkeys(evidence_balance))
        if quality_counts:
            balance_lines.append(
                "quality counts: "
                + ", ".join(f"{key}={value}" for key, value in sorted(quality_counts.items()))
            )
        if not inclusion_logic:
            inclusion_logic = ["Prioritize primary evidence, direct measurements, and reproducible analyses."]
        if not exclusion_logic:
            exclusion_logic = ["Downweight weakly described, high-bias, or indirect evidence."]
        if not exclusion_reasons:
            exclusion_reasons = ["Exclude or downweight evidence with unclear methods, weak traceability, or high bias."]
        if not screening_decisions:
            screening_decisions = ["Screen studies by direct relevance, study quality, and traceable methodology."]
        if not evidence_table_focus and review_question:
            evidence_table_focus = [review_question]
        if not evidence_table_records and evidence_table_focus:
            evidence_table_records = [f"focus evidence table on {item}" for item in evidence_table_focus[:3]]
        if not review_question:
            review_protocol_gaps.append("review question is still underspecified")
        if not review_protocol_version:
            review_protocol_gaps.append("review protocol version has not been declared")
            review_protocol_version = "draft-v1"
        if not ordered_types:
            review_protocol_gaps.append("study hierarchy has not been stabilized")
        if screened_evidence_count < 3:
            review_protocol_gaps.append("evidence screening depth is still shallow")
        return {
            "review_question": review_question,
            "review_protocol_version": review_protocol_version,
            "study_type_hierarchy": ordered_types[:10],
            "inclusion_logic": list(dict.fromkeys(inclusion_logic))[:6],
            "exclusion_logic": list(dict.fromkeys(exclusion_logic))[:6],
            "screening_decisions": list(dict.fromkeys(screening_decisions))[:8],
            "exclusion_reasons": list(dict.fromkeys(exclusion_reasons))[:8],
            "evidence_balance": balance_lines[:8],
            "bias_hotspots": list(dict.fromkeys(bias_hotspots))[:8],
            "evidence_table_focus": list(dict.fromkeys(evidence_table_focus))[:8],
            "evidence_table_records": list(dict.fromkeys(evidence_table_records))[:10],
            "review_protocol_gaps": list(dict.fromkeys(review_protocol_gaps))[:8],
            "screened_evidence_count": screened_evidence_count,
            "study_type_counts": {
                item: study_types.count(item)
                for item in ordered_types[:10]
            },
        }

    @staticmethod
    def _derive_systematic_review_summary(
        *,
        topic: str,
        systematic_review_summary: dict[str, Any],
        literature_synthesis: dict[str, Any],
        evidence_review_summary: dict[str, Any],
        claim_graph: dict[str, Any],
    ) -> dict[str, Any]:
        evidence = [item for item in claim_graph.get("evidence", []) if isinstance(item, dict)] if isinstance(claim_graph.get("evidence", []), list) else []
        evidence_claim_refs: dict[str, list[str]] = {}
        for edge in claim_graph.get("edges", []) if isinstance(claim_graph.get("edges", []), list) else []:
            if not isinstance(edge, dict):
                continue
            relation = str(edge.get("relation", "")).strip()
            source = str(edge.get("source", "")).strip()
            target = str(edge.get("target", "")).strip()
            if not source or not target:
                continue
            if relation == "supported_by":
                evidence_claim_refs.setdefault(target, []).append(source)
            elif relation == "supports":
                evidence_claim_refs.setdefault(source, []).append(target)
        evidence_table = []
        for index, item in enumerate(evidence, start=1):
            evidence_id = str(item.get("global_evidence_id", "") or item.get("evidence_id", "") or f"evidence::{index}").strip()
            local_evidence_id = str(item.get("evidence_id", "")).strip()
            claim_refs = ScientificWorkflow._strings(item.get("claim_refs", []))
            if not claim_refs:
                claim_refs = evidence_claim_refs.get(evidence_id, []) or evidence_claim_refs.get(local_evidence_id, [])
            evidence_table.append(
                {
                    "evidence_id": evidence_id,
                    "source_id": str(item.get("source_id", "") or item.get("citation", "")).strip(),
                    "evidence_type": str(item.get("evidence_type", "") or item.get("type", "study")).strip(),
                    "claim_refs": list(dict.fromkeys(claim_refs))[:10],
                    "effect_direction": ScientificWorkflow._effect_direction(str(item)),
                    "evidence_grade": str(item.get("quality_grade", "") or item.get("evidence_level", "") or "unclear").strip().lower(),
                    "bias_risk": str(item.get("bias_risk", "")).strip().lower(),
                    "sample_or_scope": str(item.get("sample_size", "") or item.get("scope", "")).strip(),
                    "method": str(item.get("method", "") or item.get("measurement_method", "")).strip(),
                    "limitations": ScientificWorkflow._strings(item.get("limitations", []))[:6],
                }
            )
        conflicts = ScientificWorkflow._strings(literature_synthesis.get("contested_questions", []))
        if not conflicts:
            directions = {str(item.get("effect_direction", "")) for item in evidence_table}
            if len(directions.intersection({"positive", "negative", "null"})) >= 2:
                conflicts.append("evidence table contains mixed effect directions")
        conflict_matrix = [
            {
                "conflict_id": f"conflict::{index}",
                "question": conflict,
                "possible_sources": ["method difference", "population or material difference", "measurement difference", "boundary condition"],
                "resolution_action": "stratify evidence before synthesis",
                "affected_evidence_ids": [item.get("evidence_id", "") for item in evidence_table[:8]],
            }
            for index, conflict in enumerate(conflicts, start=1)
        ]
        bias_records = [
            {
                "evidence_id": item.get("evidence_id", ""),
                "bias_risk": ScientificWorkflow._bias_risk(item),
                "bias_domains": ScientificWorkflow._bias_domains(item),
                "mitigation": "downgrade synthesis confidence or require replication"
                if ScientificWorkflow._bias_risk(item) != "low"
                else "none",
            }
            for item in evidence_table
        ]
        protocol_gaps = ScientificWorkflow._strings(systematic_review_summary.get("review_protocol_gaps", []))
        high_bias = len([item for item in bias_records if item.get("bias_risk") == "high"])
        synthesis_state = (
            "blocked"
            if protocol_gaps or not evidence_table
            else "needs_stratified_synthesis"
            if high_bias
            else "synthesis_ready"
        )
        engine = {
            "systematic_review_engine_id": f"systematic-review::{ScientificWorkflow._slugify(topic)}",
            "topic": topic,
            "review_question": str(systematic_review_summary.get("review_question", "") or topic).strip(),
            "protocol_state": (
                "complete"
                if not protocol_gaps
                and (
                    systematic_review_summary.get("screening_records")
                    or systematic_review_summary.get("screening_decisions")
                    or int(systematic_review_summary.get("screened_evidence_count", 0) or 0) > 0
                )
                else "needs_protocol_repair"
            ),
            "search_strategy": {
                "query_blocks": [topic, f"{topic} mechanism", f"{topic} conflicting evidence", f"{topic} systematic review"],
                "databases": ["arxiv", "crossref", "pubmed", "local_literature_wiki"],
                "versioning_rule": "record search query, date, source, and inclusion/exclusion change on every update",
            },
            "screening": {
                "screening_record_count": len(ScientificWorkflow._strings(systematic_review_summary.get("screening_records", []))),
                "inclusion_criteria": ScientificWorkflow._strings(systematic_review_summary.get("inclusion_logic", [])),
                "exclusion_criteria": ScientificWorkflow._strings(systematic_review_summary.get("exclusion_logic", [])),
                "protocol_gaps": protocol_gaps,
            },
            "evidence_table": evidence_table[:120],
            "evidence_grade_counts": ScientificWorkflow._count_by(evidence_table, "evidence_grade"),
            "bias_records": bias_records[:120],
            "bias_risk_counts": ScientificWorkflow._count_by(bias_records, "bias_risk"),
            "conflict_matrix": conflict_matrix[:80],
            "synthesis_state": synthesis_state,
            "meta_analysis_readiness": ScientificWorkflow._meta_analysis_readiness(evidence_table),
            "decision_implications": ScientificWorkflow._review_decision_implications(synthesis_state, conflict_matrix, evidence_review_summary),
            "scheduler_constraints": ScientificWorkflow._review_scheduler_constraints(synthesis_state, protocol_gaps, conflict_matrix),
        }
        return {
            **systematic_review_summary,
            "engine_version": "current",
            "engine": engine,
            "synthesis_state": engine["synthesis_state"],
            "evidence_table": engine["evidence_table"],
            "bias_records": engine["bias_records"],
            "conflict_matrix": engine["conflict_matrix"],
            "meta_analysis_readiness": engine["meta_analysis_readiness"],
            "decision_implications": engine["decision_implications"],
            "scheduler_constraints": engine["scheduler_constraints"],
        }

    @staticmethod
    def _derive_causal_reasoning(steps: list[WorkflowStepResult]) -> dict[str, Any]:
        assumptions: list[str] = []
        confounders: list[str] = []
        alternatives: list[str] = []
        strategies: list[str] = []
        for step in steps:
            parsed = step.parsed_output
            causal = parsed.get("causal_reasoning", {})
            if isinstance(causal, dict):
                assumptions.extend(
                    str(item) for item in causal.get("causal_assumptions", []) if str(item).strip()
                )
                confounders.extend(
                    str(item) for item in causal.get("priority_confounders", []) if str(item).strip()
                )
                alternatives.extend(
                    str(item) for item in causal.get("alternative_explanations", []) if str(item).strip()
                )
                strategy = str(causal.get("identification_strategy", "")).strip()
                if strategy:
                    strategies.append(strategy)
            confounders.extend(
                str(item) for item in parsed.get("confounders", []) if str(item).strip()
            )
            alternatives.extend(
                str(item) for item in parsed.get("alternative_explanations", []) if str(item).strip()
            )
        return {
            "causal_assumptions": list(dict.fromkeys(assumptions))[:10],
            "priority_confounders": list(dict.fromkeys(confounders))[:10],
            "alternative_explanations": list(dict.fromkeys(alternatives))[:10],
            "identification_strategies": list(dict.fromkeys(strategies))[:6],
        }

    @staticmethod
    def _derive_analysis_rigor(steps: list[WorkflowStepResult]) -> dict[str, Any]:
        power_notes: list[str] = []
        sensitivity_checks: list[str] = []
        model_comparisons: list[str] = []
        missing_data_strategies: list[str] = []
        robustness_checks: list[str] = []
        tests: list[str] = []
        for step in steps:
            parsed = step.parsed_output
            rigor = parsed.get("analysis_rigor", {})
            if isinstance(rigor, dict):
                power_notes.extend(
                    str(item) for item in rigor.get("power_analysis_notes", []) if str(item).strip()
                )
                sensitivity_checks.extend(
                    str(item) for item in rigor.get("sensitivity_checks", []) if str(item).strip()
                )
                model_comparisons.extend(
                    str(item) for item in rigor.get("model_comparisons", []) if str(item).strip()
                )
                strategy = str(rigor.get("missing_data_strategy", "")).strip()
                if strategy:
                    missing_data_strategies.append(strategy)
            robustness_checks.extend(
                str(item) for item in parsed.get("robustness_checks", []) if str(item).strip()
            )
            tests.extend(
                str(item) for item in parsed.get("statistical_tests", []) if str(item).strip()
            )
        return {
            "power_analysis_notes": list(dict.fromkeys(power_notes))[:8],
            "sensitivity_checks": list(dict.fromkeys(sensitivity_checks + robustness_checks))[:10],
            "model_comparisons": list(dict.fromkeys(model_comparisons + tests))[:10],
            "missing_data_strategies": list(dict.fromkeys(missing_data_strategies))[:6],
        }

    @staticmethod
    def _derive_autonomy_summary(
        *,
        topic: str,
        steps: list[WorkflowStepResult],
        stage_validation: dict[str, Any],
    ) -> dict[str, Any]:
        planner = next((step for step in steps if step.profile_name == "research_planner"), None)
        payload = (
            planner.parsed_output.get("autonomy_plan", {})
            if planner is not None and isinstance(planner.parsed_output.get("autonomy_plan", {}), dict)
            else {}
        )
        active_workstreams = [
            str(item) for item in payload.get("active_workstreams", []) if str(item).strip()
        ]
        autonomous_next_actions = [
            str(item) for item in payload.get("autonomous_next_actions", []) if str(item).strip()
        ]
        monitoring_signals = [
            str(item) for item in payload.get("monitoring_signals", []) if str(item).strip()
        ]
        handoff_points = [
            str(item) for item in payload.get("handoff_points", []) if str(item).strip()
        ]
        termination_conditions = [
            str(item) for item in payload.get("termination_conditions", []) if str(item).strip()
        ]
        if not autonomous_next_actions:
            autonomous_next_actions = [
                f"advance-to:{stage_validation.get('recommended_next_stage', 'review')}",
                "refresh-evidence-if-conflicts-grow",
            ]
        if not monitoring_signals:
            monitoring_signals = [
                "new negative results",
                "consensus becomes contested",
                "quality control failures accumulate",
            ]
        if not handoff_points:
            handoff_points = [
                "human review before route retirement",
                "human approval before irreversible project pivot",
            ]
        return {
            "current_objective": str(payload.get("current_objective", "")).strip() or topic,
            "active_workstreams": active_workstreams[:8],
            "autonomous_next_actions": autonomous_next_actions[:8],
            "monitoring_signals": monitoring_signals[:8],
            "handoff_points": handoff_points[:6],
            "termination_conditions": termination_conditions[:6],
            "autonomy_state": (
                "active"
                if not stage_validation.get("blockers")
                else "waiting_for_resolution"
            ),
        }

    @staticmethod
    def _derive_research_plan_summary(
        *,
        topic: str,
        steps: list[WorkflowStepResult],
        stage_validation: dict[str, Any],
    ) -> dict[str, Any]:
        planner = next((step for step in steps if step.profile_name == "research_planner"), None)
        coordinator = next((step for step in steps if step.profile_name == "coordinator"), None)
        payload = (
            planner.parsed_output.get("research_plan", {})
            if planner is not None and isinstance(planner.parsed_output.get("research_plan", {}), dict)
            else {}
        )
        if (not payload) and coordinator is not None:
            payload = {
                "planning_horizon": "next-cycle",
                "priority_questions": coordinator.parsed_output.get("open_questions", []),
                "next_cycle_experiments": [coordinator.parsed_output.get("next_experiment", "")],
                "decision_gates": coordinator.parsed_output.get("decision_points", []),
                "information_gain_priorities": coordinator.parsed_output.get("analysis_plan", []),
                "stop_conditions": [],
            }
        if not isinstance(payload, dict):
            payload = {}
        return {
            "topic": topic,
            "planning_horizon": str(payload.get("planning_horizon", "")).strip() or "next-three-cycles",
            "priority_questions": [
                str(item) for item in payload.get("priority_questions", []) if str(item).strip()
            ][:8],
            "next_cycle_experiments": [
                str(item) for item in payload.get("next_cycle_experiments", []) if str(item).strip()
            ][:8],
            "decision_gates": [
                str(item) for item in payload.get("decision_gates", []) if str(item).strip()
            ][:8],
            "information_gain_priorities": [
                str(item)
                for item in payload.get("information_gain_priorities", [])
                if str(item).strip()
            ][:8],
            "stop_conditions": [
                str(item) for item in payload.get("stop_conditions", []) if str(item).strip()
            ][:6],
            "strategy_memory_candidates": [
                str(item)
                for item in payload.get("strategy_memory_candidates", [])
                if str(item).strip()
            ][:8],
            "recommended_stage_gate": stage_validation.get("recommended_next_stage", ""),
        }

    @staticmethod
    def _derive_causal_graph_summary(
        *,
        steps: list[WorkflowStepResult],
        claim_graph: dict[str, Any],
    ) -> dict[str, Any]:
        reasoning = ScientificWorkflow._derive_causal_reasoning(steps)
        causal_model_payloads = [
            step.parsed_output.get("causal_model", {})
            for step in steps
            if isinstance(step.parsed_output.get("causal_model", {}), dict)
            and step.parsed_output.get("causal_model", {})
        ]
        confounders = reasoning.get("priority_confounders", [])
        alternatives = reasoning.get("alternative_explanations", [])
        assumptions = reasoning.get("causal_assumptions", [])
        interventions: list[str] = []
        mediators: list[str] = []
        target_outcomes: list[str] = []
        competing_mechanisms: list[str] = []
        mechanism_nodes: list[str] = []
        mechanism_edges: list[str] = []
        counterfactual_queries: list[str] = []
        counterfactual_experiments: list[str] = []
        eliminated_explanations: list[str] = []
        identifiability_risks: list[str] = []
        model_edges: list[dict[str, str]] = []
        intervention_priorities: list[str] = []
        for payload in causal_model_payloads:
            interventions.extend(
                str(item) for item in payload.get("interventions", []) if str(item).strip()
            )
            mediators.extend(
                str(item) for item in payload.get("mediators", []) if str(item).strip()
            )
            target_outcomes.extend(
                str(item) for item in payload.get("target_outcomes", []) if str(item).strip()
            )
            competing_mechanisms.extend(
                str(item) for item in payload.get("competing_mechanisms", []) if str(item).strip()
            )
            mechanism_nodes.extend(
                str(item) for item in payload.get("mechanism_nodes", []) if str(item).strip()
            )
            mechanism_edges.extend(
                str(item) for item in payload.get("mechanism_edges", []) if str(item).strip()
            )
            counterfactual_queries.extend(
                str(item) for item in payload.get("counterfactual_queries", []) if str(item).strip()
            )
            counterfactual_experiments.extend(
                str(item) for item in payload.get("counterfactual_experiments", []) if str(item).strip()
            )
            eliminated_explanations.extend(
                str(item) for item in payload.get("eliminated_explanations", []) if str(item).strip()
            )
            identifiability_risks.extend(
                str(item) for item in payload.get("identifiability_risks", []) if str(item).strip()
            )
            intervention_priorities.extend(
                str(item) for item in payload.get("intervention_priorities", []) if str(item).strip()
            )
            for item in payload.get("causal_edges", []) if isinstance(payload.get("causal_edges", []), list) else []:
                if isinstance(item, dict):
                    model_edges.append(
                        {
                            "source": str(item.get("source", "")).strip(),
                            "target": str(item.get("target", "")).strip(),
                            "relation": str(item.get("relation", "")).strip() or "causal",
                        }
                    )
        claims = claim_graph.get("claims", []) if isinstance(claim_graph.get("claims", []), list) else []
        mechanisms_from_hypotheses = [
            str(item.get("mechanism", "")).strip()
            for item in claim_graph.get("hypotheses", [])
            if isinstance(item, dict) and str(item.get("mechanism", "")).strip()
        ] if isinstance(claim_graph.get("hypotheses", []), list) else []
        mechanism_nodes.extend(mechanisms_from_hypotheses)
        hypothesis_nodes = (
            claim_graph.get("hypotheses", []) if isinstance(claim_graph.get("hypotheses", []), list) else []
        )
        focal_claims = [
            str(item.get("global_claim_id", "")).strip()
            for item in claims[:5]
            if isinstance(item, dict) and str(item.get("global_claim_id", "")).strip()
        ]
        focal_hypotheses = [
            str(item.get("global_hypothesis_id", "")).strip()
            for item in hypothesis_nodes[:5]
            if isinstance(item, dict) and str(item.get("global_hypothesis_id", "")).strip()
        ]
        edges: list[dict[str, str]] = []
        for confounder in confounders[:8]:
            target = focal_claims[0] if focal_claims else (focal_hypotheses[0] if focal_hypotheses else "research-question")
            edges.append({"source": confounder, "target": target, "relation": "confounds"})
        for alternative in alternatives[:8]:
            target = focal_hypotheses[0] if focal_hypotheses else "research-question"
            edges.append({"source": alternative, "target": target, "relation": "alternative_explanation"})
        for assumption in assumptions[:8]:
            target = focal_claims[0] if focal_claims else "research-question"
            edges.append({"source": assumption, "target": target, "relation": "assumption"})
        for mechanism in competing_mechanisms[:8]:
            target = focal_hypotheses[0] if focal_hypotheses else "research-question"
            edges.append({"source": mechanism, "target": target, "relation": "competing_mechanism"})
        for mechanism in mechanism_nodes[:8]:
            target = focal_hypotheses[0] if focal_hypotheses else "research-question"
            edges.append({"source": mechanism, "target": target, "relation": "mechanism_for"})
        edges.extend(item for item in model_edges if item.get("source") and item.get("target"))
        if not counterfactual_queries and interventions and target_outcomes:
            counterfactual_queries = [
                f"if {interventions[0]} changed, would {target_outcomes[0]} still move in the predicted direction?"
            ]
        if not counterfactual_experiments and competing_mechanisms:
            counterfactual_experiments = [
                f"design one experiment that distinguishes {competing_mechanisms[0]} from the default explanation"
            ]
        if not identifiability_risks and confounders:
            identifiability_risks = [
                "causal identification remains weak until major confounders are directly tested or blocked"
            ]
        return {
            "node_count": len(
                set(
                    confounders
                    + alternatives
                    + assumptions
                    + interventions
                    + mediators
                    + target_outcomes
                    + competing_mechanisms
                    + focal_claims
                    + focal_hypotheses
                )
            ),
            "edge_count": len(edges),
            "confounder_count": len(confounders),
            "alternative_explanation_count": len(alternatives),
            "assumption_count": len(assumptions),
            "intervention_count": len(list(dict.fromkeys(interventions))),
            "mediator_count": len(list(dict.fromkeys(mediators))),
            "target_outcome_count": len(list(dict.fromkeys(target_outcomes))),
            "competing_mechanism_count": len(list(dict.fromkeys(competing_mechanisms))),
            "mechanism_node_count": len(list(dict.fromkeys(mechanism_nodes))),
            "intervention_priorities": list(dict.fromkeys(intervention_priorities))[:8],
            "competing_mechanisms": list(dict.fromkeys(competing_mechanisms or alternatives))[:8],
            "mechanism_nodes": list(dict.fromkeys(mechanism_nodes))[:10],
            "mechanism_edges": list(dict.fromkeys(mechanism_edges))[:10],
            "counterfactual_queries": list(dict.fromkeys(counterfactual_queries))[:8],
            "counterfactual_experiments": list(dict.fromkeys(counterfactual_experiments))[:8],
            "eliminated_explanations": list(dict.fromkeys(eliminated_explanations))[:8],
            "identifiability_risks": list(dict.fromkeys(identifiability_risks))[:8],
            "edges": edges[:16],
        }

    @staticmethod
    def _derive_discipline_adaptation_summary(
        *,
        topic: str,
        steps: list[WorkflowStepResult],
        claim_graph: dict[str, Any],
    ) -> dict[str, Any]:
        payloads: list[dict[str, Any]] = []
        for step in steps:
            adaptation = step.parsed_output.get("discipline_adaptation", {})
            if isinstance(adaptation, dict) and adaptation:
                payloads.append(adaptation)
        primary_candidates: list[str] = []
        secondary: list[str] = []
        requirements: list[str] = []
        risks: list[str] = []
        artifacts: list[str] = []
        execution_modes: list[str] = []
        validation_norms: list[str] = []
        artifact_governance_requirements: list[str] = []
        for item in payloads:
            primary = str(item.get("primary_discipline", "")).strip()
            if primary:
                primary_candidates.append(primary)
            secondary.extend(str(x) for x in item.get("secondary_disciplines", []) if str(x).strip())
            requirements.extend(str(x) for x in item.get("adapter_requirements", []) if str(x).strip())
            risks.extend(str(x) for x in item.get("discipline_specific_risks", []) if str(x).strip())
            artifacts.extend(str(x) for x in item.get("artifact_expectations", []) if str(x).strip())
            execution_modes.extend(str(x) for x in item.get("execution_modes", []) if str(x).strip())
            validation_norms.extend(str(x) for x in item.get("validation_norms", []) if str(x).strip())
            artifact_governance_requirements.extend(
                str(x) for x in item.get("artifact_governance_requirements", []) if str(x).strip()
            )
        for item in claim_graph.get("asset_registry", []) if isinstance(claim_graph.get("asset_registry", []), list) else []:
            if isinstance(item, dict):
                role = str(item.get("asset_type", "")).strip()
                if role:
                    artifacts.append(role)
        lowered = topic.lower()
        inferred = "general_science"
        for token, name in [
            ("catalyst", "chemistry"),
            ("reaction", "chemistry"),
            ("process", "chemical_engineering"),
            ("simulation", "physics"),
            ("benchmark", "artificial_intelligence"),
            ("model training", "artificial_intelligence"),
            ("theorem", "mathematics"),
            ("proof", "mathematics"),
            ("signal", "physics"),
        ]:
            if token in lowered:
                inferred = name
                break
        primary_discipline = primary_candidates[0] if primary_candidates else inferred
        discipline_execution_map = {
            "chemistry": [
                "track reagent batches",
                "record calibration state",
                "store spectra and yield outputs",
            ],
            "chemical_engineering": [
                "record process conditions over time",
                "capture operating window deviations",
                "store control-loop and throughput artifacts",
            ],
            "physics": [
                "track calibration and noise sources",
                "record acquisition settings",
                "store signal traces and instrument metadata",
            ],
            "artificial_intelligence": [
                "record dataset version and code version",
                "store seeds, checkpoints, and metric curves",
                "track data leakage and baseline integrity checks",
            ],
            "mathematics": [
                "track assumptions and proof strategy",
                "store lemma dependencies and counterexample attempts",
                "preserve symbolic derivations and verification notes",
            ],
        }
        discipline_mode_map = {
            "chemistry": ["wet_lab", "measurement"],
            "chemical_engineering": ["process", "simulation", "measurement"],
            "physics": ["measurement", "calibration", "simulation"],
            "artificial_intelligence": ["computation", "training", "benchmarking"],
            "mathematics": ["theory", "proof", "counterexample_search"],
        }
        discipline_validation_map = {
            "chemistry": ["repeat critical assays", "confirm via orthogonal measurement"],
            "chemical_engineering": ["check operating stability across runs", "validate throughput and safety envelope"],
            "physics": ["repeat after recalibration", "separate signal from systematic noise"],
            "artificial_intelligence": ["re-run across seeds", "verify against leakage-safe baselines"],
            "mathematics": ["state assumptions explicitly", "test proof strategy against counterexamples"],
        }
        discipline_governance_map = {
            "chemistry": ["freeze spectra and calibration artifacts before interpretation"],
            "chemical_engineering": ["version process traces and control settings per run"],
            "physics": ["govern instrument settings and calibration lineage"],
            "artificial_intelligence": ["freeze datasets, checkpoints, and training configs per benchmark run"],
            "mathematics": ["version conjectures, lemma dependencies, and proof attempts"],
        }
        return {
            "primary_discipline": primary_discipline,
            "secondary_disciplines": list(dict.fromkeys(secondary))[:6],
            "adapter_requirements": list(
                dict.fromkeys(requirements + discipline_execution_map.get(primary_discipline, []))
            )[:10],
            "discipline_specific_risks": list(dict.fromkeys(risks))[:10],
            "artifact_expectations": list(dict.fromkeys(artifacts))[:10],
            "execution_modes": list(
                dict.fromkeys(execution_modes + discipline_mode_map.get(primary_discipline, []))
            )[:6],
            "validation_norms": list(
                dict.fromkeys(validation_norms + discipline_validation_map.get(primary_discipline, []))
            )[:8],
            "artifact_governance_requirements": list(
                dict.fromkeys(
                    artifact_governance_requirements
                    + discipline_governance_map.get(primary_discipline, [])
                )
            )[:8],
        }

    @staticmethod
    def _derive_consensus_state(steps: list[WorkflowStepResult]) -> dict[str, Any]:
        summary = {
            "consensus_status": "partial",
            "agreed_points": [],
            "unresolved_points": [],
            "adjudication_basis": [],
        }
        resolver = next((step for step in steps if step.profile_name == "conflict_resolver"), None)
        coordinator = next((step for step in steps if step.profile_name == "coordinator"), None)
        for source in [resolver, coordinator]:
            if source is None:
                continue
            payload = source.parsed_output.get("consensus_summary", {})
            if isinstance(payload, dict):
                status = str(payload.get("consensus_status", "")).strip()
                if status:
                    summary["consensus_status"] = status
                summary["agreed_points"].extend(
                    str(item) for item in payload.get("agreed_points", []) if str(item).strip()
                )
                summary["unresolved_points"].extend(
                    str(item) for item in payload.get("unresolved_points", []) if str(item).strip()
                )
                summary["adjudication_basis"].extend(
                    str(item) for item in payload.get("adjudication_basis", []) if str(item).strip()
                )
        summary["agreed_points"] = list(dict.fromkeys(summary["agreed_points"]))[:10]
        summary["unresolved_points"] = list(dict.fromkeys(summary["unresolved_points"]))[:10]
        summary["adjudication_basis"] = list(dict.fromkeys(summary["adjudication_basis"]))[:10]
        if summary["unresolved_points"] and not summary["agreed_points"]:
            summary["consensus_status"] = "unresolved"
        elif summary["agreed_points"] and not summary["unresolved_points"]:
            summary["consensus_status"] = "converged"
        return summary

    @staticmethod
    def _derive_consensus_state_machine(
        *,
        consensus_state: dict[str, Any],
        conflict_summary: dict[str, Any],
        stage_validation: dict[str, Any],
        negative_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        unresolved = len(consensus_state.get("unresolved_points", []))
        agreed = len(consensus_state.get("agreed_points", []))
        directional_conflicts = int(conflict_summary.get("directional_conflict_count", 0) or 0)
        negative_count = len(negative_results)
        if unresolved == 0 and directional_conflicts == 0 and agreed > 0:
            current_state = "converged"
        elif unresolved > 0 and (directional_conflicts > 1 or negative_count >= 2):
            current_state = "contested"
        elif unresolved > 0 or directional_conflicts > 0:
            current_state = "stressed"
        else:
            current_state = "forming"
        suggested_action = (
            "freeze_and_execute"
            if current_state == "converged"
            else "resolve_disagreements"
            if current_state == "contested"
            else "collect_discriminative_evidence"
        )
        return {
            "current_state": current_state,
            "previous_state": "forming",
            "transition_triggers": list(
                dict.fromkeys(
                    [
                        *(["unresolved_points"] if unresolved else []),
                        *(["directional_conflicts"] if directional_conflicts else []),
                        *(["negative_results"] if negative_count else []),
                        *(["stage_blockers"] if stage_validation.get("blockers") else []),
                    ]
                )
            ),
            "freeze_recommendation": current_state == "converged" and not stage_validation.get("blockers"),
            "suggested_action": suggested_action,
        }

    @staticmethod
    def _derive_termination_strategy_summary(
        *,
        topic: str,
        claim_graph: dict[str, Any],
        research_plan_summary: dict[str, Any],
        autonomy_summary: dict[str, Any],
        consensus_state_machine: dict[str, Any],
        negative_results: list[dict[str, Any]],
        execution_cycle_summary: dict[str, Any],
        belief_update_summary: dict[str, Any],
        experiment_economics_summary: dict[str, Any],
        lab_meeting_consensus_summary: dict[str, Any],
    ) -> dict[str, Any]:
        stop_conditions = [
            str(item)
            for item in research_plan_summary.get("stop_conditions", [])
            if str(item).strip()
        ]
        termination_conditions = [
            str(item)
            for item in autonomy_summary.get("termination_conditions", [])
            if str(item).strip()
        ]
        challenged_hypothesis_ids = {
            str(hypothesis_id).strip()
            for item in negative_results
            if isinstance(item, dict)
            for hypothesis_id in (
                item.get("affected_hypothesis_ids", [])
                if isinstance(item.get("affected_hypothesis_ids", []), list)
                else []
            )
            if str(hypothesis_id).strip()
        }
        hypothesis_nodes = (
            claim_graph.get("hypotheses", [])
            if isinstance(claim_graph.get("hypotheses", []), list)
            else []
        )
        retired_routes: list[dict[str, Any]] = []
        for item in hypothesis_nodes:
            if not isinstance(item, dict):
                continue
            hypothesis_id = str(
                item.get("global_hypothesis_id", "") or item.get("hypothesis_id", "")
            ).strip()
            if not hypothesis_id:
                continue
            status = str(item.get("status", "active")).strip().lower() or "active"
            challenge_count = int(item.get("challenge_count", 0) or 0)
            if status in {"deprecated", "rejected"} or challenge_count >= 2:
                retired_routes.append(
                    {
                        "route_id": hypothesis_id,
                        "status": status if status in {"deprecated", "rejected"} else "retire_candidate",
                        "reason": (
                            "workflow marked this hypothesis route as no longer viable"
                            if status in {"deprecated", "rejected"}
                            else "multiple challenge links accumulated against this route"
                        ),
                    }
                )
            elif hypothesis_id in challenged_hypothesis_ids:
                retired_routes.append(
                    {
                        "route_id": hypothesis_id,
                        "status": "retire_candidate",
                        "reason": "negative results now challenge this route",
                    }
                )

        quality_control_failed_count = int(
            execution_cycle_summary.get("quality_control_failed_count", 0) or 0
        )
        non_interpretable_review_count = int(
            execution_cycle_summary.get("non_interpretable_review_count", 0) or 0
        )
        negative_count = len(negative_results)
        consensus_state = str(consensus_state_machine.get("current_state", "")).strip().lower()

        paused_workstreams: list[dict[str, str]] = []
        if quality_control_failed_count or non_interpretable_review_count:
            paused_workstreams.append(
                {
                    "workstream": "experiment_execution",
                    "reason": "quality control reviews indicate the current execution route is not yet reliable",
                }
            )
        if consensus_state == "contested":
            paused_workstreams.append(
                {
                    "workstream": "consensus_finalization",
                    "reason": "key conclusions remain contested and should not be frozen into a stable route yet",
                }
            )
        if str(experiment_economics_summary.get("cost_pressure", "")).strip().lower() == "high":
            paused_workstreams.append(
                {
                    "workstream": "high_cost_execution",
                    "reason": "experiment economics indicates high cost pressure and recommends cheaper discriminative steps first",
                }
            )

        def _condition_hit(condition: str) -> bool:
            lowered = condition.lower()
            if any(token in lowered for token in ["negative", "failed", "failure", "did not support"]):
                return negative_count > 0
            if any(
                token in lowered
                for token in ["quality control", "calibration", "invalid run", "unusable run"]
            ):
                return quality_control_failed_count > 0 or non_interpretable_review_count > 0
            if any(token in lowered for token in ["contested", "conflict", "unresolved", "disagreement"]):
                return consensus_state in {"stressed", "contested"}
            if any(token in lowered for token in ["deprecated", "rejected", "retire route"]):
                return any(
                    item.get("status") in {"deprecated", "rejected"} for item in retired_routes
                )
            if any(token in lowered for token in ["human", "manual", "approval", "review gate"]):
                return bool(retired_routes) or consensus_state == "contested"
            return False

        stop_condition_hits = [item for item in stop_conditions if _condition_hit(item)]
        termination_condition_hits = [
            item for item in termination_conditions if _condition_hit(item)
        ]

        human_confirmation_reasons: list[str] = []
        if termination_condition_hits:
            human_confirmation_reasons.append("termination conditions were triggered")
        if any(item.get("status") in {"deprecated", "rejected"} for item in retired_routes):
            human_confirmation_reasons.append(
                "one or more hypothesis routes are ready for retirement"
            )
        if consensus_state == "contested":
            human_confirmation_reasons.append(
                "consensus is contested and route freezing would be premature"
            )
        if lab_meeting_consensus_summary.get("agenda_items"):
            human_confirmation_reasons.append(
                "lab meeting agenda still contains unresolved discussion items"
            )

        recommended_action = "continue"
        if termination_condition_hits or any(
            item.get("status") in {"deprecated", "rejected"} for item in retired_routes
        ):
            recommended_action = "terminate_or_retire_route"
        elif stop_condition_hits or paused_workstreams:
            recommended_action = "pause_and_review"

        blocked_specialists: list[str] = []
        if any(item.get("workstream") == "experiment_execution" for item in paused_workstreams):
            blocked_specialists.extend(["run_manager", "quality_control_reviewer"])
        if recommended_action == "terminate_or_retire_route":
            blocked_specialists.append("run_manager")

        preferred_specialists: list[str] = []
        if human_confirmation_reasons:
            preferred_specialists.extend(
                ["lab_meeting_moderator", "belief_updater", "critic", "safety_ethics_reviewer"]
            )
        elif paused_workstreams:
            preferred_specialists.extend(
                ["experiment_economist", "critic", "experiment_designer"]
            )

        return {
            "topic": topic,
            "stop_condition_hits": stop_condition_hits[:8],
            "termination_condition_hits": termination_condition_hits[:8],
            "paused_workstreams": paused_workstreams[:8],
            "retired_routes": retired_routes[:12],
            "human_confirmation_required": bool(human_confirmation_reasons),
            "human_confirmation_reasons": human_confirmation_reasons[:6],
            "recommended_action": recommended_action,
            "blocked_specialists": list(dict.fromkeys(blocked_specialists))[:8],
            "preferred_specialists": list(dict.fromkeys(preferred_specialists))[:6],
            "active_workstream_count": len(
                [
                    item
                    for item in autonomy_summary.get("active_workstreams", [])
                    if str(item).strip()
                ]
            ),
            "challenged_route_count": int(
                belief_update_summary.get("challenged_hypothesis_count", 0) or 0
            ),
        }

    @staticmethod
    def _derive_human_governance_checkpoint_summary(
        *,
        topic: str,
        termination_strategy_summary: dict[str, Any],
        lab_meeting_consensus_summary: dict[str, Any],
        experiment_governance_summary: dict[str, Any],
        experiment_economics_summary: dict[str, Any],
        consensus_state_machine: dict[str, Any],
        evaluation_summary: dict[str, Any],
    ) -> dict[str, Any]:
        checkpoints: list[dict[str, Any]] = []
        required_roles: list[str] = []
        checkpoint_reasons: list[str] = []
        recommendation_packet = [
            "latest route termination summary",
            "current lab meeting consensus packet",
            "experiment governance status and rerun candidates",
            "evaluation and benchmark readiness snapshot",
        ]

        if termination_strategy_summary.get("human_confirmation_required"):
            checkpoints.append(
                {
                    "checkpoint_id": "route_termination_review",
                    "scope": "route_termination",
                    "reason": "; ".join(
                        termination_strategy_summary.get("human_confirmation_reasons", [])[:2]
                    )
                    or "termination strategy requested human confirmation",
                    "required_roles": ["principal_investigator", "coordinator"],
                }
            )
            required_roles.extend(["principal_investigator", "coordinator"])
            checkpoint_reasons.extend(
                [
                    str(item)
                    for item in termination_strategy_summary.get(
                        "human_confirmation_reasons", []
                    )
                    if str(item).strip()
                ]
            )

        if (
            str(consensus_state_machine.get("current_state", "")).strip().lower()
            == "contested"
            or lab_meeting_consensus_summary.get("agenda_items")
            or lab_meeting_consensus_summary.get("blocking_concerns")
        ):
            checkpoints.append(
                {
                    "checkpoint_id": "evidence_adjudication_review",
                    "scope": "consensus_adjudication",
                    "reason": "; ".join(
                        lab_meeting_consensus_summary.get("blocking_concerns", [])[:2]
                        or lab_meeting_consensus_summary.get("agenda_items", [])[:2]
                    )
                    or "contested consensus needs adjudication before route freezing",
                    "required_roles": ["principal_investigator", "lab_meeting_moderator"],
                }
            )
            required_roles.extend(["principal_investigator", "lab_meeting_moderator"])
            checkpoint_reasons.append("contested consensus requires explicit adjudication")

        if experiment_governance_summary.get("approval_gate_needed") or experiment_governance_summary.get(
            "quarantine_runs"
        ):
            checkpoints.append(
                {
                    "checkpoint_id": "execution_governance_gate",
                    "scope": "experiment_execution",
                    "reason": "; ".join(
                        experiment_governance_summary.get("governance_risks", [])[:2]
                    )
                    or "execution governance indicates approval or quarantine action is needed",
                    "required_roles": ["protocol_owner", "quality_control_reviewer"],
                }
            )
            required_roles.extend(["protocol_owner", "quality_control_reviewer"])
            checkpoint_reasons.extend(
                [
                    str(item)
                    for item in experiment_governance_summary.get("governance_risks", [])
                    if str(item).strip()
                ]
            )

        if str(experiment_economics_summary.get("cost_pressure", "")).strip().lower() == "high":
            checkpoints.append(
                {
                    "checkpoint_id": "resource_allocation_review",
                    "scope": "experiment_economics",
                    "reason": "high cost pressure suggests a human review of resource allocation before execution",
                    "required_roles": ["principal_investigator", "experiment_economist"],
                }
            )
            required_roles.extend(["principal_investigator", "experiment_economist"])
            checkpoint_reasons.append("high cost pressure requires explicit resource review")

        if str(evaluation_summary.get("benchmark_readiness", "")).strip().lower() == "high":
            checkpoints.append(
                {
                    "checkpoint_id": "benchmark_release_gate",
                    "scope": "benchmark_release",
                    "reason": "high benchmark readiness should be signed off before publicizing or freezing conclusions",
                    "required_roles": ["principal_investigator", "coordinator"],
                }
            )
            required_roles.extend(["principal_investigator", "coordinator"])
            checkpoint_reasons.append("benchmark-ready routes require human release sign-off")

        governance_state = "clear"
        if checkpoints:
            governance_state = "review_required"
        if any(
            item.get("scope") in {"route_termination", "consensus_adjudication"}
            for item in checkpoints
            if isinstance(item, dict)
        ):
            governance_state = "decision_hold"

        approval_scope = sorted(
            {
                str(item.get("scope", "")).strip()
                for item in checkpoints
                if isinstance(item, dict) and str(item.get("scope", "")).strip()
            }
        )
        return {
            "topic": topic,
            "governance_state": governance_state,
            "required_checkpoints": checkpoints[:8],
            "checkpoint_reasons": list(dict.fromkeys(checkpoint_reasons))[:10],
            "required_roles": list(dict.fromkeys(required_roles))[:10],
            "approval_scope": approval_scope[:8],
            "must_pause_execution": any(
                item.get("scope") in {"experiment_execution", "route_termination"}
                for item in checkpoints
                if isinstance(item, dict)
            ),
            "human_approval_checkpoint_count": len(checkpoints),
            "recommended_decision_packet": recommendation_packet,
        }

    @staticmethod
    def _derive_benchmark_harness_summary(
        *,
        topic: str,
        evaluation_summary: dict[str, Any],
        systematic_review_summary: dict[str, Any],
        execution_cycle_summary: dict[str, Any],
        asset_graph_summary: dict[str, Any],
        graph_reference_summary: dict[str, Any],
        route_temperature_summary: dict[str, Any],
        typed_research_graph_history: dict[str, Any],
        mechanism_reasoning_summary: dict[str, Any],
        hypothesis_family_lifecycle_summary: dict[str, Any],
        human_governance_checkpoint_summary: dict[str, Any],
    ) -> dict[str, Any]:
        benchmark_axes = [
            "literature_coverage",
            "causal_identifiability",
            "experiment_reliability",
            "asset_governance",
            "family_governance",
            "graph_engagement",
        ]
        benchmark_gaps: list[str] = []
        if str(evaluation_summary.get("systematic_review_readiness", "")).strip().lower() == "low":
            benchmark_gaps.append("systematic review protocol is not mature enough")
        if str(evaluation_summary.get("causal_identifiability", "")).strip().lower() == "low":
            benchmark_gaps.append("causal identifiability remains weak")
        if int(execution_cycle_summary.get("quality_control_failed_count", 0) or 0) > 0:
            benchmark_gaps.append("quality-controlled execution still has failed runs")
        if str(evaluation_summary.get("asset_governance_readiness", "")).strip().lower() == "low":
            benchmark_gaps.append("artifact governance is incomplete")
        if str(evaluation_summary.get("family_governance_readiness", "")).strip().lower() == "low":
            benchmark_gaps.append("hypothesis family governance is immature")
        if human_governance_checkpoint_summary.get("human_approval_checkpoint_count", 0):
            benchmark_gaps.append("human governance checkpoints are still open")

        release_readiness = "low"
        if not benchmark_gaps and str(evaluation_summary.get("benchmark_readiness", "")).strip().lower() == "high":
            release_readiness = "high"
        elif str(evaluation_summary.get("benchmark_readiness", "")).strip().lower() in {"medium", "high"}:
            release_readiness = "medium"

        regression_checks = [
            "compare against previous benchmark readiness",
            "detect repeated reuse of retired routes",
            "track support density and graph growth trend",
        ]
        fail_fast_checks = [
            "stop if quality-controlled execution fails again",
            "stop if contested consensus widens after new evidence",
            "stop if causal identifiability remains low after a discriminative experiment",
        ]
        if mechanism_reasoning_summary.get("counterfactual_experiments"):
            fail_fast_checks.append("run the highest-value counterfactual discriminative experiment first")
        if route_temperature_summary.get("cooling_candidates"):
            regression_checks.append("ensure cooling candidates are not reintroduced without explicit justification")

        benchmark_ready = release_readiness in {"medium", "high"} and not benchmark_gaps
        return {
            "topic": topic,
            "benchmark_ready": benchmark_ready,
            "release_readiness": release_readiness,
            "benchmark_axes": benchmark_axes,
            "regression_checks": regression_checks[:8],
            "fail_fast_checks": fail_fast_checks[:8],
            "benchmark_gaps": benchmark_gaps[:10],
            "historical_regression_pressure": str(
                evaluation_summary.get("graph_growth_trend", "stable")
            ).strip(),
            "evidence_gate": str(
                evaluation_summary.get("systematic_review_readiness", "low")
            ).strip(),
            "reproducibility_gate": (
                "high"
                if int(execution_cycle_summary.get("quality_control_failed_count", 0) or 0) == 0
                and int(typed_research_graph_history.get("snapshot_count", 0) or 0) >= 1
                else "medium"
                if int(execution_cycle_summary.get("quality_control_review_count", 0) or 0) > 0
                else "low"
            ),
            "governance_gate": str(
                human_governance_checkpoint_summary.get("governance_state", "clear")
            ).strip(),
            "artifact_lineage_depth": int(asset_graph_summary.get("lineage_edge_count", 0) or 0),
            "graph_reference_count": int(graph_reference_summary.get("node_ref_count", 0) or 0)
            + int(graph_reference_summary.get("edge_ref_count", 0) or 0),
            "mechanism_competition_count": len(
                mechanism_reasoning_summary.get("competing_mechanisms", [])
                if isinstance(mechanism_reasoning_summary.get("competing_mechanisms", []), list)
                else []
            ),
            "hypothesis_family_count": int(
                hypothesis_family_lifecycle_summary.get("family_count", 0) or 0
            ),
        }

    @staticmethod
    def _derive_hypothesis_tree(claim_graph: dict[str, Any]) -> dict[str, Any]:
        hypotheses = claim_graph.get("hypotheses", [])
        relations = claim_graph.get("hypothesis_relations", [])
        relation_counts: dict[str, int] = {}
        roots: list[str] = []
        children = {str(item.get("target", "")).strip() for item in relations if isinstance(item, dict)}
        for item in relations:
            if not isinstance(item, dict):
                continue
            relation = str(item.get("relation", "")).strip() or "related_to"
            relation_counts[relation] = relation_counts.get(relation, 0) + 1
        for item in hypotheses:
            if not isinstance(item, dict):
                continue
            global_id = str(item.get("global_hypothesis_id", "")).strip()
            if global_id and global_id not in children:
                roots.append(global_id)
        return {
            "hypothesis_count": len(hypotheses),
            "relation_count": len(relations),
            "relation_counts": relation_counts,
            "root_hypotheses": roots[:12],
            "relations": relations[:20],
        }

    @staticmethod
    def _derive_program_management_summary(
        *,
        topic: str,
        steps: list[WorkflowStepResult],
        research_plan_summary: dict[str, Any],
        autonomy_summary: dict[str, Any],
        route_temperature_summary: dict[str, Any],
    ) -> dict[str, Any]:
        planner_payload = next(
            (
                step.parsed_output.get("program_management", {})
                for step in steps
                if step.profile_name == "research_planner"
                and isinstance(step.parsed_output.get("program_management", {}), dict)
                and step.parsed_output.get("program_management", {})
            ),
            {},
        )
        return {
            "topic": topic,
            "program_objective": str(
                planner_payload.get("program_objective", "") or autonomy_summary.get("current_objective", "")
            ).strip(),
            "primary_workstream": str(
                planner_payload.get("primary_workstream", "")
                or (autonomy_summary.get("active_workstreams", [""])[:1] or [""])[0]
            ).strip(),
            "secondary_workstreams": [
                str(item)
                for item in planner_payload.get("secondary_workstreams", [])
                if str(item).strip()
            ][:8],
            "milestones": [
                str(item)
                for item in planner_payload.get("milestones", [])
                if str(item).strip()
            ][:8]
            or [str(item) for item in research_plan_summary.get("decision_gates", []) if str(item).strip()][:6],
            "resource_allocations": [
                str(item)
                for item in planner_payload.get("resource_allocations", [])
                if str(item).strip()
            ][:8],
            "review_cadence": str(planner_payload.get("review_cadence", "")).strip() or "every major cycle",
            "pivot_triggers": [
                str(item)
                for item in planner_payload.get("pivot_triggers", [])
                if str(item).strip()
            ][:8]
            or [str(item) for item in research_plan_summary.get("stop_conditions", []) if str(item).strip()][:4],
            "route_temperature": str(route_temperature_summary.get("global_temperature", "unknown")).strip(),
        }

    @staticmethod
    def _derive_domain_playbook_summary(
        *,
        topic: str,
        steps: list[WorkflowStepResult],
        discipline_adaptation_summary: dict[str, Any],
    ) -> dict[str, Any]:
        planner_payload = next(
            (
                step.parsed_output.get("domain_playbooks", [])
                for step in steps
                if step.profile_name == "research_planner"
                and isinstance(step.parsed_output.get("domain_playbooks", []), list)
                and step.parsed_output.get("domain_playbooks", [])
            ),
            [],
        )
        records = [item for item in planner_payload if isinstance(item, dict)]
        return {
            "topic": topic,
            "primary_discipline": str(
                discipline_adaptation_summary.get("primary_discipline", "general_science")
            ).strip(),
            "playbook_count": len(records),
            "disciplines": [
                str(item.get("discipline", "")).strip()
                for item in records
                if str(item.get("discipline", "")).strip()
            ][:10],
            "execution_patterns": [
                str(item.get("execution_pattern", "")).strip()
                for item in records
                if str(item.get("execution_pattern", "")).strip()
            ][:10],
            "validation_patterns": [
                str(item.get("validation_pattern", "")).strip()
                for item in records
                if str(item.get("validation_pattern", "")).strip()
            ][:10],
            "failure_modes": list(
                dict.fromkeys(
                    [
                        str(mode).strip()
                        for item in records
                        for mode in (
                            item.get("failure_modes", [])
                            if isinstance(item.get("failure_modes", []), list)
                            else []
                        )
                        if str(mode).strip()
                    ]
                )
            )[:12],
        }

    @staticmethod
    def _derive_hypothesis_validation_summary(
        *,
        steps: list[WorkflowStepResult],
        claim_graph: dict[str, Any],
    ) -> dict[str, Any]:
        payload = next(
            (
                step.parsed_output.get("hypothesis_validations", [])
                for step in steps
                if step.profile_name == "hypothesis_generator"
                and isinstance(step.parsed_output.get("hypothesis_validations", []), list)
                and step.parsed_output.get("hypothesis_validations", [])
            ),
            [],
        )
        validations = [item for item in payload if isinstance(item, dict)]
        if not validations:
            validations = ScientificWorkflow._infer_hypothesis_validations(claim_graph)
        if not validations:
            return {}
        def _avg(field: str) -> float:
            values = []
            for item in validations:
                value = item.get(field)
                if isinstance(value, (int, float)):
                    values.append(float(value))
            return round(sum(values) / len(values), 3) if values else 0.0

        recommendation_counts: dict[str, int] = {}
        for item in validations:
            recommendation = str(item.get("overall_recommendation", "")).strip().lower() or "unknown"
            recommendation_counts[recommendation] = recommendation_counts.get(recommendation, 0) + 1

        low_falsifiability = [
            str(item.get("hypothesis_id", "")).strip()
            for item in validations
            if float(item.get("falsifiability_score", 0) or 0) < 0.5
            and str(item.get("hypothesis_id", "")).strip()
        ]
        low_novelty = [
            str(item.get("hypothesis_id", "")).strip()
            for item in validations
            if float(item.get("novelty_score", 0) or 0) < 0.5
            and str(item.get("hypothesis_id", "")).strip()
        ]
        weak_testability = [
            str(item.get("hypothesis_id", "")).strip()
            for item in validations
            if float(item.get("testability_score", 0) or 0) < 0.5
            and str(item.get("hypothesis_id", "")).strip()
        ]
        low_mechanism = [
            str(item.get("hypothesis_id", "")).strip()
            for item in validations
            if float(item.get("mechanistic_coherence_score", 0) or 0) < 0.5
            and str(item.get("hypothesis_id", "")).strip()
        ]
        weak_evidence = [
            str(item.get("hypothesis_id", "")).strip()
            for item in validations
            if float(item.get("evidence_grounding_score", 0) or 0) < 0.5
            and str(item.get("hypothesis_id", "")).strip()
        ]
        validation_matrix = [
            {
                "hypothesis_id": str(item.get("hypothesis_id", "")).strip(),
                "novelty_score": float(item.get("novelty_score", 0) or 0),
                "falsifiability_score": float(item.get("falsifiability_score", 0) or 0),
                "testability_score": float(item.get("testability_score", 0) or 0),
                "mechanistic_coherence_score": float(item.get("mechanistic_coherence_score", 0) or 0),
                "evidence_grounding_score": float(item.get("evidence_grounding_score", 0) or 0),
                "overall_recommendation": str(item.get("overall_recommendation", "")).strip() or "observe",
                "validator_flags": item.get("validator_flags", []) if isinstance(item.get("validator_flags", []), list) else [],
            }
            for item in validations
        ]
        return {
            "validation_count": len(validations),
            "recommendation_counts": recommendation_counts,
            "average_novelty_score": _avg("novelty_score"),
            "average_falsifiability_score": _avg("falsifiability_score"),
            "average_testability_score": _avg("testability_score"),
            "average_mechanistic_coherence_score": _avg("mechanistic_coherence_score"),
            "average_evidence_grounding_score": _avg("evidence_grounding_score"),
            "low_falsifiability_hypotheses": low_falsifiability[:10],
            "low_novelty_hypotheses": low_novelty[:10],
            "weak_testability_hypotheses": weak_testability[:10],
            "low_mechanism_hypotheses": low_mechanism[:10],
            "weak_evidence_hypotheses": weak_evidence[:10],
            "validator_flag_count": (
                len(low_falsifiability)
                + len(low_novelty)
                + len(weak_testability)
                + len(low_mechanism)
                + len(weak_evidence)
            ),
            "hypothesis_count": len(
                claim_graph.get("hypotheses", [])
                if isinstance(claim_graph.get("hypotheses", []), list)
                else []
            ),
            "validator_dimensions": [
                "novelty",
                "falsifiability",
                "testability",
                "mechanistic_coherence",
                "evidence_grounding",
            ],
            "records": validation_matrix[:50],
        }

    @staticmethod
    def _infer_hypothesis_validations(claim_graph: dict[str, Any]) -> list[dict[str, Any]]:
        hypotheses = claim_graph.get("hypotheses", [])
        if not isinstance(hypotheses, list):
            return []
        validations: list[dict[str, Any]] = []
        for item in hypotheses:
            if not isinstance(item, dict):
                continue
            hypothesis_id = str(item.get("hypothesis_id", "") or item.get("global_hypothesis_id", "")).strip()
            if not hypothesis_id:
                continue
            prediction = str(item.get("prediction", "")).strip()
            mechanism = str(item.get("mechanism", "")).strip()
            falsifiability_test = str(item.get("falsifiability_test", "")).strip()
            assumptions = item.get("assumptions", []) if isinstance(item.get("assumptions", []), list) else []
            failure_conditions = item.get("failure_conditions", []) if isinstance(item.get("failure_conditions", []), list) else []
            evidence_refs = item.get("evidence_refs", []) if isinstance(item.get("evidence_refs", []), list) else []
            falsifiability_score = 0.85 if falsifiability_test or failure_conditions else 0.35
            testability_score = 0.8 if prediction and (falsifiability_test or failure_conditions) else 0.4
            mechanism_score = 0.8 if mechanism and assumptions else 0.45 if mechanism else 0.25
            evidence_score = 0.75 if evidence_refs else 0.45
            novelty_score = 0.65
            flags: list[str] = []
            if falsifiability_score < 0.5:
                flags.append("missing_falsification_test")
            if testability_score < 0.5:
                flags.append("weak_testability")
            if mechanism_score < 0.5:
                flags.append("mechanism_underdeveloped")
            if evidence_score < 0.5:
                flags.append("weak_evidence_grounding")
            recommendation = "advance" if not flags else "revise" if len(flags) <= 2 else "hold"
            validations.append(
                {
                    "hypothesis_id": hypothesis_id,
                    "novelty_score": novelty_score,
                    "falsifiability_score": falsifiability_score,
                    "testability_score": testability_score,
                    "mechanistic_coherence_score": mechanism_score,
                    "evidence_grounding_score": evidence_score,
                    "overall_recommendation": recommendation,
                    "validator_flags": flags,
                }
            )
        return validations

    @staticmethod
    def _derive_hypothesis_gate_summary(
        *,
        steps: list[WorkflowStepResult],
        hypothesis_validation_summary: dict[str, Any],
    ) -> dict[str, Any]:
        payload = next(
            (
                step.parsed_output.get("hypothesis_gates", [])
                for step in steps
                if step.profile_name == "hypothesis_generator"
                and isinstance(step.parsed_output.get("hypothesis_gates", []), list)
                and step.parsed_output.get("hypothesis_gates", [])
            ),
            [],
        )
        gate_items = [item for item in payload if isinstance(item, dict)]
        if not gate_items:
            gate_items = ScientificWorkflow._infer_hypothesis_gates(hypothesis_validation_summary)
        gate_counts: dict[str, int] = {}
        blocked: list[str] = []
        revise: list[str] = []
        accepted: list[str] = []
        for item in gate_items:
            decision = str(item.get("gate_decision", "")).strip().lower() or "observe"
            gate_counts[decision] = gate_counts.get(decision, 0) + 1
            hypothesis_id = str(item.get("hypothesis_id", "")).strip()
            if decision == "reject" and hypothesis_id:
                blocked.append(hypothesis_id)
            elif decision == "revise" and hypothesis_id:
                revise.append(hypothesis_id)
            elif decision == "accept" and hypothesis_id:
                accepted.append(hypothesis_id)
        gate_state = "clear"
        if blocked:
            gate_state = "blocked"
        elif revise:
            gate_state = "revision_required"
        return {
            "gate_state": gate_state,
            "gate_counts": gate_counts,
            "accepted_hypotheses": accepted[:10],
            "revise_hypotheses": revise[:10],
            "blocked_hypotheses": blocked[:10],
            "validator_flag_count": int(hypothesis_validation_summary.get("validator_flag_count", 0) or 0),
            "records": gate_items[:20],
        }

    @staticmethod
    def _infer_hypothesis_gates(hypothesis_validation_summary: dict[str, Any]) -> list[dict[str, Any]]:
        records = hypothesis_validation_summary.get("records", [])
        if not isinstance(records, list):
            return []
        gates: list[dict[str, Any]] = []
        for item in records:
            if not isinstance(item, dict):
                continue
            hypothesis_id = str(item.get("hypothesis_id", "")).strip()
            if not hypothesis_id:
                continue
            flags = item.get("validator_flags", []) if isinstance(item.get("validator_flags", []), list) else []
            low_scores = [
                float(item.get("falsifiability_score", 0) or 0),
                float(item.get("testability_score", 0) or 0),
                float(item.get("mechanistic_coherence_score", 0) or 0),
                float(item.get("evidence_grounding_score", 0) or 0),
            ]
            if any(score < 0.35 for score in low_scores) or len(flags) >= 3:
                decision = "reject"
            elif flags or any(score < 0.5 for score in low_scores):
                decision = "revise"
            else:
                decision = "accept"
            gates.append(
                {
                    "hypothesis_id": hypothesis_id,
                    "gate_decision": decision,
                    "reason": "; ".join(str(flag) for flag in flags) or "validator scores clear",
                    "required_follow_up": [
                        str(flag).replace("_", " ")
                        for flag in flags
                    ],
                }
            )
        return gates

    @staticmethod
    def _derive_mechanism_family_lifecycle_summary(
        *,
        steps: list[WorkflowStepResult],
        mechanism_reasoning_summary: dict[str, Any],
    ) -> dict[str, Any]:
        mechanism_items: list[dict[str, Any]] = []
        for step in steps:
            payload = step.parsed_output.get("mechanism_map", [])
            if isinstance(payload, list):
                mechanism_items.extend(item for item in payload if isinstance(item, dict))
        family_status_counts: dict[str, dict[str, int]] = {}
        retire_candidates: list[str] = []
        revive_candidates: list[str] = []
        for item in mechanism_items:
            family = str(item.get("family", "")).strip() or "general"
            status = str(item.get("status", "")).strip().lower() or "active"
            family_status_counts.setdefault(family, {})
            family_status_counts[family][status] = family_status_counts[family].get(status, 0) + 1
            mechanism_id = str(item.get("mechanism_id", "")).strip()
            if mechanism_id and (status in {"deprecated", "rejected"} or len(item.get("challenge_signals", []) if isinstance(item.get("challenge_signals", []), list) else []) >= 2):
                retire_candidates.append(family)
            if mechanism_id and status in {"revised", "paused"} and (item.get("revive_conditions", []) if isinstance(item.get("revive_conditions", []), list) else []):
                revive_candidates.append(family)
        return {
            "family_count": len(family_status_counts),
            "family_status_counts": family_status_counts,
            "retire_candidates": list(dict.fromkeys(retire_candidates))[:10],
            "revive_candidates": list(dict.fromkeys(revive_candidates))[:10],
            "mechanism_count": int(mechanism_reasoning_summary.get("mechanism_count", 0) or 0),
        }

    @staticmethod
    def _derive_artifact_provenance_summary(
        *,
        claim_graph: dict[str, Any],
        run_manifest: dict[str, Any],
        asset_graph_summary: dict[str, Any],
    ) -> dict[str, Any]:
        artifacts = run_manifest.get("artifacts", []) if isinstance(run_manifest.get("artifacts", []), list) else []
        input_files = run_manifest.get("input_files", []) if isinstance(run_manifest.get("input_files", []), list) else []
        asset_registry = claim_graph.get("asset_registry", []) if isinstance(claim_graph.get("asset_registry", []), list) else []
        provenance_edges = int(asset_graph_summary.get("lineage_edge_count", 0) or 0) + len(artifacts) + len(input_files)
        governed_artifacts = [
            item for item in artifacts if isinstance(item, dict) and str(item.get("scope", "")).strip()
        ]
        return {
            "artifact_count": len(artifacts),
            "input_file_count": len(input_files),
            "registered_asset_count": len(asset_registry),
            "provenance_edge_count": provenance_edges,
            "governed_artifact_count": len(governed_artifacts),
            "ungoverned_artifact_count": max(0, len(artifacts) - len(governed_artifacts)),
            "artifact_types": asset_graph_summary.get("artifact_types", {}),
        }

    @staticmethod
    def _derive_program_portfolio_summary(
        *,
        program_management_summary: dict[str, Any],
        route_temperature_summary: dict[str, Any],
        experiment_economics_summary: dict[str, Any],
        termination_strategy_summary: dict[str, Any],
    ) -> dict[str, Any]:
        primary = str(program_management_summary.get("primary_workstream", "")).strip()
        secondary = [
            str(item) for item in program_management_summary.get("secondary_workstreams", []) if str(item).strip()
        ]
        paused = [
            str(item.get("workstream", "")).strip()
            for item in termination_strategy_summary.get("paused_workstreams", [])
            if isinstance(item, dict) and str(item.get("workstream", "")).strip()
        ]
        retired = [
            str(item.get("route_id", "")).strip()
            for item in termination_strategy_summary.get("retired_routes", [])
            if isinstance(item, dict) and str(item.get("route_id", "")).strip()
        ]
        exploratory = secondary[:]
        if primary:
            active = [primary]
        else:
            active = []
        return {
            "active_routes": active[:6],
            "exploratory_routes": exploratory[:8],
            "paused_routes": paused[:8],
            "retired_routes": retired[:8],
            "portfolio_pressure": str(route_temperature_summary.get("global_temperature", "unknown")).strip(),
            "cost_pressure": str(experiment_economics_summary.get("cost_pressure", "medium")).strip(),
        }

    @staticmethod
    def _derive_formal_review_record_summary(
        *,
        systematic_review_summary: dict[str, Any],
    ) -> dict[str, Any]:
        screening_records = [
            str(item) for item in systematic_review_summary.get("screening_records", []) if str(item).strip()
        ]
        evidence_table_records = [
            str(item) for item in systematic_review_summary.get("evidence_table_records", []) if str(item).strip()
        ]
        review_updates = [
            str(item) for item in systematic_review_summary.get("review_record_updates", []) if str(item).strip()
        ]
        exclusion_reasons = [
            str(item) for item in systematic_review_summary.get("exclusion_reasons", []) if str(item).strip()
        ]
        return {
            "review_protocol_version": str(systematic_review_summary.get("review_protocol_version", "")).strip(),
            "screening_record_count": len(screening_records),
            "evidence_table_record_count": len(evidence_table_records),
            "review_update_count": len(review_updates),
            "exclusion_reason_count": len(exclusion_reasons),
            "screening_records": screening_records[:12],
            "evidence_table_records": evidence_table_records[:12],
            "review_record_updates": review_updates[:12],
        }

    @staticmethod
    def _derive_research_route_search_summary(
        *,
        topic: str,
        research_plan_summary: dict[str, Any],
        autonomy_summary: dict[str, Any],
        systematic_review_summary: dict[str, Any],
        experiment_governance_summary: dict[str, Any],
        experiment_economics_summary: dict[str, Any],
        failure_intelligence_summary: dict[str, Any],
        route_temperature_summary: dict[str, Any],
        evaluation_summary: dict[str, Any],
        human_governance_checkpoint_summary: dict[str, Any],
        benchmark_harness_summary: dict[str, Any],
        hypothesis_validation_summary: dict[str, Any],
        typed_research_graph_history: dict[str, Any],
    ) -> dict[str, Any]:
        candidates: list[dict[str, Any]] = []

        def add_candidate(
            action_type: str,
            rationale: str,
            information_gain: int,
            cost: int,
            time_cost: int,
            risk: int,
            governance_burden: int,
        ) -> None:
            score = (information_gain * 3) - (cost + time_cost + risk + governance_burden)
            candidates.append(
                {
                    "action_type": action_type,
                    "rationale": rationale,
                    "information_gain_score": information_gain,
                    "cost_score": cost,
                    "time_score": time_cost,
                    "risk_score": risk,
                    "governance_burden_score": governance_burden,
                    "route_value_score": score,
                }
            )

        if systematic_review_summary.get("review_protocol_gaps") or systematic_review_summary.get("bias_hotspots"):
            add_candidate(
                "review_more_literature",
                "systematic review still has protocol or bias gaps",
                3,
                1,
                1,
                1,
                0,
            )
        if (
            hypothesis_validation_summary.get("low_falsifiability_hypotheses")
            or hypothesis_validation_summary.get("weak_testability_hypotheses")
            or hypothesis_validation_summary.get("low_novelty_hypotheses")
        ):
            add_candidate(
                "refine_hypothesis",
                "hypothesis validators indicate low novelty, falsifiability, or testability",
                4,
                1,
                1,
                1,
                0,
            )
        if research_plan_summary.get("next_cycle_experiments") or benchmark_harness_summary.get("benchmark_gaps"):
            add_candidate(
                "design_discriminative_experiment",
                "next cycle requires a discriminative experiment to improve evidence or benchmark readiness",
                5,
                2 if str(experiment_economics_summary.get("cost_pressure", "")).strip().lower() == "high" else 1,
                2 if str(experiment_economics_summary.get("time_pressure", "")).strip().lower() == "high" else 1,
                1,
                1 if human_governance_checkpoint_summary.get("must_pause_execution") else 0,
            )
        if experiment_governance_summary.get("approval_gate_needed") or experiment_governance_summary.get("quarantine_runs"):
            add_candidate(
                "resolve_execution_governance",
                "experiment governance has approval or quarantine issues",
                3,
                1,
                1,
                2,
                3,
            )
        if str(route_temperature_summary.get("global_temperature", "")).strip().lower() == "hot":
            add_candidate(
                "pause_or_retire_route",
                "route temperature indicates repeated pressure or reuse of weak routes",
                4,
                0,
                0,
                1,
                2,
            )
        if human_governance_checkpoint_summary.get("human_approval_checkpoint_count", 0) > 0:
            add_candidate(
                "request_human_adjudication",
                "open governance checkpoints require explicit human review",
                3,
                0,
                1,
                0,
                4,
            )
        if (
            str(evaluation_summary.get("benchmark_readiness", "")).strip().lower() in {"medium", "high"}
            and not benchmark_harness_summary.get("benchmark_gaps")
        ):
            add_candidate(
                "benchmark_route",
                "route appears mature enough for a benchmark or externalized evaluation pass",
                4,
                2,
                2,
                1,
                2,
            )
        if failure_intelligence_summary.get("theoretical_failures"):
            add_candidate(
                "compare_mechanisms",
                "theoretical failures suggest competing mechanisms should be re-ranked",
                4,
                1,
                1,
                1,
                0,
            )

        candidates = sorted(
            candidates,
            key=lambda item: (
                int(item.get("route_value_score", 0)),
                int(item.get("information_gain_score", 0)),
                -int(item.get("governance_burden_score", 0)),
            ),
            reverse=True,
        )
        best_next_action = candidates[0]["action_type"] if candidates else "continue_current_route"
        return {
            "topic": topic,
            "candidate_count": len(candidates),
            "best_next_action": best_next_action,
            "candidate_actions": candidates[:8],
            "search_state": {
                "active_workstreams": len(
                    [
                        item
                        for item in autonomy_summary.get("active_workstreams", [])
                        if str(item).strip()
                    ]
                ),
                "graph_snapshot_count": int(typed_research_graph_history.get("snapshot_count", 0) or 0),
                "route_temperature": str(route_temperature_summary.get("global_temperature", "unknown")).strip(),
                "benchmark_readiness": str(evaluation_summary.get("benchmark_readiness", "low")).strip(),
            },
        }

    @staticmethod
    def _derive_theoretical_hypothesis_tree_summary(
        *,
        claim_graph: dict[str, Any],
        hypothesis_tree: dict[str, Any],
        discipline_adaptation_summary: dict[str, Any],
    ) -> dict[str, Any]:
        relations = (
            claim_graph.get("hypothesis_relations", [])
            if isinstance(claim_graph.get("hypothesis_relations", []), list)
            else []
        )
        hypotheses = (
            claim_graph.get("hypotheses", [])
            if isinstance(claim_graph.get("hypotheses", []), list)
            else []
        )
        parent_child_count = 0
        mechanism_count = 0
        support_count = 0
        contradiction_count = 0
        family_map: dict[str, list[str]] = {}
        family_status_counts: dict[str, dict[str, int]] = {}
        challenge_frontier: list[str] = []
        for item in hypotheses:
            if not isinstance(item, dict):
                continue
            hypothesis_id = str(item.get("global_hypothesis_id", "")).strip()
            if not hypothesis_id:
                continue
            family = str(item.get("name", "")).strip().split(":")[0].strip() or "general"
            family_map.setdefault(family, []).append(hypothesis_id)
            status = str(item.get("status", "active")).strip() or "active"
            family_status_counts.setdefault(family, {})
            family_status_counts[family][status] = family_status_counts[family].get(status, 0) + 1
            if int(item.get("challenge_count", 0) or 0) > 0:
                challenge_frontier.append(hypothesis_id)
        for item in relations:
            if not isinstance(item, dict):
                continue
            relation = str(item.get("relation", "")).strip().lower()
            if relation in {"parent_of", "child_of", "derives_from"}:
                parent_child_count += 1
            if relation in {"mechanism_for", "explains", "mediates"}:
                mechanism_count += 1
            if relation in {"supports", "strengthens"}:
                support_count += 1
            if relation in {"contradicts", "competes_with", "refutes"}:
                contradiction_count += 1
        primary_discipline = str(
            discipline_adaptation_summary.get("primary_discipline", "general_science")
        ).strip()
        retire_candidates = [
            family
            for family, counts in family_status_counts.items()
            if int(counts.get("deprecated", 0) or 0) + int(counts.get("rejected", 0) or 0)
            >= max(1, len(family_map.get(family, [])) // 2)
        ]
        revive_candidates = [
            family
            for family, counts in family_status_counts.items()
            if int(counts.get("revised", 0) or 0) > 0 and int(counts.get("active", 0) or 0) > 0
        ]
        return {
            "primary_discipline": primary_discipline,
            "root_hypotheses": hypothesis_tree.get("root_hypotheses", []),
            "family_count": len(family_map),
            "hypothesis_families": {key: value[:6] for key, value in list(family_map.items())[:8]},
            "family_status_counts": family_status_counts,
            "parent_child_relation_count": parent_child_count,
            "mechanism_relation_count": mechanism_count,
            "support_relation_count": support_count,
            "contradiction_relation_count": contradiction_count,
            "challenge_frontier": list(dict.fromkeys(challenge_frontier))[:10],
            "retire_candidates": retire_candidates[:8],
            "revive_candidates": revive_candidates[:8],
            "theory_maturity": (
                "structured"
                if parent_child_count or mechanism_count
                else "flat"
            ),
        }

    @staticmethod
    def _derive_mechanism_reasoning_summary(
        *,
        steps: list[WorkflowStepResult],
        causal_graph_summary: dict[str, Any],
    ) -> dict[str, Any]:
        mechanism_map_items: list[dict[str, Any]] = []
        for step in steps:
            payload = step.parsed_output.get("mechanism_map", [])
            if isinstance(payload, list):
                mechanism_map_items.extend(item for item in payload if isinstance(item, dict))
        family_counts: dict[str, int] = {}
        competing_pairs: list[str] = []
        status_counts: dict[str, int] = {}
        retire_candidates: list[str] = []
        revive_candidates: list[str] = []
        challenged_mechanisms: list[str] = []
        for item in mechanism_map_items:
            family = str(item.get("family", "")).strip() or "general"
            family_counts[family] = family_counts.get(family, 0) + 1
            label = str(item.get("label", "")).strip()
            mechanism_id = str(item.get("mechanism_id", "")).strip() or label
            status = str(item.get("status", "")).strip().lower() or "active"
            status_counts[status] = status_counts.get(status, 0) + 1
            for rival in item.get("competes_with", []) if isinstance(item.get("competes_with", []), list) else []:
                rival_text = str(rival).strip()
                if label and rival_text:
                    competing_pairs.append(f"{label} <> {rival_text}")
            challenge_signals = (
                item.get("challenge_signals", [])
                if isinstance(item.get("challenge_signals", []), list)
                else []
            )
            revive_conditions = (
                item.get("revive_conditions", [])
                if isinstance(item.get("revive_conditions", []), list)
                else []
            )
            if challenge_signals and mechanism_id:
                challenged_mechanisms.append(mechanism_id)
            if status in {"deprecated", "rejected"} or len(challenge_signals) >= 2:
                retire_candidates.append(mechanism_id)
            if status in {"revised", "paused"} and revive_conditions:
                revive_candidates.append(mechanism_id)
        return {
            "mechanism_count": len(mechanism_map_items) or int(causal_graph_summary.get("mechanism_node_count", 0) or 0),
            "mechanism_families": family_counts,
            "mechanism_status_counts": status_counts,
            "competing_pairs": list(dict.fromkeys(competing_pairs))[:10],
            "counterfactual_experiments": causal_graph_summary.get("counterfactual_experiments", []),
            "mechanism_nodes": causal_graph_summary.get("mechanism_nodes", []),
            "challenged_mechanisms": list(dict.fromkeys(challenged_mechanisms))[:10],
            "retire_candidates": list(dict.fromkeys(retire_candidates))[:10],
            "revive_candidates": list(dict.fromkeys(revive_candidates))[:10],
        }

    @staticmethod
    def _derive_hypothesis_family_lifecycle_summary(
        *,
        steps: list[WorkflowStepResult],
        theoretical_hypothesis_tree_summary: dict[str, Any],
    ) -> dict[str, Any]:
        family_actions: list[dict[str, Any]] = []
        for step in steps:
            payload = step.parsed_output.get("hypothesis_family_actions", [])
            if isinstance(payload, list):
                family_actions.extend(item for item in payload if isinstance(item, dict))
        action_counts: dict[str, int] = {}
        family_actions_by_name: dict[str, list[str]] = {}
        for item in family_actions:
            action = str(item.get("action", "")).strip() or "observe"
            family = str(item.get("family", "")).strip() or "general"
            action_counts[action] = action_counts.get(action, 0) + 1
            family_actions_by_name.setdefault(family, []).append(action)
        return {
            "family_count": int(theoretical_hypothesis_tree_summary.get("family_count", 0) or 0),
            "family_status_counts": theoretical_hypothesis_tree_summary.get("family_status_counts", {}),
            "retire_candidates": theoretical_hypothesis_tree_summary.get("retire_candidates", []),
            "revive_candidates": theoretical_hypothesis_tree_summary.get("revive_candidates", []),
            "family_action_counts": action_counts,
            "family_actions": family_actions[:12],
            "family_actions_by_name": {key: value[:6] for key, value in list(family_actions_by_name.items())[:8]},
        }

    @staticmethod
    def _derive_route_temperature_summary(
        *,
        claim_graph: dict[str, Any],
        failure_intelligence_summary: dict[str, Any],
        graph_reference_summary: dict[str, Any],
        typed_research_graph_history: dict[str, Any],
        evaluation_history_summary: dict[str, Any],
        theoretical_hypothesis_tree_summary: dict[str, Any],
    ) -> dict[str, Any]:
        challenge_count = int(typed_research_graph_history.get("challenged_hypothesis_count", 0) or 0)
        consulted_count = int(typed_research_graph_history.get("consulted_edge_count", 0) or 0)
        specialist_reference_count = int(typed_research_graph_history.get("specialist_reference_count", 0) or 0)
        graph_refs = int(graph_reference_summary.get("node_ref_count", 0) or 0) + int(
            graph_reference_summary.get("edge_ref_count", 0) or 0
        )
        regression_count = int(evaluation_history_summary.get("regressing_count", 0) or 0)
        repeated_failures = len(failure_intelligence_summary.get("avoid_repeat_routes", []))
        active_family_count = sum(
            1
            for counts in theoretical_hypothesis_tree_summary.get("family_status_counts", {}).values()
            if isinstance(counts, dict) and int(counts.get("active", 0) or 0) > 0
        )
        pressure_score = challenge_count + repeated_failures + regression_count + (1 if consulted_count >= 4 else 0)
        if pressure_score >= 6:
            global_temperature = "hot"
        elif pressure_score >= 2:
            global_temperature = "warm"
        else:
            global_temperature = "cool"
        cooling_candidates = list(
            dict.fromkeys(
                failure_intelligence_summary.get("avoid_repeat_routes", [])[:4]
                + theoretical_hypothesis_tree_summary.get("retire_candidates", [])[:4]
            )
        )[:8]
        heating_candidates = list(
            dict.fromkeys(
                theoretical_hypothesis_tree_summary.get("revive_candidates", [])[:4]
                + [item.get("profile_name", "") for item in graph_reference_summary.get("by_profile", []) if isinstance(item, dict)]
            )
        )[:8]
        return {
            "global_temperature": global_temperature,
            "challenge_pressure": challenge_count,
            "consultation_pressure": consulted_count,
            "reference_activity": graph_refs,
            "regression_pressure": regression_count,
            "active_family_count": active_family_count,
            "cooling_candidates": cooling_candidates,
            "heating_candidates": [item for item in heating_candidates if item],
            "specialist_reference_count": specialist_reference_count,
        }

    @staticmethod
    def _derive_graph_learning_summary(
        *,
        typed_research_graph_history: dict[str, Any],
        graph_reference_summary: dict[str, Any],
        failure_intelligence_summary: dict[str, Any],
        evaluation_history_summary: dict[str, Any],
    ) -> dict[str, Any]:
        consulted_profiles = (
            typed_research_graph_history.get("consulted_profiles", {})
            if isinstance(typed_research_graph_history.get("consulted_profiles", {}), dict)
            else {}
        )
        by_profile = (
            graph_reference_summary.get("by_profile", [])
            if isinstance(graph_reference_summary.get("by_profile", []), list)
            else []
        )
        high_value_profiles = [
            str(item.get("profile_name", "")).strip()
            for item in by_profile
            if isinstance(item, dict)
            and (len(item.get("node_refs", [])) + len(item.get("edge_refs", []))) >= 2
            and str(item.get("profile_name", "")).strip()
        ]
        dominant_failure = str(failure_intelligence_summary.get("dominant_failure_class", "mixed")).strip() or "mixed"
        regression_count = int(evaluation_history_summary.get("regressing_count", 0) or 0)
        learning_signal_strength = "low"
        if consulted_profiles or regression_count >= 2 or high_value_profiles:
            learning_signal_strength = "medium"
        if len(consulted_profiles) >= 2 and regression_count >= 2:
            learning_signal_strength = "high"
        return {
            "learning_signal_strength": learning_signal_strength,
            "dominant_failure_class": dominant_failure,
            "high_value_profiles": list(dict.fromkeys(high_value_profiles))[:8],
            "consulted_profiles": consulted_profiles,
            "regression_count": regression_count,
            "recommended_learning_focus": (
                "avoid repeated technical routes"
                if dominant_failure == "technical"
                else "re-examine theory families"
                if dominant_failure == "theoretical"
                else "close evidence gaps"
            ),
        }

    @staticmethod
    def _summarize_asset_registry(
        registry_items: list[dict[str, Any]],
        run_manifest: dict[str, Any],
    ) -> dict[str, Any]:
        asset_types: dict[str, int] = {}
        for item in registry_items:
            if not isinstance(item, dict):
                continue
            asset_type = str(item.get("asset_type", "unknown")).strip() or "unknown"
            asset_types[asset_type] = asset_types.get(asset_type, 0) + 1
        for item in run_manifest.get("artifacts", []):
            if not isinstance(item, dict):
                continue
            asset_type = str(item.get("scope", "artifact")).strip() or "artifact"
            asset_types[asset_type] = asset_types.get(asset_type, 0) + 1
        return {
            "asset_count": len(registry_items) + len(run_manifest.get("artifacts", [])),
            "asset_types": asset_types,
            "registered_assets": registry_items[:20],
        }

    @staticmethod
    def _derive_asset_graph_summary(
        *,
        claim_graph: dict[str, Any],
        run_manifest: dict[str, Any],
    ) -> dict[str, Any]:
        hypotheses = claim_graph.get("hypotheses", []) if isinstance(claim_graph.get("hypotheses", []), list) else []
        asset_registry = claim_graph.get("asset_registry", []) if isinstance(claim_graph.get("asset_registry", []), list) else []
        runs = [
            item
            for item in claim_graph.get("asset_registry", [])
            if isinstance(item, dict) and str(item.get("asset_type", "")).strip() == "experiment_run"
        ] if isinstance(claim_graph.get("asset_registry", []), list) else []
        evidence = claim_graph.get("evidence", []) if isinstance(claim_graph.get("evidence", []), list) else []
        nodes = len(hypotheses) + len(asset_registry) + len(run_manifest.get("artifacts", [])) + len(evidence)
        edges: list[dict[str, str]] = []
        lineage_edges: list[dict[str, str]] = []
        for hypothesis in hypotheses[:10]:
            hypothesis_id = str(hypothesis.get("global_hypothesis_id", "")).strip()
            if not hypothesis_id:
                continue
            for asset in asset_registry[:10]:
                if not isinstance(asset, dict):
                    continue
                asset_id = str(asset.get("asset_id", "")).strip()
                if not asset_id:
                    continue
                edges.append({"source": hypothesis_id, "target": asset_id, "relation": "tracked_by"})
                break
        for claim in claim_graph.get("claims", [])[:10] if isinstance(claim_graph.get("claims", []), list) else []:
            if not isinstance(claim, dict):
                continue
            claim_id = str(claim.get("global_claim_id", "")).strip()
            supports = claim.get("supports", []) if isinstance(claim.get("supports", []), list) else []
            for evidence_id in supports[:4]:
                edges.append({"source": claim_id, "target": str(evidence_id), "relation": "supported_by"})
        for artifact in run_manifest.get("artifacts", [])[:10]:
            if not isinstance(artifact, dict):
                continue
            path = str(artifact.get("path", "")).strip()
            if not path:
                continue
            edges.append({"source": "run-manifest", "target": path, "relation": "produced"})
        governed_asset_types: dict[str, int] = {}
        artifact_type_counts: dict[str, int] = {}
        ungoverned_artifact_count = 0
        for artifact in run_manifest.get("artifacts", []) if isinstance(run_manifest.get("artifacts", []), list) else []:
            if not isinstance(artifact, dict):
                continue
            artifact_type = ScientificWorkflow._artifact_node_type(
                kind=str(artifact.get("kind", "")).strip(),
                path=str(artifact.get("path", "")).strip(),
                scope=str(artifact.get("scope", "")).strip(),
            )
            artifact_type_counts[artifact_type] = artifact_type_counts.get(artifact_type, 0) + 1
        for asset in asset_registry:
            if not isinstance(asset, dict):
                continue
            asset_id = str(asset.get("asset_id", "")).strip()
            asset_type = str(asset.get("asset_type", "")).strip() or "unknown"
            governance_status = str(asset.get("governance_status", "")).strip().lower()
            parent_asset_id = str(asset.get("parent_asset_id", "")).strip()
            derived_from_asset_ids = (
                asset.get("derived_from_asset_ids", [])
                if isinstance(asset.get("derived_from_asset_ids", []), list)
                else []
            )
            if governance_status:
                governed_asset_types[asset_type] = governed_asset_types.get(asset_type, 0) + 1
            else:
                ungoverned_artifact_count += 1
            if asset_id and parent_asset_id:
                lineage_edges.append(
                    {"source": parent_asset_id, "target": asset_id, "relation": "supersedes"}
                )
            if asset_id:
                for upstream in derived_from_asset_ids[:4]:
                    upstream_id = str(upstream).strip()
                    if upstream_id:
                        lineage_edges.append(
                            {"source": upstream_id, "target": asset_id, "relation": "derived_into"}
                        )
        edges.extend(lineage_edges[:10])
        typed_node_counts = {
            "hypothesis": len(hypotheses),
            "asset": len(asset_registry),
            "artifact": len(run_manifest.get("artifacts", [])),
            "evidence": len(evidence),
            "claim": len(
                claim_graph.get("claims", [])
                if isinstance(claim_graph.get("claims", []), list)
                else []
            ),
        }
        typed_edge_counts: dict[str, int] = {}
        for item in edges:
            relation = str(item.get("relation", "related_to")).strip() or "related_to"
            typed_edge_counts[relation] = typed_edge_counts.get(relation, 0) + 1
        return {
            "node_count": nodes,
            "edge_count": len(edges),
            "registered_asset_count": len(asset_registry),
            "run_manifest_artifact_count": len(run_manifest.get("artifacts", [])),
            "typed_node_counts": typed_node_counts,
            "typed_edge_counts": typed_edge_counts,
            "lineage_edge_count": len(lineage_edges),
            "governed_asset_types": governed_asset_types,
            "artifact_type_counts": artifact_type_counts,
            "ungoverned_artifact_count": ungoverned_artifact_count,
            "edges": edges[:20],
        }

    def _sync_typed_research_graph(
        self,
        *,
        topic: str,
        steps: list[WorkflowStepResult],
        claim_graph: dict[str, Any],
        research_state: dict[str, Any],
        run_manifest: dict[str, Any],
    ) -> dict[str, Any]:
        project_id = str(self.collaboration_context.get("project_id", "")).strip()
        if not project_id:
            return {}

        saved_node_ids: list[str] = []
        saved_edge_ids: list[str] = []
        saved_fact_ids: list[str] = []
        saved_event_ids: list[str] = []

        def _save_node(node_id: str, node_type: str, label: str, metadata: dict[str, Any] | None = None) -> None:
            node = ResearchGraphNode(
                node_id=node_id,
                node_type=node_type,
                label=label[:200],
                project_id=project_id,
                topic=topic,
                metadata=metadata or {},
            )
            self.graph_registry.save_node(node)
            saved_node_ids.append(node_id)

        def _save_edge(source_id: str, target_id: str, relation: str, metadata: dict[str, Any] | None = None) -> None:
            if not source_id or not target_id:
                return
            edge_id = f"{source_id}::{relation}::{target_id}"
            edge = ResearchGraphEdge(
                edge_id=edge_id,
                source_id=source_id,
                target_id=target_id,
                relation=relation,
                project_id=project_id,
                topic=topic,
                metadata=metadata or {},
            )
            self.graph_registry.save_edge(edge)
            saved_edge_ids.append(edge_id)

        def _save_fact(
            fact_type: str,
            subject_id: str,
            predicate: str,
            *,
            object_id: str = "",
            value: Any = None,
            source_refs: list[str] | None = None,
            produced_by: str = "workflow",
            status: str = "active",
            confidence: float = 1.0,
            metadata: dict[str, Any] | None = None,
        ) -> None:
            if not subject_id or not predicate:
                return
            fact_id = "::".join(
                [
                    "fact",
                    fact_type,
                    self._slugify_text(subject_id)[:120],
                    self._slugify_text(predicate)[:80],
                    self._slugify_text(object_id or json.dumps(value, ensure_ascii=False)[:120]),
                ]
            )
            fact = ProvenanceFact(
                fact_id=fact_id,
                fact_type=fact_type,
                subject_id=subject_id,
                predicate=predicate,
                object_id=object_id,
                value=value,
                project_id=project_id,
                topic=topic,
                confidence=confidence,
                source_refs=source_refs or [],
                produced_by=produced_by,
                status=status,
                metadata=metadata or {},
            )
            self.graph_registry.save_fact(fact)
            saved_fact_ids.append(fact_id)

        def _save_event(
            event_type: str,
            action: str,
            *,
            actor: str = "workflow",
            fact_ids: list[str] | None = None,
            metadata: dict[str, Any] | None = None,
        ) -> None:
            event_id = "::".join(
                [
                    "event",
                    event_type,
                    self._slugify_text(action)[:80],
                    datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f"),
                ]
            )
            event = ProvenanceEvent(
                event_id=event_id,
                event_type=event_type,
                fact_ids=fact_ids or [],
                project_id=project_id,
                topic=topic,
                actor=actor,
                action=action,
                metadata=metadata or {},
            )
            self.graph_registry.save_event(event)
            saved_event_ids.append(event_id)

        for item in claim_graph.get("hypotheses", []) if isinstance(claim_graph.get("hypotheses", []), list) else []:
            if not isinstance(item, dict):
                continue
            node_id = str(item.get("global_hypothesis_id", "")).strip()
            if not node_id:
                continue
            _save_node(node_id, "hypothesis", str(item.get("name", "")).strip() or node_id, item)
            _save_fact(
                "hypothesis",
                node_id,
                "has_record",
                value=item,
                source_refs=[
                    str(ref).strip()
                    for ref in item.get("evidence_refs", [])
                    if str(ref).strip()
                ] if isinstance(item.get("evidence_refs", []), list) else [],
                produced_by=str(item.get("profile_name", "workflow")),
                status=str(item.get("status", "active")).strip() or "active",
                confidence=float(item.get("confidence", 1.0) or 1.0) if isinstance(item.get("confidence", 1.0), int | float) else 1.0,
            )

        for item in claim_graph.get("claims", []) if isinstance(claim_graph.get("claims", []), list) else []:
            if not isinstance(item, dict):
                continue
            node_id = str(item.get("global_claim_id", "")).strip()
            if not node_id:
                continue
            _save_node(node_id, "claim", str(item.get("statement", "")).strip() or node_id, item)
            _save_fact(
                "claim",
                node_id,
                "states",
                value=str(item.get("statement", "")).strip() or node_id,
                source_refs=[
                    str(ref).strip()
                    for ref in item.get("supports", [])
                    if str(ref).strip()
                ] if isinstance(item.get("supports", []), list) else [],
                produced_by=str(item.get("profile_name", "workflow")),
            )
            for evidence_id in item.get("supports", []) if isinstance(item.get("supports", []), list) else []:
                if str(evidence_id).strip():
                    _save_edge(node_id, str(evidence_id).strip(), "supports")
                    _save_fact(
                        "claim_relation",
                        node_id,
                        "supported_by",
                        object_id=str(evidence_id).strip(),
                        source_refs=[str(evidence_id).strip()],
                    )

        for item in claim_graph.get("evidence", []) if isinstance(claim_graph.get("evidence", []), list) else []:
            if not isinstance(item, dict):
                continue
            node_id = str(item.get("global_evidence_id", "")).strip()
            if not node_id:
                continue
            _save_node(node_id, "evidence", str(item.get("summary", "")).strip() or node_id, item)
            _save_fact(
                "evidence",
                node_id,
                "summarizes",
                value=str(item.get("summary", "")).strip() or node_id,
                source_refs=[
                    str(ref).strip()
                    for ref in item.get("source_refs", [])
                    if str(ref).strip()
                ] if isinstance(item.get("source_refs", []), list) else [],
                produced_by=str(item.get("profile_name", "workflow")),
                confidence={"high": 0.9, "medium": 0.65, "low": 0.35}.get(
                    str(item.get("strength", "")).strip().lower(),
                    0.75,
                ),
                metadata=item,
            )

        for item in claim_graph.get("negative_results", []) if isinstance(claim_graph.get("negative_results", []), list) else []:
            if not isinstance(item, dict):
                continue
            node_id = str(item.get("negative_result_id", "")).strip()
            if not node_id:
                continue
            _save_node(node_id, "negative_result", str(item.get("result", "")).strip() or node_id, item)
            _save_fact(
                "negative_result",
                node_id,
                "records_failure_or_null",
                value=item,
                source_refs=[
                    str(ref).strip()
                    for ref in item.get("source_refs", [])
                    if str(ref).strip()
                ] if isinstance(item.get("source_refs", []), list) else [],
                produced_by=str(item.get("profile_name", "workflow")),
                status="active",
            )
            for hypothesis_id in item.get("affected_hypothesis_ids", []) if isinstance(item.get("affected_hypothesis_ids", []), list) else []:
                if str(hypothesis_id).strip():
                    _save_edge(node_id, str(hypothesis_id).strip(), "challenges")
                    _save_fact(
                        "negative_result_relation",
                        node_id,
                        "challenges",
                        object_id=str(hypothesis_id).strip(),
                        value=str(item.get("result", "")).strip(),
                    )

        for item in claim_graph.get("asset_registry", []) if isinstance(claim_graph.get("asset_registry", []), list) else []:
            if not isinstance(item, dict):
                continue
            node_id = str(item.get("asset_id", "")).strip()
            if not node_id:
                continue
            _save_node(node_id, str(item.get("asset_type", "")).strip() or "asset", str(item.get("label", "")).strip() or node_id, item)
            parent_asset_id = str(item.get("parent_asset_id", "")).strip()
            if parent_asset_id:
                _save_edge(parent_asset_id, node_id, "supersedes")
            for upstream in item.get("derived_from_asset_ids", []) if isinstance(item.get("derived_from_asset_ids", []), list) else []:
                upstream_id = str(upstream).strip()
                if upstream_id:
                    _save_edge(upstream_id, node_id, "derived_from")

        unified_assets = research_state.get("unified_asset_summary", {})
        if isinstance(unified_assets, dict):
            for item in unified_assets.get("assets", []) if isinstance(unified_assets.get("assets", []), list) else []:
                if not isinstance(item, dict):
                    continue
                node_id = str(item.get("asset_id", "")).strip()
                if not node_id:
                    continue
                _save_node(
                    f"scientific-asset::{self._slugify_text(node_id)}",
                    "scientific_asset",
                    str(item.get("label", "")).strip() or node_id,
                    item,
                )
                _save_edge(f"scientific-asset::{self._slugify_text(node_id)}", node_id, "normalizes")
                for parent_id in item.get("parent_asset_ids", []) if isinstance(item.get("parent_asset_ids", []), list) else []:
                    if str(parent_id).strip():
                        _save_edge(str(parent_id).strip(), f"scientific-asset::{self._slugify_text(node_id)}", "parent_of")
                for upstream_id in item.get("derived_from_asset_ids", []) if isinstance(item.get("derived_from_asset_ids", []), list) else []:
                    if str(upstream_id).strip():
                        _save_edge(str(upstream_id).strip(), f"scientific-asset::{self._slugify_text(node_id)}", "derived_into")

        _save_node(
            "run-manifest",
            "run_manifest",
            f"run manifest {self._slugify_text(topic)}",
            {
                "generated_at": run_manifest.get("generated_at", ""),
                "tools_used": run_manifest.get("tools_used", []),
                "models_used": run_manifest.get("models_used", []),
            },
        )

        for item in run_manifest.get("artifacts", []) if isinstance(run_manifest.get("artifacts", []), list) else []:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path", "")).strip()
            if not path:
                continue
            artifact_id = f"artifact::{path}"
            artifact_type = self._artifact_node_type(
                kind=str(item.get("kind", "")).strip(),
                path=path,
                scope=str(item.get("scope", "")).strip(),
            )
            _save_node(artifact_id, artifact_type, Path(path).name or artifact_id, item)
            _save_edge("run-manifest", artifact_id, "produced_by")
            _save_fact(
                "artifact",
                artifact_id,
                "produced_by",
                object_id="run-manifest",
                value=item,
                source_refs=[path],
                produced_by="run_manifest",
                metadata={"artifact_type": artifact_type},
            )

        for item in run_manifest.get("input_files", []) if isinstance(run_manifest.get("input_files", []), list) else []:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path", "")).strip()
            if not path:
                continue
            input_id = f"input::{path}"
            input_type = self._artifact_node_type(
                kind="dataset",
                path=path,
                scope=str(item.get("scope", "")).strip(),
            )
            _save_node(input_id, input_type, Path(path).name or input_id, item)
            _save_edge(input_id, "run-manifest", "consumed_by")
            _save_fact(
                "artifact",
                input_id,
                "consumed_by",
                object_id="run-manifest",
                value=item,
                source_refs=[path],
                produced_by="run_manifest",
                metadata={"artifact_type": input_type, "input": True},
            )

        for edge in claim_graph.get("edges", []) if isinstance(claim_graph.get("edges", []), list) else []:
            if not isinstance(edge, dict):
                continue
            _save_edge(
                str(edge.get("source", "")).strip(),
                str(edge.get("target", "")).strip(),
                str(edge.get("relation", "")).strip() or "related_to",
                edge,
            )

        for item in claim_graph.get("negative_result_links", []) if isinstance(claim_graph.get("negative_result_links", []), list) else []:
            if not isinstance(item, dict):
                continue
            negative_id = str(item.get("negative_result_id", "")).strip()
            hypothesis_id = str(item.get("hypothesis_id", "")).strip()
            if negative_id and hypothesis_id:
                _save_edge(negative_id, hypothesis_id, "challenges", item)

        systematic_review = research_state.get("systematic_review_summary", {})
        if isinstance(systematic_review, dict) and systematic_review:
            review_node_id = f"systematic-review::{project_id}::{self._slugify_text(topic)}"
            _save_node(review_node_id, "systematic_review", str(systematic_review.get("review_question", "")).strip() or topic, systematic_review)
            for record in systematic_review.get("screening_records", []) if isinstance(systematic_review.get("screening_records", []), list) else []:
                record_text = str(record).strip()
                if not record_text:
                    continue
                record_id = f"review-screening::{self._slugify_text(record_text)}"
                _save_node(record_id, "review_screening_record", record_text, {"record_kind": "screening"})
                _save_edge(review_node_id, record_id, "contains")
            for record in systematic_review.get("evidence_table_records", []) if isinstance(systematic_review.get("evidence_table_records", []), list) else []:
                record_text = str(record).strip()
                if not record_text:
                    continue
                record_id = f"review-evidence-table::{self._slugify_text(record_text)}"
                _save_node(record_id, "review_evidence_table_record", record_text, {"record_kind": "evidence_table"})
                _save_edge(review_node_id, record_id, "contains")
            for record in systematic_review.get("review_record_updates", []) if isinstance(systematic_review.get("review_record_updates", []), list) else []:
                record_text = str(record).strip()
                if not record_text:
                    continue
                record_id = f"review-update::{self._slugify_text(record_text)}"
                _save_node(record_id, "review_record_update", record_text, {"record_kind": "update"})
                _save_edge(review_node_id, record_id, "updates")

        evidence_review = research_state.get("evidence_review_summary", {})
        if isinstance(evidence_review, dict) and evidence_review:
            evidence_review_id = str(evidence_review.get("review_id", "")).strip() or (
                f"evidence-review::{project_id}::{self._slugify_text(topic)}"
            )
            _save_node(
                evidence_review_id,
                "evidence_review",
                str(evidence_review.get("review_question", "")).strip() or topic,
                evidence_review,
            )
            systematic_id = f"systematic-review::{project_id}::{self._slugify_text(topic)}"
            _save_edge(evidence_review_id, systematic_id, "assesses")
            for record in evidence_review.get("assessment_records", []) if isinstance(evidence_review.get("assessment_records", []), list) else []:
                if not isinstance(record, dict):
                    continue
                evidence_id = str(record.get("evidence_id", "")).strip()
                if evidence_id:
                    _save_edge(evidence_review_id, evidence_id, "grades")
            for link in evidence_review.get("evidence_claim_links", []) if isinstance(evidence_review.get("evidence_claim_links", []), list) else []:
                if not isinstance(link, dict):
                    continue
                claim_id = str(link.get("claim_id", "")).strip()
                evidence_id = str(link.get("evidence_id", "")).strip()
                if claim_id and evidence_id:
                    _save_edge(evidence_review_id, claim_id, "audits_claim")
                    _save_edge(evidence_review_id, evidence_id, "audits_evidence")

        autonomous_controller = research_state.get("autonomous_controller_summary", {})
        if isinstance(autonomous_controller, dict) and autonomous_controller:
            controller_id = str(autonomous_controller.get("controller_id", "")).strip() or (
                f"autonomous-controller::{project_id}::{self._slugify_text(topic)}"
            )
            _save_node(
                controller_id,
                "autonomous_controller",
                f"autonomous controller {self._slugify_text(topic)}",
                autonomous_controller,
            )
            for trace in autonomous_controller.get("decision_trace", []) if isinstance(autonomous_controller.get("decision_trace", []), list) else []:
                if not isinstance(trace, dict):
                    continue
                source_id = str(trace.get("source_id", "")).strip()
                source_type = str(trace.get("source_type", "")).strip()
                if source_id:
                    _save_edge(controller_id, source_id, f"controlled_by_{source_type}" if source_type else "controlled_by")

        experiment_scheduler = research_state.get("experiment_execution_loop_summary", {})
        if isinstance(experiment_scheduler, dict) and experiment_scheduler:
            scheduler_id = str(experiment_scheduler.get("scheduler_id", "")).strip() or (
                f"experiment-scheduler::{project_id}::{self._slugify_text(topic)}"
            )
            _save_node(
                scheduler_id,
                "experiment_scheduler",
                f"experiment scheduler {self._slugify_text(topic)}",
                experiment_scheduler,
            )
            for item in experiment_scheduler.get("execution_queue", []) if isinstance(experiment_scheduler.get("execution_queue", []), list) else []:
                if not isinstance(item, dict):
                    continue
                experiment_id = str(item.get("experiment_id", "")).strip()
                if experiment_id:
                    _save_node(experiment_id, "experiment_candidate", experiment_id, item)
                    _save_edge(scheduler_id, experiment_id, "schedules")
                    _save_fact(
                        "experiment",
                        experiment_id,
                        "scheduled_by",
                        object_id=scheduler_id,
                        value=item,
                        produced_by="experiment_scheduler",
                        status=str(item.get("schedule_state", "ready_to_schedule")).strip() or "ready_to_schedule",
                    )
            for item in experiment_scheduler.get("blocked_experiments", []) if isinstance(experiment_scheduler.get("blocked_experiments", []), list) else []:
                if not isinstance(item, dict):
                    continue
                experiment_id = str(item.get("experiment_id", "")).strip()
                if experiment_id:
                    _save_node(experiment_id, "experiment_candidate", str(item.get("title", "")) or experiment_id, item)
                    _save_edge(scheduler_id, experiment_id, "blocks_or_defers")
                    _save_fact(
                        "experiment",
                        experiment_id,
                        "blocked_or_deferred_by",
                        object_id=scheduler_id,
                        value=item,
                        produced_by="experiment_scheduler",
                        status="blocked",
                    )

        optimization_adapter = research_state.get("optimization_adapter_summary", {})
        if isinstance(optimization_adapter, dict) and optimization_adapter:
            adapter_id = str(optimization_adapter.get("adapter_id", "")).strip() or (
                f"optimization-adapter::{project_id}::{self._slugify_text(topic)}"
            )
            _save_node(
                adapter_id,
                "optimization_adapter",
                f"optimization adapter {self._slugify_text(topic)}",
                optimization_adapter,
            )
            for plan in optimization_adapter.get("plans", []) if isinstance(optimization_adapter.get("plans", []), list) else []:
                if not isinstance(plan, dict):
                    continue
                plan_id = str(plan.get("plan_id", "")).strip()
                experiment_id = str(plan.get("experiment_id", "")).strip()
                if plan_id:
                    _save_node(plan_id, "optimization_plan", plan_id, plan)
                    _save_edge(adapter_id, plan_id, "plans")
                if plan_id and experiment_id:
                    _save_edge(plan_id, experiment_id, "optimizes")
            for result in optimization_adapter.get("simulated_results", []) if isinstance(optimization_adapter.get("simulated_results", []), list) else []:
                if not isinstance(result, dict):
                    continue
                result_id = str(result.get("result_id", "")).strip()
                plan_id = str(result.get("plan_id", "")).strip()
                if result_id:
                    _save_node(result_id, "optimization_result", result_id, result)
                if result_id and plan_id:
                    _save_edge(plan_id, result_id, "produces")

        discipline_adapter = research_state.get("discipline_adapter_summary", {})
        if isinstance(discipline_adapter, dict) and discipline_adapter:
            adapter_id = str(discipline_adapter.get("adapter_id", "")).strip() or (
                f"discipline-adapter::{project_id}::{self._slugify_text(topic)}"
            )
            _save_node(
                adapter_id,
                "discipline_adapter",
                f"discipline adapter {self._slugify_text(topic)}",
                discipline_adapter,
            )
            selected_adapter = str(discipline_adapter.get("selected_adapter_id", "")).strip()
            if selected_adapter:
                _save_node(selected_adapter, "discipline_adapter_spec", selected_adapter, {"selected": True})
                _save_edge(adapter_id, selected_adapter, "selects")
            for binding in discipline_adapter.get("bindings", []) if isinstance(discipline_adapter.get("bindings", []), list) else []:
                if not isinstance(binding, dict):
                    continue
                binding_id = str(binding.get("binding_id", "")).strip()
                experiment_id = str(binding.get("experiment_id", "")).strip()
                if binding_id:
                    _save_node(binding_id, "discipline_adapter_binding", binding_id, binding)
                    _save_edge(adapter_id, binding_id, "creates_binding")
                if binding_id and experiment_id:
                    _save_edge(binding_id, experiment_id, "specializes_execution_for")

        execution_registry = research_state.get("execution_adapter_registry_summary", {})
        if isinstance(execution_registry, dict) and execution_registry:
            registry_id = str(execution_registry.get("registry_id", "")).strip() or (
                f"execution-adapter-registry::{project_id}::{self._slugify_text(topic)}"
            )
            _save_node(
                registry_id,
                "execution_adapter_registry",
                f"execution adapter registry {self._slugify_text(topic)}",
                execution_registry,
            )
            selected_adapter = str(execution_registry.get("selected_adapter_id", "")).strip()
            if selected_adapter:
                _save_node(selected_adapter, "execution_adapter", selected_adapter, {"selected": True})
                _save_edge(registry_id, selected_adapter, "selects")
            for package in execution_registry.get("execution_packages", []) if isinstance(execution_registry.get("execution_packages", []), list) else []:
                if not isinstance(package, dict):
                    continue
                package_id = str(package.get("package_id", "")).strip()
                experiment_id = str(package.get("experiment_id", "")).strip()
                adapter_id = str(package.get("adapter_id", "")).strip()
                if package_id:
                    _save_node(package_id, "execution_package", package_id, package)
                    _save_edge(registry_id, package_id, "creates")
                    _save_fact(
                        "experiment",
                        package_id,
                        "execution_package_for",
                        object_id=experiment_id,
                        value=package,
                        produced_by="execution_adapter_registry",
                        status=str(package.get("package_state", "unknown")).strip() or "unknown",
                    )
                if package_id and experiment_id:
                    _save_edge(package_id, experiment_id, "packages")
                if package_id and adapter_id:
                    _save_edge(adapter_id, package_id, "executes_or_hands_off")

        run_handoff = research_state.get("run_handoff_contract_summary", {})
        if isinstance(run_handoff, dict) and run_handoff:
            handoff_id = str(run_handoff.get("handoff_contract_id", "")).strip() or (
                f"run-handoff-contract::{project_id}::{self._slugify_text(topic)}"
            )
            _save_node(
                handoff_id,
                "run_handoff_contract",
                f"run handoff contract {self._slugify_text(topic)}",
                run_handoff,
            )
            for contract in run_handoff.get("contracts", []) if isinstance(run_handoff.get("contracts", []), list) else []:
                if not isinstance(contract, dict):
                    continue
                contract_id = str(contract.get("contract_id", "")).strip()
                package_id = str(contract.get("package_id", "")).strip()
                if contract_id:
                    _save_node(contract_id, "run_handoff_contract_item", contract_id, contract)
                    _save_edge(handoff_id, contract_id, "contains")
                if contract_id and package_id:
                    _save_edge(contract_id, package_id, "requires_return_for")

        family_lifecycle = research_state.get("hypothesis_family_lifecycle_summary", {})
        theoretical_tree = research_state.get("theoretical_hypothesis_tree_summary", {})
        if isinstance(family_lifecycle, dict):
            for family, counts in family_lifecycle.get("family_status_counts", {}).items():
                family_name = str(family).strip()
                if not family_name:
                    continue
                family_node_id = f"hypothesis-family::{self._slugify_text(family_name)}"
                _save_node(family_node_id, "hypothesis_family", family_name, {"status_counts": counts})
                for hypothesis_id in (
                    theoretical_tree.get("hypothesis_families", {}).get(family_name, [])
                    if isinstance(theoretical_tree.get("hypothesis_families", {}), dict)
                    else []
                ):
                    if str(hypothesis_id).strip():
                        _save_edge(family_node_id, str(hypothesis_id).strip(), "governs")

        causal_graph = research_state.get("causal_graph_summary", {})
        if isinstance(causal_graph, dict) and causal_graph:
            causal_node_id = f"causal-graph::{project_id}::{self._slugify_text(topic)}"
            _save_node(causal_node_id, "causal_model", topic, causal_graph)
            for hypothesis in claim_graph.get("hypotheses", [])[:6] if isinstance(claim_graph.get("hypotheses", []), list) else []:
                if isinstance(hypothesis, dict):
                    hypothesis_id = str(hypothesis.get("global_hypothesis_id", "")).strip()
                    if hypothesis_id:
                        _save_edge(causal_node_id, hypothesis_id, "tests")
            for mechanism_name in causal_graph.get("mechanism_nodes", []) if isinstance(causal_graph.get("mechanism_nodes", []), list) else []:
                mechanism_text = str(mechanism_name).strip()
                if not mechanism_text:
                    continue
                mechanism_id = f"mechanism::{self._slugify_text(mechanism_text)}"
                _save_node(mechanism_id, "mechanism", mechanism_text, {})
                _save_edge(causal_node_id, mechanism_id, "models")

        mechanism_summary = research_state.get("mechanism_reasoning_summary", {})
        if isinstance(mechanism_summary, dict):
            for mechanism_name in mechanism_summary.get("mechanism_nodes", []) if isinstance(mechanism_summary.get("mechanism_nodes", []), list) else []:
                mechanism_text = str(mechanism_name).strip()
                if not mechanism_text:
                    continue
                mechanism_id = f"mechanism::{self._slugify_text(mechanism_text)}"
                _save_node(mechanism_id, "mechanism", mechanism_text, {})
            mechanism_family_summary = research_state.get("mechanism_family_lifecycle_summary", {})
            if isinstance(mechanism_family_summary, dict):
                for family_name, counts in mechanism_family_summary.get("family_status_counts", {}).items():
                    family_text = str(family_name).strip()
                    if not family_text:
                        continue
                    family_id = f"mechanism-family::{self._slugify_text(family_text)}"
                    _save_node(family_id, "mechanism_family", family_text, {"status_counts": counts})

        hypothesis_gate = research_state.get("hypothesis_gate_summary", {})
        if isinstance(hypothesis_gate, dict):
            for item in hypothesis_gate.get("records", []) if isinstance(hypothesis_gate.get("records", []), list) else []:
                if not isinstance(item, dict):
                    continue
                hypothesis_id = str(item.get("hypothesis_id", "")).strip()
                if not hypothesis_id:
                    continue
                gate_id = f"hypothesis-gate::{hypothesis_id}"
                _save_node(
                    gate_id,
                    "hypothesis_gate",
                    f"gate {hypothesis_id}",
                    {
                        "gate_decision": str(item.get("gate_decision", "")).strip(),
                        "reason": str(item.get("reason", "")).strip(),
                        "required_follow_up": item.get("required_follow_up", []),
                    },
                )
                _save_edge(gate_id, hypothesis_id, "governs")

        hypothesis_theory = research_state.get("hypothesis_theory_summary", {})
        if isinstance(hypothesis_theory, dict):
            for item in hypothesis_theory.get("objects", []) if isinstance(hypothesis_theory.get("objects", []), list) else []:
                if not isinstance(item, dict):
                    continue
                theory_id = str(item.get("theory_object_id", "")).strip()
                hypothesis_id = str(item.get("hypothesis_id", "")).strip()
                if not theory_id or not hypothesis_id:
                    continue
                _save_node(theory_id, "hypothesis_theory_object", str(item.get("name", "")).strip() or theory_id, item)
                _save_edge(theory_id, hypothesis_id, "formalizes")
                for negative_id in item.get("negative_result_refs", []) if isinstance(item.get("negative_result_refs", []), list) else []:
                    if str(negative_id).strip():
                        _save_edge(str(negative_id).strip(), theory_id, "challenges")
                for competitor_id in item.get("competing_hypothesis_ids", []) if isinstance(item.get("competing_hypothesis_ids", []), list) else []:
                    if str(competitor_id).strip():
                        _save_edge(theory_id, str(competitor_id).strip(), "competes_with")
                gate = item.get("gate", {}) if isinstance(item.get("gate", {}), dict) else {}
                gate_hypothesis_id = str(gate.get("hypothesis_id", "")).strip()
                if gate_hypothesis_id:
                    _save_edge(f"hypothesis-gate::{gate_hypothesis_id}", theory_id, "governs")

        scientific_decisions = research_state.get("scientific_decision_summary", {})
        if isinstance(scientific_decisions, dict):
            for item in scientific_decisions.get("decision_queue", []) if isinstance(scientific_decisions.get("decision_queue", []), list) else []:
                if not isinstance(item, dict):
                    continue
                decision_id = str(item.get("decision_id", "")).strip()
                target_id = str(item.get("target_id", "")).strip()
                if not decision_id:
                    continue
                _save_node(decision_id, "scientific_decision", str(item.get("action", "")).strip() or decision_id, item)
                _save_fact(
                    "decision",
                    decision_id,
                    "recommends",
                    object_id=target_id,
                    value=item,
                    source_refs=[
                        str(trace.get("source_id", "")).strip()
                        for trace in item.get("evidence_trace", [])
                        if isinstance(trace, dict) and str(trace.get("source_id", "")).strip()
                    ] if isinstance(item.get("evidence_trace", []), list) else [],
                    produced_by="scientific_decision_engine",
                    status=str(item.get("decision_state", "active")).strip() or "active",
                )
                if target_id:
                    _save_edge(decision_id, target_id, "decides_next_action_for")
                for trace in item.get("evidence_trace", []) if isinstance(item.get("evidence_trace", []), list) else []:
                    if not isinstance(trace, dict):
                        continue
                    source_id = str(trace.get("source_id", "")).strip()
                    source_type = str(trace.get("source_type", "")).strip() or "decision_trace"
                    if not source_id:
                        continue
                    trace_node_id = f"decision-trace::{self._slugify_text(source_type)}::{self._slugify_text(source_id)}"
                    _save_node(trace_node_id, "decision_trace", source_id, trace)
                    _save_edge(trace_node_id, decision_id, "informs")

        for step in steps:
            references = step.parsed_output.get("graph_references", {})
            if not isinstance(references, dict) or not references:
                continue
            reference_node_id = (
                f"specialist-reference::{step.profile_name}::{self._slugify_text(topic)}::{len(saved_node_ids)}"
            )
            reference_metadata = {
                "profile_name": step.profile_name,
                "usage_note": str(references.get("usage_note", "")).strip(),
                "node_refs": references.get("node_refs", []) if isinstance(references.get("node_refs", []), list) else [],
                "edge_refs": references.get("edge_refs", []) if isinstance(references.get("edge_refs", []), list) else [],
            }
            _save_node(
                reference_node_id,
                "specialist_reference",
                f"{step.profile_name} graph reference",
                reference_metadata,
            )
            _save_fact(
                "agent_stance",
                reference_node_id,
                "consulted_graph_context",
                value=reference_metadata,
                source_refs=[
                    str(ref).strip()
                    for ref in reference_metadata.get("node_refs", [])
                    if str(ref).strip()
                ],
                produced_by=step.profile_name,
                metadata={
                    "profile_name": step.profile_name,
                    "stance_source": "graph_references",
                },
            )
            for node_ref in reference_metadata["node_refs"]:
                node_ref_id = str(node_ref).strip()
                if node_ref_id:
                    _save_edge(reference_node_id, node_ref_id, "consulted", {"profile_name": step.profile_name})

        lab_meeting = research_state.get("lab_meeting_consensus_summary", {})
        if isinstance(lab_meeting, dict) and lab_meeting:
            for position in lab_meeting.get("agent_positions", []) if isinstance(lab_meeting.get("agent_positions", []), list) else []:
                if not isinstance(position, dict):
                    continue
                agent = str(position.get("agent", "")).strip()
                if not agent:
                    continue
                stance_id = f"agent-stance::{agent}::{self._slugify_text(topic)}"
                _save_node(stance_id, "agent_stance", f"{agent} stance", position)
                _save_fact(
                    "agent_stance",
                    stance_id,
                    "holds_position",
                    value=position,
                    source_refs=[
                        str(ref).strip()
                        for ref in position.get("evidence_refs", [])
                        if str(ref).strip()
                    ] if isinstance(position.get("evidence_refs", []), list) else [],
                    produced_by=agent,
                    metadata={"meeting_state": lab_meeting.get("meeting_state", "")},
                )

        stance_continuity = research_state.get("agent_stance_continuity_summary", {})
        if isinstance(stance_continuity, dict) and stance_continuity:
            continuity_fact_ids: list[str] = []
            for record in stance_continuity.get("records", []) if isinstance(stance_continuity.get("records", []), list) else []:
                if not isinstance(record, dict):
                    continue
                agent = str(record.get("agent", "")).strip()
                if not agent:
                    continue
                stance_id = f"agent-stance::{agent}::{self._slugify_text(topic)}"
                _save_node(
                    stance_id,
                    "agent_stance",
                    f"{agent} stance continuity",
                    {
                        **record,
                        "role_memory_state": stance_continuity.get("role_memory_state", ""),
                    },
                )
                before = len(saved_fact_ids)
                _save_fact(
                    "agent_stance",
                    stance_id,
                    "holds_position",
                    value=record,
                    source_refs=[
                        str(ref).strip()
                        for ref in record.get("evidence_refs", [])
                        if str(ref).strip()
                    ] if isinstance(record.get("evidence_refs", []), list) else [],
                    produced_by=agent,
                    metadata={
                        "stance_source": "agent_stance_continuity",
                        "recorded_at": record.get("recorded_at", ""),
                        "continuity_state": record.get("continuity_state", ""),
                        "change_type": record.get("change_type", ""),
                        "previous_recorded_at": record.get("previous_recorded_at", ""),
                    },
                )
                if len(saved_fact_ids) > before:
                    continuity_fact_ids.append(saved_fact_ids[-1])
                for ref in record.get("evidence_refs", []) if isinstance(record.get("evidence_refs", []), list) else []:
                    ref_id = str(ref).strip()
                    if ref_id:
                        _save_edge(stance_id, ref_id, "uses_evidence", {"profile_name": agent})
            if continuity_fact_ids:
                _save_event(
                    "agent_stance_continuity_recorded",
                    "recorded",
                    actor="lab_meeting_moderator",
                    fact_ids=continuity_fact_ids,
                    metadata={
                        "agent_count": stance_continuity.get("agent_count", 0),
                        "changed_count": stance_continuity.get("changed_count", 0),
                        "missing_change_reason_count": stance_continuity.get(
                            "missing_change_reason_count", 0
                        ),
                        "role_memory_state": stance_continuity.get("role_memory_state", ""),
                    },
                )

        snapshot_id = f"{project_id}::{self._slugify_text(topic)}::{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        _save_event(
            "provenance_snapshot_created",
            "snapshot",
            actor="workflow",
            fact_ids=sorted(set(saved_fact_ids)),
            metadata={
                "node_count": len(set(saved_node_ids)),
                "edge_count": len(set(saved_edge_ids)),
            },
        )
        self.graph_registry.save_snapshot(
            ResearchGraphSnapshot(
                snapshot_id=snapshot_id,
                project_id=project_id,
                topic=topic,
                node_ids=sorted(set(saved_node_ids)),
                edge_ids=sorted(set(saved_edge_ids)),
                metadata={
                    "step_count": len(steps),
                    "claim_count": len(claim_graph.get("claims", []) if isinstance(claim_graph.get("claims", []), list) else []),
                    "hypothesis_count": len(claim_graph.get("hypotheses", []) if isinstance(claim_graph.get("hypotheses", []), list) else []),
                    "fact_ids": sorted(set(saved_fact_ids)),
                    "event_ids": sorted(set(saved_event_ids)),
                    "source_of_truth": "provenance_facts",
                },
            )
        )
        replay_summary = self.graph_registry.replay_facts(project_id=project_id, topic=topic)
        return {
            "project_id": project_id,
            "snapshot_id": snapshot_id,
            "node_count": len(set(saved_node_ids)),
            "edge_count": len(set(saved_edge_ids)),
            "fact_count": len(set(saved_fact_ids)),
            "event_count": len(set(saved_event_ids)),
            "source_of_truth": "provenance_facts",
            "replay_summary": {
                "fact_count": replay_summary.get("fact_count", 0),
                "claim_count": replay_summary.get("claim_count", 0),
                "hypothesis_count": replay_summary.get("hypothesis_count", 0),
                "evidence_count": replay_summary.get("evidence_count", 0),
                "experiment_count": replay_summary.get("experiment_count", 0),
                "artifact_count": replay_summary.get("artifact_count", 0),
            },
        }

    def _build_claim_graph_from_provenance_replay(self, topic: str) -> dict[str, Any]:
        project_id = str(self.collaboration_context.get("project_id", "")).strip()
        if not project_id:
            return {}
        replay = self.graph_registry.replay_facts(project_id=project_id, topic=topic)
        claims: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        hypotheses: list[dict[str, Any]] = []
        negative_results: list[dict[str, Any]] = []
        asset_registry: list[dict[str, Any]] = []
        edges: list[dict[str, str]] = []
        negative_result_links: list[dict[str, Any]] = []

        for item in replay.get("claims", []) if isinstance(replay.get("claims", []), list) else []:
            if not isinstance(item, dict):
                continue
            fields = item.get("fields", {}) if isinstance(item.get("fields", {}), dict) else {}
            claim_id = str(item.get("id", "")).strip()
            if not claim_id:
                continue
            claims.append(
                {
                    "global_claim_id": claim_id,
                    "statement": str(fields.get("states", "")).strip() or claim_id,
                    "supports": [
                        relation.get("target_id")
                        for relation in replay.get("relations", [])
                        if isinstance(relation, dict)
                        and str(relation.get("source_id", "")).strip() == claim_id
                        and str(relation.get("relation", "")).strip() == "supported_by"
                        and str(relation.get("target_id", "")).strip()
                    ],
                    "source_refs": item.get("source_refs", []),
                    "fact_ids": item.get("fact_ids", []),
                    "source_system": "provenance_replay",
                }
            )

        for item in replay.get("evidence", []) if isinstance(replay.get("evidence", []), list) else []:
            if not isinstance(item, dict):
                continue
            fields = item.get("fields", {}) if isinstance(item.get("fields", {}), dict) else {}
            evidence_id = str(item.get("id", "")).strip()
            if not evidence_id:
                continue
            evidence.append(
                {
                    "global_evidence_id": evidence_id,
                    "summary": str(fields.get("summarizes", "")).strip() or evidence_id,
                    "source_refs": item.get("source_refs", []),
                    "fact_ids": item.get("fact_ids", []),
                    "source_system": "provenance_replay",
                }
            )

        for item in replay.get("hypotheses", []) if isinstance(replay.get("hypotheses", []), list) else []:
            if not isinstance(item, dict):
                continue
            fields = item.get("fields", {}) if isinstance(item.get("fields", {}), dict) else {}
            hypothesis_id = str(item.get("id", "")).strip()
            if not hypothesis_id:
                continue
            record = fields.get("has_record", {})
            record_dict = record if isinstance(record, dict) else {}
            hypotheses.append(
                {
                    **record_dict,
                    "global_hypothesis_id": hypothesis_id,
                    "name": str(record_dict.get("name", "")).strip() or hypothesis_id,
                    "status": str(record_dict.get("status", "active")).strip() or "active",
                    "source_refs": item.get("source_refs", []),
                    "fact_ids": item.get("fact_ids", []),
                    "source_system": "provenance_replay",
                }
            )

        for item in replay.get("artifacts", []) if isinstance(replay.get("artifacts", []), list) else []:
            if not isinstance(item, dict):
                continue
            fields = item.get("fields", {}) if isinstance(item.get("fields", {}), dict) else {}
            artifact_id = str(item.get("id", "")).strip()
            if not artifact_id:
                continue
            value = next((value for value in fields.values() if isinstance(value, dict)), {})
            asset_registry.append(
                {
                    **(value if isinstance(value, dict) else {}),
                    "asset_id": artifact_id,
                    "source_refs": item.get("source_refs", []),
                    "fact_ids": item.get("fact_ids", []),
                    "source_system": "provenance_replay",
                }
            )

        for relation in replay.get("relations", []) if isinstance(replay.get("relations", []), list) else []:
            if not isinstance(relation, dict):
                continue
            source_id = str(relation.get("source_id", "")).strip()
            target_id = str(relation.get("target_id", "")).strip()
            rel = str(relation.get("relation", "")).strip()
            if not source_id or not target_id or not rel:
                continue
            if rel == "challenges":
                negative_result_links.append(
                    {
                        "negative_result_id": source_id,
                        "hypothesis_id": target_id,
                        "source_system": "provenance_replay",
                        "fact_id": str(relation.get("fact_id", "")).strip(),
                    }
                )
                negative_results.append(
                    {
                        "negative_result_id": source_id,
                        "result": source_id,
                        "affected_hypothesis_ids": [target_id],
                        "source_system": "provenance_replay",
                    }
                )
            edges.append(
                {
                    "source": source_id,
                    "target": target_id,
                    "relation": rel,
                    "source_system": "provenance_replay",
                }
            )

        return {
            "source_of_truth": "provenance_facts",
            "replay_summary": {
                "fact_count": replay.get("fact_count", 0),
                "claim_count": len(claims),
                "hypothesis_count": len(hypotheses),
                "evidence_count": len(evidence),
                "experiment_count": replay.get("experiment_count", 0),
                "artifact_count": len(asset_registry),
                "relation_count": len(edges),
            },
            "claims": claims,
            "evidence": evidence,
            "hypotheses": hypotheses,
            "negative_results": list({item["negative_result_id"]: item for item in negative_results}.values()),
            "negative_result_links": negative_result_links,
            "asset_registry": asset_registry,
            "edges": edges,
        }

    async def _execute_ready_packages(
        self,
        *,
        topic: str,
        research_state: dict[str, Any],
    ) -> dict[str, Any]:
        policy = self.collaboration_context.get("executor_policy", {})
        if not isinstance(policy, dict):
            policy = {}
        auto_execute = bool(policy.get("auto_dry_run", True))
        executor_type = str(policy.get("executor_type", "dry_run")).strip() or "dry_run"
        if executor_type != "dry_run" and not bool(policy.get("allow_non_dry_run", False)):
            return {
                "executor_registry": self.executor_registry.describe(),
                "run_count": 0,
                "skipped_count": 0,
                "policy_state": "non_dry_run_requires_explicit_allowance",
                "requested_executor_type": executor_type,
                "runs": [],
            }
        if not auto_execute:
            return {
                "executor_registry": self.executor_registry.describe(),
                "run_count": 0,
                "skipped_count": 0,
                "policy_state": "auto_execution_disabled",
                "requested_executor_type": executor_type,
                "runs": [],
            }
        workflow_control = research_state.get("workflow_control_summary", {})
        if isinstance(workflow_control, dict) and workflow_control.get("execution_gate") != "execution_allowed":
            return {
                "executor_registry": self.executor_registry.describe(),
                "run_count": 0,
                "skipped_count": 0,
                "policy_state": "blocked_by_workflow_control",
                "requested_executor_type": executor_type,
                "execution_gate": workflow_control.get("execution_gate", ""),
                "blocking_gates": workflow_control.get("blocking_gates", []),
                "allowed_next_actions": workflow_control.get("allowed_next_actions", []),
                "runs": [],
            }
        risk_permission = research_state.get("experiment_risk_permission_summary", {})
        if (
            isinstance(risk_permission, dict)
            and risk_permission.get("permission_state") in {"blocked", "requires_human_approval"}
            and executor_type != "dry_run"
        ):
            return {
                "executor_registry": self.executor_registry.describe(),
                "run_count": 0,
                "skipped_count": 0,
                "policy_state": "blocked_by_risk_permission",
                "requested_executor_type": executor_type,
                "permission_state": risk_permission.get("permission_state", ""),
                "overall_risk_level": risk_permission.get("overall_risk_level", ""),
                "required_approvals": risk_permission.get("required_approvals", []),
                "runs": [],
            }
        execution_registry = research_state.get("execution_adapter_registry_summary", {})
        handoff = research_state.get("run_handoff_contract_summary", {})
        packages = (
            execution_registry.get("execution_packages", [])
            if isinstance(execution_registry, dict) and isinstance(execution_registry.get("execution_packages", []), list)
            else []
        )
        contracts = (
            handoff.get("contracts", [])
            if isinstance(handoff, dict) and isinstance(handoff.get("contracts", []), list)
            else []
        )
        contracts_by_package = {
            str(contract.get("package_id", "")).strip(): contract
            for contract in contracts
            if isinstance(contract, dict) and str(contract.get("package_id", "")).strip()
        }
        max_runs = int(policy.get("max_auto_runs", 1) or 1)
        runs: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        project_id = str(self.collaboration_context.get("project_id", "")).strip()
        for package in packages:
            if len(runs) >= max_runs:
                break
            if not isinstance(package, dict):
                continue
            package_id = str(package.get("package_id", "")).strip()
            if str(package.get("package_state", "")).strip() != "ready_for_handoff":
                skipped.append(
                    {
                        "package_id": package_id,
                        "reason": f"package_state={package.get('package_state', '')}",
                    }
                )
                continue
            contract = contracts_by_package.get(package_id)
            if not contract:
                skipped.append({"package_id": package_id, "reason": "missing handoff contract"})
                continue
            result = await self.executor_registry.execute(
                package=package,
                contract=contract,
                executor_type=executor_type,
                executor_config=policy.get("executor_config", {}) if isinstance(policy.get("executor_config", {}), dict) else {},
                project_id=project_id,
                topic=topic,
            )
            run_payload = result.to_dict()
            bundle = run_payload.get("normalized_bundle", {}) if isinstance(run_payload.get("normalized_bundle", {}), dict) else {}
            if bundle:
                backpropagation_record = persist_run_handoff_bundle(
                    registry=self.experiment_registry,
                    bundle=bundle,
                )
                run_payload["backpropagation_record"] = backpropagation_record
                run_payload["experiment_registry_saved_records"] = backpropagation_record.get("saved_records", {})
                self._sync_executor_backpropagation_memory(
                    topic=topic,
                    backpropagation_record=backpropagation_record,
                )
            runs.append(run_payload)
            self._emit_runtime_event(
                "executor.run.completed",
                actor=result.executor_id,
                payload={
                    "package_id": result.package_id,
                    "experiment_id": result.experiment_id,
                    "execution_state": result.execution_state,
                    "provenance_fact_count": len(result.provenance_fact_ids),
                    "error_count": len(result.errors),
                },
            )
        return {
            "executor_registry": self.executor_registry.describe(),
            "policy_state": "executed" if runs else "no_ready_package_executed",
            "requested_executor_type": executor_type,
            "run_count": len(runs),
            "skipped_count": len(skipped),
            "runs": runs,
            "skipped": skipped[:20],
            "provenance_fact_count": sum(len(run.get("provenance_fact_ids", [])) for run in runs if isinstance(run, dict)),
            "provenance_event_count": sum(len(run.get("provenance_event_ids", [])) for run in runs if isinstance(run, dict)),
        }

    @staticmethod
    def _merge_provenance_claim_graph(
        claim_graph: dict[str, Any],
        provenance_claim_graph: dict[str, Any],
    ) -> dict[str, Any]:
        if not provenance_claim_graph:
            return {"merged": False, "reason": "no provenance replay available"}

        def merge_by_id(target_key: str, source_key: str, id_keys: list[str]) -> int:
            target = claim_graph.setdefault(target_key, [])
            source = provenance_claim_graph.get(source_key, [])
            if not isinstance(target, list) or not isinstance(source, list):
                return 0
            existing = {
                str(item.get(key, "")).strip()
                for item in target
                if isinstance(item, dict)
                for key in id_keys
                if str(item.get(key, "")).strip()
            }
            added = 0
            for item in source:
                if not isinstance(item, dict):
                    continue
                item_id = next((str(item.get(key, "")).strip() for key in id_keys if str(item.get(key, "")).strip()), "")
                if not item_id or item_id in existing:
                    continue
                target.append(item)
                existing.add(item_id)
                added += 1
            return added

        def merge_edges(target_key: str) -> int:
            target = claim_graph.setdefault(target_key, [])
            source = provenance_claim_graph.get(target_key, [])
            if not isinstance(target, list) or not isinstance(source, list):
                return 0
            existing = {
                (
                    str(item.get("source", item.get("negative_result_id", ""))).strip(),
                    str(item.get("target", item.get("hypothesis_id", ""))).strip(),
                    str(item.get("relation", "challenges" if target_key == "negative_result_links" else "")).strip(),
                )
                for item in target
                if isinstance(item, dict)
            }
            added = 0
            for item in source:
                if not isinstance(item, dict):
                    continue
                signature = (
                    str(item.get("source", item.get("negative_result_id", ""))).strip(),
                    str(item.get("target", item.get("hypothesis_id", ""))).strip(),
                    str(item.get("relation", "challenges" if target_key == "negative_result_links" else "")).strip(),
                )
                if not signature[0] or not signature[1] or signature in existing:
                    continue
                target.append(item)
                existing.add(signature)
                added += 1
            return added

        added_claims = merge_by_id("claims", "claims", ["global_claim_id", "claim_id"])
        added_evidence = merge_by_id("evidence", "evidence", ["global_evidence_id", "evidence_id"])
        added_hypotheses = merge_by_id("hypotheses", "hypotheses", ["global_hypothesis_id", "hypothesis_id"])
        added_negative = merge_by_id("negative_results", "negative_results", ["negative_result_id", "global_negative_result_id"])
        added_assets = merge_by_id("asset_registry", "asset_registry", ["asset_id"])
        added_edges = merge_edges("edges")
        added_negative_links = merge_edges("negative_result_links")
        return {
            "merged": True,
            "source_of_truth": "provenance_facts",
            "added_claims": added_claims,
            "added_evidence": added_evidence,
            "added_hypotheses": added_hypotheses,
            "added_negative_results": added_negative,
            "added_assets": added_assets,
            "added_edges": added_edges,
            "added_negative_result_links": added_negative_links,
            "replay_summary": provenance_claim_graph.get("replay_summary", {}),
        }

    @staticmethod
    def _slugify_text(value: str) -> str:
        safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
        while "--" in safe:
            safe = safe.replace("--", "-")
        return safe.strip("-") or "topic"

    @staticmethod
    def _artifact_node_type(*, kind: str, path: str, scope: str = "") -> str:
        lowered_kind = kind.strip().lower()
        lowered_path = path.strip().lower()
        lowered_scope = scope.strip().lower()
        if lowered_kind in {"dataset", "table"} or lowered_scope == "input" or lowered_path.endswith((".csv", ".tsv", ".xlsx", ".parquet")):
            return "dataset"
        if lowered_kind in {"checkpoint", "model"} or lowered_path.endswith((".pt", ".pth", ".ckpt", ".bin")):
            return "checkpoint"
        if lowered_kind in {"spectrum", "chromatogram"} or lowered_path.endswith((".mzml", ".cdf", ".jdx")):
            return "spectrum"
        if lowered_kind in {"notebook"} or lowered_path.endswith(".ipynb"):
            return "notebook"
        if lowered_kind in {"figure", "plot"} or lowered_path.endswith((".png", ".jpg", ".jpeg", ".svg", ".pdf")):
            return "figure"
        if lowered_kind in {"proof_note"} or "proof" in lowered_path:
            return "proof_note"
        return "artifact"

    @staticmethod
    def _derive_project_distill(
        *,
        topic: str,
        steps: list[WorkflowStepResult],
        literature_synthesis: dict[str, Any],
        causal_reasoning: dict[str, Any],
        analysis_rigor: dict[str, Any],
        consensus_state: dict[str, Any],
        asset_registry_summary: dict[str, Any],
        experiment_economics_summary: dict[str, Any],
        lab_meeting_consensus_summary: dict[str, Any],
    ) -> dict[str, Any]:
        belief_updater = next((step for step in steps if step.profile_name == "belief_updater"), None)
        coordinator = next((step for step in steps if step.profile_name == "coordinator"), None)
        payload = {}
        if belief_updater is not None:
            payload = belief_updater.parsed_output.get("project_distill", {})
        if (not isinstance(payload, dict) or not payload) and coordinator is not None:
            payload = coordinator.parsed_output.get("project_distill", {})
        if not isinstance(payload, dict):
            payload = {}
        failed_routes = payload.get("failed_routes", [])
        if not isinstance(failed_routes, list) or not failed_routes:
            failed_routes = [
                str(item.get("result", "")).strip()
                for step in steps
                for item in step.parsed_output.get("negative_results", [])
                if isinstance(item, dict) and str(item.get("result", "")).strip()
            ][:6]
        next_cycle_goals = payload.get("next_cycle_goals", [])
        if not isinstance(next_cycle_goals, list) or not next_cycle_goals:
            next_cycle_goals = list(
                dict.fromkeys(
                    experiment_economics_summary.get("cheapest_discriminative_actions", [])[:2]
                    + lab_meeting_consensus_summary.get("evidence_needed_to_close", [])[:2]
                    + literature_synthesis.get("evidence_gaps", [])
                    + causal_reasoning.get("priority_confounders", [])[:2]
                    + analysis_rigor.get("sensitivity_checks", [])[:2]
                )
            )[:6]
        next_cycle_goals = list(
            dict.fromkeys(
                next_cycle_goals
                + experiment_economics_summary.get("expected_information_gain", [])[:2]
            )
        )[:8]
        return {
            "topic": topic,
            "current_consensus": str(payload.get("current_consensus", "")).strip()
            or "; ".join(lab_meeting_consensus_summary.get("agenda_items", [])[:1])
            or "; ".join(consensus_state.get("agreed_points", [])[:3])
            or "Consensus is still forming.",
            "failed_routes": failed_routes,
            "next_cycle_goals": next_cycle_goals,
            "registry_updates": payload.get("registry_updates", []) or [
                f"track-assets:{asset_registry_summary.get('asset_count', 0)}",
                f"consensus:{consensus_state.get('consensus_status', 'partial')}",
            ],
        }

    @staticmethod
    def _derive_execution_cycle_summary(
        *,
        experiment_runs: list[dict[str, Any]],
        quality_control_reviews: list[dict[str, Any]],
        interpretation_records: list[dict[str, Any]],
    ) -> dict[str, Any]:
        run_status_counts: dict[str, int] = {}
        quality_status_counts: dict[str, int] = {}
        repeat_required_count = 0
        unusable_count = 0
        negative_interpretation_count = 0
        next_decisions: list[str] = []

        for item in experiment_runs:
            status = str(item.get("status", "")).strip() or "unknown"
            run_status_counts[status] = run_status_counts.get(status, 0) + 1
        for item in quality_control_reviews:
            status = str(item.get("quality_control_status", "")).strip() or "unknown"
            quality_status_counts[status] = quality_status_counts.get(status, 0) + 1
            if bool(item.get("repeat_required", False)):
                repeat_required_count += 1
            if not bool(item.get("usable_for_interpretation", True)):
                unusable_count += 1
        for item in interpretation_records:
            if bool(item.get("negative_result", False)):
                negative_interpretation_count += 1
            decision = str(item.get("next_decision", "")).strip()
            if decision:
                next_decisions.append(decision)

        return {
            "experiment_run_count": len(experiment_runs),
            "quality_control_review_count": len(quality_control_reviews),
            "interpretation_record_count": len(interpretation_records),
            "run_status_counts": run_status_counts,
            "quality_control_status_counts": quality_status_counts,
            "quality_control_failed_count": int(quality_status_counts.get("failed", 0)),
            "quality_control_warning_count": int(quality_status_counts.get("warning", 0)),
            "quality_control_passed_count": int(quality_status_counts.get("passed", 0)),
            "repeat_required_count": repeat_required_count,
            "non_interpretable_review_count": unusable_count,
            "unusable_for_interpretation_count": unusable_count,
            "negative_interpretation_count": negative_interpretation_count,
            "next_decisions": list(dict.fromkeys(next_decisions))[:8],
        }

    @staticmethod
    def _derive_experiment_governance_summary(
        *,
        experiment_runs: list[dict[str, Any]],
        quality_control_reviews: list[dict[str, Any]],
        interpretation_records: list[dict[str, Any]],
        claim_graph: dict[str, Any],
    ) -> dict[str, Any]:
        status_counts: dict[str, int] = {}
        quarantine_runs: list[str] = []
        rerun_candidates: list[str] = []
        approval_gate_needed = False
        for item in experiment_runs:
            status = str(item.get("status", "")).strip().lower() or "unknown"
            status_counts[status] = status_counts.get(status, 0) + 1
            run_id = str(item.get("run_id", "")).strip()
            if status in {"planned", "approved"}:
                approval_gate_needed = True
            if status in {"quality_control_failed", "qc_failed"} and run_id:
                quarantine_runs.append(run_id)
        for item in quality_control_reviews:
            run_id = str(item.get("run_id", "")).strip()
            review_status = str(item.get("quality_control_status", "")).strip().lower()
            if bool(item.get("repeat_required", False)) and run_id:
                rerun_candidates.append(run_id)
            if review_status == "failed" and run_id:
                quarantine_runs.append(run_id)
        protocol_assets = [
            item
            for item in (
                claim_graph.get("asset_registry", [])
                if isinstance(claim_graph.get("asset_registry", []), list)
                else []
            )
            if isinstance(item, dict) and str(item.get("asset_type", "")).strip() == "experimental_protocol"
        ]
        interpreted_run_ids = {
            str(item.get("run_id", "")).strip()
            for item in interpretation_records
            if isinstance(item, dict) and str(item.get("run_id", "")).strip()
        }
        governance_risks: list[str] = []
        if approval_gate_needed:
            governance_risks.append("there are planned or approved runs that have not yet cleared execution governance")
        if quarantine_runs:
            governance_risks.append("some runs should be quarantined because quality control failed")
        if len(protocol_assets) > len({str(item.get("experiment_id", "")).strip() for item in experiment_runs if isinstance(item, dict)}):
            governance_risks.append("protocol lineage may be diverging from run lineage")
        return {
            "run_status_counts": status_counts,
            "approval_gate_needed": approval_gate_needed,
            "quarantine_runs": list(dict.fromkeys(quarantine_runs))[:10],
            "rerun_candidates": list(dict.fromkeys(rerun_candidates))[:10],
            "interpreted_run_count": len(interpreted_run_ids),
            "protocol_record_count": len(protocol_assets),
            "governance_risks": governance_risks[:8],
        }

    @staticmethod
    def _derive_failure_intelligence_summary(
        *,
        steps: list[WorkflowStepResult],
        claim_graph: dict[str, Any],
        execution_cycle_summary: dict[str, Any],
    ) -> dict[str, Any]:
        technical_failures: list[str] = []
        theoretical_failures: list[str] = []
        evidence_failures: list[str] = []
        avoid_repeat_routes: list[str] = []
        for step in steps:
            parsed = step.parsed_output
            for item in parsed.get("negative_results", []) if isinstance(parsed.get("negative_results", []), list) else []:
                if not isinstance(item, dict):
                    continue
                result = str(item.get("result", "")).strip()
                why = str(item.get("why_it_failed_or_did_not_support", "")).strip().lower()
                implication = str(item.get("implication", "")).strip().lower()
                if any(token in why for token in ["instrument", "calibration", "noise", "quality", "protocol", "execution", "data leakage"]):
                    technical_failures.append(result or why)
                elif any(token in implication for token in ["hypothesis", "mechanism", "theory", "assumption", "causal"]):
                    theoretical_failures.append(result or implication)
                else:
                    evidence_failures.append(result or implication or why)
                for hypothesis_id in (
                    item.get("affected_hypothesis_ids", [])
                    if isinstance(item.get("affected_hypothesis_ids", []), list)
                    else []
                ):
                    if str(hypothesis_id).strip():
                        avoid_repeat_routes.append(str(hypothesis_id).strip())
        for item in claim_graph.get("hypotheses", []) if isinstance(claim_graph.get("hypotheses", []), list) else []:
            if not isinstance(item, dict):
                continue
            if str(item.get("status", "")).strip().lower() in {"deprecated", "rejected"}:
                hypothesis_id = str(item.get("global_hypothesis_id", "")).strip()
                if hypothesis_id:
                    avoid_repeat_routes.append(hypothesis_id)
        dominant_failure_class = "mixed"
        if len(technical_failures) > max(len(theoretical_failures), len(evidence_failures)):
            dominant_failure_class = "technical"
        elif len(theoretical_failures) > max(len(technical_failures), len(evidence_failures)):
            dominant_failure_class = "theoretical"
        elif len(evidence_failures) > max(len(technical_failures), len(theoretical_failures)):
            dominant_failure_class = "evidentiary"
        return {
            "technical_failures": list(dict.fromkeys(technical_failures))[:8],
            "theoretical_failures": list(dict.fromkeys(theoretical_failures))[:8],
            "evidence_failures": list(dict.fromkeys(evidence_failures))[:8],
            "avoid_repeat_routes": list(dict.fromkeys(avoid_repeat_routes))[:10],
            "dominant_failure_class": dominant_failure_class,
            "negative_interpretation_count": int(
                execution_cycle_summary.get("negative_interpretation_count", 0) or 0
            ),
        }

    @staticmethod
    def _derive_experiment_economics_summary(
        *,
        topic: str,
        steps: list[WorkflowStepResult],
        research_plan_summary: dict[str, Any],
        discipline_adaptation_summary: dict[str, Any],
        execution_cycle_summary: dict[str, Any],
        failure_intelligence_summary: dict[str, Any],
    ) -> dict[str, Any]:
        specialist_payload = next(
            (
                step.parsed_output.get("experiment_economics", {})
                for step in steps
                if step.profile_name == "experiment_economist"
                and isinstance(step.parsed_output.get("experiment_economics", {}), dict)
                and step.parsed_output.get("experiment_economics", {})
            ),
            {},
        )
        primary_discipline = str(
            discipline_adaptation_summary.get("primary_discipline", "general_science")
        ).strip()
        next_cycle_count = len(research_plan_summary.get("next_cycle_experiments", []))
        repeat_count = int(execution_cycle_summary.get("repeat_required_count", 0) or 0)
        failed_quality = int(execution_cycle_summary.get("quality_control_failed_count", 0) or 0)
        cost_pressure = "medium"
        time_pressure = "medium"
        if primary_discipline in {"chemistry", "chemical_engineering", "physics"} or repeat_count >= 2:
            cost_pressure = "high"
        if primary_discipline == "artificial_intelligence" and "benchmark" in topic.lower():
            cost_pressure = "medium"
        if next_cycle_count >= 3 or failed_quality >= 2:
            time_pressure = "high"
        cheapest_actions = list(
            dict.fromkeys(
                research_plan_summary.get("decision_gates", [])[:2]
                + research_plan_summary.get("information_gain_priorities", [])[:3]
            )
        )[:5]
        if not cheapest_actions:
            cheapest_actions = ["run the smallest discriminative next-step experiment first"]
        return {
            "primary_discipline": primary_discipline,
            "cost_pressure": str(specialist_payload.get("cost_pressure", "")).strip() or cost_pressure,
            "time_pressure": str(specialist_payload.get("time_pressure", "")).strip() or time_pressure,
            "repeat_burden": repeat_count,
            "quality_failure_burden": failed_quality,
            "information_gain_pressure": (
                str(specialist_payload.get("information_gain_pressure", "")).strip()
                or (
                "high" if next_cycle_count or failure_intelligence_summary.get("avoid_repeat_routes") else "medium"
                )
            ),
            "cheapest_discriminative_actions": (
                [
                    str(item)
                    for item in specialist_payload.get("cheapest_discriminative_actions", [])
                    if str(item).strip()
                ]
                or cheapest_actions
            )[:6],
            "resource_risks": [
                str(item)
                for item in specialist_payload.get("resource_risks", [])
                if str(item).strip()
            ][:6],
            "defer_candidates": [
                str(item)
                for item in specialist_payload.get("defer_candidates", [])
                if str(item).strip()
            ][:6],
            "expected_information_gain": [
                str(item)
                for item in specialist_payload.get("expected_information_gain", [])
                if str(item).strip()
            ][:6],
        }

    @staticmethod
    def _derive_lab_meeting_consensus_summary(
        *,
        steps: list[WorkflowStepResult],
        consensus_state: dict[str, Any],
        consensus_state_machine: dict[str, Any],
        failure_intelligence_summary: dict[str, Any],
    ) -> dict[str, Any]:
        moderator_payload = next(
            (
                step.parsed_output.get("lab_meeting_consensus", {})
                for step in steps
                if step.profile_name == "lab_meeting_moderator"
                and isinstance(step.parsed_output.get("lab_meeting_consensus", {}), dict)
                and step.parsed_output.get("lab_meeting_consensus", {})
            ),
            {},
        )
        agent_positions: list[dict[str, Any]] = []
        for step in steps:
            payload = (
                step.parsed_output.get("consensus_summary", {})
                if isinstance(step.parsed_output.get("consensus_summary", {}), dict)
                else {}
            )
            if not payload:
                continue
            agent_positions.append(
                {
                    "agent": step.profile_name,
                    "consensus_status": str(payload.get("consensus_status", "")).strip() or "partial",
                    "agreed_point_count": len(payload.get("agreed_points", []) if isinstance(payload.get("agreed_points", []), list) else []),
                    "unresolved_point_count": len(payload.get("unresolved_points", []) if isinstance(payload.get("unresolved_points", []), list) else []),
                }
            )
        evidence_needed = list(
            dict.fromkeys(
                consensus_state.get("unresolved_points", [])[:3]
                + failure_intelligence_summary.get("technical_failures", [])[:2]
                + failure_intelligence_summary.get("theoretical_failures", [])[:2]
            )
        )[:8]
        return {
            "meeting_state": str(consensus_state_machine.get("current_state", "forming")).strip(),
            "agenda_items": (
                [
                    str(item)
                    for item in moderator_payload.get("agenda_items", [])
                    if str(item).strip()
                ]
                or consensus_state.get("unresolved_points", [])
            )[:8],
            "agent_positions": agent_positions[:10],
            "position_summaries": [
                str(item)
                for item in moderator_payload.get("position_summaries", [])
                if str(item).strip()
            ][:8],
            "evidence_needed_to_close": (
                [
                    str(item)
                    for item in moderator_payload.get("evidence_needed_to_close", [])
                    if str(item).strip()
                ]
                or evidence_needed
            )[:8],
            "chair_recommendation": (
                str(moderator_payload.get("chair_recommendation", "")).strip()
                or str(
                    consensus_state_machine.get(
                        "suggested_action", "collect_discriminative_evidence"
                    )
                ).strip()
            ),
            "decision_rule": (
                str(moderator_payload.get("decision_rule", "")).strip()
                or "advance only when disagreement is narrowed by discriminative evidence"
            ),
            "blocking_concerns": [
                str(item)
                for item in moderator_payload.get("blocking_concerns", [])
                if str(item).strip()
            ][:8],
            "provisional_decisions": [
                str(item)
                for item in moderator_payload.get("provisional_decisions", [])
                if str(item).strip()
            ][:8],
        }

    def _derive_agent_stance_continuity_summary(
        self,
        *,
        topic: str,
        steps: list[WorkflowStepResult],
        lab_meeting_consensus_summary: dict[str, Any],
    ) -> dict[str, Any]:
        project_id = str(self.collaboration_context.get("project_id", "")).strip()
        current_records = self._extract_current_agent_stance_records(
            steps=steps,
            lab_meeting_consensus_summary=lab_meeting_consensus_summary,
        )
        previous_records = self._load_previous_agent_stance_records(topic=topic, project_id=project_id)
        records: list[dict[str, Any]] = []
        for record in current_records:
            agent = str(record.get("agent", "")).strip()
            previous = previous_records.get(agent, {})
            previous_position = str(previous.get("current_position", "") or previous.get("position", "")).strip()
            previous_label = str(previous.get("stance_label", "")).strip()
            current_position = str(record.get("current_position", "")).strip()
            current_label = str(record.get("stance_label", "")).strip()
            changed = bool(
                previous_position
                and self._normalize_stance_text(previous_position)
                != self._normalize_stance_text(current_position)
            )
            if not previous:
                continuity_state = "new_position"
                change_type = "new"
            elif not current_position:
                continuity_state = "missing_current_position"
                change_type = "unknown"
            elif not changed and previous_label == current_label:
                continuity_state = "continuous"
                change_type = "stable"
            else:
                continuity_state = (
                    "changed_with_reason"
                    if record.get("change_reason")
                    else "changed_without_explicit_reason"
                )
                change_type = self._classify_stance_change(previous_label, current_label)
            records.append(
                {
                    **record,
                    "previous_position": previous_position,
                    "previous_stance_label": previous_label,
                    "previous_recorded_at": str(previous.get("recorded_at", "")).strip(),
                    "changed": changed,
                    "change_type": change_type,
                    "continuity_state": continuity_state,
                }
            )

        missing_reason_count = len(
            [
                item
                for item in records
                if item.get("continuity_state") == "changed_without_explicit_reason"
            ]
        )
        unresolved_objection_count = sum(
            len(item.get("blocking_concerns", []) if isinstance(item.get("blocking_concerns", []), list) else [])
            + len(item.get("open_questions", []) if isinstance(item.get("open_questions", []), list) else [])
            for item in records
        )
        return {
            "topic": topic,
            "project_id": project_id,
            "role_memory_state": "ready" if records and not missing_reason_count else "needs_review",
            "agent_count": len(records),
            "prior_agent_count": len(previous_records),
            "changed_count": len([item for item in records if item.get("changed")]),
            "missing_change_reason_count": missing_reason_count,
            "unresolved_objection_count": unresolved_objection_count,
            "continuity_ready": bool(records and not missing_reason_count),
            "records": records[:20],
            "standing_objections": [
                concern
                for item in records
                for concern in (
                    item.get("blocking_concerns", [])
                    if isinstance(item.get("blocking_concerns", []), list)
                    else []
                )
                if str(concern).strip()
            ][:12],
            "role_memory_updates": [
                {
                    "agent": item.get("agent", ""),
                    "continuity_state": item.get("continuity_state", ""),
                    "change_type": item.get("change_type", ""),
                    "current_position": item.get("current_position", ""),
                }
                for item in records[:12]
            ],
            "policy": (
                "Each specialist keeps a persistent stance. A changed stance is acceptable only "
                "when tied to new evidence, failed attempts, boundary conditions, or explicit uncertainty."
            ),
        }

    def _extract_current_agent_stance_records(
        self,
        *,
        steps: list[WorkflowStepResult],
        lab_meeting_consensus_summary: dict[str, Any],
    ) -> list[dict[str, Any]]:
        meeting_positions = {
            str(item.get("agent", "")).strip(): item
            for item in lab_meeting_consensus_summary.get("agent_positions", [])
            if isinstance(item, dict) and str(item.get("agent", "")).strip()
        } if isinstance(lab_meeting_consensus_summary.get("agent_positions", []), list) else {}
        records: list[dict[str, Any]] = []
        for step in steps:
            parsed = step.parsed_output if isinstance(step.parsed_output, dict) else {}
            consensus = parsed.get("consensus_summary", {}) if isinstance(parsed.get("consensus_summary", {}), dict) else {}
            meeting_position = meeting_positions.get(step.profile_name, {})
            current_position = self._first_nonempty(
                consensus.get("position"),
                consensus.get("stance"),
                consensus.get("consensus_status"),
                parsed.get("position"),
                parsed.get("stance"),
                parsed.get("recommendation"),
                parsed.get("chair_recommendation"),
                self._summarize_agent_step_position(parsed),
                meeting_position.get("consensus_status"),
            )
            agreed_points = self._strings(consensus.get("agreed_points", []))[:6]
            unresolved_points = self._strings(consensus.get("unresolved_points", []))[:6]
            open_questions = self._strings(parsed.get("open_questions", []))[:6]
            blocking_concerns = list(dict.fromkeys(unresolved_points + self._strings(parsed.get("blockers", []))))[:8]
            evidence_refs = self._extract_agent_stance_evidence_refs(parsed, consensus)
            stance_label = self._infer_stance_label(
                " ".join([current_position, " ".join(agreed_points), " ".join(blocking_concerns)])
            )
            change_reason = self._first_nonempty(
                consensus.get("change_reason"),
                parsed.get("change_reason"),
                parsed.get("rationale"),
                "new evidence or graph reference" if evidence_refs else "",
                "unresolved objection or boundary condition" if blocking_concerns else "",
            )
            records.append(
                {
                    "agent": step.profile_name,
                    "current_position": current_position or "position not explicitly stated",
                    "stance_label": stance_label,
                    "agreed_points": agreed_points,
                    "open_questions": list(dict.fromkeys(open_questions + unresolved_points))[:8],
                    "blocking_concerns": blocking_concerns,
                    "evidence_refs": evidence_refs,
                    "change_reason": change_reason,
                    "source_profile": step.profile_name,
                    "position_source": "consensus_summary" if consensus else "step_output_inference",
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        return records

    def _load_previous_agent_stance_records(self, *, topic: str, project_id: str) -> dict[str, dict[str, Any]]:
        if not project_id:
            return {}
        facts = [
            item
            for item in self.graph_registry.load_facts(project_id=project_id, topic=topic)
            if isinstance(item, dict)
            and str(item.get("fact_type", "")).strip() == "agent_stance"
            and str(item.get("predicate", "")).strip() == "holds_position"
            and str(item.get("status", "active")).strip() == "active"
        ]
        by_agent: dict[str, dict[str, Any]] = {}
        for fact in facts:
            value = fact.get("value", {}) if isinstance(fact.get("value", {}), dict) else {}
            agent = str(fact.get("produced_by", "") or value.get("agent", "")).strip()
            if not agent:
                continue
            metadata = fact.get("metadata", {}) if isinstance(fact.get("metadata", {}), dict) else {}
            record = {
                **value,
                "recorded_at": str(metadata.get("recorded_at", "") or value.get("recorded_at", "")).strip(),
                "fact_id": str(fact.get("fact_id", "")).strip(),
            }
            previous = by_agent.get(agent)
            if previous is None or str(record.get("recorded_at", "")) >= str(previous.get("recorded_at", "")):
                by_agent[agent] = record
        return by_agent

    @staticmethod
    def _summarize_agent_step_position(parsed: dict[str, Any]) -> str:
        for key in [
            "summary",
            "interpretation",
            "decision",
            "conclusion",
            "analysis_summary",
            "review_summary",
        ]:
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:240]
        hypotheses = parsed.get("hypotheses", []) if isinstance(parsed.get("hypotheses", []), list) else []
        if hypotheses:
            first = hypotheses[0]
            if isinstance(first, dict):
                return str(first.get("statement", "") or first.get("hypothesis", "")).strip()[:240]
        return ""

    @staticmethod
    def _extract_agent_stance_evidence_refs(parsed: dict[str, Any], consensus: dict[str, Any]) -> list[str]:
        refs: list[str] = []
        refs.extend(ScientificWorkflow._strings(consensus.get("evidence_refs", [])))
        graph_refs = parsed.get("graph_references", {}) if isinstance(parsed.get("graph_references", {}), dict) else {}
        refs.extend(ScientificWorkflow._strings(graph_refs.get("node_refs", [])))
        refs.extend(ScientificWorkflow._strings(graph_refs.get("edge_refs", [])))
        for evidence in parsed.get("evidence", []) if isinstance(parsed.get("evidence", []), list) else []:
            if isinstance(evidence, dict):
                refs.append(
                    str(
                        evidence.get("global_evidence_id", "")
                        or evidence.get("evidence_id", "")
                        or evidence.get("source_id", "")
                    ).strip()
                )
        for item in parsed.get("negative_results", []) if isinstance(parsed.get("negative_results", []), list) else []:
            if isinstance(item, dict):
                refs.append(str(item.get("negative_result_id", "")).strip())
        return list(dict.fromkeys([ref for ref in refs if ref]))[:12]

    @staticmethod
    def _infer_stance_label(text: str) -> str:
        lower = text.lower()
        if any(token in lower for token in ["reject", "block", "challenge", "skeptic", "concern", "negative", "failed"]):
            return "skeptical"
        if any(token in lower for token in ["support", "agree", "advance", "ready", "confirm"]):
            return "supportive"
        if any(token in lower for token in ["validate", "quality", "review", "repair", "audit"]):
            return "quality_control"
        if any(token in lower for token in ["experiment", "test", "measure", "simulate", "execute"]):
            return "experimental"
        if any(token in lower for token in ["uncertain", "partial", "mixed", "ambiguous"]):
            return "cautious"
        return "neutral"

    @staticmethod
    def _classify_stance_change(previous_label: str, current_label: str) -> str:
        previous = previous_label.strip().lower()
        current = current_label.strip().lower()
        if not previous:
            return "new"
        if previous == current:
            return "reframed"
        if {previous, current} == {"supportive", "skeptical"}:
            return "reversed"
        if previous == "skeptical" and current in {"cautious", "neutral", "quality_control"}:
            return "softened"
        if previous in {"neutral", "cautious"} and current in {"supportive", "skeptical"}:
            return "strengthened"
        return "shifted"

    @staticmethod
    def _normalize_stance_text(text: str) -> str:
        return " ".join(str(text).strip().lower().split())

    @staticmethod
    def _first_nonempty(*values: Any) -> str:
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _strings(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, tuple):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    @staticmethod
    def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in items:
            value = str(item.get(key, "")).strip() or "unknown"
            counts[value] = counts.get(value, 0) + 1
        return counts

    @staticmethod
    def _slugify(value: str) -> str:
        return ScientificWorkflow._slugify_text(value)

    @staticmethod
    def _effect_direction(text: str) -> str:
        lowered = str(text).lower()
        positive_terms = ["increase", "improve", "higher", "positive", "enhance", "promote", "yield"]
        negative_terms = ["decrease", "reduce", "lower", "negative", "inhibit", "suppress", "fail"]
        null_terms = ["null", "no effect", "insignificant", "unchanged", "no difference"]
        if any(term in lowered for term in null_terms):
            return "null"
        if any(term in lowered for term in positive_terms) and not any(term in lowered for term in negative_terms):
            return "positive"
        if any(term in lowered for term in negative_terms) and not any(term in lowered for term in positive_terms):
            return "negative"
        if any(term in lowered for term in positive_terms + negative_terms):
            return "mixed"
        return "unclear"

    @staticmethod
    def _bias_risk(evidence_record: dict[str, Any]) -> str:
        explicit = str(evidence_record.get("bias_risk", "")).strip().lower()
        if explicit in {"low", "medium", "moderate", "high", "unclear"}:
            return "medium" if explicit == "moderate" else explicit
        evidence_grade = str(evidence_record.get("evidence_grade", "")).strip().lower()
        if evidence_grade in {"low", "very_low"}:
            return "high"
        if evidence_grade in {"unclear", "unknown"}:
            return "unclear"
        text = " ".join(
            [
                str(evidence_record.get("method", "")),
                " ".join(ScientificWorkflow._strings(evidence_record.get("limitations", []))),
            ]
        ).lower()
        if any(term in text for term in ["low", "randomized", "controlled", "replicate", "pre-registered"]):
            return "low"
        if any(term in text for term in ["high", "unclear", "weak", "single", "uncontrolled", "selection", "confound"]):
            return "high"
        if not text.strip():
            return "unclear"
        return "medium"

    @staticmethod
    def _bias_domains(evidence_record: dict[str, Any]) -> list[str]:
        text = " ".join(
            [
                str(evidence_record.get("method", "")),
                str(evidence_record.get("sample_or_scope", "")),
                " ".join(ScientificWorkflow._strings(evidence_record.get("limitations", []))),
            ]
        ).lower()
        domains: list[str] = []
        if any(term in text for term in ["selection", "sample", "dataset", "population"]):
            domains.append("selection_bias")
        if any(term in text for term in ["measurement", "instrument", "metric", "assay", "calibration"]):
            domains.append("measurement_bias")
        if any(term in text for term in ["confound", "baseline", "control"]):
            domains.append("confounding")
        if any(term in text for term in ["publication", "positive-only", "reporting"]):
            domains.append("reporting_bias")
        return domains or ["not_assessed"]

    @staticmethod
    def _meta_analysis_readiness(evidence_table: list[dict[str, Any]]) -> str:
        if len(evidence_table) < 3:
            return "insufficient_evidence"
        methods = {str(item.get("method", "")).strip().lower() for item in evidence_table if str(item.get("method", "")).strip()}
        directions = {str(item.get("effect_direction", "")).strip().lower() for item in evidence_table if str(item.get("effect_direction", "")).strip()}
        if len(methods) <= 2 and len(directions) <= 2:
            return "candidate_for_meta_analysis"
        return "requires_stratification"

    @staticmethod
    def _review_decision_implications(
        synthesis_state: str,
        conflict_matrix: list[dict[str, Any]],
        evidence_review_summary: dict[str, Any],
    ) -> list[str]:
        implications: list[str] = []
        if synthesis_state == "blocked":
            implications.append("do not promote claims until review protocol and evidence table are repaired")
        if synthesis_state == "needs_stratified_synthesis":
            implications.append("stratify claims by method, population/material, and measurement boundary before deciding")
        if conflict_matrix:
            implications.append("route contested questions into discriminating experiments or targeted literature search")
        if evidence_review_summary.get("review_blockers"):
            implications.append("carry evidence review blockers into scheduler constraints")
        return implications or ["systematic review can inform hypothesis ranking and next-cycle planning"]

    @staticmethod
    def _review_scheduler_constraints(
        synthesis_state: str,
        protocol_gaps: list[str],
        conflict_matrix: list[dict[str, Any]],
    ) -> list[str]:
        constraints: list[str] = []
        if protocol_gaps:
            constraints.append("repair systematic review protocol before high-cost experiments")
        if synthesis_state == "blocked":
            constraints.append("schedule low-cost evidence repair or source screening first")
        if conflict_matrix:
            constraints.append("prioritize experiments that resolve explicit literature conflicts")
        return constraints or ["use systematic review evidence grades as scheduler priors"]

    @staticmethod
    def _derive_hypothesis_system_summary(
        *,
        topic: str,
        hypothesis_tree_summary: dict[str, Any],
        theoretical_hypothesis_tree_summary: dict[str, Any],
        hypothesis_theory_summary: dict[str, Any],
        hypothesis_validation_summary: dict[str, Any],
        hypothesis_gate_summary: dict[str, Any],
        mechanism_family_lifecycle_summary: dict[str, Any],
        theory_prediction_compiler_summary: dict[str, Any],
    ) -> dict[str, Any]:
        theory_objects = hypothesis_theory_summary.get("objects", [])
        theory_objects = theory_objects if isinstance(theory_objects, list) else []
        hypothesis_count = int(hypothesis_tree_summary.get("hypothesis_count", 0) or 0)
        accepted = ScientificWorkflow._strings(hypothesis_gate_summary.get("accepted_hypotheses", []))
        revise = ScientificWorkflow._strings(hypothesis_gate_summary.get("revise_hypotheses", []))
        blocked = ScientificWorkflow._strings(hypothesis_gate_summary.get("blocked_hypotheses", []))
        prediction_count = int(theory_prediction_compiler_summary.get("prediction_count", 0) or 0)
        discriminating_count = int(theory_prediction_compiler_summary.get("discriminating_test_count", 0) or 0)
        gate_state = str(hypothesis_gate_summary.get("gate_state", "not_evaluated")).strip()
        maturity = "empty"
        if hypothesis_count:
            maturity = "candidate"
        if theory_objects:
            maturity = "theory_objects_available"
        if prediction_count and discriminating_count:
            maturity = "predictive"
        if gate_state in {"blocked", "revision_required"}:
            maturity = "needs_revision"
        return {
            "hypothesis_system_id": f"hypothesis-system::{ScientificWorkflow._slugify(topic)}",
            "topic": topic,
            "system_state": maturity,
            "hypothesis_count": hypothesis_count,
            "theory_object_count": len(theory_objects),
            "accepted_hypothesis_count": len(accepted),
            "revise_hypothesis_count": len(revise),
            "blocked_hypothesis_count": len(blocked),
            "prediction_count": prediction_count,
            "discriminating_test_count": discriminating_count,
            "mechanism_family_count": int(mechanism_family_lifecycle_summary.get("family_count", 0) or 0),
            "theory_family_count": int(theoretical_hypothesis_tree_summary.get("family_count", 0) or 0),
            "gate_state": gate_state,
            "canonical_layers": {
                "tree": hypothesis_tree_summary,
                "theory_tree": theoretical_hypothesis_tree_summary,
                "theory_objects": hypothesis_theory_summary,
                "validators": hypothesis_validation_summary,
                "gate": hypothesis_gate_summary,
                "mechanism_lifecycle": mechanism_family_lifecycle_summary,
                "prediction_compiler": theory_prediction_compiler_summary,
            },
            "blocking_reasons": (
                blocked
                + ScientificWorkflow._strings(hypothesis_gate_summary.get("gate_blockers", []))
                + ScientificWorkflow._strings(theory_prediction_compiler_summary.get("formalization_gaps", []))
            )[:12],
        }

    @staticmethod
    def _derive_scientific_evaluation_system_summary(
        *,
        topic: str,
        benchmark_harness_summary: dict[str, Any],
        benchmark_case_suite_summary: dict[str, Any],
        kaivu_evaluation_harness_summary: dict[str, Any],
        evaluation_summary: dict[str, Any],
    ) -> dict[str, Any]:
        scientific_benchmark = (
            benchmark_case_suite_summary.get("scientific_evaluation_benchmark_summary", {})
            if isinstance(benchmark_case_suite_summary.get("scientific_evaluation_benchmark_summary", {}), dict)
            else {}
        )
        blocking_gates = ScientificWorkflow._strings(
            kaivu_evaluation_harness_summary.get("blocking_gates", [])
        )
        benchmark_gaps = ScientificWorkflow._strings(benchmark_case_suite_summary.get("benchmark_gaps", []))
        harness_gaps = ScientificWorkflow._strings(benchmark_harness_summary.get("benchmark_gaps", []))
        release_state = str(kaivu_evaluation_harness_summary.get("release_state", "")).strip()
        if not release_state:
            release_state = str(benchmark_harness_summary.get("release_readiness", "low")).strip()
        return {
            "scientific_evaluation_system_id": f"scientific-evaluation-system::{ScientificWorkflow._slugify(topic)}",
            "topic": topic,
            "system_state": release_state,
            "case_suite_state": str(benchmark_case_suite_summary.get("benchmark_readiness", "")).strip(),
            "benchmark_state": str(scientific_benchmark.get("benchmark_state", "")).strip(),
            "harness_state": str(benchmark_harness_summary.get("release_readiness", "")).strip(),
            "overall_score": kaivu_evaluation_harness_summary.get("overall_score", 0),
            "blocking_gate_count": len(blocking_gates),
            "benchmark_gap_count": len(benchmark_gaps) + len(harness_gaps),
            "canonical_layers": {
                "case_suite": benchmark_case_suite_summary,
                "scientific_benchmark": scientific_benchmark,
                "benchmark_harness": benchmark_harness_summary,
                "agent_evaluation_harness": kaivu_evaluation_harness_summary,
                "research_evaluation": evaluation_summary,
            },
            "blocking_reasons": (blocking_gates + benchmark_gaps + harness_gaps)[:12],
        }

    @staticmethod
    def _derive_workflow_control_summary(
        *,
        topic: str,
        current_stage: str,
        recommended_next_stage: str,
        claim_graph: dict[str, Any],
        systematic_review_summary: dict[str, Any],
        evidence_review_summary: dict[str, Any],
        hypothesis_system_summary: dict[str, Any],
        scientific_decision_summary: dict[str, Any],
        experiment_execution_loop_summary: dict[str, Any],
        research_campaign_plan_summary: dict[str, Any],
        scientific_evaluation_system_summary: dict[str, Any],
        stage_validation: dict[str, Any],
    ) -> dict[str, Any]:
        claim_count = len(claim_graph.get("claims", []) if isinstance(claim_graph.get("claims", []), list) else [])
        evidence_count = len(claim_graph.get("evidence", []) if isinstance(claim_graph.get("evidence", []), list) else [])
        hypothesis_count = int(hypothesis_system_summary.get("hypothesis_count", 0) or 0)
        accepted_count = int(hypothesis_system_summary.get("accepted_hypothesis_count", 0) or 0)
        queue_count = len(
            experiment_execution_loop_summary.get("execution_queue", [])
            if isinstance(experiment_execution_loop_summary.get("execution_queue", []), list)
            else []
        )
        review_ready = str(evidence_review_summary.get("review_readiness", "")).strip()
        protocol_gaps = ScientificWorkflow._strings(systematic_review_summary.get("review_protocol_gaps", []))
        missing_prereqs = ScientificWorkflow._strings(stage_validation.get("missing_prerequisites", []))
        blockers: list[str] = []
        if claim_count == 0 and evidence_count == 0:
            blockers.append("no claim or evidence objects available")
        if hypothesis_count == 0:
            blockers.append("no explicit hypotheses available")
        if hypothesis_count and accepted_count == 0 and hypothesis_system_summary.get("gate_state") in {"blocked", "revision_required"}:
            blockers.append("hypothesis gate has not accepted any executable hypothesis")
        if protocol_gaps:
            blockers.append("systematic review protocol has open gaps")
        if review_ready and review_ready not in {"decision_ready", "release_ready"} and queue_count:
            blockers.append(f"evidence review is {review_ready}")
        blockers.extend(missing_prereqs)
        execution_allowed = (
            queue_count > 0
            and hypothesis_count > 0
            and (claim_count > 0 or evidence_count > 0 or accepted_count > 0)
            and not protocol_gaps
            and not any("no claim or evidence" in item or "no explicit hypotheses" in item for item in blockers)
        )
        if not execution_allowed and queue_count:
            execution_gate = "blocked_until_scientific_prerequisites"
        elif execution_allowed:
            execution_gate = "execution_allowed"
        else:
            execution_gate = "no_execution_candidate"
        if evidence_count == 0 and claim_count == 0:
            allowed_next_actions = ["ingest_literature", "run_systematic_review", "ask_clarifying_research_question"]
        elif hypothesis_count == 0:
            allowed_next_actions = ["generate_hypotheses", "formalize_research_question"]
        elif not execution_allowed:
            allowed_next_actions = ["repair_evidence", "validate_hypotheses", "revise_campaign_plan"]
        else:
            allowed_next_actions = ["schedule_ready_experiment", "run_quality_gate", "prepare_handoff"]
        return {
            "workflow_control_id": f"workflow-control::{ScientificWorkflow._slugify(topic)}",
            "topic": topic,
            "current_stage": current_stage,
            "recommended_next_stage": recommended_next_stage,
            "control_state": "blocked" if blockers and not execution_allowed else "active",
            "execution_gate": execution_gate,
            "entry_conditions": {
                "has_claims_or_evidence": claim_count > 0 or evidence_count > 0,
                "has_hypotheses": hypothesis_count > 0,
                "has_accepted_or_pending_hypotheses": accepted_count > 0 or hypothesis_count > 0,
                "systematic_review_protocol_clear": not protocol_gaps,
                "has_execution_queue": queue_count > 0,
            },
            "exit_conditions": {
                "campaign_has_next_decision": bool(research_campaign_plan_summary.get("next_campaign_decision")),
                "evaluation_system_ready": scientific_evaluation_system_summary.get("system_state") in {"release_ready", "high"},
                "scientific_decision_state": scientific_decision_summary.get("overall_decision_state", ""),
            },
            "blocking_gates": list(dict.fromkeys(blockers))[:12],
            "allowed_next_actions": allowed_next_actions,
            "active_control_policy": {
                "block_executor_when_prerequisites_missing": True,
                "block_high_cost_experiments_before_evidence_review": True,
                "prefer_review_or_hypothesis_repair_before_execution": execution_gate != "execution_allowed",
            },
        }

    @staticmethod
    def _derive_evaluation_summary(
        *,
        claim_graph: dict[str, Any],
        literature_quality_summary: dict[str, Any],
        consensus_state_machine: dict[str, Any],
        execution_cycle_summary: dict[str, Any],
        failure_intelligence_summary: dict[str, Any],
        theoretical_hypothesis_tree_summary: dict[str, Any],
        systematic_review_summary: dict[str, Any],
        causal_graph_summary: dict[str, Any],
        asset_graph_summary: dict[str, Any],
        graph_reference_summary: dict[str, Any],
        typed_research_graph_history: dict[str, Any],
        evaluation_history_summary: dict[str, Any],
        route_temperature_summary: dict[str, Any],
        graph_learning_summary: dict[str, Any],
    ) -> dict[str, Any]:
        hypothesis_count = len(
            claim_graph.get("hypotheses", [])
            if isinstance(claim_graph.get("hypotheses", []), list)
            else []
        )
        claim_count = len(
            claim_graph.get("claims", [])
            if isinstance(claim_graph.get("claims", []), list)
            else []
        )
        evidence_count = len(
            claim_graph.get("evidence", [])
            if isinstance(claim_graph.get("evidence", []), list)
            else []
        )
        benchmark_readiness = "low"
        if (
            str(consensus_state_machine.get("current_state", "")).strip() in {"stressed", "converged"}
            and evidence_count >= max(1, hypothesis_count)
        ):
            benchmark_readiness = "medium"
        if (
            str(consensus_state_machine.get("current_state", "")).strip() == "converged"
            and execution_cycle_summary.get("quality_control_failed_count", 0) == 0
            and evidence_count >= max(2, hypothesis_count)
        ):
            benchmark_readiness = "high"
        systematic_review_readiness = "low"
        if (
            systematic_review_summary.get("screened_evidence_count", 0) >= max(3, hypothesis_count)
            and not systematic_review_summary.get("review_protocol_gaps", [])
        ):
            systematic_review_readiness = "high"
        elif systematic_review_summary.get("screened_evidence_count", 0) > 0:
            systematic_review_readiness = "medium"
        asset_governance_readiness = "low"
        if asset_graph_summary.get("registered_asset_count", 0) > 0 and asset_graph_summary.get(
            "ungoverned_artifact_count", 0
        ) == 0:
            asset_governance_readiness = "high"
        elif asset_graph_summary.get("registered_asset_count", 0) > 0:
            asset_governance_readiness = "medium"
        causal_identifiability = "low"
        if not causal_graph_summary.get("identifiability_risks", []):
            causal_identifiability = "high"
        elif causal_graph_summary.get("intervention_count", 0) > 0:
            causal_identifiability = "medium"
        graph_continuity = "low"
        if typed_research_graph_history.get("snapshot_count", 0) >= 3:
            graph_continuity = "high"
        elif typed_research_graph_history.get("snapshot_count", 0) >= 1:
            graph_continuity = "medium"
        graph_reference_engagement = "low"
        total_refs = int(graph_reference_summary.get("node_ref_count", 0) or 0) + int(
            graph_reference_summary.get("edge_ref_count", 0) or 0
        )
        if total_refs >= 8:
            graph_reference_engagement = "high"
        elif total_refs >= 2:
            graph_reference_engagement = "medium"
        support_density = "low"
        support_edges = len(
            claim_graph.get("edges", [])
            if isinstance(claim_graph.get("edges", []), list)
            else []
        )
        if support_edges >= max(2, hypothesis_count):
            support_density = "high"
        elif support_edges > 0:
            support_density = "medium"
        graph_growth_trend = str(evaluation_history_summary.get("latest_trend", "")).strip() or "stable"
        retired_route_reuse_risk = "low"
        if route_temperature_summary.get("cooling_candidates"):
            retired_route_reuse_risk = "medium"
        if (
            route_temperature_summary.get("global_temperature") == "hot"
            and len(route_temperature_summary.get("cooling_candidates", [])) >= 2
        ):
            retired_route_reuse_risk = "high"
        family_governance_readiness = "low"
        if theoretical_hypothesis_tree_summary.get("family_count", 0) >= 2:
            family_governance_readiness = "medium"
        if theoretical_hypothesis_tree_summary.get("family_status_counts", {}):
            family_governance_readiness = "high"
        return {
            "hypothesis_coverage": {
                "hypothesis_count": hypothesis_count,
                "claim_count": claim_count,
                "evidence_count": evidence_count,
            },
            "literature_strength": literature_quality_summary.get("overall", "mixed"),
            "consensus_readiness": str(consensus_state_machine.get("current_state", "forming")).strip(),
            "benchmark_readiness": benchmark_readiness,
            "failure_pressure": failure_intelligence_summary.get("dominant_failure_class", "mixed"),
            "theory_maturity": theoretical_hypothesis_tree_summary.get("theory_maturity", "flat"),
            "systematic_review_readiness": systematic_review_readiness,
            "asset_governance_readiness": asset_governance_readiness,
            "causal_identifiability": causal_identifiability,
            "graph_continuity": graph_continuity,
            "graph_reference_engagement": graph_reference_engagement,
            "graph_growth_trend": graph_growth_trend,
            "retired_route_reuse_risk": retired_route_reuse_risk,
            "support_density": support_density,
            "family_governance_readiness": family_governance_readiness,
            "learning_signal_strength": graph_learning_summary.get("learning_signal_strength", "low"),
        }

    @staticmethod
    def _derive_graph_reference_summary(steps: list[WorkflowStepResult]) -> dict[str, Any]:
        node_refs: set[str] = set()
        edge_refs: set[str] = set()
        by_profile: list[dict[str, Any]] = []
        for step in steps:
            payload = step.parsed_output.get("graph_references", {})
            if not isinstance(payload, dict) or not payload:
                continue
            profile_nodes = [
                str(item).strip()
                for item in payload.get("node_refs", [])
                if str(item).strip()
            ] if isinstance(payload.get("node_refs", []), list) else []
            profile_edges = [
                str(item).strip()
                for item in payload.get("edge_refs", [])
                if str(item).strip()
            ] if isinstance(payload.get("edge_refs", []), list) else []
            node_refs.update(profile_nodes)
            edge_refs.update(profile_edges)
            by_profile.append(
                {
                    "profile_name": step.profile_name,
                    "node_refs": profile_nodes,
                    "edge_refs": profile_edges,
                    "usage_note": str(payload.get("usage_note", "")).strip(),
                }
            )
        return {
            "node_ref_count": len(node_refs),
            "edge_ref_count": len(edge_refs),
            "node_refs": sorted(node_refs),
            "edge_refs": sorted(edge_refs),
            "by_profile": by_profile,
        }

    @staticmethod
    def _derive_belief_update_summary(
        *,
        steps: list[WorkflowStepResult],
        claim_graph: dict[str, Any],
    ) -> dict[str, Any]:
        belief_step = next((step for step in steps if step.profile_name == "belief_updater"), None)
        if belief_step is None:
            return {}
        parsed = belief_step.parsed_output if isinstance(belief_step.parsed_output, dict) else {}
        consensus = parsed.get("consensus_summary", {}) if isinstance(parsed.get("consensus_summary", {}), dict) else {}
        project_distill = parsed.get("project_distill", {}) if isinstance(parsed.get("project_distill", {}), dict) else {}
        registry_updates = (
            parsed.get("asset_registry_updates", [])
            if isinstance(parsed.get("asset_registry_updates", []), list)
            else []
        )
        hypotheses = claim_graph.get("hypotheses", [])
        hypothesis_relations = claim_graph.get("hypothesis_relations", [])
        status_counts: dict[str, int] = {}
        challenged_count = 0
        for item in hypotheses if isinstance(hypotheses, list) else []:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status", "active")).strip().lower() or "active"
            status_counts[status] = status_counts.get(status, 0) + 1
            if int(item.get("challenge_count", 0) or 0) > 0:
                challenged_count += 1
        relation_counts: dict[str, int] = {}
        for item in hypothesis_relations if isinstance(hypothesis_relations, list) else []:
            if not isinstance(item, dict):
                continue
            relation = str(item.get("relation", "related_to")).strip().lower() or "related_to"
            relation_counts[relation] = relation_counts.get(relation, 0) + 1
        return {
            "consensus_status": str(consensus.get("consensus_status", "")).strip() or "partial",
            "agreed_points": consensus.get("agreed_points", []) if isinstance(consensus.get("agreed_points", []), list) else [],
            "unresolved_points": (
                consensus.get("unresolved_points", [])
                if isinstance(consensus.get("unresolved_points", []), list)
                else []
            ),
            "adjudication_basis": (
                consensus.get("adjudication_basis", [])
                if isinstance(consensus.get("adjudication_basis", []), list)
                else []
            ),
            "current_consensus": str(project_distill.get("current_consensus", "")).strip(),
            "next_cycle_goals": (
                project_distill.get("next_cycle_goals", [])
                if isinstance(project_distill.get("next_cycle_goals", []), list)
                else []
            ),
            "failed_routes": (
                project_distill.get("failed_routes", [])
                if isinstance(project_distill.get("failed_routes", []), list)
                else []
            ),
            "registry_update_count": len([item for item in registry_updates if isinstance(item, dict)]),
            "status_counts": status_counts,
            "challenged_hypothesis_count": challenged_count,
            "hypothesis_relation_counts": relation_counts,
        }

    def _derive_run_manifest(
        self,
        *,
        topic: str,
        steps: list[WorkflowStepResult],
        execution_records: list[dict[str, Any]],
        usage_summary: dict[str, Any],
    ) -> dict[str, Any]:
        input_files: dict[str, dict[str, Any]] = {}
        artifacts: dict[str, dict[str, Any]] = {}
        seeds: list[int] = []
        tools_used: list[str] = []
        models_used: list[dict[str, Any]] = []

        for step in steps:
            models_used.append(
                {
                    "profile_name": step.profile_name,
                    **step.model_meta,
                }
            )

        for record in execution_records:
            tool_name = str(record.get("tool_name", "")).strip()
            if tool_name:
                tools_used.append(tool_name)
            inputs = record.get("inputs", {})
            if isinstance(inputs, dict):
                seed = inputs.get("seed")
                if isinstance(seed, int):
                    seeds.append(seed)
                for item in inputs.get("file_inputs", []):
                    if isinstance(item, dict) and item.get("path"):
                        input_files[str(item["path"])] = item
            for item in record.get("artifacts", []):
                if isinstance(item, dict) and item.get("path"):
                    artifacts[str(item["path"])] = item

        report_artifact = {
            "path": str(self.report_path),
            "kind": "report",
            "exists": False,
            "scope": "artifact",
        }
        artifacts[str(self.report_path)] = report_artifact

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "topic": topic,
            "cwd": str(self.cwd),
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "collaboration_context": self.collaboration_context,
            "tools_used": sorted(set(tools_used)),
            "models_used": models_used,
            "input_files": list(input_files.values()),
            "artifacts": list(artifacts.values()),
            "seeds": sorted(set(seeds)),
            "usage_summary": usage_summary,
        }

    @staticmethod
    def _extract_routing_object_state(
        completed_steps: list[WorkflowStepResult],
    ) -> dict[str, Any]:
        planner = next((step for step in completed_steps if step.profile_name == "research_planner"), None)
        literature = next((step for step in completed_steps if step.profile_name == "literature_reviewer"), None)
        return {
            "research_plan": (
                planner.parsed_output.get("research_plan", {})
                if planner is not None and isinstance(planner.parsed_output.get("research_plan", {}), dict)
                else {}
            ),
            "program_management": (
                planner.parsed_output.get("program_management", {})
                if planner is not None and isinstance(planner.parsed_output.get("program_management", {}), dict)
                else {}
            ),
            "domain_playbooks": (
                planner.parsed_output.get("domain_playbooks", [])
                if planner is not None and isinstance(planner.parsed_output.get("domain_playbooks", []), list)
                else []
            ),
            "autonomy_plan": (
                planner.parsed_output.get("autonomy_plan", {})
                if planner is not None and isinstance(planner.parsed_output.get("autonomy_plan", {}), dict)
                else {}
            ),
            "systematic_review": (
                planner.parsed_output.get("systematic_review", {})
                if planner is not None and isinstance(planner.parsed_output.get("systematic_review", {}), dict)
                else {}
            ),
            "discipline_adaptation": (
                planner.parsed_output.get("discipline_adaptation", {})
                if planner is not None and isinstance(planner.parsed_output.get("discipline_adaptation", {}), dict)
                else {}
            ),
            "causal_model": (
                planner.parsed_output.get("causal_model", {})
                if planner is not None and isinstance(planner.parsed_output.get("causal_model", {}), dict)
                else {}
            ),
            "literature_synthesis": (
                literature.parsed_output.get("literature_synthesis", {})
                if literature is not None and isinstance(literature.parsed_output.get("literature_synthesis", {}), dict)
                else {}
            ),
            "hypothesis_validations": next(
                (
                    step.parsed_output.get("hypothesis_validations", [])
                    for step in completed_steps
                    if step.profile_name == "hypothesis_generator"
                    and isinstance(step.parsed_output.get("hypothesis_validations", []), list)
                    and step.parsed_output.get("hypothesis_validations", [])
                ),
                [],
            ),
            "research_route_search": {},
            "experiment_economics": next(
                (
                    step.parsed_output.get("experiment_economics", {})
                    for step in completed_steps
                    if step.profile_name == "experiment_economist"
                    and isinstance(step.parsed_output.get("experiment_economics", {}), dict)
                    and step.parsed_output.get("experiment_economics", {})
                ),
                {},
            ),
            "lab_meeting_consensus": next(
                (
                    step.parsed_output.get("lab_meeting_consensus", {})
                    for step in completed_steps
                    if step.profile_name == "lab_meeting_moderator"
                    and isinstance(step.parsed_output.get("lab_meeting_consensus", {}), dict)
                    and step.parsed_output.get("lab_meeting_consensus", {})
                ),
                {},
            ),
            "failure_intelligence": ScientificWorkflow._derive_failure_intelligence_summary(
                steps=completed_steps,
                claim_graph=ScientificWorkflow._build_claim_graph(completed_steps),
                execution_cycle_summary=ScientificWorkflow._derive_execution_cycle_summary(
                    experiment_runs=[
                        step.parsed_output.get("experiment_run", {})
                        for step in completed_steps
                        if isinstance(step.parsed_output.get("experiment_run", {}), dict)
                        and step.parsed_output.get("experiment_run", {})
                    ],
                    quality_control_reviews=[
                        step.parsed_output.get("quality_control_review", {})
                        for step in completed_steps
                        if isinstance(step.parsed_output.get("quality_control_review", {}), dict)
                        and step.parsed_output.get("quality_control_review", {})
                    ],
                    interpretation_records=[
                        step.parsed_output.get("interpretation_record", {})
                        for step in completed_steps
                        if isinstance(step.parsed_output.get("interpretation_record", {}), dict)
                        and step.parsed_output.get("interpretation_record", {})
                    ],
                ),
            ),
            "graph_reference_summary": ScientificWorkflow._derive_graph_reference_summary(completed_steps),
            "typed_research_graph_history": {},
        }

    @staticmethod
    def _derive_routing_termination_strategy(
        completed_steps: list[WorkflowStepResult],
    ) -> dict[str, Any]:
        object_state = ScientificWorkflow._extract_routing_object_state(completed_steps)
        temporary_claim_graph = ScientificWorkflow._build_claim_graph(completed_steps)
        negative_results: list[dict[str, Any]] = []
        experiment_runs: list[dict[str, Any]] = []
        quality_control_reviews: list[dict[str, Any]] = []
        interpretation_records: list[dict[str, Any]] = []
        conflict_groups: dict[str, list[dict[str, Any]]] = {}
        for step in completed_steps:
            parsed = step.parsed_output
            items = parsed.get("negative_results", [])
            if isinstance(items, list):
                negative_results.extend(item for item in items if isinstance(item, dict))
            run_payload = parsed.get("experiment_run", {})
            if isinstance(run_payload, dict) and run_payload:
                experiment_runs.append(run_payload)
            quality_payload = parsed.get("quality_control_review", {})
            if isinstance(quality_payload, dict) and quality_payload:
                quality_control_reviews.append(quality_payload)
            interpretation_payload = parsed.get("interpretation_record", {})
            if isinstance(interpretation_payload, dict) and interpretation_payload:
                interpretation_records.append(interpretation_payload)
            for evidence in parsed.get("evidence", []) if isinstance(parsed.get("evidence", []), list) else []:
                if isinstance(evidence, dict):
                    conflict_group = str(evidence.get("conflict_group", "")).strip()
                    if conflict_group:
                        conflict_groups.setdefault(conflict_group, []).append(evidence)

        stage_validation = ScientificWorkflow._validate_stage_progression(completed_steps)
        consensus_state = ScientificWorkflow._derive_consensus_state(completed_steps)
        conflict_summary = ScientificWorkflow._summarize_conflict_groups(conflict_groups)
        consensus_state_machine = ScientificWorkflow._derive_consensus_state_machine(
            consensus_state=consensus_state,
            conflict_summary=conflict_summary,
            stage_validation=stage_validation,
            negative_results=negative_results,
        )
        execution_cycle_summary = ScientificWorkflow._derive_execution_cycle_summary(
            experiment_runs=experiment_runs,
            quality_control_reviews=quality_control_reviews,
            interpretation_records=interpretation_records,
        )
        belief_update_summary = ScientificWorkflow._derive_belief_update_summary(
            steps=completed_steps,
            claim_graph=temporary_claim_graph,
        )
        return ScientificWorkflow._derive_termination_strategy_summary(
            topic="routing",
            claim_graph=temporary_claim_graph,
            research_plan_summary=ScientificWorkflow._derive_research_plan_summary(
                topic="routing",
                steps=completed_steps,
                stage_validation=stage_validation,
            ),
            autonomy_summary=ScientificWorkflow._derive_autonomy_summary(
                topic="routing",
                steps=completed_steps,
                stage_validation=stage_validation,
            ),
            consensus_state_machine=consensus_state_machine,
            negative_results=negative_results,
            execution_cycle_summary=execution_cycle_summary,
            belief_update_summary=belief_update_summary,
            experiment_economics_summary=ScientificWorkflow._derive_experiment_economics_summary(
                topic="routing",
                steps=completed_steps,
                research_plan_summary=ScientificWorkflow._derive_research_plan_summary(
                    topic="routing",
                    steps=completed_steps,
                    stage_validation=stage_validation,
                ),
                discipline_adaptation_summary=object_state.get("discipline_adaptation", {}),
                execution_cycle_summary=execution_cycle_summary,
                failure_intelligence_summary=object_state.get("failure_intelligence", {}),
            ),
            lab_meeting_consensus_summary=ScientificWorkflow._derive_lab_meeting_consensus_summary(
                steps=completed_steps,
                consensus_state=consensus_state,
                consensus_state_machine=consensus_state_machine,
                failure_intelligence_summary=object_state.get("failure_intelligence", {}),
            ),
        )

    @staticmethod
    def _heuristic_next_profiles_from_objects(
        *,
        completed_steps: list[WorkflowStepResult],
        remaining_names: list[str],
        negative_signals: list[str],
        topic: str,
        evaluation_history_summary: dict[str, Any] | None = None,
        graph_history_summary: dict[str, Any] | None = None,
    ) -> list[str]:
        completed_names = {step.profile_name for step in completed_steps}
        object_state = ScientificWorkflow._extract_routing_object_state(completed_steps)
        research_plan = object_state.get("research_plan", {})
        autonomy_plan = object_state.get("autonomy_plan", {})
        systematic_review = object_state.get("systematic_review", {})
        discipline_adaptation = object_state.get("discipline_adaptation", {})
        causal_model = object_state.get("causal_model", {})
        literature_synthesis = object_state.get("literature_synthesis", {})
        program_management = object_state.get("program_management", {})
        domain_playbooks = (
            object_state.get("domain_playbooks", [])
            if isinstance(object_state.get("domain_playbooks", []), list)
            else []
        )
        hypothesis_validations = (
            object_state.get("hypothesis_validations", [])
            if isinstance(object_state.get("hypothesis_validations", []), list)
            else []
        )
        failure_intelligence = object_state.get("failure_intelligence", {})
        graph_reference_summary = object_state.get("graph_reference_summary", {})
        evaluation_history = evaluation_history_summary if isinstance(evaluation_history_summary, dict) else {}
        graph_history = graph_history_summary if isinstance(graph_history_summary, dict) else {}
        theoretical_hypothesis_tree_summary = ScientificWorkflow._derive_theoretical_hypothesis_tree_summary(
            claim_graph=ScientificWorkflow._build_claim_graph(completed_steps),
            hypothesis_tree=ScientificWorkflow._derive_hypothesis_tree(
                ScientificWorkflow._build_claim_graph(completed_steps)
            ),
            discipline_adaptation_summary=discipline_adaptation,
        )
        route_temperature_summary = ScientificWorkflow._derive_route_temperature_summary(
            claim_graph=ScientificWorkflow._build_claim_graph(completed_steps),
            failure_intelligence_summary=failure_intelligence,
            graph_reference_summary=graph_reference_summary,
            typed_research_graph_history=graph_history,
            evaluation_history_summary=evaluation_history,
            theoretical_hypothesis_tree_summary=theoretical_hypothesis_tree_summary,
        )
        graph_learning_summary = ScientificWorkflow._derive_graph_learning_summary(
            typed_research_graph_history=graph_history,
            graph_reference_summary=graph_reference_summary,
            failure_intelligence_summary=failure_intelligence,
            evaluation_history_summary=evaluation_history,
        )
        temporary_claim_graph = ScientificWorkflow._build_claim_graph(completed_steps)
        execution_cycle_summary = ScientificWorkflow._derive_execution_cycle_summary(
            experiment_runs=[
                step.parsed_output.get("experiment_run", {})
                for step in completed_steps
                if isinstance(step.parsed_output.get("experiment_run", {}), dict)
                and step.parsed_output.get("experiment_run", {})
            ],
            quality_control_reviews=[
                step.parsed_output.get("quality_control_review", {})
                for step in completed_steps
                if isinstance(step.parsed_output.get("quality_control_review", {}), dict)
                and step.parsed_output.get("quality_control_review", {})
            ],
            interpretation_records=[
                step.parsed_output.get("interpretation_record", {})
                for step in completed_steps
                if isinstance(step.parsed_output.get("interpretation_record", {}), dict)
                and step.parsed_output.get("interpretation_record", {})
            ],
        )
        lab_meeting_consensus_summary = ScientificWorkflow._derive_lab_meeting_consensus_summary(
            steps=completed_steps,
            consensus_state=ScientificWorkflow._derive_consensus_state(completed_steps),
            consensus_state_machine=ScientificWorkflow._derive_consensus_state_machine(
                consensus_state=ScientificWorkflow._derive_consensus_state(completed_steps),
                conflict_summary=ScientificWorkflow._summarize_conflict_groups({}),
                stage_validation=ScientificWorkflow._validate_stage_progression(completed_steps),
                negative_results=[
                    item
                    for step in completed_steps
                    for item in (
                        step.parsed_output.get("negative_results", [])
                        if isinstance(step.parsed_output.get("negative_results", []), list)
                        else []
                    )
                    if isinstance(item, dict)
                ],
            ),
            failure_intelligence_summary=failure_intelligence,
        )
        evaluation_summary = ScientificWorkflow._derive_evaluation_summary(
            claim_graph=temporary_claim_graph,
            literature_quality_summary={},
            consensus_state_machine=ScientificWorkflow._derive_consensus_state_machine(
                consensus_state=ScientificWorkflow._derive_consensus_state(completed_steps),
                conflict_summary=ScientificWorkflow._summarize_conflict_groups({}),
                stage_validation=ScientificWorkflow._validate_stage_progression(completed_steps),
                negative_results=[
                    item
                    for step in completed_steps
                    for item in (
                        step.parsed_output.get("negative_results", [])
                        if isinstance(step.parsed_output.get("negative_results", []), list)
                        else []
                    )
                    if isinstance(item, dict)
                ],
            ),
            execution_cycle_summary=execution_cycle_summary,
            failure_intelligence_summary=failure_intelligence,
            theoretical_hypothesis_tree_summary=theoretical_hypothesis_tree_summary,
            systematic_review_summary=systematic_review,
            causal_graph_summary=causal_model,
            asset_graph_summary={},
            graph_reference_summary=graph_reference_summary,
            typed_research_graph_history=graph_history,
            evaluation_history_summary=evaluation_history,
            route_temperature_summary=route_temperature_summary,
            graph_learning_summary=graph_learning_summary,
        )
        termination_strategy = ScientificWorkflow._derive_routing_termination_strategy(
            completed_steps
        )
        human_governance_checkpoint_summary = (
            ScientificWorkflow._derive_human_governance_checkpoint_summary(
                topic="routing",
                termination_strategy_summary=termination_strategy,
                lab_meeting_consensus_summary=lab_meeting_consensus_summary,
                experiment_governance_summary=ScientificWorkflow._derive_experiment_governance_summary(
                    experiment_runs=[
                        step.parsed_output.get("experiment_run", {})
                        for step in completed_steps
                        if isinstance(step.parsed_output.get("experiment_run", {}), dict)
                        and step.parsed_output.get("experiment_run", {})
                    ],
                    quality_control_reviews=[
                        step.parsed_output.get("quality_control_review", {})
                        for step in completed_steps
                        if isinstance(step.parsed_output.get("quality_control_review", {}), dict)
                        and step.parsed_output.get("quality_control_review", {})
                    ],
                    interpretation_records=[
                        step.parsed_output.get("interpretation_record", {})
                        for step in completed_steps
                        if isinstance(step.parsed_output.get("interpretation_record", {}), dict)
                        and step.parsed_output.get("interpretation_record", {})
                    ],
                    claim_graph=temporary_claim_graph,
                ),
                experiment_economics_summary=object_state.get("experiment_economics", {}),
                consensus_state_machine=ScientificWorkflow._derive_consensus_state_machine(
                    consensus_state=ScientificWorkflow._derive_consensus_state(completed_steps),
                    conflict_summary=ScientificWorkflow._summarize_conflict_groups({}),
                    stage_validation=ScientificWorkflow._validate_stage_progression(completed_steps),
                    negative_results=[
                        item
                        for step in completed_steps
                        for item in (
                            step.parsed_output.get("negative_results", [])
                            if isinstance(step.parsed_output.get("negative_results", []), list)
                            else []
                        )
                        if isinstance(item, dict)
                    ],
                ),
                evaluation_summary=evaluation_summary,
            )
        )
        benchmark_harness_summary = ScientificWorkflow._derive_benchmark_harness_summary(
            topic="routing",
            evaluation_summary=evaluation_summary,
            systematic_review_summary=systematic_review,
            execution_cycle_summary=execution_cycle_summary,
            asset_graph_summary={},
            graph_reference_summary=graph_reference_summary,
            route_temperature_summary=route_temperature_summary,
            typed_research_graph_history=graph_history,
            mechanism_reasoning_summary=ScientificWorkflow._derive_mechanism_reasoning_summary(
                steps=completed_steps,
                causal_graph_summary=causal_model,
            ),
            hypothesis_family_lifecycle_summary=ScientificWorkflow._derive_hypothesis_family_lifecycle_summary(
                steps=completed_steps,
                theoretical_hypothesis_tree_summary=theoretical_hypothesis_tree_summary,
            ),
            human_governance_checkpoint_summary=human_governance_checkpoint_summary,
        )
        research_route_search = ScientificWorkflow._derive_research_route_search_summary(
            topic="routing",
            research_plan_summary=research_plan,
            autonomy_summary=autonomy_plan,
            systematic_review_summary=systematic_review,
            experiment_governance_summary=ScientificWorkflow._derive_experiment_governance_summary(
                experiment_runs=[
                    step.parsed_output.get("experiment_run", {})
                    for step in completed_steps
                    if isinstance(step.parsed_output.get("experiment_run", {}), dict)
                    and step.parsed_output.get("experiment_run", {})
                ],
                quality_control_reviews=[
                    step.parsed_output.get("quality_control_review", {})
                    for step in completed_steps
                    if isinstance(step.parsed_output.get("quality_control_review", {}), dict)
                    and step.parsed_output.get("quality_control_review", {})
                ],
                interpretation_records=[
                    step.parsed_output.get("interpretation_record", {})
                    for step in completed_steps
                    if isinstance(step.parsed_output.get("interpretation_record", {}), dict)
                    and step.parsed_output.get("interpretation_record", {})
                ],
                claim_graph=temporary_claim_graph,
            ),
            experiment_economics_summary=object_state.get("experiment_economics", {}),
            failure_intelligence_summary=failure_intelligence,
            route_temperature_summary=route_temperature_summary,
            evaluation_summary=evaluation_summary,
            human_governance_checkpoint_summary=human_governance_checkpoint_summary,
            benchmark_harness_summary=benchmark_harness_summary,
            hypothesis_validation_summary=ScientificWorkflow._derive_hypothesis_validation_summary(
                steps=completed_steps,
                claim_graph=temporary_claim_graph,
            ),
            typed_research_graph_history=graph_history,
        )
        hypothesis_theory_summary = build_hypothesis_theory_summary(
            claim_graph=temporary_claim_graph,
            steps=completed_steps,
            causal_graph_summary=causal_model,
        )
        evidence_review_summary = build_evidence_review_summary(
            topic=topic,
            project_id=str(self.collaboration_context.get("project_id", "")).strip(),
            literature_synthesis=ScientificWorkflow._derive_literature_synthesis(completed_steps),
            systematic_review_summary=systematic_review,
            literature_quality_summary=ScientificWorkflow._summarize_quality_grades(
                [
                    str(evidence.get("quality_grade", "")).strip().lower()
                    for evidence in temporary_claim_graph.get("evidence", [])
                    if isinstance(evidence, dict) and str(evidence.get("quality_grade", "")).strip()
                ]
            ),
            conflict_attribution=ScientificWorkflow._summarize_conflict_groups({}),
            formal_review_record_summary=ScientificWorkflow._derive_formal_review_record_summary(
                systematic_review_summary=systematic_review,
            ),
            claim_graph=temporary_claim_graph,
        )
        scientific_decision_summary = build_scientific_decision_summary(
            topic=topic,
            hypothesis_theory_summary=hypothesis_theory_summary,
            research_route_search_summary=research_route_search,
            experiment_economics_summary=object_state.get("experiment_economics", {}),
            failure_intelligence_summary=failure_intelligence,
            systematic_review_summary=systematic_review,
            evidence_review_summary=evidence_review_summary,
            human_governance_checkpoint_summary=human_governance_checkpoint_summary,
            lab_meeting_consensus_summary=lab_meeting_consensus_summary,
            termination_strategy_summary=termination_strategy,
        )
        hypothesis_gate_summary = ScientificWorkflow._derive_hypothesis_gate_summary(
            steps=completed_steps,
            hypothesis_validation_summary=ScientificWorkflow._derive_hypothesis_validation_summary(
                steps=completed_steps,
                claim_graph=temporary_claim_graph,
            ),
        )
        blocked_specialists = {
            str(item).strip()
            for item in termination_strategy.get("blocked_specialists", [])
            if str(item).strip()
        }

        if termination_strategy.get("human_confirmation_required"):
            for preferred in termination_strategy.get("preferred_specialists", []):
                if preferred in remaining_names and preferred not in completed_names:
                    return [preferred]
        if termination_strategy.get("recommended_action") == "terminate_or_retire_route":
            governance_batch = [
                name
                for name in ["belief_updater", "critic", "safety_ethics_reviewer"]
                if name in remaining_names
                and name not in completed_names
                and name not in blocked_specialists
            ]
            if governance_batch:
                return governance_batch[:2]

        decision_queue = (
            scientific_decision_summary.get("decision_queue", [])
            if isinstance(scientific_decision_summary.get("decision_queue", []), list)
            else []
        )
        for decision in decision_queue[:3]:
            if not isinstance(decision, dict):
                continue
            preferred_agents = [
                str(name).strip()
                for name in decision.get("recommended_agents", [])
                if str(name).strip()
            ]
            if not preferred_agents:
                continue
            decision_batch = [
                name
                for name in preferred_agents
                if name in remaining_names
                and name not in completed_names
                and name not in blocked_specialists
            ]
            if decision_batch:
                return decision_batch[:2]

        best_next_action = str(research_route_search.get("best_next_action", "")).strip().lower()
        action_to_profiles = {
            "review_more_literature": ["literature_reviewer", "critic"],
            "refine_hypothesis": ["hypothesis_generator", "critic"],
            "design_discriminative_experiment": ["experiment_designer", "experiment_economist"],
            "resolve_execution_governance": ["quality_control_reviewer", "lab_meeting_moderator"],
            "pause_or_retire_route": ["belief_updater", "lab_meeting_moderator"],
            "request_human_adjudication": ["lab_meeting_moderator", "coordinator"],
            "benchmark_route": ["critic", "experiment_economist"],
            "compare_mechanisms": ["hypothesis_generator", "experiment_designer"],
        }
        if best_next_action in action_to_profiles:
            ranked_batch = [
                name
                for name in action_to_profiles[best_next_action]
                if name in remaining_names
                and name not in completed_names
                and name not in blocked_specialists
            ]
            if ranked_batch:
                return ranked_batch[:2]

        if str(hypothesis_gate_summary.get("gate_state", "")).strip().lower() == "blocked":
            gate_batch = [
                name
                for name in ["hypothesis_generator", "critic", "lab_meeting_moderator"]
                if name in remaining_names
                and name not in completed_names
                and name not in blocked_specialists
            ]
            if gate_batch:
                return gate_batch[:2]
            return []

        regressing_streak = int(evaluation_history.get("regressing_streak", 0) or 0)
        latest_trend = str(evaluation_history.get("latest_trend", "")).strip().lower()
        if regressing_streak >= 2 or latest_trend == "regressing":
            regression_batch = [
                name
                for name in ["critic", "lab_meeting_moderator", "experiment_economist"]
                if name in remaining_names
                and name not in completed_names
                and name not in blocked_specialists
            ]
            if regression_batch:
                return regression_batch[:2]

        if any(
            float(item.get("falsifiability_score", 0) or 0) < 0.5
            or float(item.get("testability_score", 0) or 0) < 0.5
            for item in hypothesis_validations
            if isinstance(item, dict)
        ):
            validation_batch = [
                name
                for name in ["hypothesis_generator", "experiment_designer", "critic"]
                if name in remaining_names
                and name not in completed_names
                and name not in blocked_specialists
            ]
            if validation_batch:
                return validation_batch[:2]

        if any(
            float(item.get("novelty_score", 0) or 0) < 0.5
            for item in hypothesis_validations
            if isinstance(item, dict)
        ):
            novelty_batch = [
                name
                for name in ["literature_reviewer", "hypothesis_generator", "lab_meeting_moderator"]
                if name in remaining_names
                and name not in completed_names
                and name not in blocked_specialists
            ]
            if novelty_batch:
                return novelty_batch[:2]

        if human_governance_checkpoint_summary.get("human_approval_checkpoint_count", 0) >= 2:
            governance_batch = [
                name
                for name in ["lab_meeting_moderator", "coordinator", "safety_ethics_reviewer"]
                if name in remaining_names
                and name not in completed_names
                and name not in blocked_specialists
            ]
            if governance_batch:
                return governance_batch[:2]

        if (
            benchmark_harness_summary.get("release_readiness") == "low"
            and benchmark_harness_summary.get("benchmark_gaps")
        ):
            benchmark_batch = [
                name
                for name in ["critic", "literature_reviewer", "experiment_designer"]
                if name in remaining_names
                and name not in completed_names
                and name not in blocked_specialists
            ]
            if benchmark_batch:
                return benchmark_batch[:2]

        if program_management.get("pivot_triggers") and route_temperature_summary.get("global_temperature") == "hot":
            management_batch = [
                name
                for name in ["research_planner", "coordinator", "experiment_economist"]
                if name in remaining_names
                and name not in completed_names
                and name not in blocked_specialists
            ]
            if management_batch:
                return management_batch[:2]

        if domain_playbooks:
            dominant_disciplines = {
                str(item.get("discipline", "")).strip().lower()
                for item in domain_playbooks
                if isinstance(item, dict) and str(item.get("discipline", "")).strip()
            }
            if (
                dominant_disciplines.intersection({"artificial_intelligence", "mathematics"})
                and "data_analyst" in remaining_names
                and "data_analyst" not in completed_names
                and "data_analyst" not in blocked_specialists
            ):
                return ["data_analyst"]

        if route_temperature_summary.get("global_temperature") == "hot":
            hot_route_batch = [
                name
                for name in ["lab_meeting_moderator", "critic", "experiment_economist", "belief_updater"]
                if name in remaining_names
                and name not in completed_names
                and name not in blocked_specialists
            ]
            if hot_route_batch:
                return hot_route_batch[:2]

        if (
            graph_learning_summary.get("learning_signal_strength") == "high"
            and "research_planner" not in completed_names
            and "research_planner" in remaining_names
        ):
            return ["research_planner"]

        if int(graph_history.get("challenged_hypothesis_count", 0) or 0) >= 2:
            graph_batch = [
                name
                for name in ["lab_meeting_moderator", "critic", "belief_updater"]
                if name in remaining_names
                and name not in completed_names
                and name not in blocked_specialists
            ]
            if graph_batch:
                return graph_batch[:2]

        if (
            int(graph_history.get("consulted_edge_count", 0) or 0) >= 2
            or int(graph_history.get("specialist_reference_count", 0) or 0) >= 1
            or int(graph_reference_summary.get("edge_ref_count", 0) or 0) >= 1
        ):
            consultation_batch = [
                name
                for name in ["belief_updater", "critic", "lab_meeting_moderator"]
                if name in remaining_names
                and name not in completed_names
                and name not in blocked_specialists
            ]
            if consultation_batch:
                return consultation_batch[:2]

        if (
            "lab_meeting_moderator" in remaining_names
            and "lab_meeting_moderator" not in completed_names
            and (
                literature_synthesis.get("contested_questions")
                or systematic_review.get("evidence_balance")
                or systematic_review.get("review_protocol_gaps")
                or failure_intelligence.get("theoretical_failures")
            )
        ):
            return ["lab_meeting_moderator"]

        if (
            "experiment_designer" in completed_names
            and "run_manager" in remaining_names
            and "run_manager" not in blocked_specialists
        ):
            return ["run_manager"]
        if (
            "run_manager" in completed_names
            and "quality_control_reviewer" in remaining_names
            and "quality_control_reviewer" not in blocked_specialists
        ):
            return ["quality_control_reviewer"]
        if "quality_control_reviewer" in completed_names and "result_interpreter" in remaining_names:
            return ["result_interpreter"]
        if "result_interpreter" in completed_names and "belief_updater" in remaining_names:
            return ["belief_updater"]

        if negative_signals:
            if "critic" in remaining_names and "critic" not in completed_names:
                return ["critic"]
            if len(negative_signals) >= 2 and "hypothesis_generator" in remaining_names:
                return ["hypothesis_generator"]
            if "experiment_designer" in remaining_names and "hypothesis_generator" in completed_names:
                return ["experiment_designer"]

        dominant_failure_class = str(
            failure_intelligence.get("dominant_failure_class", "")
        ).strip().lower()
        if (
            route_temperature_summary.get("cooling_candidates")
            and "belief_updater" in remaining_names
            and "belief_updater" not in completed_names
        ):
            return ["belief_updater"]
        if dominant_failure_class == "technical":
            if "experiment_designer" in remaining_names and "experiment_designer" not in blocked_specialists:
                batch = ["experiment_designer"]
                if "quality_control_reviewer" in remaining_names and "quality_control_reviewer" not in completed_names:
                    batch.append("quality_control_reviewer")
                return batch[:2]
        if dominant_failure_class == "theoretical" and "hypothesis_generator" in remaining_names:
            return ["hypothesis_generator"]

        if (
            "experiment_economist" in remaining_names
            and "experiment_economist" not in completed_names
            and (
                research_plan.get("next_cycle_experiments")
                or failure_intelligence.get("avoid_repeat_routes")
                or discipline_adaptation.get("artifact_expectations")
            )
        ):
            return ["experiment_economist"]

        if (
            "hypothesis_generator" in remaining_names
            and (
                research_plan.get("priority_questions")
                or literature_synthesis.get("contested_questions")
                or systematic_review.get("review_question")
            )
        ):
            return ["hypothesis_generator"]

        if (
            "literature_reviewer" in remaining_names
            and "literature_reviewer" not in completed_names
            and systematic_review.get("review_protocol_gaps")
        ):
            return ["literature_reviewer"]

        primary_discipline = str(discipline_adaptation.get("primary_discipline", "")).strip().lower()
        artifact_expectations = " ".join(
            str(item) for item in discipline_adaptation.get("artifact_expectations", []) if str(item).strip()
        ).lower()
        lowered_topic = topic.lower()
        data_like = (
            primary_discipline in {"artificial_intelligence", "chemical_engineering"}
            or any(token in lowered_topic for token in ["dataset", "benchmark", "table", "csv", "xlsx", "simulation"])
            or any(token in artifact_expectations for token in ["checkpoint", "metric", "curve", "throughput"])
        )
        if data_like and "data_analyst" in remaining_names and "data_analyst" not in completed_names:
            return ["data_analyst"]

        if (
            "experiment_designer" in remaining_names
            and (
                causal_model.get("intervention_priorities")
                or causal_model.get("confounders")
                or causal_model.get("identifiability_risks")
                or research_plan.get("next_cycle_experiments")
            )
            and "experiment_designer" not in blocked_specialists
        ):
            batch = ["experiment_designer"]
            if data_like and "data_analyst" in remaining_names and "data_analyst" not in completed_names:
                batch.append("data_analyst")
            return batch[:2]

        if (
            systematic_review.get("bias_hotspots")
            or literature_synthesis.get("contested_questions")
            or causal_model.get("identifiability_risks")
            or autonomy_plan.get("monitoring_signals")
        ):
            if "critic" in remaining_names and "critic" not in completed_names:
                return ["critic"]

        if (
            autonomy_plan.get("handoff_points")
            and "safety_ethics_reviewer" in remaining_names
            and "safety_ethics_reviewer" not in completed_names
        ):
            return ["safety_ethics_reviewer"]

        if (
            "coordinator" not in remaining_names
            and "conflict_resolver" in remaining_names
            and (
                systematic_review.get("evidence_balance")
                or literature_synthesis.get("contested_questions")
            )
        ):
            return ["conflict_resolver"]

        return []

    async def _route_next_profiles(
        self,
        topic: str,
        completed_steps: list[WorkflowStepResult],
        remaining_names: list[str],
    ) -> list[str]:
        if not remaining_names:
            return []
        prior_directives = (
            self.collaboration_context.get("next_cycle_decision_directives_summary", {})
            if isinstance(self.collaboration_context.get("next_cycle_decision_directives_summary", {}), dict)
            else {}
        )
        preferred_from_prior = [
            str(name).strip()
            for name in prior_directives.get("preferred_agents", [])
            if str(name).strip()
        ] if isinstance(prior_directives.get("preferred_agents", []), list) else []
        completed_names = {step.profile_name for step in completed_steps}
        directive_batch = [
            name
            for name in preferred_from_prior
            if name in remaining_names and name not in completed_names
        ]
        if directive_batch:
            return directive_batch[:2]
        negative_signals = self._collect_negative_result_signals(completed_steps)
        termination_strategy = ScientificWorkflow._derive_routing_termination_strategy(
            completed_steps
        )
        heuristic = ScientificWorkflow._heuristic_next_profiles_from_objects(
            completed_steps=completed_steps,
            remaining_names=remaining_names,
            negative_signals=negative_signals,
            topic=topic,
            evaluation_history_summary=(
                self.collaboration_context.get("evaluation_history_summary", {})
                if isinstance(self.collaboration_context.get("evaluation_history_summary", {}), dict)
                else {}
            ),
            graph_history_summary=(
                self.collaboration_context.get("typed_research_graph_history", {})
                if isinstance(self.collaboration_context.get("typed_research_graph_history", {}), dict)
                else {}
            ),
        )
        if heuristic:
            return [name for name in heuristic if name in remaining_names][:2]
        object_state = ScientificWorkflow._extract_routing_object_state(completed_steps)
        object_state["evaluation_history_summary"] = (
            self.collaboration_context.get("evaluation_history_summary", {})
            if isinstance(self.collaboration_context.get("evaluation_history_summary", {}), dict)
            else {}
        )
        object_state["typed_graph_query_context"] = (
            self.collaboration_context.get("typed_research_graph_query", {})
            if isinstance(self.collaboration_context.get("typed_research_graph_query", {}), dict)
            else {}
        )
        router_schema = StructuredSchema(
            name="router_decision",
            description="Decide which specialist agents should run next.",
            schema={
                "type": "object",
                "properties": {
                    "next_specialists": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "reason": {"type": "string"},
                    "stop": {"type": "boolean"},
                },
                "required": ["next_specialists", "reason", "stop"],
                "additionalProperties": False,
            },
        )
        backend: ModelBackend = self.model_registry.build_backend(
            AgentModelConfig(
                model=self.model_name,
                reasoning_effort="medium",
                max_output_tokens=1000,
                allow_web_search=False,
                base_url=self.base_url,
            ),
            allow_web_search_override=False,
        )
        router_agent = ScientificAgent(
            model=backend,
            tools=ToolRegistry([]),
            cwd=self.cwd,
            system_prompt=(
                "You are a workflow router for a scientific multi-agent system. "
                "Choose the minimal next specialists needed to advance the research. "
                "Favor data specialists when datasets are present, hypothesis and experiment design after literature is established, "
                "critic/safety review after a concrete plan exists, and conflict resolution only when specialists materially disagree."
            ),
            permission_policy=self.permission_policy,
            max_turns=3,
        )
        completed_json = [
            {"profile_name": step.profile_name, "parsed_output": step.parsed_output}
            for step in completed_steps
        ]
        prompt = "\n\n".join(
            [
                f"Research topic: {topic}",
                f"Remaining specialists: {remaining_names}",
                f"Object state: {json.dumps(object_state, ensure_ascii=False)}",
                f"Negative signals: {json.dumps(negative_signals, ensure_ascii=False)}",
                f"Completed outputs: {json.dumps(completed_json, ensure_ascii=False)}",
                schema_instruction(router_schema),
                "Choose one or two next specialists unless stopping is justified.",
                "Use the research plan, autonomy plan, discipline adaptation, causal model, and systematic review as first-class routing inputs.",
                "Favor agents that reduce uncertainty fastest, respect stop conditions, and match the primary discipline's execution requirements.",
            ]
        )
        result = await router_agent.run(prompt)
        try:
            routed = parse_structured_output(result.final_text, router_schema)
        except Exception:
            try:
                routed = salvage_structured_output(result.final_text, router_schema)
            except Exception:
                return remaining_names[:1]
        if routed.get("stop"):
            return []
        valid = [
            name for name in routed.get("next_specialists", []) if name in remaining_names
        ]
        blocked = {
            str(item).strip()
            for item in termination_strategy.get("blocked_specialists", [])
            if str(item).strip()
        }
        valid = [name for name in valid if name not in blocked]
        if valid:
            return valid[:2]
        fallback = [name for name in remaining_names if name not in blocked]
        return fallback[:1]

    @staticmethod
    def _collect_execution_records(steps: list[WorkflowStepResult]) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for step in steps:
            raw_records = step.state.scratchpad.get("execution_records", [])
            if not isinstance(raw_records, list):
                continue
            for record in raw_records:
                if isinstance(record, dict):
                    tagged = dict(record)
                    tagged.setdefault("profile_name", step.profile_name)
                    tagged.setdefault("model_meta", step.model_meta)
                    records.append(tagged)
        return records

    @staticmethod
    def _collect_usage_summary(steps: list[WorkflowStepResult]) -> dict[str, Any]:
        by_profile: list[dict[str, Any]] = []
        total = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_usd": 0.0,
            "rounds": 0,
        }
        for step in steps:
            usage_totals = step.state.scratchpad.get("model_usage_totals", {})
            if not isinstance(usage_totals, dict):
                continue
            profile_summary = {
                "profile_name": step.profile_name,
                "model": step.model_meta.get("model", "unknown"),
                "input_tokens": int(usage_totals.get("input_tokens", 0)),
                "output_tokens": int(usage_totals.get("output_tokens", 0)),
                "total_tokens": int(usage_totals.get("total_tokens", 0)),
                "estimated_cost_usd": round(float(usage_totals.get("estimated_cost_usd", 0.0)), 6),
                "rounds": int(usage_totals.get("rounds", 0)),
            }
            by_profile.append(profile_summary)
            total["input_tokens"] += profile_summary["input_tokens"]
            total["output_tokens"] += profile_summary["output_tokens"]
            total["total_tokens"] += profile_summary["total_tokens"]
            total["estimated_cost_usd"] = round(
                total["estimated_cost_usd"] + profile_summary["estimated_cost_usd"],
                6,
            )
            total["rounds"] += profile_summary["rounds"]
        return {"by_profile": by_profile, "total": total}

    def _build_model_meta(self, config: AgentModelConfig) -> dict[str, Any]:
        return self.model_registry.describe_config(config)

    @staticmethod
    def _should_escalate_result(parsed: dict[str, Any]) -> bool:
        if "schema_parse_error" in parsed:
            return True
        if parsed.get("_repair_note"):
            return True
        confidence = str(parsed.get("confidence", "")).strip().lower()
        if confidence == "low":
            return True
        claims = parsed.get("claims", [])
        evidence = parsed.get("evidence", [])
        if isinstance(claims, list) and claims and isinstance(evidence, list) and not evidence:
            return True
        return False

    @staticmethod
    def _needs_conflict_resolution(steps: list[WorkflowStepResult]) -> bool:
        critique = next((s for s in steps if s.profile_name == "critic"), None)
        coordinator = next((s for s in steps if s.profile_name == "coordinator"), None)
        if critique is None:
            return False
        risks = critique.parsed_output.get("major_risks", [])
        overclaims = critique.parsed_output.get("overclaims", [])
        negative_signals = ScientificWorkflow._collect_negative_result_signals(steps)
        if risks or overclaims or (negative_signals and len(negative_signals) >= 2):
            return True
        if coordinator is not None:
            return False
        return False

    @staticmethod
    def _collect_negative_result_signals(
        steps: list[WorkflowStepResult],
    ) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        seen: set[str] = set()
        for step in steps:
            raw_items = step.parsed_output.get("negative_results", [])
            if not isinstance(raw_items, list):
                continue
            stage_info = step.parsed_output.get("stage_assessment", {})
            current_stage = ""
            if isinstance(stage_info, dict):
                current_stage = str(stage_info.get("current_stage", "")).strip()
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                result = str(item.get("result", "")).strip()
                if not result:
                    continue
                fingerprint = result.lower()
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                signals.append(
                    {
                        "profile_name": step.profile_name,
                        "stage": current_stage,
                        "negative_key": f"{step.profile_name}::negative::{len(signals) + 1}",
                        "result": result,
                        "reason": str(item.get("why_it_failed_or_did_not_support", "")).strip(),
                        "implication": str(item.get("implication", "")).strip(),
                        "affected_hypothesis_ids": [
                            str(value).strip()
                            for value in (
                                item.get("affected_hypothesis_ids", [])
                                if isinstance(item.get("affected_hypothesis_ids", []), list)
                                else []
                            )
                            if str(value).strip()
                        ],
                    }
                )
        return signals

    @staticmethod
    def _build_negative_result_links(
        steps: list[WorkflowStepResult],
        hypothesis_id_map: dict[tuple[str, str], str],
        hypothesis_nodes: list[dict[str, Any]],
        negative_result_nodes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        hypothesis_term_map: dict[str, set[str]] = {}
        for item in hypothesis_nodes:
            global_id = str(item.get("global_hypothesis_id", "")).strip()
            if not global_id:
                continue
            hypothesis_term_map[global_id] = ScientificWorkflow._term_set(
                " ".join(
                    [
                        str(item.get("name", "")),
                        str(item.get("mechanism", "")),
                        str(item.get("prediction", "")),
                        " ".join(item.get("failure_conditions", []))
                        if isinstance(item.get("failure_conditions", []), list)
                        else "",
                    ]
                )
            )

        links: list[dict[str, Any]] = []
        for item in negative_result_nodes:
            negative_id = str(item.get("global_negative_result_id", "")).strip()
            if not negative_id:
                continue
            explicit_targets = [
                str(value).strip()
                for value in (
                    item.get("affected_hypothesis_ids", [])
                    if isinstance(item.get("affected_hypothesis_ids", []), list)
                    else []
                )
                if str(value).strip()
            ]
            targets: list[str] = []
            profile_name = str(item.get("profile_name", "")).strip()
            for value in explicit_targets:
                mapped = hypothesis_id_map.get((profile_name, value))
                if mapped is None:
                    for (_, hypothesis_local_id), candidate in hypothesis_id_map.items():
                        if hypothesis_local_id == value:
                            mapped = candidate
                            break
                if mapped and mapped not in targets:
                    targets.append(mapped)

            if not targets:
                negative_terms = ScientificWorkflow._term_set(
                    " ".join(
                        [
                            str(item.get("result", "")),
                            str(item.get("why_it_failed_or_did_not_support", "")),
                            str(item.get("implication", "")),
                        ]
                    )
                )
                scored: list[tuple[int, str]] = []
                for hypothesis_id, hypothesis_terms in hypothesis_term_map.items():
                    overlap = len(negative_terms.intersection(hypothesis_terms))
                    if overlap > 0:
                        scored.append((overlap, hypothesis_id))
                scored.sort(key=lambda pair: pair[0], reverse=True)
                targets = [hypothesis_id for _, hypothesis_id in scored[:3]]

            for target_id in targets:
                links.append(
                    {
                        "negative_result_id": negative_id,
                        "hypothesis_id": target_id,
                        "relation": "challenges",
                    }
                )
        return links

    @staticmethod
    def _term_set(text: str) -> set[str]:
        import re

        return {
            term
            for term in re.findall(r"[a-zA-Z0-9_]+", text.lower())
            if len(term) >= 4
        }

    def _capture_negative_result_memories(
        self,
        steps: list[WorkflowStepResult],
    ) -> None:
        project_id = self.collaboration_context.get("project_id", "")
        user_id = self.collaboration_context.get("user_id", "")
        group_id = self.collaboration_context.get("group_id", "")
        manager = self.subagent_runtime.memory_manager
        existing_titles = {record.title.strip().lower() for record in manager._scan_memory_records()}
        for signal in self._collect_negative_result_signals(steps):
            title = manager._clip_title(f"negative result: {signal['result']}", 80)
            normalized = title.strip().lower()
            if normalized in existing_titles:
                continue
            tags = ["negative-result", "failed-attempt", signal["profile_name"]]
            if signal["stage"]:
                tags.append(signal["stage"])
            content_parts = [signal["result"]]
            if signal["reason"]:
                content_parts.append(f"Why it failed or did not support: {signal['reason']}")
            if signal["implication"]:
                content_parts.append(f"Implication: {signal['implication']}")
            if signal["affected_hypothesis_ids"]:
                content_parts.append(
                    "Affected hypothesis ids: "
                    + ", ".join(signal["affected_hypothesis_ids"])
                )
            manager.save_memory(
                title=title,
                summary="Negative result or failed attempt carried forward into project memory",
                kind="warning",
                scope="project",
                content="\n\n".join(content_parts),
                tags=tags,
                source_refs=[],
                evidence_level="high" if signal["profile_name"] == "data_analyst" else "medium",
                confidence="medium",
                status="active",
                owner_agent=signal["profile_name"],
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                needs_review=False,
                validated_by=[
                    f"agent:{signal['profile_name']}",
                    "workflow:negative-results-loop",
                    *[
                        f"challenged-hypothesis:{value}"
                        for value in signal["affected_hypothesis_ids"]
                    ],
                ],
            )
            existing_titles.add(normalized)

    def _sync_hypothesis_memories(self, claim_graph: dict[str, Any]) -> None:
        hypothesis_nodes = claim_graph.get("hypotheses", [])
        if not isinstance(hypothesis_nodes, list) or not hypothesis_nodes:
            return

        challenge_map: dict[str, list[str]] = {}
        for item in claim_graph.get("negative_result_links", []):
            if not isinstance(item, dict):
                continue
            hypothesis_id = str(item.get("hypothesis_id", "")).strip()
            negative_id = str(item.get("negative_result_id", "")).strip()
            if not hypothesis_id or not negative_id:
                continue
            challenge_map.setdefault(hypothesis_id, []).append(negative_id)

        user_id = self.collaboration_context.get("user_id", "")
        project_id = self.collaboration_context.get("project_id", "")
        group_id = self.collaboration_context.get("group_id", "")
        manager = self.subagent_runtime.memory_manager
        memory_updates: list[dict[str, Any]] = []
        validation_summary = claim_graph.get("hypothesis_validation_summary", {})
        validation_by_id = {
            str(record.get("hypothesis_id", "")).strip(): record
            for record in validation_summary.get("records", [])
            if isinstance(record, dict) and str(record.get("hypothesis_id", "")).strip()
        } if isinstance(validation_summary, dict) and isinstance(validation_summary.get("records", []), list) else {}
        gate_summary = claim_graph.get("hypothesis_gate_summary", {})
        gate_by_id = {
            str(record.get("hypothesis_id", "")).strip(): record
            for record in gate_summary.get("records", [])
            if isinstance(record, dict) and str(record.get("hypothesis_id", "")).strip()
        } if isinstance(gate_summary, dict) and isinstance(gate_summary.get("records", []), list) else {}

        for item in hypothesis_nodes:
            if not isinstance(item, dict):
                continue
            global_id = str(item.get("global_hypothesis_id", "")).strip()
            local_id = str(item.get("hypothesis_id", "")).strip()
            if not global_id or not local_id:
                continue
            title_name = str(item.get("name", "")).strip() or local_id
            filename = manager._slugify(
                f"hypothesis-{local_id}-{title_name}"
            )
            linked_negatives = challenge_map.get(global_id, [])
            tags = ["hypothesis-memory", str(item.get("profile_name", "unknown"))]
            status = str(item.get("status", "active")).strip().lower()
            if status:
                tags.append(status)
            if linked_negatives:
                tags.append("challenged")

            content_lines = [
                f"Hypothesis ID: {local_id}",
                f"Global Hypothesis ID: {global_id}",
                f"Name: {title_name}",
                f"Status: {status or 'active'}",
                f"Prediction: {str(item.get('prediction', '')).strip() or 'Not stated'}",
                f"Mechanism: {str(item.get('mechanism', '')).strip() or 'Not stated'}",
                f"Falsifiability Test: {str(item.get('falsifiability_test', '')).strip() or 'Not stated'}",
            ]
            assumptions = item.get("assumptions", [])
            if isinstance(assumptions, list) and assumptions:
                content_lines.append("Assumptions: " + "; ".join(str(v) for v in assumptions if str(v).strip()))
            failure_conditions = item.get("failure_conditions", [])
            if isinstance(failure_conditions, list) and failure_conditions:
                content_lines.append(
                    "Failure Conditions: " + "; ".join(str(v) for v in failure_conditions if str(v).strip())
                )
            if linked_negatives:
                content_lines.append("Challenged By Negative Results: " + ", ".join(linked_negatives))
            if item.get("challenge_count"):
                content_lines.append(f"Challenge Count: {item.get('challenge_count')}")
            validation = validation_by_id.get(local_id) or validation_by_id.get(global_id) or {}
            if validation:
                content_lines.extend(
                    [
                        f"Validator Recommendation: {str(validation.get('overall_recommendation', '')).strip() or 'observe'}",
                        "Validator Scores: "
                        + "; ".join(
                            [
                                f"novelty={validation.get('novelty_score', 0)}",
                                f"falsifiability={validation.get('falsifiability_score', 0)}",
                                f"testability={validation.get('testability_score', 0)}",
                                f"mechanism={validation.get('mechanistic_coherence_score', 0)}",
                                f"evidence={validation.get('evidence_grounding_score', 0)}",
                            ]
                        ),
                    ]
                )
                flags = validation.get("validator_flags", [])
                if isinstance(flags, list) and flags:
                    content_lines.append("Validator Flags: " + "; ".join(str(flag) for flag in flags if str(flag).strip()))
                    tags.extend(f"validator:{flag}" for flag in flags if str(flag).strip())
            gate = gate_by_id.get(local_id) or gate_by_id.get(global_id) or {}
            if gate:
                gate_decision = str(gate.get("gate_decision", "")).strip()
                content_lines.append(f"Hypothesis Gate: {gate_decision or 'observe'}")
                if gate_decision:
                    tags.append(f"gate:{gate_decision}")

            path = manager.save_memory(
                title=f"Hypothesis {local_id}: {title_name}",
                summary="Project hypothesis lifecycle record",
                kind="hypothesis",
                scope="project",
                content="\n\n".join(content_lines),
                filename=filename,
                tags=tags,
                source_refs=[],
                evidence_level="medium",
                confidence="medium",
                status=(
                    status
                    if status in {"active", "revised", "uncertain", "deprecated", "rejected"}
                    else "active"
                ),
                owner_agent=str(item.get("profile_name", "hypothesis_generator")),
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                needs_review=False,
                validated_by=[
                    f"workflow:hypothesis-lifecycle:{status or 'active'}",
                    *[f"challenged-by:{negative_id}" for negative_id in linked_negatives],
                ],
            )
            memory_updates.append(
                {
                    "filename": path.name,
                    "updated_by": "hypothesis-lifecycle",
                    "hypothesis_id": local_id,
                    "status": status or "active",
                }
            )

        if memory_updates:
            existing = claim_graph.get("memory_updates", [])
            if isinstance(existing, list):
                claim_graph["memory_updates"] = existing + memory_updates
            else:
                claim_graph["memory_updates"] = memory_updates

    def _sync_project_distill_memory(self, research_state: dict[str, Any]) -> None:
        distill = research_state.get("project_distill", {})
        if not isinstance(distill, dict) or not distill:
            return
        project_id = str(self.collaboration_context.get("project_id", "")).strip()
        if not project_id:
            return
        consensus = str(distill.get("current_consensus", "")).strip()
        if not consensus:
            return
        body = "\n".join(
            [
                f"Topic: {research_state.get('topic', '')}",
                f"Current consensus: {consensus}",
                "",
                "Failed routes:",
                *(f"- {item}" for item in distill.get("failed_routes", []) if str(item).strip()),
                "",
                "Next cycle goals:",
                *(f"- {item}" for item in distill.get("next_cycle_goals", []) if str(item).strip()),
                "",
                "Registry updates:",
                *(f"- {item}" for item in distill.get("registry_updates", []) if str(item).strip()),
            ]
        ).strip()
        self.subagent_runtime.memory_manager.save_memory(
            title=f"Project distill: {research_state.get('topic', 'research thread')}",
            summary=consensus[:220],
            kind="decision",
            scope="project",
            content=body,
            filename="project-distill.md",
            source_refs=[],
            evidence_level="medium",
            confidence="medium",
            status="active",
            owner_agent="belief_updater" if research_state.get("belief_update_summary") else "coordinator",
            user_id=str(self.collaboration_context.get("user_id", "")),
            project_id=project_id,
            group_id=str(self.collaboration_context.get("group_id", "")),
            visibility="project",
            promotion_status="project",
            validated_by=["workflow:project-distill"],
        )

    def _sync_belief_update_memories(self, research_state: dict[str, Any]) -> None:
        summary = research_state.get("belief_update_summary", {})
        if not isinstance(summary, dict) or not summary:
            return
        project_id = str(self.collaboration_context.get("project_id", "")).strip()
        if not project_id:
            return
        consensus_status = str(summary.get("consensus_status", "")).strip() or "partial"
        current_consensus = str(summary.get("current_consensus", "")).strip()
        next_cycle_goals = summary.get("next_cycle_goals", []) if isinstance(summary.get("next_cycle_goals", []), list) else []
        failed_routes = summary.get("failed_routes", []) if isinstance(summary.get("failed_routes", []), list) else []
        status_counts = summary.get("status_counts", {}) if isinstance(summary.get("status_counts", {}), dict) else {}
        relation_counts = (
            summary.get("hypothesis_relation_counts", {})
            if isinstance(summary.get("hypothesis_relation_counts", {}), dict)
            else {}
        )
        body = "\n".join(
            [
                f"Topic: {research_state.get('topic', '')}",
                f"Consensus status: {consensus_status}",
                f"Current consensus: {current_consensus or 'Consensus still evolving.'}",
                f"Challenged hypotheses: {summary.get('challenged_hypothesis_count', 0)}",
                f"Hypothesis status counts: {json.dumps(status_counts, ensure_ascii=False)}",
                f"Hypothesis relation counts: {json.dumps(relation_counts, ensure_ascii=False)}",
                "",
                "Next cycle goals:",
                *(f"- {item}" for item in next_cycle_goals if str(item).strip()),
                "",
                "Failed routes:",
                *(f"- {item}" for item in failed_routes if str(item).strip()),
            ]
        ).strip()
        self.subagent_runtime.memory_manager.save_memory(
            title=f"Belief update summary: {research_state.get('topic', 'research thread')}",
            summary=(current_consensus or consensus_status or "Belief update recorded.")[:220],
            kind="decision",
            scope="project",
            content=body,
            filename="belief-update-summary.md",
            source_refs=[],
            evidence_level="medium",
            confidence="medium",
            status="active",
            owner_agent="belief_updater",
            user_id=str(self.collaboration_context.get("user_id", "")),
            project_id=project_id,
            group_id=str(self.collaboration_context.get("group_id", "")),
            visibility="project",
            promotion_status="project",
            tags=["belief-update", "hypothesis-lifecycle", "next-cycle"],
            validated_by=["workflow:belief-update"],
        )

    def _sync_research_strategy_memories(self, research_state: dict[str, Any]) -> None:
        project_id = str(self.collaboration_context.get("project_id", "")).strip()
        if not project_id:
            return
        manager = self.subagent_runtime.memory_manager
        user_id = str(self.collaboration_context.get("user_id", ""))
        group_id = str(self.collaboration_context.get("group_id", ""))

        research_plan = research_state.get("research_plan_summary", {})
        if isinstance(research_plan, dict) and research_plan:
            manager.save_memory(
                title=f"Research plan: {research_state.get('topic', 'research thread')}",
                summary=str(research_plan.get("planning_horizon", "next-three-cycles")),
                kind="decision",
                scope="project",
                content="\n".join(
                    [
                        f"Topic: {research_state.get('topic', '')}",
                        f"Planning horizon: {research_plan.get('planning_horizon', '')}",
                        "",
                        "Priority questions:",
                        *[f"- {item}" for item in research_plan.get("priority_questions", []) if str(item).strip()],
                        "",
                        "Next cycle experiments:",
                        *[f"- {item}" for item in research_plan.get("next_cycle_experiments", []) if str(item).strip()],
                        "",
                        "Decision gates:",
                        *[f"- {item}" for item in research_plan.get("decision_gates", []) if str(item).strip()],
                        "",
                        "Stop conditions:",
                        *[f"- {item}" for item in research_plan.get("stop_conditions", []) if str(item).strip()],
                        "",
                        "Strategy memory candidates:",
                        *[f"- {item}" for item in research_plan.get("strategy_memory_candidates", []) if str(item).strip()],
                    ]
                ).strip(),
                filename="research-plan-summary.md",
                source_refs=[],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="research_planner",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["research-plan", "information-gain", "next-cycle"],
                validated_by=["workflow:research-plan"],
            )

            if research_plan.get("strategy_memory_candidates"):
                manager.save_memory(
                    title=f"Planner strategy memory: {research_state.get('topic', 'research thread')}",
                    summary=str(research_plan.get("strategy_memory_candidates", [""])[0]).strip()[:220],
                    kind="decision",
                    scope="project",
                    content="\n".join(
                        [
                            f"Topic: {research_state.get('topic', '')}",
                            "Reusable strategy lessons:",
                            *[
                                f"- {item}"
                                for item in research_plan.get("strategy_memory_candidates", [])
                                if str(item).strip()
                            ],
                        ]
                    ).strip(),
                    filename="planner-strategy-memory.md",
                    source_refs=[],
                    evidence_level="medium",
                    confidence="medium",
                    status="active",
                    owner_agent="research_planner",
                    user_id=user_id,
                    project_id=project_id,
                    group_id=group_id,
                    visibility="project",
                    promotion_status="project",
                    tags=["planner-memory", "strategy", "long-horizon"],
                    validated_by=["workflow:planner-strategy-memory"],
                )

        program_portfolio = research_state.get("program_portfolio_summary", {})
        if isinstance(program_portfolio, dict) and program_portfolio:
            manager.save_memory(
                title=f"Program portfolio: {research_state.get('topic', 'research thread')}",
                summary=str(program_portfolio.get("portfolio_pressure", "unknown")),
                kind="decision",
                scope="project",
                content="\n".join(
                    [
                        f"Portfolio pressure: {program_portfolio.get('portfolio_pressure', '')}",
                        f"Cost pressure: {program_portfolio.get('cost_pressure', '')}",
                        "",
                        "Active routes:",
                        *[f"- {item}" for item in program_portfolio.get("active_routes", []) if str(item).strip()],
                        "",
                        "Exploratory routes:",
                        *[f"- {item}" for item in program_portfolio.get("exploratory_routes", []) if str(item).strip()],
                        "",
                        "Paused routes:",
                        *[f"- {item}" for item in program_portfolio.get("paused_routes", []) if str(item).strip()],
                        "",
                        "Retired routes:",
                        *[f"- {item}" for item in program_portfolio.get("retired_routes", []) if str(item).strip()],
                    ]
                ).strip(),
                filename="program-portfolio-summary.md",
                source_refs=[],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="research_planner",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["program-portfolio", "route-management"],
                validated_by=["workflow:program-portfolio"],
            )

        discipline = research_state.get("discipline_adaptation_summary", {})
        if isinstance(discipline, dict) and discipline:
            manager.save_memory(
                title=f"Discipline adaptation: {research_state.get('topic', 'research thread')}",
                summary=str(discipline.get("primary_discipline", "general_science")),
                kind="method",
                scope="project",
                content="\n".join(
                    [
                        f"Primary discipline: {discipline.get('primary_discipline', '')}",
                        "",
                        "Secondary disciplines:",
                        *[f"- {item}" for item in discipline.get("secondary_disciplines", []) if str(item).strip()],
                        "",
                        "Adapter requirements:",
                        *[f"- {item}" for item in discipline.get("adapter_requirements", []) if str(item).strip()],
                        "",
                        "Discipline-specific risks:",
                        *[f"- {item}" for item in discipline.get("discipline_specific_risks", []) if str(item).strip()],
                    ]
                ).strip(),
                filename="discipline-adaptation-summary.md",
                source_refs=[],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="research_planner",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["discipline-adaptation", str(discipline.get("primary_discipline", ""))],
                validated_by=["workflow:discipline-adaptation"],
            )

        program_management = research_state.get("program_management_summary", {})
        if isinstance(program_management, dict) and program_management:
            manager.save_memory(
                title=f"Program management: {research_state.get('topic', 'research thread')}",
                summary=str(program_management.get("primary_workstream", "primary")),
                kind="decision",
                scope="project",
                content="\n".join(
                    [
                        f"Program objective: {program_management.get('program_objective', '')}",
                        f"Primary workstream: {program_management.get('primary_workstream', '')}",
                        f"Review cadence: {program_management.get('review_cadence', '')}",
                        f"Route temperature: {program_management.get('route_temperature', '')}",
                        "",
                        "Secondary workstreams:",
                        *[f"- {item}" for item in program_management.get("secondary_workstreams", []) if str(item).strip()],
                        "",
                        "Milestones:",
                        *[f"- {item}" for item in program_management.get("milestones", []) if str(item).strip()],
                        "",
                        "Resource allocations:",
                        *[f"- {item}" for item in program_management.get("resource_allocations", []) if str(item).strip()],
                        "",
                        "Pivot triggers:",
                        *[f"- {item}" for item in program_management.get("pivot_triggers", []) if str(item).strip()],
                    ]
                ).strip(),
                filename="program-management-summary.md",
                source_refs=[],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="research_planner",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["program-management", "milestones", "workstreams"],
                validated_by=["workflow:program-management"],
            )

        domain_playbook = research_state.get("domain_playbook_summary", {})
        if isinstance(domain_playbook, dict) and domain_playbook:
            manager.save_memory(
                title=f"Domain playbooks: {research_state.get('topic', 'research thread')}",
                summary=str(domain_playbook.get("primary_discipline", "general_science")),
                kind="method",
                scope="project",
                content="\n".join(
                    [
                        f"Primary discipline: {domain_playbook.get('primary_discipline', '')}",
                        f"Playbook count: {domain_playbook.get('playbook_count', 0)}",
                        "",
                        "Execution patterns:",
                        *[f"- {item}" for item in domain_playbook.get("execution_patterns", []) if str(item).strip()],
                        "",
                        "Validation patterns:",
                        *[f"- {item}" for item in domain_playbook.get("validation_patterns", []) if str(item).strip()],
                        "",
                        "Failure modes:",
                        *[f"- {item}" for item in domain_playbook.get("failure_modes", []) if str(item).strip()],
                    ]
                ).strip(),
                filename="domain-playbook-summary.md",
                source_refs=[],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="research_planner",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["domain-playbook", str(domain_playbook.get("primary_discipline", ""))],
                validated_by=["workflow:domain-playbook"],
            )

        program_portfolio = research_state.get("program_portfolio_summary", {})
        if isinstance(program_portfolio, dict) and program_portfolio:
            manager.save_memory(
                title=f"Program portfolio: {research_state.get('topic', 'research thread')}",
                summary=str(program_portfolio.get("portfolio_pressure", "unknown")),
                kind="decision",
                scope="project",
                content="\n".join(
                    [
                        f"Portfolio pressure: {program_portfolio.get('portfolio_pressure', '')}",
                        f"Cost pressure: {program_portfolio.get('cost_pressure', '')}",
                        "",
                        "Active routes:",
                        *[f"- {item}" for item in program_portfolio.get("active_routes", []) if str(item).strip()],
                        "",
                        "Exploratory routes:",
                        *[f"- {item}" for item in program_portfolio.get("exploratory_routes", []) if str(item).strip()],
                        "",
                        "Paused routes:",
                        *[f"- {item}" for item in program_portfolio.get("paused_routes", []) if str(item).strip()],
                        "",
                        "Retired routes:",
                        *[f"- {item}" for item in program_portfolio.get("retired_routes", []) if str(item).strip()],
                    ]
                ).strip(),
                filename="program-portfolio-summary.md",
                source_refs=[],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="research_planner",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["program-portfolio", "route-management"],
                validated_by=["workflow:program-portfolio"],
            )

        formal_review = research_state.get("formal_review_record_summary", {})
        if isinstance(formal_review, dict) and formal_review:
            manager.save_memory(
                title=f"Formal review records: {research_state.get('topic', 'research thread')}",
                summary=f"protocol={formal_review.get('review_protocol_version', 'draft')}",
                kind="reference",
                scope="project",
                content="\n".join(
                    [
                        f"Review protocol version: {formal_review.get('review_protocol_version', '')}",
                        f"Screening record count: {formal_review.get('screening_record_count', 0)}",
                        f"Evidence table record count: {formal_review.get('evidence_table_record_count', 0)}",
                        f"Review update count: {formal_review.get('review_update_count', 0)}",
                        f"Exclusion reason count: {formal_review.get('exclusion_reason_count', 0)}",
                        "",
                        "Screening records:",
                        *[f"- {item}" for item in formal_review.get("screening_records", []) if str(item).strip()],
                        "",
                        "Evidence table records:",
                        *[f"- {item}" for item in formal_review.get("evidence_table_records", []) if str(item).strip()],
                        "",
                        "Review record updates:",
                        *[f"- {item}" for item in formal_review.get("review_record_updates", []) if str(item).strip()],
                    ]
                ).strip(),
                filename="formal-review-records.md",
                source_refs=[],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="literature_reviewer",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["formal-review", "screening", "evidence-table"],
                validated_by=["workflow:formal-review-records"],
            )

        evidence_review = research_state.get("evidence_review_summary", {})
        if isinstance(evidence_review, dict) and evidence_review:
            manager.save_memory(
                title=f"Evidence review engine: {research_state.get('topic', 'research thread')}",
                summary=(
                    f"readiness={evidence_review.get('review_readiness', 'draft')}; "
                    f"quality={evidence_review.get('review_quality_state', 'needs_review')}"
                ),
                kind="reference",
                scope="project",
                content="\n".join(
                    [
                        f"Review id: {evidence_review.get('review_id', '')}",
                        f"Review question: {evidence_review.get('review_question', '')}",
                        f"Review readiness: {evidence_review.get('review_readiness', '')}",
                        f"Review quality state: {evidence_review.get('review_quality_state', '')}",
                        f"Protocol completeness score: {evidence_review.get('protocol_completeness_score', 0)}",
                        f"Screening quality score: {evidence_review.get('screening_quality_score', 0)}",
                        f"Evidence grade balance: {json.dumps(evidence_review.get('evidence_grade_balance', {}), ensure_ascii=False)}",
                        f"Bias risk summary: {json.dumps(evidence_review.get('bias_risk_summary', {}), ensure_ascii=False)}",
                        f"Conflict resolution state: {evidence_review.get('conflict_resolution_state', '')}",
                        "",
                        "Review blockers:",
                        *[f"- {item}" for item in evidence_review.get("review_blockers", []) if str(item).strip()],
                        "",
                        "Recommended review actions:",
                        *[f"- {item}" for item in evidence_review.get("recommended_review_actions", []) if str(item).strip()],
                    ]
                ).strip(),
                filename="evidence-review-engine.md",
                source_refs=[
                    str(item.get("evidence_id", "")).strip()
                    for item in evidence_review.get("assessment_records", [])
                    if isinstance(item, dict) and str(item.get("evidence_id", "")).strip()
                ],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="literature_reviewer",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["evidence-review", "systematic-review", "bias-risk", "conflict-attribution"],
                validated_by=["workflow:evidence-review-engine"],
            )

        autonomous_controller = research_state.get("autonomous_controller_summary", {})
        if isinstance(autonomous_controller, dict) and autonomous_controller:
            manager.save_memory(
                title=f"Autonomous research controller: {research_state.get('topic', 'research thread')}",
                summary=(
                    f"state={autonomous_controller.get('controller_state', '')}; "
                    f"loop={autonomous_controller.get('loop_decision', '')}"
                ),
                kind="decision",
                scope="project",
                content="\n".join(
                    [
                        f"Controller id: {autonomous_controller.get('controller_id', '')}",
                        f"Controller state: {autonomous_controller.get('controller_state', '')}",
                        f"Loop decision: {autonomous_controller.get('loop_decision', '')}",
                        f"Next cycle stage: {autonomous_controller.get('next_cycle_stage', '')}",
                        f"Next cycle action: {autonomous_controller.get('next_cycle_action', '')}",
                        f"Can continue autonomously: {autonomous_controller.get('can_continue_autonomously', False)}",
                        f"Must pause for human: {autonomous_controller.get('must_pause_for_human', False)}",
                        f"Continuation budget: {json.dumps(autonomous_controller.get('continuation_budget', {}), ensure_ascii=False)}",
                        "",
                        "Recommended agents:",
                        *[f"- {item}" for item in autonomous_controller.get("recommended_agents", []) if str(item).strip()],
                        "",
                        "Pause reasons:",
                        *[f"- {item}" for item in autonomous_controller.get("pause_reasons", []) if str(item).strip()],
                        "",
                        "Required inputs:",
                        *[f"- {item}" for item in autonomous_controller.get("required_inputs", []) if str(item).strip()],
                        "",
                        "Safety gates:",
                        *[f"- {item}" for item in autonomous_controller.get("safety_gates", []) if str(item).strip()],
                    ]
                ).strip(),
                filename="autonomous-research-controller.md",
                source_refs=[
                    str(trace.get("source_id", "")).strip()
                    for trace in autonomous_controller.get("decision_trace", [])
                    if isinstance(trace, dict) and str(trace.get("source_id", "")).strip()
                ],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="coordinator",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["autonomous-controller", "research-loop", "human-gate"],
                validated_by=["workflow:autonomous-research-controller"],
            )

        hypothesis_gate = research_state.get("hypothesis_gate_summary", {})
        if isinstance(hypothesis_gate, dict) and hypothesis_gate:
            manager.save_memory(
                title=f"Hypothesis gate: {research_state.get('topic', 'research thread')}",
                summary=str(hypothesis_gate.get("gate_state", "open")),
                kind="decision",
                scope="project",
                content="\n".join(
                    [
                        f"Gate state: {hypothesis_gate.get('gate_state', '')}",
                        f"Validator flag count: {hypothesis_gate.get('validator_flag_count', 0)}",
                        f"Gate counts: {json.dumps(hypothesis_gate.get('gate_counts', {}), ensure_ascii=False)}",
                        "",
                        "Accepted hypotheses:",
                        *[f"- {item}" for item in hypothesis_gate.get("accepted_hypotheses", []) if str(item).strip()],
                        "",
                        "Revise hypotheses:",
                        *[f"- {item}" for item in hypothesis_gate.get("revise_hypotheses", []) if str(item).strip()],
                        "",
                        "Blocked hypotheses:",
                        *[f"- {item}" for item in hypothesis_gate.get("blocked_hypotheses", []) if str(item).strip()],
                    ]
                ).strip(),
                filename="hypothesis-gate-summary.md",
                source_refs=[],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="hypothesis_generator",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["hypothesis-gate", "validators", "decision-gate"],
                validated_by=["workflow:hypothesis-gate"],
            )

        hypothesis_theory = research_state.get("hypothesis_theory_summary", {})
        if isinstance(hypothesis_theory, dict) and hypothesis_theory:
            manager.save_memory(
                title=f"Hypothesis theory objects: {research_state.get('topic', 'research thread')}",
                summary=(
                    f"objects={hypothesis_theory.get('theory_object_count', 0)}; "
                    f"decisions={json.dumps(hypothesis_theory.get('decision_state_counts', {}), ensure_ascii=False)}"
                ),
                kind="hypothesis",
                scope="project",
                content="\n".join(
                    [
                        f"Theory object count: {hypothesis_theory.get('theory_object_count', 0)}",
                        f"Maturity counts: {json.dumps(hypothesis_theory.get('maturity_counts', {}), ensure_ascii=False)}",
                        f"Decision state counts: {json.dumps(hypothesis_theory.get('decision_state_counts', {}), ensure_ascii=False)}",
                        f"Missing field counts: {json.dumps(hypothesis_theory.get('missing_field_counts', {}), ensure_ascii=False)}",
                        "",
                        "Advance candidates:",
                        *[f"- {item}" for item in hypothesis_theory.get("advance_candidates", []) if str(item).strip()],
                        "",
                        "Revise candidates:",
                        *[f"- {item}" for item in hypothesis_theory.get("revise_candidates", []) if str(item).strip()],
                        "",
                        "Blocked candidates:",
                        *[f"- {item}" for item in hypothesis_theory.get("blocked_candidates", []) if str(item).strip()],
                    ]
                ).strip(),
                filename="hypothesis-theory-objects.md",
                source_refs=[],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="hypothesis_generator",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["hypothesis-theory-object", "theory-maturity", "decision-state"],
                validated_by=["workflow:hypothesis-theory-objects"],
            )

        scientific_decision = research_state.get("scientific_decision_summary", {})
        if isinstance(scientific_decision, dict) and scientific_decision:
            manager.save_memory(
                title=f"Scientific decision engine: {research_state.get('topic', 'research thread')}",
                summary=str(scientific_decision.get("recommended_next_action", "continue_current_route")),
                kind="decision",
                scope="project",
                content="\n".join(
                    [
                        f"Decision state: {scientific_decision.get('decision_state', '')}",
                        f"Recommended next action: {scientific_decision.get('recommended_next_action', '')}",
                        f"Recommended target id: {scientific_decision.get('recommended_target_id', '')}",
                        f"Must pause for human review: {scientific_decision.get('must_pause_for_human_review', False)}",
                        f"Provenance trace count: {scientific_decision.get('provenance_trace_count', 0)}",
                        f"Route search best action: {scientific_decision.get('route_search_best_action', '')}",
                        "",
                        "Decision queue:",
                        *[
                            "- "
                            + str(item.get("action", "")).strip()
                            + " | target="
                            + str(item.get("target_id", "")).strip()
                            + " | priority="
                            + str(item.get("priority", "")).strip()
                            + " | value="
                            + str(item.get("route_value_score", "")).strip()
                            for item in scientific_decision.get("decision_queue", [])
                            if isinstance(item, dict)
                        ][:10],
                    ]
                ).strip(),
                filename="scientific-decision-engine.md",
                source_refs=[],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="coordinator",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["decision-engine", "next-action", "information-gain"],
                validated_by=["workflow:scientific-decision-engine"],
            )

        experiment_scheduler = research_state.get("experiment_execution_loop_summary", {})
        if isinstance(experiment_scheduler, dict) and experiment_scheduler:
            manager.save_memory(
                title=f"Experiment execution loop: {research_state.get('topic', 'research thread')}",
                summary=(
                    f"state={experiment_scheduler.get('scheduler_state', '')}; "
                    f"top={experiment_scheduler.get('top_experiment_id', '')}"
                ),
                kind="decision",
                scope="project",
                content="\n".join(
                    [
                        f"Scheduler id: {experiment_scheduler.get('scheduler_id', '')}",
                        f"Scheduler state: {experiment_scheduler.get('scheduler_state', '')}",
                        f"Top experiment id: {experiment_scheduler.get('top_experiment_id', '')}",
                        f"Top action: {experiment_scheduler.get('top_action', '')}",
                        f"Candidate count: {experiment_scheduler.get('candidate_count', 0)}",
                        f"Parameter optimization supported: {experiment_scheduler.get('parameter_optimization_supported', False)}",
                        f"MCTS-like search: {json.dumps(experiment_scheduler.get('mcts_like_search', {}), ensure_ascii=False)}",
                        "",
                        "Execution queue:",
                        *[
                            "- "
                            + str(item.get("experiment_id", "")).strip()
                            + " | action="
                            + str(item.get("action", "")).strip()
                            + " | score="
                            + str(item.get("portfolio_score", "")).strip()
                            for item in experiment_scheduler.get("execution_queue", [])
                            if isinstance(item, dict)
                        ][:10],
                        "",
                        "Blocked experiments:",
                        *[
                            "- "
                            + str(item.get("experiment_id", "")).strip()
                            + " | gate="
                            + str(item.get("gate_state", "")).strip()
                            + " | reasons="
                            + ", ".join(str(reason) for reason in item.get("gate_reasons", []) if str(reason).strip())
                            for item in experiment_scheduler.get("blocked_experiments", [])
                            if isinstance(item, dict)
                        ][:10],
                    ]
                ).strip(),
                filename="experiment-execution-loop.md",
                source_refs=[
                    str(item.get("experiment_id", "")).strip()
                    for item in experiment_scheduler.get("execution_queue", [])
                    if isinstance(item, dict) and str(item.get("experiment_id", "")).strip()
                ],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="run_manager",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["experiment-scheduler", "execution-loop", "mcts-like-search", "parameter-optimization"],
                validated_by=["workflow:experiment-execution-loop"],
            )

        optimization_adapter = research_state.get("optimization_adapter_summary", {})
        if isinstance(optimization_adapter, dict) and optimization_adapter:
            manager.save_memory(
                title=f"Optimization adapter: {research_state.get('topic', 'research thread')}",
                summary=(
                    f"state={optimization_adapter.get('adapter_state', '')}; "
                    f"plans={optimization_adapter.get('plan_count', 0)}"
                ),
                kind="reference",
                scope="project",
                content="\n".join(
                    [
                        f"Adapter id: {optimization_adapter.get('adapter_id', '')}",
                        f"Adapter state: {optimization_adapter.get('adapter_state', '')}",
                        f"Optimization candidate count: {optimization_adapter.get('optimization_candidate_count', 0)}",
                        f"Plan count: {optimization_adapter.get('plan_count', 0)}",
                        f"Execution boundary: {json.dumps(optimization_adapter.get('execution_boundary', {}), ensure_ascii=False)}",
                        "",
                        "Plans:",
                        *[
                            "- "
                            + str(plan.get("plan_id", "")).strip()
                            + " | experiment="
                            + str(plan.get("experiment_id", "")).strip()
                            + " | strategy="
                            + str(plan.get("search_strategy", "")).strip()
                            + " | trials="
                            + str(len(plan.get("exploratory_trials", [])))
                            for plan in optimization_adapter.get("plans", [])
                            if isinstance(plan, dict)
                        ][:10],
                        "",
                        "Best config candidates:",
                        *[
                            "- " + json.dumps(item, ensure_ascii=False)
                            for item in optimization_adapter.get("best_config_candidates", [])
                            if isinstance(item, dict)
                        ][:6],
                    ]
                ).strip(),
                filename="optimization-adapter.md",
                source_refs=[
                    str(plan.get("experiment_id", "")).strip()
                    for plan in optimization_adapter.get("plans", [])
                    if isinstance(plan, dict) and str(plan.get("experiment_id", "")).strip()
                ],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="experiment_economist",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["optimization-adapter", "parameter-optimization", "confirmatory-evaluation"],
                validated_by=["workflow:optimization-adapter"],
            )

        discipline_adapter = research_state.get("discipline_adapter_summary", {})
        if isinstance(discipline_adapter, dict) and discipline_adapter:
            manager.save_memory(
                title=f"Discipline adapters: {research_state.get('topic', 'research thread')}",
                summary=(
                    f"state={discipline_adapter.get('adapter_state', '')}; "
                    f"discipline={discipline_adapter.get('primary_discipline', '')}; "
                    f"bindings={discipline_adapter.get('binding_count', 0)}"
                ),
                kind="reference",
                scope="project",
                content="\n".join(
                    [
                        f"Adapter id: {discipline_adapter.get('adapter_id', '')}",
                        f"Adapter state: {discipline_adapter.get('adapter_state', '')}",
                        f"Primary discipline: {discipline_adapter.get('primary_discipline', '')}",
                        f"Selected adapter id: {discipline_adapter.get('selected_adapter_id', '')}",
                        f"Execution boundary: {json.dumps(discipline_adapter.get('execution_boundary', {}), ensure_ascii=False)}",
                        f"Handoff extensions: {json.dumps(discipline_adapter.get('handoff_contract_extensions', {}), ensure_ascii=False)}",
                        "",
                        "Bindings:",
                        *[
                            "- "
                            + str(binding.get("binding_id", "")).strip()
                            + " | experiment="
                            + str(binding.get("experiment_id", "")).strip()
                            + " | state="
                            + str(binding.get("readiness_state", "")).strip()
                            + " | failure_modes="
                            + ", ".join(
                                str(mode)
                                for mode in binding.get("failure_modes_to_watch", [])[:4]
                                if str(mode).strip()
                            )
                            + " | scheduler_rules="
                            + ", ".join(
                                str(rule)
                                for rule in binding.get("scheduler_rules", [])[:3]
                                if str(rule).strip()
                            )
                            for binding in discipline_adapter.get("bindings", [])
                            if isinstance(binding, dict)
                        ][:10],
                    ]
                ).strip(),
                filename="discipline-adapters.md",
                source_refs=[
                    str(binding.get("experiment_id", "")).strip()
                    for binding in discipline_adapter.get("bindings", [])
                    if isinstance(binding, dict) and str(binding.get("experiment_id", "")).strip()
                ],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="run_manager",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["discipline-adapter", "domain-contract", "execution-loop"],
                validated_by=["workflow:discipline-adapter"],
            )

        execution_registry = research_state.get("execution_adapter_registry_summary", {})
        if isinstance(execution_registry, dict) and execution_registry:
            manager.save_memory(
                title=f"Execution adapter registry: {research_state.get('topic', 'research thread')}",
                summary=(
                    f"state={execution_registry.get('registry_state', '')}; "
                    f"packages={execution_registry.get('execution_package_count', 0)}"
                ),
                kind="reference",
                scope="project",
                content="\n".join(
                    [
                        f"Registry id: {execution_registry.get('registry_id', '')}",
                        f"Registry state: {execution_registry.get('registry_state', '')}",
                        f"Primary discipline: {execution_registry.get('primary_discipline', '')}",
                        f"Selected adapter id: {execution_registry.get('selected_adapter_id', '')}",
                        f"Execution package count: {execution_registry.get('execution_package_count', 0)}",
                        f"Ready package count: {execution_registry.get('ready_package_count', 0)}",
                        f"Blocked package count: {execution_registry.get('blocked_package_count', 0)}",
                        f"Handoff policy: {json.dumps(execution_registry.get('handoff_policy', {}), ensure_ascii=False)}",
                        "",
                        "Execution packages:",
                        *[
                            "- "
                            + str(package.get("package_id", "")).strip()
                            + " | experiment="
                            + str(package.get("experiment_id", "")).strip()
                            + " | state="
                            + str(package.get("package_state", "")).strip()
                            + " | handoff="
                            + str(package.get("handoff_target", "")).strip()
                            for package in execution_registry.get("execution_packages", [])
                            if isinstance(package, dict)
                        ][:10],
                    ]
                ).strip(),
                filename="execution-adapter-registry.md",
                source_refs=[
                    str(package.get("experiment_id", "")).strip()
                    for package in execution_registry.get("execution_packages", [])
                    if isinstance(package, dict) and str(package.get("experiment_id", "")).strip()
                ],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="run_manager",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["execution-adapter", "handoff", "domain-adapter"],
                validated_by=["workflow:execution-adapter-registry"],
            )

        run_handoff = research_state.get("run_handoff_contract_summary", {})
        if isinstance(run_handoff, dict) and run_handoff:
            manager.save_memory(
                title=f"Run handoff contract: {research_state.get('topic', 'research thread')}",
                summary=(
                    f"state={run_handoff.get('contract_state', '')}; "
                    f"contracts={run_handoff.get('contract_count', 0)}"
                ),
                kind="reference",
                scope="project",
                content="\n".join(
                    [
                        f"Handoff contract id: {run_handoff.get('handoff_contract_id', '')}",
                        f"Contract state: {run_handoff.get('contract_state', '')}",
                        f"Contract count: {run_handoff.get('contract_count', 0)}",
                        f"Return contract: {json.dumps(run_handoff.get('return_contract', {}), ensure_ascii=False)}",
                        f"Normalization function: {run_handoff.get('normalization_function', '')}",
                        "",
                        "Contracts:",
                        *[
                            "- "
                            + str(contract.get("contract_id", "")).strip()
                            + " | package="
                            + str(contract.get("package_id", "")).strip()
                            + " | experiment="
                            + str(contract.get("experiment_id", "")).strip()
                            for contract in run_handoff.get("contracts", [])
                            if isinstance(contract, dict)
                        ][:10],
                    ]
                ).strip(),
                filename="run-handoff-contract.md",
                source_refs=[
                    str(contract.get("package_id", "")).strip()
                    for contract in run_handoff.get("contracts", [])
                    if isinstance(contract, dict) and str(contract.get("package_id", "")).strip()
                ],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="run_manager",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["run-handoff", "execution-contract", "result-return"],
                validated_by=["workflow:run-handoff-contract"],
            )

        unified_assets = research_state.get("unified_asset_summary", {})
        if isinstance(unified_assets, dict) and unified_assets:
            manager.save_memory(
                title=f"Unified scientific assets: {research_state.get('topic', 'research thread')}",
                summary=f"assets={unified_assets.get('asset_count', 0)}; governed={unified_assets.get('governed_asset_count', 0)}",
                kind="reference",
                scope="project",
                content="\n".join(
                    [
                        f"Asset count: {unified_assets.get('asset_count', 0)}",
                        f"Governed asset count: {unified_assets.get('governed_asset_count', 0)}",
                        f"Asset type counts: {json.dumps(unified_assets.get('asset_type_counts', {}), ensure_ascii=False)}",
                        f"Source system counts: {json.dumps(unified_assets.get('source_system_counts', {}), ensure_ascii=False)}",
                        "",
                        "Review required assets:",
                        *[f"- {item}" for item in unified_assets.get("review_required_assets", []) if str(item).strip()],
                    ]
                ).strip(),
                filename="unified-scientific-assets.md",
                source_refs=[],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="coordinator",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["scientific-asset", "asset-index", "provenance"],
                validated_by=["workflow:unified-scientific-assets"],
            )

        mechanism_family_lifecycle = research_state.get("mechanism_family_lifecycle_summary", {})
        if isinstance(mechanism_family_lifecycle, dict) and mechanism_family_lifecycle:
            manager.save_memory(
                title=f"Mechanism family lifecycle: {research_state.get('topic', 'research thread')}",
                summary=f"families={mechanism_family_lifecycle.get('family_count', 0)}",
                kind="reference",
                scope="project",
                content="\n".join(
                    [
                        f"Family count: {mechanism_family_lifecycle.get('family_count', 0)}",
                        f"Mechanism count: {mechanism_family_lifecycle.get('mechanism_count', 0)}",
                        f"Family status counts: {json.dumps(mechanism_family_lifecycle.get('family_status_counts', {}), ensure_ascii=False)}",
                        "",
                        "Retire candidates:",
                        *[f"- {item}" for item in mechanism_family_lifecycle.get("retire_candidates", []) if str(item).strip()],
                        "",
                        "Revive candidates:",
                        *[f"- {item}" for item in mechanism_family_lifecycle.get("revive_candidates", []) if str(item).strip()],
                    ]
                ).strip(),
                filename="mechanism-family-lifecycle.md",
                source_refs=[],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="belief_updater",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["mechanism-family", "mechanism-lifecycle", "theory-governance"],
                validated_by=["workflow:mechanism-family-lifecycle"],
            )

        artifact_provenance = research_state.get("artifact_provenance_summary", {})
        if isinstance(artifact_provenance, dict) and artifact_provenance:
            manager.save_memory(
                title=f"Artifact provenance: {research_state.get('topic', 'research thread')}",
                summary=f"artifacts={artifact_provenance.get('artifact_count', 0)}",
                kind="reference",
                scope="project",
                content="\n".join(
                    [
                        f"Artifact count: {artifact_provenance.get('artifact_count', 0)}",
                        f"Input file count: {artifact_provenance.get('input_file_count', 0)}",
                        f"Registered asset count: {artifact_provenance.get('registered_asset_count', 0)}",
                        f"Provenance edge count: {artifact_provenance.get('provenance_edge_count', 0)}",
                        f"Governed artifact count: {artifact_provenance.get('governed_artifact_count', 0)}",
                        f"Ungoverned artifact count: {artifact_provenance.get('ungoverned_artifact_count', 0)}",
                        "",
                        "Artifact types:",
                        *[f"- {item}" for item in artifact_provenance.get("artifact_types", []) if str(item).strip()],
                    ]
                ).strip(),
                filename="artifact-provenance-summary.md",
                source_refs=[],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="run_manager",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["artifact-provenance", "lineage", "governance"],
                validated_by=["workflow:artifact-provenance"],
            )

        autonomy = research_state.get("autonomy_summary", {})
        if isinstance(autonomy, dict) and autonomy:
            manager.save_memory(
                title=f"Autonomy summary: {research_state.get('topic', 'research thread')}",
                summary=str(autonomy.get("autonomy_state", "active")),
                kind="decision",
                scope="project",
                content="\n".join(
                    [
                        f"Current objective: {autonomy.get('current_objective', '')}",
                        f"Autonomy state: {autonomy.get('autonomy_state', '')}",
                        "",
                        "Autonomous next actions:",
                        *[f"- {item}" for item in autonomy.get("autonomous_next_actions", []) if str(item).strip()],
                        "",
                        "Monitoring signals:",
                        *[f"- {item}" for item in autonomy.get("monitoring_signals", []) if str(item).strip()],
                        "",
                        "Handoff points:",
                        *[f"- {item}" for item in autonomy.get("handoff_points", []) if str(item).strip()],
                    ]
                ).strip(),
                filename="autonomy-summary.md",
                source_refs=[],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="research_planner",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["autonomy", "research-control", str(autonomy.get("autonomy_state", ""))],
                validated_by=["workflow:autonomy-summary"],
            )

        systematic = research_state.get("systematic_review_summary", {})
        if isinstance(systematic, dict) and systematic:
            manager.save_memory(
                title=f"Systematic review summary: {research_state.get('topic', 'research thread')}",
                summary=str(systematic.get("review_question", "")).strip()[:220] or "Systematic review summary",
                kind="reference",
                scope="project",
                content="\n".join(
                    [
                        f"Review question: {systematic.get('review_question', '')}",
                        "",
                        "Study type hierarchy:",
                        *[f"- {item}" for item in systematic.get("study_type_hierarchy", []) if str(item).strip()],
                        "",
                        f"Review protocol version: {systematic.get('review_protocol_version', '')}",
                        "",
                        "Evidence balance:",
                        *[f"- {item}" for item in systematic.get("evidence_balance", []) if str(item).strip()],
                        "",
                        "Bias hotspots:",
                        *[f"- {item}" for item in systematic.get("bias_hotspots", []) if str(item).strip()],
                        "",
                        "Exclusion reasons:",
                        *[f"- {item}" for item in systematic.get("exclusion_reasons", []) if str(item).strip()],
                    ]
                ).strip(),
                filename="systematic-review-summary.md",
                source_refs=[],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="literature_reviewer",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["systematic-review", "evidence-synthesis"],
                validated_by=["workflow:systematic-review-summary"],
            )

        mechanism_summary = research_state.get("mechanism_reasoning_summary", {})
        if isinstance(mechanism_summary, dict) and mechanism_summary:
            manager.save_memory(
                title=f"Mechanism reasoning: {research_state.get('topic', 'research thread')}",
                summary=f"mechanisms={mechanism_summary.get('mechanism_count', 0)}",
                kind="hypothesis",
                scope="project",
                content="\n".join(
                    [
                        f"Mechanism count: {mechanism_summary.get('mechanism_count', 0)}",
                        "Competing pairs:",
                        *[f"- {item}" for item in mechanism_summary.get("competing_pairs", []) if str(item).strip()],
                        "",
                        "Counterfactual experiments:",
                        *[
                            f"- {item}"
                            for item in mechanism_summary.get("counterfactual_experiments", [])
                            if str(item).strip()
                        ],
                    ]
                ).strip(),
                filename="mechanism-reasoning-summary.md",
                source_refs=[],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="research_planner",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["mechanism", "counterfactual", "competing-mechanisms"],
                validated_by=["workflow:mechanism-reasoning"],
            )

        family_lifecycle = research_state.get("hypothesis_family_lifecycle_summary", {})
        if isinstance(family_lifecycle, dict) and family_lifecycle:
            manager.save_memory(
                title=f"Hypothesis family lifecycle: {research_state.get('topic', 'research thread')}",
                summary=f"families={family_lifecycle.get('family_count', 0)}",
                kind="decision",
                scope="project",
                content="\n".join(
                    [
                        f"Family count: {family_lifecycle.get('family_count', 0)}",
                        "Retire candidates:",
                        *[f"- {item}" for item in family_lifecycle.get("retire_candidates", []) if str(item).strip()],
                        "",
                        "Revive candidates:",
                        *[f"- {item}" for item in family_lifecycle.get("revive_candidates", []) if str(item).strip()],
                    ]
                ).strip(),
                filename="hypothesis-family-lifecycle.md",
                source_refs=[],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="belief_updater",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["hypothesis-family", "lifecycle", "route-governance"],
                validated_by=["workflow:hypothesis-family-lifecycle"],
            )

        hypothesis_validation = research_state.get("hypothesis_validation_summary", {})
        if isinstance(hypothesis_validation, dict) and hypothesis_validation:
            manager.save_memory(
                title=f"Hypothesis validators: {research_state.get('topic', 'research thread')}",
                summary=f"count={hypothesis_validation.get('validation_count', 0)}",
                kind="reference",
                scope="project",
                content="\n".join(
                    [
                        f"Average novelty score: {hypothesis_validation.get('average_novelty_score', 0)}",
                        f"Average falsifiability score: {hypothesis_validation.get('average_falsifiability_score', 0)}",
                        f"Average testability score: {hypothesis_validation.get('average_testability_score', 0)}",
                        f"Average mechanistic coherence score: {hypothesis_validation.get('average_mechanistic_coherence_score', 0)}",
                        f"Average evidence grounding score: {hypothesis_validation.get('average_evidence_grounding_score', 0)}",
                        "",
                        "Low novelty hypotheses:",
                        *[f"- {item}" for item in hypothesis_validation.get("low_novelty_hypotheses", []) if str(item).strip()],
                        "",
                        "Low falsifiability hypotheses:",
                        *[f"- {item}" for item in hypothesis_validation.get("low_falsifiability_hypotheses", []) if str(item).strip()],
                        "",
                        "Weak testability hypotheses:",
                        *[f"- {item}" for item in hypothesis_validation.get("weak_testability_hypotheses", []) if str(item).strip()],
                    ]
                ).strip(),
                filename="hypothesis-validation-summary.md",
                source_refs=[],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="hypothesis_generator",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["hypothesis-validator", "novelty", "falsifiability", "testability"],
                validated_by=["workflow:hypothesis-validation"],
            )

        consensus_machine = research_state.get("consensus_state_machine", {})
        if isinstance(consensus_machine, dict) and consensus_machine:
            manager.save_memory(
                title=f"Consensus state machine: {research_state.get('topic', 'research thread')}",
                summary=str(consensus_machine.get("current_state", "forming")),
                kind="decision",
                scope="project",
                content="\n".join(
                    [
                        f"Current state: {consensus_machine.get('current_state', '')}",
                        f"Previous state: {consensus_machine.get('previous_state', '')}",
                        f"Suggested action: {consensus_machine.get('suggested_action', '')}",
                        f"Freeze recommendation: {consensus_machine.get('freeze_recommendation', False)}",
                        "",
                        "Transition triggers:",
                        *[f"- {item}" for item in consensus_machine.get("transition_triggers", []) if str(item).strip()],
                    ]
                ).strip(),
                filename="consensus-state-machine.md",
                source_refs=[],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="coordinator",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["consensus", "state-machine", str(consensus_machine.get("current_state", ""))],
                validated_by=["workflow:consensus-state-machine"],
            )

        termination = research_state.get("termination_strategy_summary", {})
        if isinstance(termination, dict) and termination:
            manager.save_memory(
                title=f"Route termination strategy: {research_state.get('topic', 'research thread')}",
                summary=str(termination.get("recommended_action", "continue")),
                kind="decision",
                scope="project",
                content="\n".join(
                    [
                        f"Recommended action: {termination.get('recommended_action', '')}",
                        f"Human confirmation required: {termination.get('human_confirmation_required', False)}",
                        "",
                        "Stop condition hits:",
                        *[
                            f"- {item}"
                            for item in termination.get("stop_condition_hits", [])
                            if str(item).strip()
                        ],
                        "",
                        "Termination condition hits:",
                        *[
                            f"- {item}"
                            for item in termination.get("termination_condition_hits", [])
                            if str(item).strip()
                        ],
                        "",
                        "Paused workstreams:",
                        *[
                            f"- {item.get('workstream', '')}: {item.get('reason', '')}"
                            for item in termination.get("paused_workstreams", [])
                            if isinstance(item, dict)
                        ],
                        "",
                        "Retired routes:",
                        *[
                            f"- {item.get('route_id', '')} [{item.get('status', '')}]: {item.get('reason', '')}"
                            for item in termination.get("retired_routes", [])
                            if isinstance(item, dict)
                        ],
                        "",
                        "Human confirmation reasons:",
                        *[
                            f"- {item}"
                            for item in termination.get("human_confirmation_reasons", [])
                            if str(item).strip()
                        ],
                    ]
                ).strip(),
                filename="route-termination-summary.md",
                source_refs=[],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="research_planner",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["termination-strategy", "route-retirement", "human-confirmation"],
                validated_by=["workflow:termination-strategy"],
            )

        failure_intelligence = research_state.get("failure_intelligence_summary", {})
        if isinstance(failure_intelligence, dict) and failure_intelligence:
            manager.save_memory(
                title=f"Failure intelligence: {research_state.get('topic', 'research thread')}",
                summary=str(failure_intelligence.get("dominant_failure_class", "mixed")),
                kind="warning",
                scope="project",
                content="\n".join(
                    [
                        f"Dominant failure class: {failure_intelligence.get('dominant_failure_class', '')}",
                        "",
                        "Technical failures:",
                        *[
                            f"- {item}"
                            for item in failure_intelligence.get("technical_failures", [])
                            if str(item).strip()
                        ],
                        "",
                        "Theoretical failures:",
                        *[
                            f"- {item}"
                            for item in failure_intelligence.get("theoretical_failures", [])
                            if str(item).strip()
                        ],
                        "",
                        "Evidence failures:",
                        *[
                            f"- {item}"
                            for item in failure_intelligence.get("evidence_failures", [])
                            if str(item).strip()
                        ],
                        "",
                        "Avoid repeat routes:",
                        *[
                            f"- {item}"
                            for item in failure_intelligence.get("avoid_repeat_routes", [])
                            if str(item).strip()
                        ],
                    ]
                ).strip(),
                filename="failure-intelligence-summary.md",
                source_refs=[],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="belief_updater",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["failure-intelligence", "negative-results", "route-avoidance"],
                validated_by=["workflow:failure-intelligence"],
            )

        experiment_economics = research_state.get("experiment_economics_summary", {})
        if isinstance(experiment_economics, dict) and experiment_economics:
            manager.save_memory(
                title=f"Experiment economics: {research_state.get('topic', 'research thread')}",
                summary=str(experiment_economics.get("cost_pressure", "medium")),
                kind="decision",
                scope="project",
                content="\n".join(
                    [
                        f"Primary discipline: {experiment_economics.get('primary_discipline', '')}",
                        f"Cost pressure: {experiment_economics.get('cost_pressure', '')}",
                        f"Time pressure: {experiment_economics.get('time_pressure', '')}",
                        f"Information gain pressure: {experiment_economics.get('information_gain_pressure', '')}",
                        "",
                        "Cheapest discriminative actions:",
                        *[
                            f"- {item}"
                            for item in experiment_economics.get("cheapest_discriminative_actions", [])
                            if str(item).strip()
                        ],
                    ]
                ).strip(),
                filename="experiment-economics-summary.md",
                source_refs=[],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="research_planner",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["experiment-economics", "information-gain", "cost-awareness"],
                validated_by=["workflow:experiment-economics"],
            )

        lab_meeting = research_state.get("lab_meeting_consensus_summary", {})
        if isinstance(lab_meeting, dict) and lab_meeting:
            manager.save_memory(
                title=f"Lab meeting consensus: {research_state.get('topic', 'research thread')}",
                summary=str(lab_meeting.get("meeting_state", "forming")),
                kind="decision",
                scope="project",
                content="\n".join(
                    [
                        f"Meeting state: {lab_meeting.get('meeting_state', '')}",
                        f"Chair recommendation: {lab_meeting.get('chair_recommendation', '')}",
                        "",
                        "Agenda items:",
                        *[
                            f"- {item}"
                            for item in lab_meeting.get("agenda_items", [])
                            if str(item).strip()
                        ],
                        "",
                        "Evidence needed to close:",
                        *[
                            f"- {item}"
                            for item in lab_meeting.get("evidence_needed_to_close", [])
                            if str(item).strip()
                        ],
                    ]
                ).strip(),
                filename="lab-meeting-consensus-summary.md",
                source_refs=[],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="lab_meeting_moderator",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["lab-meeting", "consensus", "adjudication"],
                validated_by=["workflow:lab-meeting-consensus"],
            )

        evaluation = research_state.get("evaluation_summary", {})
        if isinstance(evaluation, dict) and evaluation:
            manager.save_memory(
                title=f"Evaluation summary: {research_state.get('topic', 'research thread')}",
                summary=str(evaluation.get("benchmark_readiness", "low")),
                kind="reference",
                scope="project",
                content="\n".join(
                    [
                        f"Benchmark readiness: {evaluation.get('benchmark_readiness', '')}",
                        f"Consensus readiness: {evaluation.get('consensus_readiness', '')}",
                        f"Failure pressure: {evaluation.get('failure_pressure', '')}",
                        f"Theory maturity: {evaluation.get('theory_maturity', '')}",
                        f"Literature strength: {evaluation.get('literature_strength', '')}",
                    ]
                ).strip(),
                filename="evaluation-summary.md",
                source_refs=[],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="coordinator",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["evaluation", "benchmark-readiness", "regression-risk"],
                validated_by=["workflow:evaluation-summary"],
            )

        human_governance = research_state.get("human_governance_checkpoint_summary", {})
        if isinstance(human_governance, dict) and human_governance:
            manager.save_memory(
                title=f"Human governance checkpoints: {research_state.get('topic', 'research thread')}",
                summary=str(human_governance.get("governance_state", "clear")),
                kind="decision",
                scope="project",
                content="\n".join(
                    [
                        f"Governance state: {human_governance.get('governance_state', '')}",
                        f"Must pause execution: {human_governance.get('must_pause_execution', False)}",
                        "",
                        "Approval scope:",
                        *[
                            f"- {item}"
                            for item in human_governance.get("approval_scope", [])
                            if str(item).strip()
                        ],
                        "",
                        "Checkpoint reasons:",
                        *[
                            f"- {item}"
                            for item in human_governance.get("checkpoint_reasons", [])
                            if str(item).strip()
                        ],
                        "",
                        "Required roles:",
                        *[
                            f"- {item}"
                            for item in human_governance.get("required_roles", [])
                            if str(item).strip()
                        ],
                    ]
                ).strip(),
                filename="human-governance-checkpoints.md",
                source_refs=[],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="coordinator",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["human-governance", "approval-gate", "checkpoint"],
                validated_by=["workflow:human-governance"],
            )

        benchmark_harness = research_state.get("benchmark_harness_summary", {})
        if isinstance(benchmark_harness, dict) and benchmark_harness:
            manager.save_memory(
                title=f"Benchmark harness: {research_state.get('topic', 'research thread')}",
                summary=str(benchmark_harness.get("release_readiness", "low")),
                kind="reference",
                scope="project",
                content="\n".join(
                    [
                        f"Benchmark ready: {benchmark_harness.get('benchmark_ready', False)}",
                        f"Release readiness: {benchmark_harness.get('release_readiness', '')}",
                        f"Evidence gate: {benchmark_harness.get('evidence_gate', '')}",
                        f"Reproducibility gate: {benchmark_harness.get('reproducibility_gate', '')}",
                        f"Governance gate: {benchmark_harness.get('governance_gate', '')}",
                        "",
                        "Benchmark gaps:",
                        *[
                            f"- {item}"
                            for item in benchmark_harness.get("benchmark_gaps", [])
                            if str(item).strip()
                        ],
                        "",
                        "Regression checks:",
                        *[
                            f"- {item}"
                            for item in benchmark_harness.get("regression_checks", [])
                            if str(item).strip()
                        ],
                        "",
                        "Fail-fast checks:",
                        *[
                            f"- {item}"
                            for item in benchmark_harness.get("fail_fast_checks", [])
                            if str(item).strip()
                        ],
                    ]
                ).strip(),
                filename="benchmark-harness-summary.md",
                source_refs=[],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="coordinator",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["benchmark-harness", "regression", "release-readiness"],
                validated_by=["workflow:benchmark-harness"],
            )

        evaluation_harness = research_state.get("kaivu_evaluation_harness_summary", {})
        if isinstance(evaluation_harness, dict) and evaluation_harness:
            manager.save_memory(
                title=f"Kaivu evaluation harness: {research_state.get('topic', 'research thread')}",
                summary=(
                    f"score={evaluation_harness.get('overall_score', 0)}; "
                    f"state={evaluation_harness.get('release_state', '')}"
                ),
                kind="reference",
                scope="project",
                content="\n".join(
                    [
                        f"Harness id: {evaluation_harness.get('harness_id', '')}",
                        f"Overall score: {evaluation_harness.get('overall_score', 0)}",
                        f"Release state: {evaluation_harness.get('release_state', '')}",
                        f"Blocking gate count: {evaluation_harness.get('blocking_gate_count', 0)}",
                        "",
                        "Axes:",
                        *[
                            "- "
                            + str(axis.get("axis_id", "")).strip()
                            + " | score="
                            + str(axis.get("score", 0))
                            + " | state="
                            + str(axis.get("state", "")).strip()
                            for axis in evaluation_harness.get("axes", [])
                            if isinstance(axis, dict)
                        ],
                        "",
                        "Blocking gates:",
                        *[
                            f"- {item}"
                            for item in evaluation_harness.get("blocking_gates", [])
                            if str(item).strip()
                        ],
                        "",
                        "Regression suite:",
                        *[
                            f"- {item}"
                            for item in evaluation_harness.get("regression_suite", [])
                            if str(item).strip()
                        ],
                        "",
                        "Fail-fast checks:",
                        *[
                            f"- {item}"
                            for item in evaluation_harness.get("fail_fast_checks", [])
                            if str(item).strip()
                        ],
                    ]
                ).strip(),
                filename="kaivu-evaluation-harness.md",
                source_refs=[
                    str(axis.get("axis_id", "")).strip()
                    for axis in evaluation_harness.get("axes", [])
                    if isinstance(axis, dict) and str(axis.get("axis_id", "")).strip()
                ],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="coordinator",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["kaivu-evaluation", "regression-suite", "release-gate"],
                validated_by=["workflow:kaivu-evaluation-harness"],
            )

        typed_graph = research_state.get("typed_research_graph_summary", {})
        if isinstance(typed_graph, dict) and typed_graph:
            manager.save_memory(
                title=f"Typed research graph: {research_state.get('topic', 'research thread')}",
                summary=f"nodes={typed_graph.get('node_count', 0)} edges={typed_graph.get('edge_count', 0)}",
                kind="reference",
                scope="project",
                content="\n".join(
                    [
                        f"Snapshot id: {typed_graph.get('snapshot_id', '')}",
                        f"Project id: {typed_graph.get('project_id', '')}",
                        f"Node count: {typed_graph.get('node_count', 0)}",
                        f"Edge count: {typed_graph.get('edge_count', 0)}",
                        f"Fact count: {typed_graph.get('fact_count', 0)}",
                        f"Source of truth: {typed_graph.get('source_of_truth', '')}",
                        f"Replay summary: {json.dumps(typed_graph.get('replay_summary', {}), ensure_ascii=False)}",
                    ]
                ).strip(),
                filename="typed-research-graph-summary.md",
                source_refs=[],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="coordinator",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                tags=["typed-graph", "research-graph", "knowledge-graph"],
                validated_by=["workflow:typed-research-graph"],
            )

    def _sync_agent_stance_memories(self, research_state: dict[str, Any]) -> None:
        stance_summary = research_state.get("agent_stance_continuity_summary", {})
        if not isinstance(stance_summary, dict) or not stance_summary.get("records"):
            return
        manager = self.subagent_runtime.memory_manager
        user_id = str(self.collaboration_context.get("user_id", ""))
        project_id = str(self.collaboration_context.get("project_id", ""))
        group_id = str(self.collaboration_context.get("group_id", ""))
        topic = str(research_state.get("topic", "research thread"))
        records = stance_summary.get("records", []) if isinstance(stance_summary.get("records", []), list) else []
        for record in records[:20]:
            if not isinstance(record, dict):
                continue
            agent = str(record.get("agent", "")).strip()
            if not agent:
                continue
            safe_agent = self._slugify_text(agent)
            content = "\n".join(
                [
                    f"Agent: {agent}",
                    f"Topic: {topic}",
                    f"Current position: {record.get('current_position', '')}",
                    f"Stance label: {record.get('stance_label', '')}",
                    f"Previous position: {record.get('previous_position', '')}",
                    f"Previous stance label: {record.get('previous_stance_label', '')}",
                    f"Continuity state: {record.get('continuity_state', '')}",
                    f"Change type: {record.get('change_type', '')}",
                    f"Change reason: {record.get('change_reason', '')}",
                    "",
                    "Evidence refs:",
                    *([
                        f"- {item}"
                        for item in record.get("evidence_refs", [])
                        if str(item).strip()
                    ] if isinstance(record.get("evidence_refs", []), list) else []),
                    "",
                    "Open questions:",
                    *([
                        f"- {item}"
                        for item in record.get("open_questions", [])
                        if str(item).strip()
                    ] if isinstance(record.get("open_questions", []), list) else []),
                    "",
                    "Blocking concerns:",
                    *([
                        f"- {item}"
                        for item in record.get("blocking_concerns", [])
                        if str(item).strip()
                    ] if isinstance(record.get("blocking_concerns", []), list) else []),
                ]
            ).strip()
            manager.save_memory(
                title=f"Agent stance memory: {agent}",
                summary=(
                    f"{record.get('continuity_state', '')}; "
                    f"{record.get('stance_label', '')}; "
                    f"{record.get('change_type', '')}"
                ),
                kind="decision",
                scope="agent",
                content=content,
                filename=f"stance-{safe_agent}-{self._slugify_text(topic)}.md",
                source_refs=[
                    str(item).strip()
                    for item in record.get("evidence_refs", [])
                    if str(item).strip()
                ] if isinstance(record.get("evidence_refs", []), list) else [],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent=agent,
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="private",
                promotion_status="personal",
                tags=["agent-stance", "role-memory", "stance-continuity", safe_agent],
                validated_by=["workflow:agent-stance-continuity"],
            )
        manager.save_memory(
            title=f"Multi-agent stance continuity: {topic}",
            summary=(
                f"agents={stance_summary.get('agent_count', 0)}; "
                f"changed={stance_summary.get('changed_count', 0)}; "
                f"state={stance_summary.get('role_memory_state', '')}"
            ),
            kind="decision",
            scope="project",
            content="\n".join(
                [
                    f"Role memory state: {stance_summary.get('role_memory_state', '')}",
                    f"Continuity ready: {stance_summary.get('continuity_ready', False)}",
                    f"Changed count: {stance_summary.get('changed_count', 0)}",
                    f"Missing change reason count: {stance_summary.get('missing_change_reason_count', 0)}",
                    "",
                    "Role memory updates:",
                    *[
                        "- "
                        + str(item.get("agent", "")).strip()
                        + " | "
                        + str(item.get("continuity_state", "")).strip()
                        + " | "
                        + str(item.get("change_type", "")).strip()
                        + " | "
                        + str(item.get("current_position", "")).strip()
                        for item in stance_summary.get("role_memory_updates", [])
                        if isinstance(item, dict)
                    ],
                    "",
                    "Standing objections:",
                    *[
                        f"- {item}"
                        for item in stance_summary.get("standing_objections", [])
                        if str(item).strip()
                    ],
                ]
            ).strip(),
            filename=f"multi-agent-stance-continuity-{self._slugify_text(topic)}.md",
            source_refs=[],
            evidence_level="medium",
            confidence="medium",
            status="active",
            owner_agent="lab_meeting_moderator",
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            visibility="project",
            promotion_status="project",
            tags=["multi-agent", "role-memory", "stance-continuity", "lab-meeting"],
            validated_by=["workflow:agent-stance-continuity"],
        )

    def _sync_graph_memory_distill(self, research_state: dict[str, Any]) -> None:
        project_id = str(self.collaboration_context.get("project_id", "")).strip()
        if not project_id:
            return
        graph_summary = research_state.get("typed_research_graph_summary", {})
        graph_history = research_state.get("typed_research_graph_history", {})
        graph_refs = research_state.get("graph_reference_summary", {})
        route_temperature = research_state.get("route_temperature_summary", {})
        graph_learning = research_state.get("graph_learning_summary", {})
        if not isinstance(graph_summary, dict) or not graph_summary:
            return
        manager = self.subagent_runtime.memory_manager
        user_id = str(self.collaboration_context.get("user_id", ""))
        group_id = str(self.collaboration_context.get("group_id", ""))
        body = "\n".join(
            [
                f"Topic: {research_state.get('topic', '')}",
                f"Snapshot id: {graph_summary.get('snapshot_id', '')}",
                f"Node count: {graph_summary.get('node_count', 0)}",
                f"Edge count: {graph_summary.get('edge_count', 0)}",
                f"Fact count: {graph_summary.get('fact_count', 0)}",
                f"Source of truth: {graph_summary.get('source_of_truth', '')}",
                f"Replay summary: {json.dumps(graph_summary.get('replay_summary', {}), ensure_ascii=False)}",
                f"Historical snapshots: {graph_history.get('snapshot_count', 0)}",
                f"Challenged hypotheses: {graph_history.get('challenged_hypothesis_count', 0)}",
                f"Specialist reference nodes: {graph_history.get('specialist_reference_count', 0)}",
                f"Consulted edges: {graph_history.get('consulted_edge_count', 0)}",
                f"Route temperature: {route_temperature.get('global_temperature', 'cool')}",
                f"Learning signal strength: {graph_learning.get('learning_signal_strength', 'low')}",
                "",
                "Frequently referenced nodes:",
                *[f"- {item}" for item in graph_refs.get("node_refs", [])[:12] if str(item).strip()],
                "",
                "Frequently referenced edges:",
                *[f"- {item}" for item in graph_refs.get("edge_refs", [])[:12] if str(item).strip()],
            ]
        ).strip()
        manager.save_memory(
            title=f"Typed graph distill: {research_state.get('topic', 'research thread')}",
            summary=f"nodes={graph_summary.get('node_count', 0)} edges={graph_summary.get('edge_count', 0)} refs={graph_refs.get('node_ref_count', 0)}",
            kind="reference",
            scope="project",
            content=body,
            filename="typed-graph-distill.md",
            source_refs=[],
            evidence_level="medium",
            confidence="medium",
            status="active",
            owner_agent="coordinator",
            user_id=user_id,
            project_id=project_id,
            group_id=group_id,
            visibility="project",
            promotion_status="project",
            tags=["typed-graph", "graph-distill", "graph-references"],
            validated_by=["workflow:typed-graph-distill"],
        )

    def _sync_executor_backpropagation_memory(
        self,
        *,
        topic: str,
        backpropagation_record: dict[str, Any],
    ) -> None:
        project_id = str(self.collaboration_context.get("project_id", "")).strip()
        if not project_id:
            return
        manager = self.subagent_runtime.memory_manager
        for item in build_backpropagation_memory_items(
            backpropagation_record=backpropagation_record,
            topic=topic,
            project_id=project_id,
            user_id=str(self.collaboration_context.get("user_id", "")),
            group_id=str(self.collaboration_context.get("group_id", "")),
        ):
            if not isinstance(item, dict):
                continue
            manager.save_memory(
                title=str(item.get("title", "Experiment backpropagation")),
                summary=str(item.get("summary", "Experiment backpropagation update")),
                kind=item.get("kind", "reference"),
                scope=item.get("scope", "project"),
                content=str(item.get("content", "")),
                filename=str(item.get("filename", "")).strip() or None,
                tags=[
                    str(tag).strip()
                    for tag in item.get("tags", [])
                    if str(tag).strip()
                ] if isinstance(item.get("tags", []), list) else [],
                source_refs=[
                    str(ref).strip()
                    for ref in item.get("source_refs", [])
                    if str(ref).strip()
                ] if isinstance(item.get("source_refs", []), list) else [],
                evidence_level=item.get("evidence_level", "medium"),
                confidence=item.get("confidence", "medium"),
                status=item.get("status", "active"),
                owner_agent=str(item.get("owner_agent", "run_manager")),
                user_id=str(item.get("user_id", "")),
                project_id=project_id,
                group_id=str(item.get("group_id", "")),
                visibility=item.get("visibility", "project"),
                promotion_status=item.get("promotion_status", "project"),
                validated_by=[
                    str(value).strip()
                    for value in item.get("validated_by", [])
                    if str(value).strip()
                ] if isinstance(item.get("validated_by", []), list) else ["workflow:executor-backpropagation"],
            )

    def _sync_literature_workspace(
        self,
        topic: str,
        steps: list[WorkflowStepResult],
        research_state: dict[str, Any],
    ) -> None:
        root = self.cwd / "literature"
        wiki_root = root / "wiki"
        papers_dir = wiki_root / "papers"
        claims_dir = wiki_root / "claims"
        concepts_dir = wiki_root / "concepts"
        mechanisms_dir = wiki_root / "mechanisms"
        controversies_dir = wiki_root / "controversies"
        methods_dir = wiki_root / "methods"
        datasets_dir = wiki_root / "datasets"
        reviews_dir = wiki_root / "reviews"
        review_records_dir = root / "review_records"
        screening_dir = review_records_dir / "screening"
        evidence_tables_dir = review_records_dir / "evidence_tables"
        exclusion_dir = review_records_dir / "exclusion_records"
        protocols_dir = review_records_dir / "protocols"
        exports_dir = root / "exports"

        for directory in [
            papers_dir,
            claims_dir,
            concepts_dir,
            mechanisms_dir,
            controversies_dir,
            methods_dir,
            datasets_dir,
            reviews_dir,
            screening_dir,
            evidence_tables_dir,
            exclusion_dir,
            protocols_dir,
            exports_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)

        topic_slug = self._slugify_text(topic) or "research-topic"
        citations = self._collect_citations(steps)
        literature_step = next((step for step in steps if step.profile_name == "literature_reviewer"), None)
        literature_payload = literature_step.parsed_output if literature_step else {}
        literature_synthesis = (
            research_state.get("literature_synthesis", {})
            if isinstance(research_state.get("literature_synthesis", {}), dict)
            else {}
        )
        systematic_review = (
            research_state.get("systematic_review_summary", {})
            if isinstance(research_state.get("systematic_review_summary", {}), dict)
            else {}
        )
        representative_sources = (
            literature_payload.get("representative_sources", [])
            if isinstance(literature_payload.get("representative_sources", []), list)
            else []
        )
        evidence_gaps = (
            literature_payload.get("evidence_gaps", [])
            if isinstance(literature_payload.get("evidence_gaps", []), list)
            else []
        )
        claims = literature_payload.get("claims", []) if isinstance(literature_payload.get("claims", []), list) else []
        evidence_records = (
            literature_payload.get("evidence", [])
            if isinstance(literature_payload.get("evidence", []), list)
            else []
        )
        open_questions = (
            research_state.get("open_questions", [])
            if isinstance(research_state.get("open_questions", []), list)
            else []
        )
        contested_questions = (
            literature_synthesis.get("contested_questions", [])
            if isinstance(literature_synthesis.get("contested_questions", []), list)
            else []
        )

        for citation in citations:
            if not isinstance(citation, dict):
                continue
            title = str(citation.get("title", "")).strip()
            if not title:
                continue
            paper_slug = self._slugify_text(title) or "paper"
            doi = str(citation.get("doi", "")).strip()
            pmid = str(citation.get("pmid", "")).strip()
            arxiv_id = str(citation.get("arxiv_id", "")).strip()
            page_path = papers_dir / f"{paper_slug}.md"
            quoted_title = title.replace('"', '\\"')
            frontmatter = [
                "---",
                f'title: "{quoted_title}"',
                "kind: paper",
                f'source_id: "{doi or pmid or arxiv_id or paper_slug}"',
                f'doi: "{doi}"',
                f'pmid: "{pmid}"',
                f'arxiv_id: "{arxiv_id}"',
                f'year: "{str(citation.get("published", "")).strip()[:4]}"',
                f'study_type: "{str(citation.get("source_type", "")).strip()}"',
                'status: "active"',
                "---",
                "",
            ]
            body = [
                "# Summary",
                "",
                f"- {str(citation.get('summary', '')).strip() or str(citation.get('abstract', '')).strip() or 'Summary pending.'}",
                "",
                "# Main Claims",
                "",
                "- See linked review and mechanism pages.",
                "",
                "# Evidence",
                "",
                f"- Source type: {str(citation.get('source_type', '')).strip() or 'unknown'}",
                f"- Journal: {str(citation.get('journal', '')).strip() or 'unknown'}",
                f"- Authors: {', '.join(str(item).strip() for item in citation.get('authors', []) if str(item).strip()) or 'unknown'}",
                "",
                "# Methods",
                "",
                "- See original source for details.",
                "",
                "# Limitations",
                "",
                "- Auto-generated source page; may need manual refinement.",
                "",
                "# Conflicts Or Contradictions",
                "",
                "- Check controversy pages linked from topic review.",
                "",
                "# Relevance To Current Hypotheses",
                "",
                "- Referenced by the current topic review.",
                "",
                "# Linked Concepts",
                "",
                f"- [[reviews/review-{topic_slug}.md]]",
                "",
                "# Linked Mechanisms",
                "",
                "- [[ ]]",
            ]
            page_path.write_text("\n".join(frontmatter + body).strip() + "\n", encoding="utf-8")

        claim_records = [item for item in claims if isinstance(item, dict)]
        for index, item in enumerate(claim_records[:30], start=1):
            statement = str(item.get("statement", "") or item.get("claim", "") or item.get("title", "")).strip()
            if not statement:
                continue
            claim_id = str(item.get("claim_id", "") or item.get("id", "") or f"claim-{index}").strip()
            claim_slug = self._slugify_text(claim_id or statement[:80]) or f"claim-{index}"
            claim_path = claims_dir / f"{claim_slug}.md"
            linked_evidence = [
                evidence
                for evidence in evidence_records
                if isinstance(evidence, dict)
                and (
                    str(evidence.get("claim_id", "")).strip() == claim_id
                    or statement.lower()[:40] in str(evidence).lower()
                )
            ]
            claim_path.write_text(
                "\n".join(
                    [
                        "---",
                        f'title: "{statement[:120].replace(chr(34), chr(92) + chr(34))}"',
                        'kind: "claim"',
                        f'claim_id: "{claim_id.replace(chr(34), chr(92) + chr(34))}"',
                        'status: "active"',
                        "---",
                        "",
                        "# Claim",
                        "",
                        f"- {statement}",
                        "",
                        "# Supporting Evidence",
                        "",
                        *[
                            f"- {str(evidence.get('statement', '') or evidence.get('summary', '') or evidence)[:300]}"
                            for evidence in linked_evidence[:10]
                        ],
                        *([] if linked_evidence else ["- Evidence link pending."]),
                        "",
                        "# Challenging Evidence",
                        "",
                        *[f"- {item}" for item in contested_questions[:8] if str(item).strip()],
                        *([] if contested_questions else ["- No explicit contradiction recorded yet."]),
                        "",
                        "# Evidence Grade",
                        "",
                        f"- {str(item.get('evidence_grade', '') or item.get('confidence', '') or 'ungraded')}",
                        "",
                        "# Provenance",
                        "",
                        f"- [[reviews/review-{topic_slug}.md]]",
                    ]
                ).strip()
                + "\n",
                encoding="utf-8",
            )

        concept_terms = self._derive_literature_concepts(
            topic=topic,
            representative_sources=representative_sources,
            claims=claims,
            evidence_records=evidence_records,
            contested_questions=(
                literature_synthesis.get("contested_questions", [])
                if isinstance(literature_synthesis.get("contested_questions", []), list)
                else []
            ),
        )
        for concept in concept_terms:
            concept_slug = self._slugify_text(concept) or "concept"
            concept_path = concepts_dir / f"{concept_slug}.md"
            quoted_concept = concept.replace('"', '\\"')
            concept_path.write_text(
                "\n".join(
                    [
                        "---",
                        f'title: "{quoted_concept}"',
                        'kind: "concept"',
                        'status: "active"',
                        "---",
                        "",
                        "# Definition",
                        "",
                        f"- Working concept linked to {topic}.",
                        "",
                        "# Why It Matters",
                        "",
                        "- This concept recurs in the current literature synthesis and should stay linked.",
                        "",
                        "# Supporting Sources",
                        "",
                        *[f"- {item}" for item in representative_sources[:6] if str(item).strip()],
                        "",
                        "# Challenging Sources",
                        "",
                        *[
                            f"- {item}"
                            for item in literature_synthesis.get("contested_questions", [])
                            if str(item).strip()
                        ][:6],
                        "",
                        "# Open Questions",
                        "",
                        *[f"- {item}" for item in open_questions[:6] if str(item).strip()],
                        "",
                        "# Linked Hypotheses",
                        "",
                        *[
                            f"- {item.get('name') or item.get('hypothesis_id')}"
                            for item in research_state.get("hypothesis_tree_summary", {}).get("nodes", [])
                            if isinstance(item, dict) and (item.get("name") or item.get("hypothesis_id"))
                        ][:8],
                    ]
                ).strip()
                + "\n",
                encoding="utf-8",
            )

        mechanism_records: list[dict[str, Any]] = []
        for step in steps:
            payload = step.parsed_output.get("mechanism_map", [])
            if isinstance(payload, list):
                mechanism_records.extend(item for item in payload if isinstance(item, dict))
        for item in mechanism_records:
            label = str(item.get("label", "")).strip() or str(item.get("mechanism_id", "")).strip()
            if not label:
                continue
            mechanism_slug = self._slugify_text(label) or "mechanism"
            mechanism_path = mechanisms_dir / f"{mechanism_slug}.md"
            quoted_label = label.replace('"', '\\"')
            mechanism_path.write_text(
                "\n".join(
                    [
                        "---",
                        f'title: "{quoted_label}"',
                        'kind: "mechanism"',
                        f'status: "{str(item.get("status", "active")).strip()}"',
                        "---",
                        "",
                        "# Mechanism Summary",
                        "",
                        f"- Family: {str(item.get('family', '')).strip() or 'general'}",
                        "",
                        "# Supporting Evidence",
                        "",
                        *[f"- {ref}" for ref in item.get("evidence_ref_ids", []) if str(ref).strip()],
                        "",
                        "# Challenging Evidence",
                        "",
                        *[f"- {signal}" for signal in item.get("challenge_signals", []) if str(signal).strip()],
                        "",
                        "# Competing Mechanisms",
                        "",
                        *[f"- {rival}" for rival in item.get("competes_with", []) if str(rival).strip()],
                        "",
                        "# Counterfactual Expectations",
                        "",
                        *[f"- {value}" for value in item.get("revive_conditions", []) if str(value).strip()],
                        "",
                        "# Linked Hypotheses",
                        "",
                        *[
                            f"- {value}"
                            for value in item.get("supports_hypothesis_ids", [])
                            if str(value).strip()
                        ],
                        "",
                        "# Linked Experiments",
                        "",
                        f"- [[reviews/review-{topic_slug}.md]]",
                    ]
                ).strip()
                + "\n",
                encoding="utf-8",
            )

        if contested_questions:
            controversy_path = controversies_dir / f"controversy-{topic_slug}.md"
            quoted_topic = topic.replace('"', '\\"')
            controversy_path.write_text(
                "\n".join(
                    [
                        "---",
                        f'title: "{quoted_topic} controversy"',
                        'kind: "controversy"',
                        'status: "open"',
                        "---",
                        "",
                        "# Question",
                        "",
                        f"- {topic}",
                        "",
                        "# Position A",
                        "",
                        "- Emerging support in current literature.",
                        "",
                        "# Position B",
                        "",
                        "- Open challenge or competing interpretation remains.",
                        "",
                        "# Key Evidence",
                        "",
                        *[f"- {item}" for item in representative_sources if str(item).strip()],
                        "",
                        "# What Would Resolve This",
                        "",
                        *[f"- {item}" for item in evidence_gaps if str(item).strip()],
                        "",
                        "# Current Assessment",
                        "",
                        *[f"- {item}" for item in contested_questions if str(item).strip()],
                    ]
                ).strip()
                + "\n",
                encoding="utf-8",
            )

        contradiction_ledger_path = wiki_root / "contradiction-ledger.md"
        contradiction_lines = [
            "# Contradiction Ledger",
            "",
            "This file tracks literature conflicts as first-class review objects.",
            "",
            f"## {topic}",
            "",
        ]
        if contested_questions:
            contradiction_lines.extend(
                [
                    f"- Conflict: {item}",
                    f"  - Resolution target: [[reviews/review-{topic_slug}.md]]",
                    "  - Required action: screen source quality, mechanism compatibility, and experimental boundary conditions.",
                ]
                for item in contested_questions
                if str(item).strip()
            )
        else:
            contradiction_lines.append("- No explicit contradiction recorded for this topic yet.")
        contradiction_ledger_path.write_text(
            "\n".join(
                line
                for block in contradiction_lines
                for line in (block if isinstance(block, list) else [block])
            ).strip()
            + "\n",
            encoding="utf-8",
        )

        quoted_topic = topic.replace('"', '\\"')
        review_path = reviews_dir / f"review-{topic_slug}.md"
        review_path.write_text(
            "\n".join(
                [
                    "---",
                    f'title: "{quoted_topic}"',
                    'kind: "review"',
                    f'review_protocol_version: "{str(systematic_review.get("review_protocol_version", "")).strip()}"',
                    'status: "draft"',
                    "---",
                    "",
                    "# Review Question",
                    "",
                    f"- {str(systematic_review.get('review_question', '')).strip() or topic}",
                    "",
                    "# Scope",
                    "",
                    *[f"- {item}" for item in systematic_review.get("study_type_hierarchy", []) if str(item).strip()],
                    "",
                    "# Included Evidence",
                    "",
                    *[f"- {item}" for item in representative_sources if str(item).strip()],
                    "",
                    "# Main Synthesis",
                    "",
                    *[f"- {item}" for item in literature_synthesis.get("consensus_findings", []) if str(item).strip()],
                    "",
                    "# Contradictions",
                    "",
                    *[f"- {item}" for item in contested_questions if str(item).strip()],
                    "",
                    "# Evidence Gaps",
                    "",
                    *[f"- {item}" for item in evidence_gaps if str(item).strip()],
                    "",
                    "# Implications For Hypotheses",
                    "",
                    *[f"- {item}" for item in research_state.get("open_questions", []) if str(item).strip()],
                ]
            ).strip()
            + "\n",
            encoding="utf-8",
        )

        protocol_path = protocols_dir / f"review-protocol-{topic_slug}.md"
        protocol_path.write_text(
            "\n".join(
                [
                    f"# Review Protocol | {topic}",
                    "",
                    f"- Version: {str(systematic_review.get('review_protocol_version', '')).strip() or 'draft'}",
                    "",
                    "## Inclusion Logic",
                    "",
                    *[f"- {item}" for item in systematic_review.get("inclusion_logic", []) if str(item).strip()],
                    "",
                    "## Exclusion Logic",
                    "",
                    *[f"- {item}" for item in systematic_review.get("exclusion_logic", []) if str(item).strip()],
                    "",
                    "## Review Protocol Gaps",
                    "",
                    *[f"- {item}" for item in systematic_review.get("review_protocol_gaps", []) if str(item).strip()],
                ]
            ).strip()
            + "\n",
            encoding="utf-8",
        )

        screening_path = screening_dir / f"screening-{topic_slug}.md"
        screening_path.write_text(
            "\n".join(
                [
                    f"# Screening Records | {topic}",
                    "",
                    *[f"- {item}" for item in systematic_review.get("screening_records", []) if str(item).strip()],
                    "",
                    "## Screening Decisions",
                    "",
                    *[f"- {item}" for item in systematic_review.get("screening_decisions", []) if str(item).strip()],
                    "",
                    "## Exclusion Reasons",
                    "",
                    *[f"- {item}" for item in systematic_review.get("exclusion_reasons", []) if str(item).strip()],
                ]
            ).strip()
            + "\n",
            encoding="utf-8",
        )

        evidence_table_path = evidence_tables_dir / f"evidence-table-{topic_slug}.md"
        evidence_table_path.write_text(
            "\n".join(
                [
                    f"# Evidence Table Records | {topic}",
                    "",
                    *[f"- {item}" for item in systematic_review.get("evidence_table_records", []) if str(item).strip()],
                ]
            ).strip()
            + "\n",
            encoding="utf-8",
        )

        exclusion_path = exclusion_dir / f"exclusion-records-{topic_slug}.md"
        exclusion_path.write_text(
            "\n".join(
                [
                    f"# Exclusion Records | {topic}",
                    "",
                    *[f"- {item}" for item in systematic_review.get("exclusion_reasons", []) if str(item).strip()],
                ]
            ).strip()
            + "\n",
            encoding="utf-8",
        )

        review_matrix_path = exports_dir / f"systematic-review-matrix-{topic_slug}.md"
        review_matrix_path.write_text(
            "\n".join(
                [
                    f"# Systematic Review Matrix | {topic}",
                    "",
                    "| Object | Count | Notes |",
                    "| --- | ---: | --- |",
                    f"| citations | {len(citations)} | paper/source pages generated |",
                    f"| claims | {len(claim_records)} | claim pages generated |",
                    f"| evidence records | {len(evidence_records)} | evidence table source rows |",
                    f"| contradictions | {len(contested_questions)} | see contradiction ledger |",
                    f"| evidence gaps | {len(evidence_gaps)} | scheduler should consider evidence repair |",
                    "",
                    "## Review Protocol State",
                    "",
                    f"- Version: {str(systematic_review.get('review_protocol_version', '')).strip() or 'draft'}",
                    f"- Screened evidence count: {systematic_review.get('screened_evidence_count', 0)}",
                    f"- Protocol gaps: {len(systematic_review.get('review_protocol_gaps', []) if isinstance(systematic_review.get('review_protocol_gaps', []), list) else [])}",
                ]
            ).strip()
            + "\n",
            encoding="utf-8",
        )

        query_filing_path = reviews_dir / f"analysis-{topic_slug}.md"
        query_filing_path.write_text(
            "\n".join(
                [
                    "---",
                    f'title: "Analysis for {quoted_topic}"',
                    'kind: "review"',
                    'status: "filed"',
                    "---",
                    "",
                    "# Filed Analysis",
                    "",
                    f"- Topic: {topic}",
                    "",
                    "# Consensus Findings",
                    "",
                    *[f"- {item}" for item in literature_synthesis.get("consensus_findings", []) if str(item).strip()],
                    "",
                    "# Contested Questions",
                    "",
                    *[f"- {item}" for item in contested_questions if str(item).strip()],
                    "",
                    "# Evidence Gaps",
                    "",
                    *[f"- {item}" for item in evidence_gaps if str(item).strip()],
                ]
            ).strip()
            + "\n",
            encoding="utf-8",
        )

        lint_findings = self._lint_literature_workspace(root)
        lint_path = wiki_root / "lint.md"
        lint_path.write_text(
            "\n".join(
                [
                    "# Literature Lint",
                    "",
                    *([f"- {item}" for item in lint_findings] if lint_findings else ["- No major issues detected."]),
                ]
            ).strip()
            + "\n",
            encoding="utf-8",
        )

        policy_path = root / "INGEST_POLICY.md"
        if not policy_path.exists():
            policy_path.write_text(
                "\n".join(
                    [
                        "# Literature Ingest Policy",
                        "",
                        "- Papers go to `raw_sources/papers/` and should produce paper pages.",
                        "- Reports go to `raw_sources/reports/` and should be marked as report-style evidence.",
                        "- Web articles go to `raw_sources/web/` and should be downweighted unless they provide primary evidence.",
                        "- Dataset cards and benchmark notes should update `wiki/datasets/`.",
                        "- Each ingest updates `wiki/index.md` and `wiki/log.md`.",
                        "- Contradictions should update controversy or mechanism pages instead of being buried in summaries.",
                    ]
                ).strip()
                + "\n",
                encoding="utf-8",
            )

        self._sync_literature_pages_to_graph(
            topic=topic,
            citations=citations,
            concept_terms=concept_terms,
            mechanism_records=mechanism_records,
            contested_questions=contested_questions,
        )
        self._rewrite_literature_index(root)
        self._append_literature_log(root, topic, len(citations), len(contested_questions), len(mechanism_records))

    def _rewrite_literature_index(self, root: Path) -> None:
        wiki_root = root / "wiki"
        sections = [
            ("Papers", wiki_root / "papers"),
            ("Claims", wiki_root / "claims"),
            ("Concepts", wiki_root / "concepts"),
            ("Mechanisms", wiki_root / "mechanisms"),
            ("Controversies", wiki_root / "controversies"),
            ("Methods", wiki_root / "methods"),
            ("Datasets", wiki_root / "datasets"),
            ("Reviews", wiki_root / "reviews"),
        ]
        lines = ["# Literature Index", "", "This file is the content-oriented entry point to the literature wiki.", ""]
        for heading, directory in sections:
            lines.append(f"## {heading}")
            lines.append("")
            entries = [path for path in sorted(directory.glob("*.md")) if path.name.upper() != "TEMPLATE.MD"]
            if not entries:
                lines.append("- None yet.")
                lines.append("")
                continue
            for path in entries:
                relative = path.relative_to(wiki_root).as_posix()
                title = self._extract_markdown_title(path) or path.stem
                summary = self._extract_markdown_summary(path)
                line = f"- [[{relative}]]"
                if title:
                    line += f" - {title}"
                if summary:
                    line += f" | {summary}"
                lines.append(line)
            lines.append("")
        (wiki_root / "index.md").write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    def _append_literature_log(
        self,
        root: Path,
        topic: str,
        citation_count: int,
        controversy_count: int,
        mechanism_count: int,
    ) -> None:
        log_path = root / "wiki" / "log.md"
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        entry = "\n".join(
            [
                "",
                f"## [{timestamp}] ingest | {topic}",
                "",
                f"- Updated paper pages: {citation_count}",
                f"- Updated mechanism pages: {mechanism_count}",
                f"- Updated controversy pages: {controversy_count}",
                "- Updated review pages, review records, and index.",
            ]
        )
        existing = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Literature Log\n"
        log_path.write_text(existing.rstrip() + entry + "\n", encoding="utf-8")

    @staticmethod
    def _derive_literature_concepts(
        *,
        topic: str,
        representative_sources: list[Any],
        claims: list[Any],
        evidence_records: list[Any],
        contested_questions: list[Any],
    ) -> list[str]:
        terms: list[str] = []
        text_blobs: list[str] = [topic]
        text_blobs.extend(str(item) for item in representative_sources if str(item).strip())
        for item in claims:
            if isinstance(item, dict):
                text_blobs.append(str(item.get("statement", "")))
                text_blobs.append(str(item.get("title", "")))
        for item in evidence_records:
            if isinstance(item, dict):
                text_blobs.append(str(item.get("statement", "")))
                text_blobs.append(str(item.get("study_type", "")))
                text_blobs.append(str(item.get("model_system", "")))
        text_blobs.extend(str(item) for item in contested_questions if str(item).strip())

        seen: set[str] = set()
        stopwords = {
            "the", "and", "for", "with", "from", "that", "this", "into", "using", "does", "support",
            "current", "literature", "question", "review", "study", "studies", "result", "results",
            "mechanism", "hypothesis", "evidence", "paper", "topic", "analysis", "summary",
        }
        for blob in text_blobs:
            for token in str(blob).replace("/", " ").replace("-", " ").split():
                cleaned = "".join(ch for ch in token.lower() if ch.isalnum())
                if len(cleaned) < 5 or cleaned in stopwords or cleaned in seen:
                    continue
                seen.add(cleaned)
                terms.append(cleaned)
                if len(terms) >= 10:
                    return terms
        return terms

    def _lint_literature_workspace(self, root: Path) -> list[str]:
        wiki_root = root / "wiki"
        findings: list[str] = []
        review_pages = [p for p in (wiki_root / "reviews").glob("*.md") if p.name.upper() != "TEMPLATE.MD"]
        concept_pages = [p for p in (wiki_root / "concepts").glob("*.md") if p.name.upper() != "TEMPLATE.MD"]
        mechanism_pages = [p for p in (wiki_root / "mechanisms").glob("*.md") if p.name.upper() != "TEMPLATE.MD"]
        controversy_pages = [p for p in (wiki_root / "controversies").glob("*.md") if p.name.upper() != "TEMPLATE.MD"]

        if not review_pages:
            findings.append("No review pages found.")
        if not concept_pages:
            findings.append("No concept pages found.")
        if not mechanism_pages:
            findings.append("No mechanism pages found.")
        if not controversy_pages:
            findings.append("No controversy pages found.")

        index_text = (wiki_root / "index.md").read_text(encoding="utf-8") if (wiki_root / "index.md").exists() else ""
        for page in concept_pages + mechanism_pages + review_pages:
            relative = page.relative_to(wiki_root).as_posix()
            if relative not in index_text:
                findings.append(f"Index missing page link: {relative}")

        for page in review_pages:
            text = page.read_text(encoding="utf-8")
            if "# Contradictions" in text and "- " not in text.split("# Contradictions", 1)[1]:
                findings.append(f"Review page may have unresolved contradiction section: {page.name}")

        return findings

    def _sync_literature_pages_to_graph(
        self,
        *,
        topic: str,
        citations: list[dict[str, Any]],
        concept_terms: list[str],
        mechanism_records: list[dict[str, Any]],
        contested_questions: list[str],
    ) -> None:
        project_id = str(self.collaboration_context.get("project_id", "")).strip()
        if not project_id:
            return
        topic_slug = self._slugify_text(topic) or "research-topic"
        review_node_id = f"literature-review::{project_id}::{topic_slug}"
        self.graph_registry.save_node(
            ResearchGraphNode(
                node_id=review_node_id,
                node_type="literature_review_page",
                label=topic,
                project_id=project_id,
                topic=topic,
                metadata={"source": "literature/wiki/reviews", "kind": "review"},
            )
        )

        for citation in citations:
            if not isinstance(citation, dict):
                continue
            title = str(citation.get("title", "")).strip()
            if not title:
                continue
            paper_id = f"literature-paper::{project_id}::{self._slugify_text(title)}"
            self.graph_registry.save_node(
                ResearchGraphNode(
                    node_id=paper_id,
                    node_type="literature_paper_page",
                    label=title,
                    project_id=project_id,
                    topic=topic,
                    metadata={
                        "doi": str(citation.get("doi", "")).strip(),
                        "source_type": str(citation.get("source_type", "")).strip(),
                        "kind": "paper",
                    },
                )
            )
            self.graph_registry.save_edge(
                ResearchGraphEdge(
                    edge_id=f"{review_node_id}::contains::{paper_id}",
                    source_id=review_node_id,
                    target_id=paper_id,
                    relation="contains",
                    project_id=project_id,
                    topic=topic,
                    metadata={"source": "literature_workspace"},
                )
            )

        for concept in concept_terms:
            concept_text = str(concept).strip()
            if not concept_text:
                continue
            concept_id = f"literature-concept::{project_id}::{self._slugify_text(concept_text)}"
            self.graph_registry.save_node(
                ResearchGraphNode(
                    node_id=concept_id,
                    node_type="literature_concept_page",
                    label=concept_text,
                    project_id=project_id,
                    topic=topic,
                    metadata={"kind": "concept"},
                )
            )
            self.graph_registry.save_edge(
                ResearchGraphEdge(
                    edge_id=f"{review_node_id}::mentions::{concept_id}",
                    source_id=review_node_id,
                    target_id=concept_id,
                    relation="mentions",
                    project_id=project_id,
                    topic=topic,
                    metadata={"source": "literature_workspace"},
                )
            )

        for item in mechanism_records:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label", "")).strip() or str(item.get("mechanism_id", "")).strip()
            if not label:
                continue
            mechanism_id = f"literature-mechanism::{project_id}::{self._slugify_text(label)}"
            self.graph_registry.save_node(
                ResearchGraphNode(
                    node_id=mechanism_id,
                    node_type="literature_mechanism_page",
                    label=label,
                    project_id=project_id,
                    topic=topic,
                    metadata={"family": str(item.get("family", "")).strip(), "kind": "mechanism"},
                )
            )
            self.graph_registry.save_edge(
                ResearchGraphEdge(
                    edge_id=f"{review_node_id}::tracks::{mechanism_id}",
                    source_id=review_node_id,
                    target_id=mechanism_id,
                    relation="tracks",
                    project_id=project_id,
                    topic=topic,
                    metadata={"source": "literature_workspace"},
                )
            )

        for controversy in contested_questions:
            text = str(controversy).strip()
            if not text:
                continue
            controversy_id = f"literature-controversy::{project_id}::{self._slugify_text(text)}"
            self.graph_registry.save_node(
                ResearchGraphNode(
                    node_id=controversy_id,
                    node_type="literature_controversy_page",
                    label=text,
                    project_id=project_id,
                    topic=topic,
                    metadata={"kind": "controversy"},
                )
            )
            self.graph_registry.save_edge(
                ResearchGraphEdge(
                    edge_id=f"{review_node_id}::contests::{controversy_id}",
                    source_id=review_node_id,
                    target_id=controversy_id,
                    relation="contests",
                    project_id=project_id,
                    topic=topic,
                    metadata={"source": "literature_workspace"},
                )
            )

    @staticmethod
    def _extract_markdown_title(path: Path) -> str:
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("title:"):
                return line.split(":", 1)[1].strip().strip('"')
            if line.startswith("# "):
                return line[2:].strip()
        return ""

    @staticmethod
    def _extract_markdown_summary(path: Path) -> str:
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            cleaned = line.strip()
            if cleaned.startswith("- ") and len(cleaned) > 2:
                return cleaned[2:162]
        return ""

    def _sync_execution_cycle_memories(
        self,
        steps: list[WorkflowStepResult],
        research_state: dict[str, Any],
    ) -> None:
        summary = research_state.get("execution_cycle_summary", {})
        if not isinstance(summary, dict) or not summary:
            return
        project_id = str(self.collaboration_context.get("project_id", "")).strip()
        if not project_id:
            return
        manager = self.subagent_runtime.memory_manager
        user_id = str(self.collaboration_context.get("user_id", ""))
        group_id = str(self.collaboration_context.get("group_id", ""))

        quality_review = next(
            (
                step.parsed_output.get("quality_control_review", {})
                for step in steps
                if step.profile_name == "quality_control_reviewer"
                and isinstance(step.parsed_output.get("quality_control_review", {}), dict)
                and step.parsed_output.get("quality_control_review", {})
            ),
            {},
        )
        if quality_review:
            review_id = str(quality_review.get("review_id", "quality-control-review")).strip() or "quality-control-review"
            manager.save_memory(
                title=f"Quality control review {review_id}",
                summary=str(quality_review.get("recommended_action", "")).strip()
                or f"quality control status {quality_review.get('quality_control_status', 'unknown')}",
                kind="warning",
                scope="project",
                content="\n".join(
                    [
                        f"Run id: {quality_review.get('run_id', '')}",
                        f"Quality control status: {quality_review.get('quality_control_status', '')}",
                        f"Evidence reliability: {quality_review.get('evidence_reliability', '')}",
                        "",
                        "Issues:",
                        *[
                            f"- {item}"
                            for item in quality_review.get("issues", [])
                            if str(item).strip()
                        ],
                        "",
                        "Recommended action:",
                        str(quality_review.get("recommended_action", "")).strip(),
                    ]
                ).strip(),
                filename=f"{manager._slugify(review_id)}.md",
                source_refs=[],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="quality_control_reviewer",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                validated_by=["workflow:quality-control"],
            )

        interpretation = next(
            (
                step.parsed_output.get("interpretation_record", {})
                for step in steps
                if step.profile_name == "result_interpreter"
                and isinstance(step.parsed_output.get("interpretation_record", {}), dict)
                and step.parsed_output.get("interpretation_record", {})
            ),
            {},
        )
        if interpretation:
            interpretation_id = (
                str(interpretation.get("interpretation_id", "interpretation-record")).strip()
                or "interpretation-record"
            )
            manager.save_memory(
                title=f"Interpretation {interpretation_id}",
                summary=str(interpretation.get("next_decision", "")).strip()
                or "Experiment interpretation recorded.",
                kind="decision",
                scope="project",
                content="\n".join(
                    [
                        f"Run id: {interpretation.get('run_id', '')}",
                        f"Negative result: {interpretation.get('negative_result', False)}",
                        f"Confidence: {interpretation.get('confidence', '')}",
                        "",
                        "Supported hypothesis ids:",
                        *[
                            f"- {item}"
                            for item in interpretation.get("supported_hypothesis_ids", [])
                            if str(item).strip()
                        ],
                        "",
                        "Weakened hypothesis ids:",
                        *[
                            f"- {item}"
                            for item in interpretation.get("weakened_hypothesis_ids", [])
                            if str(item).strip()
                        ],
                        "",
                        "Next decision:",
                        str(interpretation.get("next_decision", "")).strip(),
                    ]
                ).strip(),
                filename=f"{manager._slugify(interpretation_id)}.md",
                source_refs=[],
                evidence_level="medium",
                confidence="medium",
                status="active",
                owner_agent="result_interpreter",
                user_id=user_id,
                project_id=project_id,
                group_id=group_id,
                visibility="project",
                promotion_status="project",
                validated_by=["workflow:interpretation"],
            )

    @staticmethod
    def _apply_hypothesis_status_updates(
        steps: list[WorkflowStepResult],
        claim_graph: dict[str, Any],
    ) -> None:
        links = claim_graph.get("negative_result_links", [])
        if not isinstance(links, list) or not links:
            return

        negative_nodes = {
            str(item.get("global_negative_result_id", "")).strip(): item
            for item in claim_graph.get("negative_results", [])
            if isinstance(item, dict) and str(item.get("global_negative_result_id", "")).strip()
        }
        link_counts: dict[str, int] = {}
        explicit_rejections: set[str] = set()
        for item in links:
            if not isinstance(item, dict):
                continue
            hypothesis_id = str(item.get("hypothesis_id", "")).strip()
            negative_id = str(item.get("negative_result_id", "")).strip()
            if not hypothesis_id:
                continue
            link_counts[hypothesis_id] = link_counts.get(hypothesis_id, 0) + 1
            node = negative_nodes.get(negative_id, {})
            joined = " ".join(
                [
                    str(node.get("result", "")),
                    str(node.get("why_it_failed_or_did_not_support", "")),
                    str(node.get("implication", "")),
                ]
            ).lower()
            if any(
                token in joined
                for token in [
                    "falsif",
                    "refute",
                    "rule out",
                    "invalidate",
                    "reject",
                    "contradict",
                ]
            ):
                explicit_rejections.add(hypothesis_id)

        hypothesis_nodes = claim_graph.get("hypotheses", [])
        if isinstance(hypothesis_nodes, list):
            for item in hypothesis_nodes:
                if not isinstance(item, dict):
                    continue
                global_id = str(item.get("global_hypothesis_id", "")).strip()
                if not global_id:
                    continue
                current = str(item.get("status", "active")).strip().lower()
                next_status = ScientificWorkflow._next_hypothesis_status(
                    current_status=current,
                    challenge_count=link_counts.get(global_id, 0),
                    explicit_rejection=global_id in explicit_rejections,
                )
                if next_status != current:
                    item["status"] = next_status
                    item["status_updated_by_workflow"] = True
                    item["challenge_count"] = link_counts.get(global_id, 0)

        for step in steps:
            hypotheses = step.parsed_output.get("hypotheses", [])
            if not isinstance(hypotheses, list):
                continue
            for item in hypotheses:
                if not isinstance(item, dict):
                    continue
                local_id = str(item.get("hypothesis_id", "")).strip()
                if not local_id:
                    continue
                global_id = f"{step.profile_name}::{local_id}"
                current = str(item.get("status", "active")).strip().lower()
                next_status = ScientificWorkflow._next_hypothesis_status(
                    current_status=current,
                    challenge_count=link_counts.get(global_id, 0),
                    explicit_rejection=global_id in explicit_rejections,
                )
                if next_status != current:
                    item["status"] = next_status
                    item["status_updated_by_workflow"] = True
                    item["challenge_count"] = link_counts.get(global_id, 0)

    @staticmethod
    def _next_hypothesis_status(
        *,
        current_status: str,
        challenge_count: int,
        explicit_rejection: bool,
    ) -> str:
        normalized = current_status if current_status in {"active", "revised", "deprecated", "rejected"} else "active"
        rank = {"active": 0, "revised": 1, "deprecated": 2, "rejected": 3}
        if explicit_rejection:
            target = "rejected"
        elif challenge_count >= 2:
            target = "deprecated"
        elif challenge_count >= 1:
            target = "revised"
        else:
            target = normalized
        return target if rank[target] > rank[normalized] else normalized

    def _apply_conflict_memory_updates(
        self,
        steps: list[WorkflowStepResult],
        claim_graph: dict[str, Any],
    ) -> None:
        resolver = next((s for s in steps if s.profile_name == "conflict_resolver"), None)
        critic = next((s for s in steps if s.profile_name == "critic"), None)
        if resolver is None and critic is None:
            return

        conflict_texts: list[str] = []
        rejection_bias = False
        if critic is not None:
            conflict_texts.extend(
                str(item) for item in critic.parsed_output.get("overclaims", []) if item
            )
            conflict_texts.extend(
                str(item) for item in critic.parsed_output.get("major_risks", []) if item
            )
            if critic.parsed_output.get("overclaims"):
                rejection_bias = True
        if resolver is not None:
            conflict_texts.extend(
                str(item)
                for item in resolver.parsed_output.get("remaining_disagreements", [])
                if item
            )
            conflict_texts.extend(
                str(item)
                for item in resolver.parsed_output.get("resolved_conflicts", [])
                if item
            )

        if not conflict_texts:
            return

        updated_files: set[str] = set()
        candidate_records = self.subagent_runtime.memory_manager._scan_memory_records()
        graph_statements = [
            str(item.get("statement", ""))
            for item in claim_graph.get("claims", [])
            if isinstance(item, dict) and item.get("statement")
        ]
        query_terms = self.subagent_runtime.memory_manager._terms(
            " ".join(conflict_texts + graph_statements)
        )
        scored_records: list[tuple[float, Any]] = []
        for record in candidate_records:
            haystack = " ".join([record.title, record.summary, record.excerpt])
            haystack_terms = self.subagent_runtime.memory_manager._terms(haystack)
            overlap = len(query_terms.intersection(haystack_terms))
            if overlap <= 0:
                continue
            if any(fragment.lower() in haystack.lower() for fragment in conflict_texts):
                overlap += 3
            scored_records.append((float(overlap), record))
        scored_records.sort(key=lambda pair: pair[0], reverse=True)

        for _, record in scored_records[:5]:
            filename = record.path.name
            if filename in updated_files:
                continue
            status = "rejected" if rejection_bias and record.kind == "hypothesis" else "deprecated"
            self.subagent_runtime.memory_manager.review_memory(
                filename,
                status=status,
                needs_review=False,
                conflicts_with=conflict_texts[:3],
                validated_by=["agent:conflict_resolver" if resolver is not None else "agent:critic"],
            )
            updated_files.add(filename)

        if updated_files:
            claim_graph["memory_updates"] = [
                {"filename": filename, "updated_by": "conflict-resolution"}
                for filename in sorted(updated_files)
            ]

