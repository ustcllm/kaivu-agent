from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .memory import MemoryManager
from .messages import Message, ToolCall
from .model import AgentAction, ModelBackend
from .permissions import PermissionPolicy
from .state import AgentState
from .tool_permission import evaluate_scientific_tool_call
from .tools import ToolContext, ToolRegistry, record_execution_log


@dataclass(slots=True)
class AgentRunResult:
    final_text: str
    state: AgentState


class ToolCallingAgent:
    def __init__(
        self,
        *,
        model: ModelBackend,
        tools: ToolRegistry,
        cwd: str | Path,
        system_prompt: str,
        permission_policy: PermissionPolicy | None = None,
        max_turns: int = 8,
        memory_manager: MemoryManager | None = None,
    ) -> None:
        self.model = model
        self.tools = tools
        self.state = AgentState(cwd=Path(cwd).resolve())
        self.system_prompt = system_prompt
        self.permission_policy = permission_policy or PermissionPolicy()
        self.max_turns = max_turns
        self.state.add_message(Message(role="system", content=system_prompt))
        self.memory_manager = memory_manager or MemoryManager(self.state.cwd)
        self.runtime_event_stream: Any | None = None
        self.runtime_event_context: dict[str, Any] = {}
        memory_prompt = self.memory_manager.build_system_memory_prompt()
        if memory_prompt:
            self.state.add_message(Message(role="system", content=memory_prompt))

    async def run(
        self,
        user_prompt: str,
        *,
        collaboration_context: dict[str, str] | None = None,
    ) -> AgentRunResult:
        self.model.reset()
        collaboration_context = collaboration_context or {}
        self.runtime_event_stream = collaboration_context.get("_runtime_event_stream")
        self.runtime_event_context = collaboration_context
        self.state.session_meta.update(
            {
                key: value
                for key, value in collaboration_context.items()
                if key
                in {
                    "discipline",
                    "primary_discipline",
                    "project_id",
                    "group_id",
                    "user_id",
                    "topic",
                }
            }
        )
        query_memory = self.memory_manager.build_query_memory_context(
            user_prompt,
            user_id=collaboration_context.get("user_id"),
            project_id=collaboration_context.get("project_id"),
            group_id=collaboration_context.get("group_id"),
        )
        if query_memory:
            self.state.add_message(Message(role="system", content=query_memory))
        self.state.add_message(Message(role="user", content=user_prompt))
        final_text = ""

        for _ in range(self.max_turns):
            self._emit_runtime_event(
                "model.round.started",
                payload={
                    "message_count": len(self.state.messages),
                    "tool_count": len(self.tools.all()),
                    "memory_namespace": self.memory_manager.agent_namespace,
                },
            )
            action = await self.model.decide(self.state.messages, self._tool_specs())
            self._emit_runtime_event(
                "model.round.completed",
                payload={
                    "final": bool(action.final),
                    "tool_call_count": len(action.tool_calls),
                    "model": str(action.meta.get("model", "unknown")),
                    "response_id": str(action.meta.get("response_id", "") or ""),
                    "usage": action.meta.get("usage", {}) if isinstance(action.meta.get("usage", {}), dict) else {},
                },
            )
            self.state.add_message(
                Message(
                    role="assistant",
                    content=action.message,
                    tool_calls=action.tool_calls,
                    meta=action.meta,
                )
            )
            usage = action.meta.get("usage")
            if isinstance(usage, dict):
                usage_record = dict(usage)
                usage_record["model"] = action.meta.get("model", "unknown")
                usage_record["response_id"] = action.meta.get("response_id")
                self.state.record_model_usage(usage_record)
            if action.final and not action.tool_calls:
                final_text = action.message
                break
            if not action.tool_calls:
                final_text = action.message
                break
            await self._execute_tool_calls(action.tool_calls)
            if self.memory_manager.maybe_update_session_memory(
                self.state.messages,
                self.state.session_meta,
            ):
                self._emit_runtime_event(
                    "memory.session.updated",
                    payload={
                        "memory_namespace": self.memory_manager.agent_namespace,
                        "session_file": str(self.memory_manager.session_file),
                    },
                )
        else:
            final_text = "stopped: max_turns exceeded"

        if self.memory_manager.maybe_update_session_memory(
            self.state.messages,
            self.state.session_meta,
        ):
            self._emit_runtime_event(
                "memory.session.updated",
                payload={
                    "memory_namespace": self.memory_manager.agent_namespace,
                    "session_file": str(self.memory_manager.session_file),
                },
            )
        saved_memories = self.memory_manager.maybe_extract_long_term_memories(
            self.state.messages,
            self.state.session_meta,
            owner_agent=self.memory_manager.agent_namespace or "coordinator",
            user_id=collaboration_context.get("user_id", ""),
            project_id=collaboration_context.get("project_id", ""),
            group_id=collaboration_context.get("group_id", ""),
        )
        if saved_memories:
            self._emit_runtime_event(
                "memory.long_term.extracted",
                payload={
                    "memory_namespace": self.memory_manager.agent_namespace,
                    "saved_count": len(saved_memories),
                    "paths": [str(path) for path in saved_memories[:20]],
                },
            )
        return AgentRunResult(final_text=final_text, state=self.state)

    def _tool_specs(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters_schema,
                "read_only": tool.read_only,
                "destructive": tool.destructive,
                "concurrency_safe": tool.concurrency_safe,
            }
            for tool in self.tools.all()
        ]

    async def _execute_tool_calls(self, tool_calls: list[ToolCall]) -> None:
        current_batch: list[ToolCall] = []
        current_safe: bool | None = None

        def flush_needed(next_safe: bool) -> bool:
            return current_batch and (
                current_safe != next_safe or not next_safe or not current_safe
            )

        for call in tool_calls:
            tool = self.tools.get(call.name)
            if flush_needed(tool.concurrency_safe):
                await self._run_batch(current_batch, bool(current_safe))
                current_batch = []
                current_safe = None
            current_batch.append(call)
            current_safe = tool.concurrency_safe
            if not tool.concurrency_safe:
                await self._run_batch(current_batch, False)
                current_batch = []
                current_safe = None

        if current_batch:
            await self._run_batch(current_batch, bool(current_safe))

    async def _run_batch(self, batch: list[ToolCall], concurrency_safe: bool) -> None:
        if concurrency_safe:
            await asyncio.gather(*(self._run_one_tool_call(call) for call in batch))
            return
        for call in batch:
            await self._run_one_tool_call(call)

    async def _run_one_tool_call(self, call: ToolCall) -> None:
        tool = self.tools.get(call.name)
        arguments = tool.validate(call.arguments)
        decision = self.permission_policy.evaluate(
            tool_name=tool.name,
            arguments=arguments,
            is_destructive=tool.destructive,
            cwd=self.state.cwd,
        )
        scientific_decision = evaluate_scientific_tool_call(
            tool_name=tool.name,
            arguments=arguments,
            autonomy_level=self.permission_policy.scientific_autonomy_level,
            destructive=tool.destructive,
            enforce_review=self.permission_policy.enforce_scientific_tool_policy,
        )
        if not scientific_decision.allowed:
            decision.allowed = False
            decision.reason = scientific_decision.reason or (
                f"scientific tool policy blocked '{tool.name}'"
            )
        self._emit_runtime_event(
            "permission.decision",
            payload={
                "tool_call_id": call.id,
                "tool_name": tool.name,
                "allowed": bool(decision.allowed),
                "reason": decision.reason,
                "destructive": bool(tool.destructive),
                "scientific_tool_policy": scientific_decision.to_dict(),
            },
        )
        if not decision.allowed:
            self.state.add_message(
                Message(
                    role="tool",
                    content=json.dumps({"error": decision.reason}, ensure_ascii=False),
                    tool_call_id=call.id,
                    meta={"tool_name": tool.name, "allowed": False},
                )
            )
            return

        task = self.state.create_task("tool", f"{tool.name}: {arguments}")
        task.mark_running()
        self._emit_runtime_event(
            "tool.call.started",
            payload={
                "tool_call_id": call.id,
                "task_id": task.id,
                "tool_name": tool.name,
                "arguments": arguments,
                "concurrency_safe": bool(tool.concurrency_safe),
                "read_only": bool(tool.read_only),
                "destructive": bool(tool.destructive),
            },
        )
        try:
            tool_context = ToolContext(self.state, self.memory_manager)
            result = await tool.call(
                decision.updated_input or arguments,
                tool_context,
            )
            task.mark_completed(result)
            record_execution_log(
                tool_context,
                task_id=task.id,
                tool_name=tool.name,
                arguments=decision.updated_input or arguments,
                result=result,
            )
            payload = json.dumps(result, ensure_ascii=False, default=str)
            self._emit_runtime_event(
                "tool.call.completed",
                payload={
                    "tool_call_id": call.id,
                    "task_id": task.id,
                    "tool_name": tool.name,
                    "status": "completed",
                },
            )
        except Exception as exc:
            task.mark_failed(exc)
            record_execution_log(
                ToolContext(self.state, self.memory_manager),
                task_id=task.id,
                tool_name=tool.name,
                arguments=decision.updated_input or arguments,
                error=str(exc),
            )
            payload = json.dumps({"error": str(exc)}, ensure_ascii=False)
            self._emit_runtime_event(
                "tool.call.completed",
                payload={
                    "tool_call_id": call.id,
                    "task_id": task.id,
                    "tool_name": tool.name,
                    "status": "failed",
                    "error": str(exc),
                },
            )

        self.state.add_message(
            Message(
                role="tool",
                content=payload,
                tool_call_id=call.id,
                meta={"tool_name": tool.name, "allowed": True},
            )
        )

    def _emit_runtime_event(self, event_type: str, *, payload: dict[str, Any] | None = None) -> None:
        stream = self.runtime_event_stream
        if stream is None or not hasattr(stream, "emit"):
            return
        try:
            stream.emit(
                event_type,
                actor=self.memory_manager.agent_namespace or "kaivu",
                project_id=str(self.runtime_event_context.get("project_id", "")),
                user_id=str(self.runtime_event_context.get("user_id", "")),
                group_id=str(self.runtime_event_context.get("group_id", "")),
                payload=payload or {},
            )
        except Exception:
            return



