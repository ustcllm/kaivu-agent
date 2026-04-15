from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .profiles import DisciplineProfile, build_profile
from .stage_types import StagePlan, StageSpec
from ..prompts import PromptBuildInput, PromptBuilder, PromptSection


@dataclass(slots=True)
class ScientificAgentRunContext:
    topic: str
    project_id: str = ""
    discipline: str = "general_science"
    task_type: str = "general"
    dataset_path: str = ""
    target_column: str = ""
    metric: str = ""
    constraints: dict[str, Any] = field(default_factory=dict)
    prior_context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_scientific_task(
        cls,
        task: Any,
        *,
        prior_context: dict[str, Any] | None = None,
    ) -> ScientificAgentRunContext:
        task_dict = task.to_dict() if hasattr(task, "to_dict") else task
        task_dict = task_dict if isinstance(task_dict, dict) else {}
        merged_prior = dict(prior_context or {})
        merged_prior.setdefault("scientific_task", task_dict)
        inputs = task_dict.get("inputs", {}) if isinstance(task_dict.get("inputs", {}), dict) else {}
        return cls(
            topic=str(task_dict.get("topic", "")).strip()
            or str(task_dict.get("problem_statement", "")).strip()
            or "untitled research task",
            project_id=str(task_dict.get("project_id", "")).strip(),
            discipline=str(task_dict.get("discipline", "general_science")).strip() or "general_science",
            task_type=str(task_dict.get("task_type", "general")).strip() or "general",
            dataset_path=str(inputs.get("data_dir", inputs.get("dataset_path", ""))).strip(),
            target_column=str(inputs.get("target_column", "")).strip(),
            metric=str(inputs.get("metric", "")).strip(),
            constraints=task_dict.get("constraints", {}) if isinstance(task_dict.get("constraints", {}), dict) else {},
            prior_context=merged_prior,
        )


