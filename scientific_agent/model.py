from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from urllib import error, request
from uuid import uuid4

from .messages import Message, ToolCall


MODEL_PRICING_PER_1M_TOKENS: dict[str, dict[str, float]] = {
    "gpt-5": {"input": 1.25, "output": 10.0},
    "gpt-5-mini": {"input": 0.25, "output": 2.0},
    "gpt-5-nano": {"input": 0.05, "output": 0.4},
}


@dataclass(slots=True)
class AgentAction:
    message: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    final: bool = False
    meta: dict[str, Any] = field(default_factory=dict)


class ModelBackend(ABC):
    def reset(self) -> None:
        """Optional hook for stateful backends."""

    @abstractmethod
    async def decide(self, messages: list[Message], tools: list[dict[str, Any]]) -> AgentAction:
        raise NotImplementedError


class StubScienceModel(ModelBackend):
    """
    一个不依赖外部 API 的演示模型。
    规则很简单，但足够演示智能体循环和工具调用。
    """

    async def decide(self, messages: list[Message], tools: list[dict[str, Any]]) -> AgentAction:
        last = messages[-1]
        if last.role == "user":
            if "文件" in last.content or "read" in last.content.lower():
                return AgentAction(
                    message="我先读取文件再继续。",
                    tool_calls=[
                        ToolCall(
                            id=uuid4().hex,
                            name="read_file",
                            arguments={"path": "demo_data/experiment.txt"},
                        )
                    ],
                )
            if "python" in last.content.lower() or "计算" in last.content:
                return AgentAction(
                    message="我先用 Python 做一次计算。",
                    tool_calls=[
                        ToolCall(
                            id=uuid4().hex,
                            name="python_exec",
                            arguments={
                                "code": "import math; print(sum(math.sqrt(i) for i in range(1, 6)))"
                            },
                        )
                    ],
                )
            return AgentAction(
                message="我先记录一个实验观察。",
                tool_calls=[
                    ToolCall(
                        id=uuid4().hex,
                        name="record_observation",
                        arguments={
                            "title": "initial hypothesis",
                            "observation": last.content,
                            "tags": ["user-goal"],
                        },
                    )
                ],
            )

        tool_messages = [m for m in messages if m.role == "tool"]
        if tool_messages:
            return AgentAction(
                message=f"已完成一步工具调用。最新结果如下：\n{tool_messages[-1].content}",
                final=True,
            )

        return AgentAction(message="没有更多动作。", final=True)


