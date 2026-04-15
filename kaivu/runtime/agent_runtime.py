from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..agents.base import ScientificAgent, ScientificAgentLifecycleResult, ScientificAgentRunContext
from ..science_capabilities import ScientificCapabilityRegistry, build_default_scientific_capability_registry


@dataclass(slots=True)
class ScientificAgentStageExecutionRecord:
    stage: str
    hook: str
    execution_state: str
    prompt_chars: int = 0
    output_contract: list[str] = field(default_factory=list)
    semantic_output_keys: list[str] = field(default_factory=list)
    requires_external_execution: bool = False
    records_memory_or_graph: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ScientificAgentToolCallRequest:
    stage: str
    capability: str
    intent: str
    candidate_tools: list[str] = field(default_factory=list)
    arguments: dict[str, Any] = field(default_factory=dict)
    required: bool = False
    execution_mode: str = "runtime_resolved"
    capability_pack: str = "unknown"
    status: str = "proposed"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ScientificAgentToolCallResult:
    stage: str
    capability: str
    selected_tool: str = ""
    status: str = "skipped"
    arguments: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: str = ""
    execution_log: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ScientificAgentRuntimePolicy:
    allow_tool_execution: bool = False
    execute_read_only_tools_only: bool = True
    allowed_capabilities: list[str] = field(default_factory=list)
    blocked_capabilities: list[str] = field(default_factory=lambda: ["executor_handoff"])
    approval_required_capabilities: list[str] = field(
        default_factory=lambda: ["executor_handoff", "memory_write", "graph_update", "python_analysis"]
    )
    blocked_tools: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ScientificAgentRuntimeResult:
    runtime_id: str
    runtime_state: str
    agent_id: str
    agent_family: str
    discipline: str
    task_type: str
    lifecycle_state: str
    lifecycle: dict[str, Any]
    stage_execution_records: list[dict[str, Any]] = field(default_factory=list)
    tool_call_requests: list[dict[str, Any]] = field(default_factory=list)
    tool_call_results: list[dict[str, Any]] = field(default_factory=list)
    memory_update_requests: list[dict[str, Any]] = field(default_factory=list)
    graph_update_requests: list[dict[str, Any]] = field(default_factory=list)
    external_execution_requests: list[dict[str, Any]] = field(default_factory=list)
    trajectory_events: list[dict[str, Any]] = field(default_factory=list)
    runtime_policy: dict[str, Any] = field(default_factory=dict)
    runtime_boundary: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ScientificAgentRuntime:
    """Infrastructure runner for scientific agents.

    The runtime intentionally composes with ScientificAgent instead of being
    its parent class: agents own scientific semantics, while this layer owns
    execution observability, replay records, and future training data capture.
    """

    def __init__(
        self,
        *,
        runtime_id: str = "scientific-agent-runtime",
        mode: str = "plan_only",
        tools: Any = None,
        tool_context: Any = None,
        auto_execute_tools: bool = False,
        policy: ScientificAgentRuntimePolicy | None = None,
        capability_registry: ScientificCapabilityRegistry | None = None,
    ) -> None:
        self.runtime_id = runtime_id
        self.mode = mode
        self.tools = tools
        self.tool_context = tool_context
        self.auto_execute_tools = auto_execute_tools
        self.policy = policy or ScientificAgentRuntimePolicy(allow_tool_execution=auto_execute_tools)
        self.capability_registry = capability_registry or build_default_scientific_capability_registry()

    def run_agent(
        self,
        agent: ScientificAgent,
        context: ScientificAgentRunContext | dict[str, Any],
    ) -> ScientificAgentRuntimeResult:
        request = context if isinstance(context, ScientificAgentRunContext) else ScientificAgentRunContext(**context)
        lifecycle_result = self.run_lifecycle(agent, request)
        lifecycle = lifecycle_result.to_dict()
        records = self.build_stage_execution_records(lifecycle_result)
        tool_requests = self.extract_tool_call_requests(lifecycle)
        memory_requests, graph_requests = self.extract_memory_and_graph_requests(lifecycle)
        external_requests = self.extract_external_execution_requests(lifecycle)
        trajectory_events = self.build_trajectory_events(
            lifecycle=lifecycle,
            records=records,
            tool_requests=tool_requests,
            memory_requests=memory_requests,
            graph_requests=graph_requests,
            external_requests=external_requests,
        )
        return ScientificAgentRuntimeResult(
            runtime_id=self.runtime_id,
            runtime_state=self.select_runtime_state(lifecycle_result),
            agent_id=lifecycle_result.agent_id,
            agent_family=lifecycle_result.agent_family,
            discipline=lifecycle_result.discipline,
            task_type=lifecycle_result.task_type,
            lifecycle_state=lifecycle_result.lifecycle_state,
            lifecycle=lifecycle,
            stage_execution_records=[record.to_dict() for record in records],
            tool_call_requests=tool_requests,
            tool_call_results=[],
            memory_update_requests=memory_requests,
            graph_update_requests=graph_requests,
            external_execution_requests=external_requests,
            trajectory_events=trajectory_events,
            runtime_policy=self.policy.to_dict(),
            runtime_boundary=self.runtime_boundary(),
        )

    def run_task(
        self,
        agent: ScientificAgent,
        task_or_adapter_result: Any,
    ) -> ScientificAgentRuntimeResult:
        """Run an agent from a normalized ScientificTask or TaskAdapterResult."""

        task = getattr(task_or_adapter_result, "task", task_or_adapter_result)
        prior_context: dict[str, Any] = {}
        if hasattr(task_or_adapter_result, "to_dict") and hasattr(task_or_adapter_result, "task"):
            adapter_dict = task_or_adapter_result.to_dict()
            prior_context = {
                "task_adapter_result": adapter_dict,
                "memory_items": adapter_dict.get("memory_items", []),
                "graph_facts": adapter_dict.get("graph_facts", []),
                "quality_gates": adapter_dict.get("quality_gates", []),
                "capability_requirements": adapter_dict.get("capability_requirements", {}),
                "adapter_metadata": adapter_dict.get("adapter_metadata", {}),
            }
        context = ScientificAgentRunContext.from_scientific_task(task, prior_context=prior_context)
        return self.run_agent(agent, context)

    async def run_agent_async(
        self,
        agent: ScientificAgent,
        context: ScientificAgentRunContext | dict[str, Any],
    ) -> ScientificAgentRuntimeResult:
        result = self.run_agent(agent, context)
        if not self.auto_execute_tools:
            return result
        result.tool_call_results = await self.execute_tool_call_requests(result.tool_call_requests)
        self.attach_tool_results_to_lifecycle(result.lifecycle, result.tool_call_results)
        result.trajectory_events.extend(
            self.build_tool_result_events(
                agent_id=result.agent_id,
                tool_results=result.tool_call_results,
            )
        )
        result.runtime_state = self.select_runtime_state_after_tools(result)
        return result

    def run_lifecycle(
        self,
        agent: ScientificAgent,
        context: ScientificAgentRunContext,
    ) -> ScientificAgentLifecycleResult:
        stage_order = agent.lifecycle_stage_order()
        stage_results = {
            stage: self.run_lifecycle_stage(agent, stage, context)
            for stage in stage_order
        }
        blockers = agent.collect_lifecycle_blockers(stage_results)
        next_actions = agent.collect_lifecycle_next_actions(stage_results, blockers=blockers)
        return ScientificAgentLifecycleResult(
            agent_id=agent.agent_id(),
            agent_family=agent.agent_family,
            discipline=agent.discipline,
            inherits_from="ScientificAgent",
            task_type=context.task_type,
            lifecycle_state="blocked" if blockers else "planned",
            current_stage=stage_order[0] if stage_order else "question",
            next_stage=agent.select_next_stage(stage_results, blockers=blockers),
            stage_order=stage_order,
            stage_results=stage_results,
            blockers=blockers,
            next_actions=next_actions,
            workflow_contract=agent.workflow_contract(),
            extension_points=agent.extension_points(),
        )

    def run_lifecycle_stage(
        self,
        agent: ScientificAgent,
        stage: str,
        context: ScientificAgentRunContext,
    ) -> dict[str, Any]:
        stage_plan = agent.build_lifecycle_stage_plan(stage, context)
        tool_call_plan = self.build_tool_call_plan(stage_plan)
        return {
            **stage_plan,
            "runtime": {
                "runtime_id": self.runtime_id,
                "mode": self.mode,
                "tool_call_plan": tool_call_plan,
                "execution_boundary": self.stage_execution_boundary(stage_plan),
            },
        }

    def build_stage_execution_records(
        self,
        lifecycle_result: ScientificAgentLifecycleResult,
    ) -> list[ScientificAgentStageExecutionRecord]:
        records: list[ScientificAgentStageExecutionRecord] = []
        for stage in lifecycle_result.stage_order:
            result = lifecycle_result.stage_results.get(stage, {})
            transition = result.get("transition", {}) if isinstance(result.get("transition", {}), dict) else {}
            prompt = result.get("prompt", {}) if isinstance(result.get("prompt", {}), dict) else {}
            semantic_output = result.get("semantic_output", {})
            records.append(
                ScientificAgentStageExecutionRecord(
                    stage=stage,
                    hook=str(result.get("hook", "")),
                    execution_state=str(result.get("state", "planned")),
                    prompt_chars=len(str(prompt.get("prompt", ""))),
                    output_contract=[
                        str(item)
                        for item in prompt.get("output_contract", [])
                        if str(item).strip()
                    ]
                    if isinstance(prompt.get("output_contract", []), list)
                    else [],
                    semantic_output_keys=sorted(semantic_output.keys()) if isinstance(semantic_output, dict) else [],
                    requires_external_execution=bool(transition.get("requires_external_execution")),
                    records_memory_or_graph=bool(transition.get("records_memory_or_graph")),
                )
            )
        return records

    def build_tool_call_plan(self, stage_plan: dict[str, Any]) -> dict[str, Any]:
        stage = str(stage_plan.get("stage", ""))
        tool_requests = self.resolve_tool_capabilities(stage_plan)
        semantic_output = stage_plan.get("semantic_output", {})
        if stage == "literature_review":
            return {
                "tool_policy": "runtime_may_call_literature_tools",
                "tool_call_requests": tool_requests,
                "reason": "literature review often needs retrieval before synthesis",
            }
        if stage == "execution_planning":
            handoff_target = ""
            if isinstance(semantic_output, dict):
                handoff_target = str(semantic_output.get("handoff_target", ""))
            return {
                "tool_policy": "runtime_may_handoff_to_executor",
                "tool_call_requests": tool_requests,
                "reason": "execution planning is a runtime boundary, not a pure semantic hook",
            }
        if stage == "memory_and_graph_update":
            return {
                "tool_policy": "runtime_may_write_memory_and_graph_after_policy_check",
                "tool_call_requests": tool_requests,
                "reason": "agents propose updates; runtime applies or logs them",
            }
        return {
            "tool_policy": "runtime_resolves_declared_capabilities" if tool_requests else "no_default_tool_call",
            "tool_call_requests": tool_requests,
            "reason": "stage can be completed by agent hook unless runtime policy adds tools",
        }

    def resolve_tool_capabilities(self, stage_plan: dict[str, Any]) -> list[dict[str, Any]]:
        stage = str(stage_plan.get("stage", ""))
        capabilities = stage_plan.get("tool_capabilities", [])
        if not isinstance(capabilities, list):
            return []
        requests: list[dict[str, Any]] = []
        for capability in capabilities:
            if not isinstance(capability, dict):
                continue
            name = str(capability.get("capability", "")).strip()
            if not name:
                continue
            requests.append(
                ScientificAgentToolCallRequest(
                    stage=stage,
                    capability=name,
                    intent=str(capability.get("intent", "")).strip(),
                    candidate_tools=self.candidate_tools_for_capability(name),
                    arguments=capability.get("arguments", {}) if isinstance(capability.get("arguments", {}), dict) else {},
                    required=bool(capability.get("required")),
                    execution_mode=self.execution_mode_for_capability(name),
                    capability_pack=self.capability_registry.pack(name),
                ).to_dict()
            )
        return requests

    def candidate_tools_for_capability(self, capability: str) -> list[str]:
        return self.capability_registry.resolve_tools(capability)

    def execution_mode_for_capability(self, capability: str) -> str:
        return self.capability_registry.execution_mode(capability)

    async def execute_tool_call_requests(self, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not requests:
            return []
        if not self.policy.allow_tool_execution:
            return [
                ScientificAgentToolCallResult(
                    stage=str(request.get("stage", "")),
                    capability=str(request.get("capability", "")),
                    status="skipped_tool_execution_disabled_by_policy",
                    arguments=request.get("arguments", {}) if isinstance(request.get("arguments", {}), dict) else {},
                ).to_dict()
                for request in requests
            ]
        if self.tools is None:
            return [
                ScientificAgentToolCallResult(
                    stage=str(request.get("stage", "")),
                    capability=str(request.get("capability", "")),
                    status="skipped_no_tool_registry",
                    arguments=request.get("arguments", {}) if isinstance(request.get("arguments", {}), dict) else {},
                ).to_dict()
                for request in requests
            ]
        if self.tool_context is None:
            return [
                ScientificAgentToolCallResult(
                    stage=str(request.get("stage", "")),
                    capability=str(request.get("capability", "")),
                    status="skipped_no_tool_context",
                    arguments=request.get("arguments", {}) if isinstance(request.get("arguments", {}), dict) else {},
                ).to_dict()
                for request in requests
            ]

        results: list[dict[str, Any]] = []
        for request in requests:
            results.append(await self.execute_tool_call_request(request))
        return results

    async def execute_tool_call_request(self, request: dict[str, Any]) -> dict[str, Any]:
        from ..tools import record_execution_log

        stage = str(request.get("stage", ""))
        capability = str(request.get("capability", ""))
        arguments = request.get("arguments", {}) if isinstance(request.get("arguments", {}), dict) else {}
        policy_block = self.evaluate_tool_policy(request)
        if policy_block:
            return ScientificAgentToolCallResult(
                stage=stage,
                capability=capability,
                status=policy_block,
                arguments=arguments,
            ).to_dict()
        selected_tool = self.select_registered_tool(request)
        if not selected_tool:
            return ScientificAgentToolCallResult(
                stage=stage,
                capability=capability,
                status="skipped_no_registered_candidate_tool",
                arguments=arguments,
            ).to_dict()
        try:
            tool = self.tools.get(selected_tool)
            tool_block = self.evaluate_registered_tool_policy(request, tool)
            if tool_block:
                return ScientificAgentToolCallResult(
                    stage=stage,
                    capability=capability,
                    selected_tool=selected_tool,
                    status=tool_block,
                    arguments=arguments,
                ).to_dict()
            validated = tool.validate(dict(arguments))
            output = await tool.call(validated, self.tool_context)
            execution_log = record_execution_log(
                self.tool_context,
                task_id=f"{self.runtime_id}:{stage}:{capability}",
                tool_name=selected_tool,
                arguments=validated,
                result=output,
            )
            return ScientificAgentToolCallResult(
                stage=stage,
                capability=capability,
                selected_tool=selected_tool,
                status="completed",
                arguments=validated,
                result=output,
                execution_log=execution_log,
            ).to_dict()
        except Exception as exc:
            execution_log = {}
            try:
                execution_log = record_execution_log(
                    self.tool_context,
                    task_id=f"{self.runtime_id}:{stage}:{capability}",
                    tool_name=selected_tool,
                    arguments=arguments,
                    error=str(exc),
                )
            except Exception:
                execution_log = {}
            return ScientificAgentToolCallResult(
                stage=stage,
                capability=capability,
                selected_tool=selected_tool,
                status="failed",
                arguments=arguments,
                error=str(exc),
                execution_log=execution_log,
            ).to_dict()

    def evaluate_tool_policy(self, request: dict[str, Any]) -> str:
        capability = str(request.get("capability", "")).strip()
        if capability in set(self.policy.blocked_capabilities):
            return "skipped_blocked_capability"
        if self.policy.allowed_capabilities and capability not in set(self.policy.allowed_capabilities):
            return "skipped_capability_not_allowed"
        if capability in set(self.policy.approval_required_capabilities) or self.capability_registry.requires_approval(capability):
            return "skipped_requires_approval"
        return ""

    def evaluate_registered_tool_policy(self, request: dict[str, Any], tool: Any) -> str:
        if tool.name in set(self.policy.blocked_tools):
            return "skipped_blocked_tool"
        if self.policy.execute_read_only_tools_only and not bool(getattr(tool, "read_only", False)):
            return "skipped_non_read_only_tool"
        if bool(getattr(tool, "destructive", False)):
            return "skipped_destructive_tool"
        return ""

    def select_registered_tool(self, request: dict[str, Any]) -> str:
        if self.tools is None:
            return ""
        candidates = request.get("candidate_tools", [])
        if not isinstance(candidates, list):
            return ""
        available = {tool.name for tool in self.tools.all()}
        for name in candidates:
            normalized = str(name).strip()
            if normalized in available:
                return normalized
        return ""

    def build_tool_result_events(
        self,
        *,
        agent_id: str,
        tool_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not tool_results:
            return []
        return [
            {
                "event_type": "scientific_agent_tool_calls_completed",
                "runtime_id": self.runtime_id,
                "agent_id": agent_id,
                "completed_count": sum(1 for result in tool_results if result.get("status") == "completed"),
                "failed_count": sum(1 for result in tool_results if result.get("status") == "failed"),
                "skipped_count": sum(1 for result in tool_results if str(result.get("status", "")).startswith("skipped")),
            }
        ]

    def select_runtime_state_after_tools(self, result: ScientificAgentRuntimeResult) -> str:
        if not result.tool_call_results:
            return result.runtime_state
        if any(item.get("status") == "failed" for item in result.tool_call_results):
            return "tool_execution_failed"
        if any(str(item.get("status", "")).startswith("skipped") for item in result.tool_call_results):
            return "tool_execution_partially_skipped"
        return result.runtime_state

    def attach_tool_results_to_lifecycle(
        self,
        lifecycle: dict[str, Any],
        tool_results: list[dict[str, Any]],
    ) -> None:
        if not tool_results:
            return
        stage_results = lifecycle.get("stage_results", {})
        if not isinstance(stage_results, dict):
            return
        by_stage: dict[str, list[dict[str, Any]]] = {}
        for result in tool_results:
            stage = str(result.get("stage", "")).strip()
            if stage:
                by_stage.setdefault(stage, []).append(result)
        for stage, results in by_stage.items():
            stage_plan = stage_results.get(stage)
            if not isinstance(stage_plan, dict):
                continue
            runtime = stage_plan.setdefault("runtime", {})
            if isinstance(runtime, dict):
                runtime["tool_call_results"] = results
                runtime["tool_result_summary"] = {
                    "completed": sum(1 for item in results if item.get("status") == "completed"),
                    "failed": sum(1 for item in results if item.get("status") == "failed"),
                    "skipped": sum(1 for item in results if str(item.get("status", "")).startswith("skipped")),
                }

    def stage_execution_boundary(self, stage_plan: dict[str, Any]) -> dict[str, Any]:
        transition = stage_plan.get("transition", {}) if isinstance(stage_plan.get("transition", {}), dict) else {}
        return {
            "agent_returns": ["prompt", "output_contract", "semantic_output", "transition"],
            "runtime_may_add": ["tool_calls", "model_calls", "memory_writes", "graph_writes", "executor_handoffs"],
            "requires_external_execution": bool(transition.get("requires_external_execution")),
            "records_memory_or_graph": bool(transition.get("records_memory_or_graph")),
        }

    def extract_tool_call_requests(self, lifecycle: dict[str, Any]) -> list[dict[str, Any]]:
        requests: list[dict[str, Any]] = []
        for stage in lifecycle.get("stage_results", {}).values():
            if not isinstance(stage, dict):
                continue
            runtime = stage.get("runtime", {}) if isinstance(stage.get("runtime", {}), dict) else {}
            tool_call_plan = runtime.get("tool_call_plan", {}) if isinstance(runtime.get("tool_call_plan", {}), dict) else {}
            stage_requests = tool_call_plan.get("tool_call_requests", [])
            if isinstance(stage_requests, list):
                requests.extend(item for item in stage_requests if isinstance(item, dict))
        return requests

    def extract_memory_and_graph_requests(
        self,
        lifecycle: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        stage = self._stage(lifecycle, "memory_and_graph_update")
        semantic_output = stage.get("semantic_output", {}) if isinstance(stage, dict) else {}
        if not isinstance(semantic_output, dict):
            return [], []
        memory_policy = semantic_output.get("memory_update_policy", {})
        graph_policy = semantic_output.get("graph_update_policy", {})
        memory_requests = [
            {
                "kind": "memory_update_request",
                "stage": "memory_and_graph_update",
                "policy": memory_policy,
            }
        ] if memory_policy else []
        graph_requests = [
            {
                "kind": "graph_update_request",
                "stage": "memory_and_graph_update",
                "policy": graph_policy,
            }
        ] if graph_policy else []
        return memory_requests, graph_requests

    def extract_external_execution_requests(self, lifecycle: dict[str, Any]) -> list[dict[str, Any]]:
        requests: list[dict[str, Any]] = []
        for stage_name, stage in lifecycle.get("stage_results", {}).items():
            if not isinstance(stage, dict):
                continue
            transition = stage.get("transition", {}) if isinstance(stage.get("transition", {}), dict) else {}
            if not transition.get("requires_external_execution"):
                continue
            requests.append(
                {
                    "kind": "external_execution_request",
                    "stage": str(stage_name),
                    "hook": str(stage.get("hook", "")),
                    "semantic_output": stage.get("semantic_output", {}),
                }
            )
        return requests

    def build_trajectory_events(
        self,
        *,
        lifecycle: dict[str, Any],
        records: list[ScientificAgentStageExecutionRecord],
        tool_requests: list[dict[str, Any]],
        memory_requests: list[dict[str, Any]],
        graph_requests: list[dict[str, Any]],
        external_requests: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        agent_id = str(lifecycle.get("agent_id", ""))
        events = [
            {
                "event_type": "scientific_agent_runtime_started",
                "runtime_id": self.runtime_id,
                "agent_id": agent_id,
                "discipline": lifecycle.get("discipline", ""),
                "task_type": lifecycle.get("task_type", ""),
            }
        ]
        events.extend(
            {
                "event_type": "scientific_agent_stage_planned",
                "runtime_id": self.runtime_id,
                "agent_id": agent_id,
                "stage": record.stage,
                "hook": record.hook,
                "requires_external_execution": record.requires_external_execution,
                "records_memory_or_graph": record.records_memory_or_graph,
            }
            for record in records
        )
        if tool_requests:
            events.append(
                {
                    "event_type": "scientific_agent_tool_calls_requested",
                    "runtime_id": self.runtime_id,
                    "agent_id": agent_id,
                    "request_count": len(tool_requests),
                    "capabilities": sorted(
                        {
                            str(request.get("capability", "")).strip()
                            for request in tool_requests
                            if str(request.get("capability", "")).strip()
                        }
                    ),
                }
            )
        for request in external_requests:
            events.append(
                {
                    "event_type": "scientific_agent_external_execution_requested",
                    "runtime_id": self.runtime_id,
                    "agent_id": agent_id,
                    "stage": request.get("stage", ""),
                }
            )
        if memory_requests:
            events.append(
                {
                    "event_type": "scientific_agent_memory_update_requested",
                    "runtime_id": self.runtime_id,
                    "agent_id": agent_id,
                    "request_count": len(memory_requests),
                }
            )
        if graph_requests:
            events.append(
                {
                    "event_type": "scientific_agent_graph_update_requested",
                    "runtime_id": self.runtime_id,
                    "agent_id": agent_id,
                    "request_count": len(graph_requests),
                }
            )
        events.append(
            {
                "event_type": "scientific_agent_runtime_completed",
                "runtime_id": self.runtime_id,
                "agent_id": agent_id,
                "lifecycle_state": lifecycle.get("lifecycle_state", ""),
                "next_stage": lifecycle.get("next_stage", ""),
            }
        )
        return events

    def select_runtime_state(self, lifecycle_result: ScientificAgentLifecycleResult) -> str:
        if lifecycle_result.lifecycle_state == "blocked":
            return "blocked"
        if lifecycle_result.next_stage == "execution_planning":
            return "awaiting_external_execution"
        return "planned"

    def runtime_boundary(self) -> dict[str, Any]:
        return {
            "composition_model": "runtime_wraps_scientific_agent",
            "capability_registry": self.capability_registry.to_dict(),
            "runtime_owns": [
                "single-agent lifecycle orchestration",
                "stage execution records",
                "tool and model call insertion",
                "tool execution policy enforcement",
                "tool capability resolution",
                "tool result feedback into lifecycle stages",
                "trajectory events",
                "memory and graph update requests",
                "external execution requests",
                "future replay and training data capture",
            ],
            "agent_owns": [
                "scientific lifecycle stage definitions",
                "tool capability declarations",
                "discipline-specific hooks",
                "hypothesis and evidence interpretation",
                "quality gates and next-action policy",
            ],
            "not_a_base_class_reason": "runtime infrastructure should be replaceable without changing scientific agent inheritance",
        }

    def _stage(self, lifecycle: dict[str, Any], stage: str) -> dict[str, Any]:
        stage_results = lifecycle.get("stage_results", {})
        if not isinstance(stage_results, dict):
            return {}
        value = stage_results.get(stage, {})
        return value if isinstance(value, dict) else {}


