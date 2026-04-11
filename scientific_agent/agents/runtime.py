from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..engine import ScientificAgent, AgentRunResult
from ..memory import MemoryManager
from ..model import ModelBackend
from ..permissions import PermissionPolicy
from ..prompts import PromptBuildInput, PromptBuilder
from ..tools import ToolRegistry


@dataclass(slots=True)
class SubagentSpec:
    name: str
    system_prompt: str
    tools: ToolRegistry
    model: ModelBackend
    task_prompt: str
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


class SubagentRuntime:
    def __init__(
        self,
        *,
        cwd: str | Path,
        permission_policy: PermissionPolicy | None = None,
        memory_manager: MemoryManager | None = None,
    ) -> None:
        self.cwd = Path(cwd).resolve()
        self.permission_policy = permission_policy or PermissionPolicy()
        self.memory_manager = memory_manager or MemoryManager(self.cwd)
        self.prompt_builder = PromptBuilder()

    async def run_subagent(self, spec: SubagentSpec) -> SubagentResult:
        agent_memory = MemoryManager(
            self.cwd,
            agent_namespace=spec.memory_namespace or spec.name,
        )
        prompt = self.prompt_builder.build(
            PromptBuildInput(
                base_role=spec.system_prompt,
                memory=agent_memory.build_system_memory_prompt(),
                workflow_state=spec.workflow_state,
                skill_prompt=spec.skill_prompt,
                schema_instruction=spec.schema_instruction,
                mcp_instructions=spec.mcp_instructions,
                safety_policy=spec.safety_policy,
            )
        )
        agent = ScientificAgent(
            model=spec.model,
            tools=spec.tools,
            cwd=self.cwd,
            system_prompt=prompt,
            permission_policy=self.permission_policy,
            memory_manager=agent_memory,
        )
        result = await agent.run(
            spec.task_prompt,
            collaboration_context=spec.collaboration_context or {},
        )
        return SubagentResult(name=spec.name, prompt=prompt, result=result)

    async def run_subagents(self, specs: list[SubagentSpec]) -> list[SubagentResult]:
        if not specs:
            return []
        return list(await asyncio.gather(*(self.run_subagent(spec) for spec in specs)))