class OpenAIResponsesModel(ModelBackend):
    """
    A minimal OpenAI Responses API backend using the standard library only.
    It supports:
    - stateful response chaining via previous_response_id
    - built-in OpenAI tools such as web_search
    - custom function tools implemented by this framework
    """

    def __init__(
        self,
        *,
        model: str = "gpt-5",
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1/responses",
        allow_web_search: bool = False,
        web_search_domains: list[str] | None = None,
        reasoning: dict[str, Any] | None = None,
        max_output_tokens: int | None = 1600,
        parallel_tool_calls: bool = True,
        timeout: int = 120,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url
        self.allow_web_search = allow_web_search
        self.web_search_domains = web_search_domains or []
        self.reasoning = reasoning
        self.max_output_tokens = max_output_tokens
        self.parallel_tool_calls = parallel_tool_calls
        self.timeout = timeout
        self._previous_response_id: str | None = None
        self._seen_messages = 0

        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAIResponsesModel")

    def reset(self) -> None:
        self._previous_response_id = None
        self._seen_messages = 0

    async def decide(self, messages: list[Message], tools: list[dict[str, Any]]) -> AgentAction:
        instructions = messages[0].content if messages and messages[0].role == "system" else None
        payload = {
            "model": self.model,
            "input": self._build_input(messages),
            "tools": self._build_tools(tools),
            "parallel_tool_calls": self.parallel_tool_calls and not self.allow_web_search,
        }
        if instructions:
            payload["instructions"] = instructions
        if self._previous_response_id:
            payload["previous_response_id"] = self._previous_response_id
        if self.max_output_tokens is not None:
            payload["max_output_tokens"] = self.max_output_tokens
        if self.reasoning:
            payload["reasoning"] = self.reasoning

        response = await self._post(payload)
        self._previous_response_id = response["id"]
        self._seen_messages = len(messages)
        return self._to_agent_action(response)

    def _build_input(self, messages: list[Message]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for msg in messages[self._seen_messages :]:
            if msg.role == "system":
                continue
            if msg.role == "assistant":
                continue
            if msg.role == "tool":
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": msg.tool_call_id,
                        "output": msg.content,
                    }
                )
            else:
                items.append({"role": msg.role, "content": msg.content})
        return items

    def _build_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = [
            {
                "type": "function",
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"],
                "strict": True,
            }
            for tool in tools
        ]
        if self.allow_web_search:
            web_search: dict[str, Any] = {
                "type": "web_search",
                "search_context_size": "high",
            }
            if self.web_search_domains:
                web_search["filters"] = {"allowed_domains": self.web_search_domains}
            payload.append(web_search)
        return payload

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.base_url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI API error {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Failed to reach OpenAI API: {exc.reason}") from exc

    def _to_agent_action(self, response: dict[str, Any]) -> AgentAction:
        output = response.get("output", [])
        tool_calls: list[ToolCall] = []
        sources: list[str] = []
        final_chunks: list[str] = []

        for item in output:
            item_type = item.get("type")
            if item_type == "function_call":
                raw_args = item.get("arguments", "{}")
                tool_calls.append(
                    ToolCall(
                        id=item["call_id"],
                        name=item["name"],
                        arguments=json.loads(raw_args),
                    )
                )
            elif item_type == "message":
                for content in item.get("content", []):
                    text = content.get("text")
                    if text:
                        final_chunks.append(text)
            elif item_type == "web_search_call":
                action = item.get("action", {})
                for source in action.get("sources", []):
                    url = source.get("url")
                    if url:
                        sources.append(url)

        text = response.get("output_text") or "\n".join(chunk.strip() for chunk in final_chunks if chunk.strip())
        usage = _extract_usage(response, response.get("model", self.model))
        return AgentAction(
            message=text,
            tool_calls=tool_calls,
            final=not tool_calls,
            meta={
                "response_id": response.get("id"),
                "sources": sources,
                "model": response.get("model", self.model),
                "usage": usage,
            },
        )


def _extract_usage(response: dict[str, Any], model_name: str) -> dict[str, Any]:
    usage = response.get("usage", {}) or {}
    input_tokens = int(
        usage.get("input_tokens")
        or usage.get("prompt_tokens")
        or usage.get("input_text_tokens")
        or 0
    )
    output_tokens = int(
        usage.get("output_tokens")
        or usage.get("completion_tokens")
        or usage.get("output_text_tokens")
        or 0
    )
    total_tokens = int(usage.get("total_tokens") or (input_tokens + output_tokens))
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": _estimate_cost_usd(model_name, input_tokens, output_tokens),
    }


def _estimate_cost_usd(model_name: str, input_tokens: int, output_tokens: int) -> float:
    pricing = MODEL_PRICING_PER_1M_TOKENS.get(model_name) or MODEL_PRICING_PER_1M_TOKENS.get(
        _normalize_pricing_model_name(model_name)
    )
    if pricing is None:
        return 0.0
    return round(
        (input_tokens / 1_000_000.0) * pricing["input"]
        + (output_tokens / 1_000_000.0) * pricing["output"],
        6,
    )


def _normalize_pricing_model_name(model_name: str) -> str:
    lowered = str(model_name).strip().lower()
    for known in sorted(MODEL_PRICING_PER_1M_TOKENS, key=len, reverse=True):
        if lowered == known or lowered.startswith(f"{known}-"):
            return known
    return lowered
