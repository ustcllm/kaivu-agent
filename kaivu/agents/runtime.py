from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..engine import AgentRunResult, ToolCallingAgent
from ..memory import MemoryManager
from ..model import ModelBackend
from ..permissions import PermissionPolicy
from ..prompts import PromptBuildInput, PromptBuilder
from ..runtime.manifest import RuntimeManifest, RuntimeManifestStore
from ..runtime.workspace import WorkspaceBoundary
from ..tools import ToolRegistry
from .config import ScientificAgentConfig, render_agent_config_prompt


@dataclass(slots=True)
class SubagentSpec:
    name: str
    system_prompt: str
    tools: ToolRegistry
    model: ModelBackend
    task_prompt: str
    config: ScientificAgentConfig | None = None
    skill_prompt: str = ""
    workflow_state: str = ""
    schema_instruction: str = ""
    mcp_instructions: str = ""
    safety_policy: str = ""
    memory_namespace: str = ""
    collaboration_context: dict[str, str] | None = None


@dataclass(slots=True)
class SubagentResult:
    name: str
    prompt: str
    result: AgentRunResult
    manifest_path: str = ""


class SubagentRuntime:
    def __init__(
        self,
        *,
        cwd: str | Path,
        permission_policy: PermissionPolicy | None = None,
        memory_manager: MemoryManager | None = None,
        memory_root: str | Path | None = None,
        state_root: str | Path | None = None,
    ) -> None:
        self.cwd = Path(cwd).resolve()
        self.memory_root = Path(memory_root).resolve() if memory_root else None
        self.state_root = Path(state_root).resolve() if state_root else self.cwd / ".state"
        self.permission_policy = permission_policy or PermissionPolicy()
        self.memory_manager = memory_manager or MemoryManager(
            self.cwd,
            memory_root=self.memory_root,
            state_root=self.state_root,
        )
        self.prompt_builder = PromptBuilder()
        self.manifest_store = RuntimeManifestStore(self.state_root / "runtime_manifests")

    async def run_subagent(self, spec: SubagentSpec) -> SubagentResult:
        config = spec.config or ScientificAgentConfig(
            name=spec.name,
            role=spec.system_prompt,
            model=spec.model.__class__.__name__,
            memory_namespace=spec.memory_namespace or spec.name,
        )
        tools = spec.tools
        if config.allowed_tools:
            tools = tools.subset(config.allowed_tools)
        for denied in config.denied_tools:
            if denied in self.permission_policy.allow_tools:
                self.permission_policy.allow_tools.remove(denied)
            self.permission_policy.deny_tools.add(denied)
        if config.autonomy_level:
            self.permission_policy.scientific_autonomy_level = config.autonomy_level
        if config.tool_policy == "enforce":
            self.permission_policy.enforce_scientific_tool_policy = True

        agent_memory = MemoryManager(
            self.cwd,
            agent_namespace=config.memory_namespace or spec.memory_namespace or spec.name,
            memory_root=self.memory_root,
            state_root=self.state_root,
        )
        config_prompt = render_agent_config_prompt(config)
        prompt = self.prompt_builder.build(
            PromptBuildInput(
                base_role=spec.system_prompt,
                memory=agent_memory.build_system_memory_prompt(),
                workflow_state=spec.workflow_state,
                skill_prompt="\n\n".join(part for part in [config_prompt, spec.skill_prompt] if part),
                schema_instruction=spec.schema_instruction,
                mcp_instructions=spec.mcp_instructions,
                safety_policy=spec.safety_policy,
            )
        )
        agent = ToolCallingAgent(
            model=spec.model,
            tools=tools,
            cwd=self.cwd,
            system_prompt=prompt,
            permission_policy=self.permission_policy,
            memory_manager=agent_memory,
        )
        result = await agent.run(
            spec.task_prompt,
            collaboration_context=spec.collaboration_context or {},
        )
        manifest_path = self._save_manifest(
            spec=spec,
            config=config,
            prompt=prompt,
            result=result,
            tools=tools,
        )
        return SubagentResult(name=spec.name, prompt=prompt, result=result, manifest_path=str(manifest_path))

    async def run_subagents(self, specs: list[SubagentSpec]) -> list[SubagentResult]:
        if not specs:
            return []
        return list(await asyncio.gather(*(self.run_subagent(spec) for spec in specs)))

    def _save_manifest(
        self,
        *,
        spec: SubagentSpec,
        config: ScientificAgentConfig,
        prompt: str,
        result: AgentRunResult,
        tools: ToolRegistry,
    ) -> Path:
        context = spec.collaboration_context or {}
        run_id = context.get("run_id") or f"{config.name}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
        workspace = WorkspaceBoundary.for_project(
            self.cwd,
            project_id=str(context.get("project_id", "")),
            user_id=str(context.get("user_id", "")),
            group_id=str(context.get("group_id", "")),
        )
        manifest = RuntimeManifest(
            run_id=str(run_id),
            agent_name=config.name,
            model=config.model or spec.model.__class__.__name__,
            topic=str(context.get("topic", "")),
            project_id=str(context.get("project_id", "")),
            user_id=str(context.get("user_id", "")),
            group_id=str(context.get("group_id", "")),
            prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            memory_namespace=config.memory_namespace or spec.memory_namespace or spec.name,
            tool_names=[tool.name for tool in tools.all()],
            workspace=workspace.to_dict(),
            permission_policy=self.permission_policy.summary(),
            usage_summary=result.state.scratchpad.get("model_usage_totals", {}),
            trajectory={
                "message_count": len(result.state.messages),
                "task_count": len(result.state.tasks),
                "completed": bool(result.final_text),
            },
            artifacts=result.state.scratchpad.get("execution_records", []),
            status="completed" if result.final_text else "incomplete",
        )
        return self.manifest_store.save(manifest)