@dataclass(slots=True)
class ExperimentExecutionPlan:
    plan_id: str
    discipline: str
    experiment_unit: str
    protocol_template: list[str] = field(default_factory=list)
    measurement_contract: list[str] = field(default_factory=list)
    artifact_contract: list[str] = field(default_factory=list)
    quality_gates: list[str] = field(default_factory=list)
    safety_constraints: list[str] = field(default_factory=list)
    failure_modes: list[str] = field(default_factory=list)
    interpretation_boundaries: list[str] = field(default_factory=list)
    scheduler_rules: list[str] = field(default_factory=list)
    handoff_target: str = "run_manager"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ScientificAgentPrompt:
    agent_id: str
    discipline: str
    stage: str
    prompt: str
    output_contract: list[str] = field(default_factory=list)
    prompt_layers: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ScientificAgentLifecycleResult:
    agent_id: str
    agent_family: str
    discipline: str
    inherits_from: str
    task_type: str
    lifecycle_state: str
    current_stage: str
    next_stage: str
    stage_order: list[str] = field(default_factory=list)
    stage_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)
    next_actions: list[dict[str, Any]] = field(default_factory=list)
    workflow_contract: dict[str, Any] = field(default_factory=dict)
    extension_points: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ScientificAgent:
    """Shared scientific-agent lifecycle governed by profiles, schemas, and runtime policy."""

    discipline = "general_science"
    agent_family = "scientific_agent"
    experiment_unit = "one approved scientific test"
    handoff_target = "run_manager"

    def discipline_profile(self, context: ScientificAgentRunContext | None = None) -> DisciplineProfile:
        name = self.discipline
        if context is not None:
            if context.task_type == "kaggle_competition":
                name = "kaggle_competition"
            elif context.discipline:
                name = context.discipline
        return build_profile(name)

    def lifecycle_stage_specs(self, context: ScientificAgentRunContext | None = None) -> list[StageSpec]:
        profile = self.discipline_profile(context)
        return profile.lifecycle_stages

    def build_agent_blueprint(self, context: ScientificAgentRunContext | dict[str, Any]) -> dict[str, Any]:
        request = context if isinstance(context, ScientificAgentRunContext) else ScientificAgentRunContext(**context)
        stage_order = self.lifecycle_stage_order()
        return {
            "agent_id": self.agent_id(),
            "agent_family": self.agent_family,
            "discipline": self.discipline,
            "agent_class": "ScientificAgent",
            "task_type": request.task_type,
            "stage_order": stage_order,
            "workflow_contract": self.workflow_contract(),
            "extension_points": self.extension_points(),
            "prompt_policy": self.build_prompt_policy(request),
            "discipline_profile": self.discipline_profile(request).to_dict(),
        }

    def agent_id(self) -> str:
        return f"{self.discipline}::{self.agent_family}"

    def lifecycle_stage_order(self) -> list[str]:
        return [spec.name for spec in self.lifecycle_stage_specs()]

    def build_lifecycle_stage_plan(self, stage: str, context: ScientificAgentRunContext) -> dict[str, Any]:
        normalized_stage = _normalize_stage(stage)
        output = self.lifecycle_stage_output(normalized_stage, context)
        prompt = self.build_prompt(normalized_stage, context)
        spec = self.stage_spec(normalized_stage, context)
        plan = StagePlan(
            stage=normalized_stage,
            state="planned",
            hook=self.lifecycle_stage_hook_name(normalized_stage),
            prompt=prompt.to_dict(),
            output_contract=prompt.output_contract,
            semantic_output=output,
            tool_capabilities=self.tool_capabilities_for_stage(normalized_stage, context, output),
            transition=self.lifecycle_stage_transition(normalized_stage, output),
            execution_mode=spec.execution_mode.to_dict() if spec else {},
            profile=self.discipline_profile(context).to_dict(),
            task={
                "topic": context.topic,
                "project_id": context.project_id,
                "discipline": context.discipline,
                "task_type": context.task_type,
                "dataset_path": context.dataset_path,
                "target_column": context.target_column,
                "metric": context.metric,
                "constraints": context.constraints,
            },
        )
        return plan.to_dict()

    def stage_spec(self, stage: str, context: ScientificAgentRunContext | None = None) -> StageSpec | None:
        return self.discipline_profile(context).stage_spec(stage)

    def default_capability_requests_for_stage(self, stage: str, context: ScientificAgentRunContext) -> list[dict[str, Any]]:
        profile = self.discipline_profile(context)
        spec = profile.stage_spec(stage)
        capability_names = list(spec.default_capabilities) if spec else []
        capability_names.extend(profile.capabilities_for_stage(stage))
        adapter_requirements = context.prior_context.get("capability_requirements", {})
        if isinstance(adapter_requirements, dict):
            values = adapter_requirements.get(stage, [])
            if isinstance(values, list):
                capability_names.extend(str(item) for item in values if str(item).strip())
        return [
            {
                "capability": name,
                "intent": f"support scientific lifecycle stage `{stage}`",
                "arguments": self.default_capability_arguments(name, stage, context),
                "required": name == "executor_handoff",
            }
            for name in dict.fromkeys(capability_names)
        ]

    def default_capability_arguments(
        self,
        capability: str,
        stage: str,
        context: ScientificAgentRunContext,
    ) -> dict[str, Any]:
        if capability in {"literature_search", "literature_wiki_query"}:
            return {"query": context.topic, "limit": 10}
        if capability == "citation_resolution":
            return {}
        if capability == "data_read":
            return {"path": context.dataset_path}
        if capability == "executor_handoff":
            scientific_task = context.prior_context.get("scientific_task", {})
            if isinstance(scientific_task, dict):
                environment = scientific_task.get("environment", {})
                if isinstance(environment, dict):
                    executor = str(environment.get("executor", "")).strip()
                    if executor:
                        return {"handoff_target": executor}
            return {"handoff_target": self.handoff_target}
        if capability in {"memory_write", "graph_update"}:
            return {"topic": context.topic, "project_id": context.project_id}
        return {}

    def lifecycle_stage_output(self, stage: str, context: ScientificAgentRunContext) -> dict[str, Any] | list[dict[str, Any]]:
        if stage == "question":
            return self.frame_problem(context)
        if stage == "literature_review":
            return self.build_literature_plan(context)
        if stage == "hypothesis_generation":
            return self.synthesize_hypotheses(context)
        if stage == "hypothesis_validation":
            return self.validate_hypothesis(context)
        if stage == "experiment_design":
            return self.design_experiment(context)
        if stage == "execution_planning":
            return self.build_execution_plan(context).to_dict()
        if stage == "quality_review":
            return {"quality_gates": self.define_quality_gates(context)}
        if stage == "analysis":
            return self.interpret_result(context)
        if stage == "decision":
            return self.decide_next_action(context)
        if stage == "memory_and_graph_update":
            return {
                "memory_update_policy": self.update_memory(context),
                "graph_update_policy": self.update_graph(context),
            }
        if stage == "reporting":
            return self.build_reporting_plan(context)
        return {"stage": stage, "state": "not_implemented"}

    def lifecycle_stage_hook_name(self, stage: str) -> str:
        return {
            "question": "frame_problem",
            "literature_review": "build_literature_plan",
            "hypothesis_generation": "synthesize_hypotheses",
            "hypothesis_validation": "validate_hypothesis",
            "experiment_design": "design_experiment",
            "execution_planning": "build_execution_plan",
            "quality_review": "define_quality_gates",
            "analysis": "interpret_result",
            "decision": "decide_next_action",
            "memory_and_graph_update": "update_memory_and_graph",
            "reporting": "build_reporting_plan",
        }.get(stage, "unknown")

    def tool_capabilities_for_stage(
        self,
        stage: str,
        context: ScientificAgentRunContext,
        semantic_output: Any,
    ) -> list[dict[str, Any]]:
        profile_requests = self.default_capability_requests_for_stage(stage, context)
        if profile_requests:
            if stage == "analysis" and not context.dataset_path:
                profile_requests = [
                    request
                    for request in profile_requests
                    if request.get("capability") != "data_read"
                ]
            if stage == "execution_planning":
                for request in profile_requests:
                    if request.get("capability") == "executor_handoff":
                        if isinstance(semantic_output, dict):
                            requested_target = str(request.get("arguments", {}).get("handoff_target", "")).strip()
                            request["arguments"] = {
                                "handoff_target": requested_target
                                or str(semantic_output.get("handoff_target", "")).strip()
                                or self.handoff_target
                            }
                return profile_requests
            return profile_requests
        if stage == "literature_review":
            return [
                {
                    "capability": "literature_search",
                    "intent": "retrieve relevant papers, claims, methods, and conflicts",
                    "arguments": {"query": context.topic, "max_results": 5},
                    "required": False,
                },
                {
                    "capability": "citation_resolution",
                    "intent": "resolve ambiguous citations or identifiers when sources are referenced",
                    "arguments": {},
                    "required": False,
                },
                {
                    "capability": "literature_wiki_query",
                    "intent": "reuse compiled literature wiki knowledge before raw retrieval",
                    "arguments": {"query": context.topic, "limit": 10},
                    "required": False,
                },
            ]
        if stage == "analysis":
            requests: list[dict[str, Any]] = []
            if context.dataset_path:
                requests.append(
                    {
                        "capability": "data_read",
                        "intent": "inspect available dataset or result table before interpretation",
                        "arguments": {"path": context.dataset_path},
                        "required": False,
                    }
                )
            requests.append(
                {
                    "capability": "python_analysis",
                    "intent": "run reproducible statistical or computational checks when needed",
                    "arguments": {},
                    "required": False,
                }
            )
            return requests
        if stage == "execution_planning":
            handoff_target = ""
            if isinstance(semantic_output, dict):
                handoff_target = str(semantic_output.get("handoff_target", "")).strip()
            return [
                {
                    "capability": "executor_handoff",
                    "intent": "handoff an approved execution package to the selected executor",
                    "arguments": {"handoff_target": handoff_target or self.handoff_target},
                    "required": True,
                }
            ]
        if stage == "memory_and_graph_update":
            return [
                {
                    "capability": "memory_write",
                    "intent": "persist validated decisions, failures, and claim updates",
                    "arguments": {"topic": context.topic, "scope": "project"},
                    "required": False,
                },
                {
                    "capability": "graph_update",
                    "intent": "persist provenance links among problem, source, claim, hypothesis, evidence, artifact, failure, and decision",
                    "arguments": {"project_id": context.project_id},
                    "required": False,
                },
            ]
        return []

    def lifecycle_stage_transition(self, stage: str, output: Any) -> dict[str, Any]:
        order = self.lifecycle_stage_order()
        try:
            index = order.index(stage)
        except ValueError:
            index = -1
        next_stage = order[index + 1] if 0 <= index < len(order) - 1 else ""
        return {
            "next_stage": next_stage,
            "can_continue": True,
            "requires_external_execution": stage == "execution_planning",
            "records_memory_or_graph": stage == "memory_and_graph_update",
        }

    def collect_lifecycle_blockers(self, stage_results: dict[str, dict[str, Any]]) -> list[str]:
        blockers: list[str] = []
        validation = stage_results.get("hypothesis_validation", {}).get("semantic_output", {})
        if isinstance(validation, dict):
            blockers.extend(
                str(item)
                for item in validation.get("active_blockers", [])
                if str(item).strip()
            )
        gates = stage_results.get("quality_review", {}).get("semantic_output", {})
        if isinstance(gates, dict):
            for gate in gates.get("quality_gates", []):
                if isinstance(gate, dict) and gate.get("state") == "blocked":
                    blockers.append(str(gate.get("gate", "quality_gate_blocked")))
        return list(dict.fromkeys(blockers))

    def collect_lifecycle_next_actions(
        self,
        stage_results: dict[str, dict[str, Any]],
        *,
        blockers: list[str],
    ) -> list[dict[str, Any]]:
        if blockers:
            return [
                {
                    "action": "resolve_lifecycle_blockers",
                    "priority": "high",
                    "reason": "; ".join(blockers[:5]),
                }
            ]
        decision = stage_results.get("decision", {}).get("semantic_output", {})
        if isinstance(decision, dict):
            options = decision.get("decision_options", [])
            if isinstance(options, list) and options:
                return [
                    {
                        "action": str(options[0]),
                        "priority": "medium",
                        "reason": str(decision.get("policy", {}).get("default_action", "")) if isinstance(decision.get("policy", {}), dict) else "",
                    }
                ]
        return [{"action": "continue", "priority": "medium", "reason": "lifecycle planned without blockers"}]

    def select_next_stage(self, stage_results: dict[str, dict[str, Any]], *, blockers: list[str]) -> str:
        if blockers:
            return "quality_review"
        for stage, result in stage_results.items():
            transition = result.get("transition", {})
            if transition.get("requires_external_execution"):
                return stage
        return "reporting"

    def workflow_contract(self) -> dict[str, Any]:
        return {
            "shared_stages": [
                "question",
                "literature_review",
                "hypothesis_generation",
                "hypothesis_validation",
                "experiment_design",
                "execution_planning",
                "quality_review",
                "analysis",
                "decision",
                "memory_and_graph_update",
                "reporting",
            ],
            "invariant": "discipline agents share one lifecycle; prompt/profile/schema/capability differences are preferred over subclass overrides",
            "profile_first_rule": "scientific reasoning differences should live in DisciplineProfile unless hard runtime behavior is required",
            "allowed_hard_overrides": [
                "build_prompt",
                "discipline_prompt_addendum",
                "task_prompt_addendum",
                "frame_problem",
                "build_literature_plan",
                "synthesize_hypotheses",
                "validate_hypothesis",
                "design_experiment",
                "build_execution_plan",
                "define_quality_gates",
                "interpret_result",
                "classify_failure",
                "update_memory",
                "update_graph",
                "decide_next_action",
                "build_reporting_plan",
                "build_memory_policy",
                "build_decision_policy",
            ],
        }

    def build_prompt(
        self,
        stage: str,
        context: ScientificAgentRunContext | dict[str, Any],
        *,
        output_schema: str = "",
        memory: str = "",
        tool_policy: str = "",
    ) -> ScientificAgentPrompt:
        request = context if isinstance(context, ScientificAgentRunContext) else ScientificAgentRunContext(**context)
        normalized_stage = _normalize_stage(stage)
        base_role = self.base_prompt_for_stage(normalized_stage, request)
        discipline_addendum = self.discipline_prompt_addendum(normalized_stage, request)
        task_addendum = self.task_prompt_addendum(normalized_stage, request)
        self_check = self.self_check_rubric(normalized_stage, request)
        prompt = PromptBuilder().build(
            PromptBuildInput(
                base_role=base_role,
                memory=memory,
                schema_instruction=output_schema,
                tool_policy=tool_policy,
                extra_sections=[
                    PromptSection("Discipline Method", discipline_addendum, optional=True),
                    PromptSection("Task Specialization", task_addendum, optional=True),
                    PromptSection("Self Check", self_check, optional=True),
                ],
            )
        )
        return ScientificAgentPrompt(
            agent_id=f"{self.discipline}::{self.agent_family}",
            discipline=self.discipline,
            stage=normalized_stage,
            prompt=prompt,
            output_contract=self.output_contract_for_stage(normalized_stage, request),
            prompt_layers={
                "base": base_role,
                "profile": self.discipline_profile(request).prompt_for_stage(normalized_stage),
                "discipline": discipline_addendum,
                "task": task_addendum,
                "self_check": self_check,
            },
        )

    def build_prompt_policy(self, context: ScientificAgentRunContext) -> dict[str, Any]:
        return {
            "composition_order": ["base_scientific_prompt", "discipline_addendum", "task_addendum", "output_schema", "self_check"],
            "automatic_prompt_stages": self.workflow_contract()["shared_stages"],
            "override_rule": "subclasses should add or override only the stage-specific scientific semantics they truly own",
            "sample_prompts": {
                stage: self.build_prompt(stage, context).to_dict()
                for stage in ["literature_review", "hypothesis_generation", "experiment_design", "quality_review", "decision"]
            },
        }

    def base_prompt_for_stage(self, stage: str, context: ScientificAgentRunContext) -> str:
        spec = self.stage_spec(stage, context)
        goal = spec.goal if spec else f"perform the scientific lifecycle stage `{stage}`"
        return "\n".join(
            [
                f"You are the {self.discipline} scientific agent for project `{context.project_id or 'workspace'}`.",
                f"Current topic: {context.topic}.",
                f"Lifecycle stage: {stage}. Your job is to {goal}.",
                "Maintain scientific rigor: separate evidence from speculation, record uncertainty, preserve provenance, and treat negative results as useful knowledge.",
                "Do not claim real-world execution happened unless a verified executor result is provided.",
            ]
        )

    def discipline_prompt_addendum(self, stage: str, context: ScientificAgentRunContext) -> str:
        profile_text = self.discipline_profile(context).prompt_for_stage(stage)
        execution_plan = self.build_execution_plan(context)
        if stage in {"experiment_design", "execution_planning", "quality_review", "analysis", "decision"}:
            return "\n".join(
                [
                    profile_text,
                    f"Experiment unit: {execution_plan.experiment_unit}.",
                    f"Measurement contract: {_join_items(execution_plan.measurement_contract)}.",
                    f"Artifact contract: {_join_items(execution_plan.artifact_contract)}.",
                    f"Quality gates: {_join_items(execution_plan.quality_gates)}.",
                    f"Known failure modes: {_join_items(execution_plan.failure_modes)}.",
                    f"Interpretation boundaries: {_join_items(execution_plan.interpretation_boundaries)}.",
                ]
            )
        return profile_text

    def task_prompt_addendum(self, stage: str, context: ScientificAgentRunContext) -> str:
        return ""

    def output_contract_for_stage(self, stage: str, context: ScientificAgentRunContext) -> list[str]:
        spec = self.stage_spec(stage, context)
        return list(spec.output_contract) if spec else ["result", "rationale", "next_action"]

    def self_check_rubric(self, stage: str, context: ScientificAgentRunContext) -> str:
        return "\n".join(
            [
                "Before finalizing, check:",
                "- Are claims separated from assumptions and speculation?",
                "- Are quality gates and failure modes considered?",
                "- Is negative or missing evidence recorded rather than ignored?",
                "- Are next actions tied to information gain, cost, and risk?",
            ]
        )

    def frame_problem(self, context: ScientificAgentRunContext) -> dict[str, Any]:
        return {
            "topic": context.topic,
            "project_id": context.project_id,
            "discipline": self.discipline,
            "task_type": context.task_type,
            "scientific_question_unit": "claim or hypothesis to be tested",
            "evidence_unit": "observation plus provenance plus quality status",
        }

    def build_literature_plan(self, context: ScientificAgentRunContext) -> dict[str, Any]:
        return {
            "strategy": "systematic_context_first",
            "must_extract": [
                "claims",
                "methods",
                "assumptions",
                "failure_modes",
                "measurement_or_evaluation_protocols",
                "conflicts",
            ],
            "output_contract": ["review_digest", "claim_table", "method_table", "open_questions"],
        }

    def synthesize_hypotheses(self, context: ScientificAgentRunContext) -> dict[str, Any]:
        return {
            "hypothesis_unit": "testable scientific claim",
            "validators": [
                "novelty",
                "feasibility",
                "falsifiability",
                "mechanism_or_theory_grounding",
                "measurement_or_evaluation_readiness",
            ],
            "must_include": ["assumptions", "predictions", "rival_hypotheses", "minimum_discriminative_test"],
        }

    def validate_hypothesis(self, context: ScientificAgentRunContext) -> dict[str, Any]:
        profile = self.discipline_profile(context)
        validators = [
            "novelty",
            "feasibility",
            "falsifiability",
            "mechanism_or_theory_grounding",
            "measurement_or_evaluation_readiness",
        ]
        validators.extend(profile.validators)
        blockers = [
            "hypothesis is not testable",
            "evidence needed to evaluate it is unavailable",
            "quality gates cannot distinguish support from artifact",
        ]
        blockers.extend(profile.validation_blockers)
        return {
            "validator_set": list(dict.fromkeys(validators)),
            "validation_boundary": "base validators are combined with DisciplineProfile validators and task adapter gates",
            "blocks_progress_when": list(dict.fromkeys(blockers)),
        }

    def design_experiment(self, context: ScientificAgentRunContext) -> dict[str, Any]:
        execution_plan = self.build_execution_plan(context)
        return {
            "design_state": "interface_only",
            "role": "define a discriminative test; discipline subclasses own experiment semantics",
            "experiment_unit": execution_plan.experiment_unit,
            "protocol_template": execution_plan.protocol_template,
            "quality_gates": execution_plan.quality_gates,
            "handoff_target": execution_plan.handoff_target,
        }

    def build_execution_plan(self, context: ScientificAgentRunContext) -> ExperimentExecutionPlan:
        contract = self.discipline_profile(context).execution_contract
        if contract:
            return ExperimentExecutionPlan(
                plan_id=f"execution-plan::{self.discipline}::{_slugify(context.topic)}",
                discipline=self.discipline,
                experiment_unit=str(contract.get("experiment_unit", self.experiment_unit)),
                protocol_template=_string_list(contract.get("protocol_template", [])),
                measurement_contract=_string_list(contract.get("measurement_contract", [])),
                artifact_contract=_string_list(contract.get("artifact_contract", [])),
                quality_gates=_string_list(contract.get("quality_gates", [])),
                safety_constraints=_string_list(contract.get("safety_constraints", [])),
                failure_modes=_string_list(contract.get("failure_modes", [])),
                interpretation_boundaries=_string_list(contract.get("interpretation_boundaries", [])),
                scheduler_rules=_string_list(contract.get("scheduler_rules", [])),
                handoff_target=str(contract.get("handoff_target", self.handoff_target)).strip() or self.handoff_target,
            )
        return ExperimentExecutionPlan(
            plan_id=f"execution-plan::{self.discipline}::{_slugify(context.topic)}",
            discipline=self.discipline,
            experiment_unit=self.experiment_unit,
            protocol_template=[
                "state hypothesis and expected observation",
                "freeze protocol and quality gates",
                "record artifacts and provenance",
            ],
            measurement_contract=["primary outcome", "quality-control status", "artifact references"],
            artifact_contract=["run_record", "observation_record", "quality_control_review"],
            quality_gates=["protocol_version_recorded", "artifact_provenance_recorded"],
            safety_constraints=["require explicit approval for real-world execution"],
            failure_modes=["missing protocol", "missing artifact", "ambiguous interpretation"],
            interpretation_boundaries=["quality failure blocks strong claim updates"],
            scheduler_rules=["prefer lower-cost discriminative tests when uncertainty is high"],
            handoff_target=self.handoff_target,
        )

    def define_quality_gates(self, context: ScientificAgentRunContext) -> list[dict[str, Any]]:
        execution_plan = self.build_execution_plan(context)
        profile_gates_by_name: dict[str, dict[str, Any]] = {}
        for gate in self.discipline_profile(context).quality_gates:
            profile_gates_by_name.setdefault(gate.name, gate.to_dict())
        profile_gates = list(profile_gates_by_name.values())
        adapter_gates = context.prior_context.get("quality_gates", [])
        if isinstance(adapter_gates, list):
            for gate in adapter_gates:
                if isinstance(gate, dict):
                    name = str(gate.get("name", gate.get("gate", ""))).strip()
                    if name and name not in profile_gates_by_name:
                        profile_gates_by_name[name] = gate
        profile_gates = list(profile_gates_by_name.values())
        execution_gates = [
            {
                "gate": gate,
                "scope": self.discipline,
                "required": True,
                "failure_effect": "blocks strong claim update until resolved",
            }
            for gate in execution_plan.quality_gates
        ]
        return profile_gates + execution_gates

    def interpret_result(self, context: ScientificAgentRunContext) -> dict[str, Any]:
        execution_plan = self.build_execution_plan(context)
        policy = {
            "interpretation_unit": "evidence update with uncertainty and provenance",
            "evidence_unit": "observation plus quality status plus artifact references",
            "interpretation_boundaries": execution_plan.interpretation_boundaries,
            "default_rule": "quality failure prevents strong support or rejection",
            "allowed_claim_updates": ["support", "weaken", "revise", "reject", "remain_uncertain"],
        }
        profile_policy = self.discipline_profile(context).interpretation_policy
        if profile_policy:
            policy.update(profile_policy)
        return policy

    def classify_failure(self, context: ScientificAgentRunContext) -> dict[str, Any]:
        execution_plan = self.build_execution_plan(context)
        taxonomy = list(execution_plan.failure_modes)
        taxonomy.extend(self.discipline_profile(context).failure_taxonomy)
        return {
            "failure_taxonomy": list(dict.fromkeys(taxonomy)),
            "default_classes": [
                "protocol_failure",
                "quality_control_failure",
                "negative_result",
                "ambiguous_result",
                "execution_failure",
            ],
            "memory_effect": "failed attempts are recorded and fed back into scheduling",
            "claim_effect": "only valid negative evidence should weaken or reject hypotheses",
        }

    def build_memory_policy(self, context: ScientificAgentRunContext) -> dict[str, Any]:
        return {
            "write_scopes": ["project", "group", "user"],
            "must_record": [
                "decisions",
                "protocol changes",
                "negative results",
                "failed attempts",
                "quality failures",
                "claim status updates",
            ],
            "promotion_rule": "local observations require validation before group promotion",
        }

    def update_memory(self, context: ScientificAgentRunContext) -> dict[str, Any]:
        return {
            "write_policy": self.build_memory_policy(context),
            "must_write_after": [
                "decision",
                "quality failure",
                "negative result",
                "failed attempt",
                "protocol change",
                "claim status change",
            ],
            "scope_rule": "write local/project memory first; promote to group memory only after validation",
        }

    def update_graph(self, context: ScientificAgentRunContext) -> dict[str, Any]:
        return {
            "graph_objects": [
                "problem",
                "source",
                "claim",
                "hypothesis",
                "experiment",
                "evidence",
                "artifact",
                "failure",
                "decision",
            ],
            "required_edges": [
                "source_supports_or_challenges_claim",
                "hypothesis_tested_by_experiment",
                "experiment_produced_evidence",
                "evidence_updates_claim",
                "failure_informs_next_decision",
            ],
            "provenance_rule": "graph updates must preserve source, run, artifact, and decision provenance",
        }

    def build_decision_policy(self, context: ScientificAgentRunContext) -> dict[str, Any]:
        return {
            "default_action": "continue_only_if_next_test_has_clear_information_gain",
            "stop_or_pause_conditions": [
                "quality gates fail",
                "evidence is insufficient for the claimed update",
                "cost exceeds expected information gain",
            ],
        }

    def decide_next_action(self, context: ScientificAgentRunContext) -> dict[str, Any]:
        return {
            "decision_options": ["continue", "revise", "replicate", "stop", "report", "ask_human"],
            "policy": self.build_decision_policy(context),
            "requires": [
                "current evidence state",
                "quality gate state",
                "expected information gain",
                "cost and risk estimate",
                "memory of failed attempts",
            ],
        }

    def build_reporting_plan(self, context: ScientificAgentRunContext) -> dict[str, Any]:
        return {
            "report_sections": [
                "research question",
                "literature and prior evidence",
                "hypotheses and validators",
                "experiment or proof plan",
                "quality gates",
                "evidence interpretation boundaries",
                "failed attempts and negative knowledge",
                "memory and graph updates",
                "next decision",
            ],
            "release_gate": "do not present unsupported or quality-blocked claims as conclusions",
            "audience": "research collaborator",
        }

    def build_problem_framing(self, context: ScientificAgentRunContext) -> dict[str, Any]:
        return self.frame_problem(context)

    def build_literature_strategy(self, context: ScientificAgentRunContext) -> dict[str, Any]:
        return self.build_literature_plan(context)

    def build_hypothesis_strategy(self, context: ScientificAgentRunContext) -> dict[str, Any]:
        return self.synthesize_hypotheses(context)

    def build_experiment_execution_plan(self, context: ScientificAgentRunContext) -> ExperimentExecutionPlan:
        return self.build_execution_plan(context)

    def extension_points(self) -> dict[str, Any]:
        return {
            "task_adapters": "competition, benchmark, instrument, or proof-task adapters can add methods without owning workflow",
            "toolchain_adapters": "external tools can be bound through execution handoff contracts",
            "model_policy": "agent model choice can vary by stage without changing workflow",
        }


def _slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value).strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "topic"


def _normalize_stage(stage: str) -> str:
    normalized = stage.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "problem_definition": "question",
        "literature": "literature_review",
        "review": "literature_review",
        "hypothesis": "hypothesis_generation",
        "design": "experiment_design",
        "execute": "execution_planning",
        "interpret": "analysis",
        "memory": "memory_and_graph_update",
        "report": "reporting",
    }
    return aliases.get(normalized, normalized or "question")


def _join_items(items: list[str]) -> str:
    return ", ".join(item for item in items if item) or "not specified"


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


