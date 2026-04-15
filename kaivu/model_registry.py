from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any
import json

from .model import ModelBackend, OpenAIResponsesModel


@dataclass(slots=True)
class AgentModelConfig:
    model: str
    provider: str = "openai"
    reasoning_effort: str = "medium"
    max_output_tokens: int = 1600
    allow_web_search: bool | None = False
    parallel_tool_calls: bool | None = True
    timeout: int = 120
    base_url: str | None = None

    def merged_with(self, override: "AgentModelConfig") -> "AgentModelConfig":
        return AgentModelConfig(
            model=override.model or self.model,
            provider=override.provider or self.provider,
            reasoning_effort=override.reasoning_effort or self.reasoning_effort,
            max_output_tokens=override.max_output_tokens or self.max_output_tokens,
            allow_web_search=(
                override.allow_web_search
                if override.allow_web_search is not None
                else self.allow_web_search
            ),
            parallel_tool_calls=(
                override.parallel_tool_calls
                if override.parallel_tool_calls is not None
                else self.parallel_tool_calls
            ),
            timeout=override.timeout or self.timeout,
            base_url=override.base_url or self.base_url,
        )


class ModelRegistry:
    def __init__(
        self,
        *,
        default_model: str = "gpt-5",
        default_base_url: str = "https://api.openai.com/v1/responses",
    ) -> None:
        self.default_model = default_model
        self.default_base_url = default_base_url
        self.file_overrides: dict[str, AgentModelConfig] = {}

    def load_config_file(self, path: str | Path) -> None:
        config_path = Path(path).resolve()
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        agents = payload.get("agents", {})
        overrides: dict[str, AgentModelConfig] = {}
        for agent_name, item in agents.items():
            overrides[agent_name] = AgentModelConfig(
                model=str(item.get("model", self.default_model)),
                provider=str(item.get("provider", "openai")),
                reasoning_effort=str(item.get("reasoning_effort", "medium")),
                max_output_tokens=int(item.get("max_output_tokens", 1600)),
                allow_web_search=(
                    bool(item["allow_web_search"])
                    if "allow_web_search" in item
                    else None
                ),
                parallel_tool_calls=(
                    bool(item["parallel_tool_calls"])
                    if "parallel_tool_calls" in item
                    else None
                ),
                timeout=int(item.get("timeout", 120)),
                base_url=item.get("base_url"),
            )
        self.file_overrides = overrides

    def resolve_for_agent(
        self,
        agent_name: str,
        base_config: AgentModelConfig,
    ) -> AgentModelConfig:
        file_override = self.file_overrides.get(agent_name)
        if file_override is not None:
            base_config = base_config.merged_with(file_override)
        prefix = self._agent_env_prefix(agent_name)
        override_model = os.getenv(f"{prefix}_MODEL")
        override_reasoning = os.getenv(f"{prefix}_REASONING")
        override_provider = os.getenv(f"{prefix}_PROVIDER")
        override_tokens = os.getenv(f"{prefix}_MAX_OUTPUT_TOKENS")
        override_timeout = os.getenv(f"{prefix}_TIMEOUT")
        override_base_url = os.getenv(f"{prefix}_BASE_URL")
        if not any(
            [
                override_model,
                override_reasoning,
                override_provider,
                override_tokens,
                override_timeout,
                override_base_url,
            ]
        ):
            return base_config
        return AgentModelConfig(
            model=override_model or base_config.model,
            provider=override_provider or base_config.provider,
            reasoning_effort=override_reasoning or base_config.reasoning_effort,
            max_output_tokens=int(override_tokens) if override_tokens else base_config.max_output_tokens,
            allow_web_search=base_config.allow_web_search,
            parallel_tool_calls=base_config.parallel_tool_calls,
            timeout=int(override_timeout) if override_timeout else base_config.timeout,
            base_url=override_base_url or base_config.base_url,
        )

    def escalate_config(self, config: AgentModelConfig) -> AgentModelConfig:
        model = config.model
        reasoning = config.reasoning_effort
        if model.endswith("-mini"):
            model = model.removesuffix("-mini")
        elif model.endswith("-nano"):
            model = model.removesuffix("-nano")
        if reasoning == "low":
            reasoning = "medium"
        elif reasoning == "medium":
            reasoning = "high"
        return AgentModelConfig(
            model=model,
            provider=config.provider,
            reasoning_effort=reasoning,
            max_output_tokens=max(config.max_output_tokens, 2200),
            allow_web_search=config.allow_web_search,
            parallel_tool_calls=config.parallel_tool_calls,
            timeout=max(config.timeout, 180),
            base_url=config.base_url,
        )

    def build_backend(
        self,
        config: AgentModelConfig,
        *,
        allow_web_search_override: bool | None = None,
    ) -> ModelBackend:
        provider = config.provider.lower()
        if provider != "openai":
            raise ValueError(f"Unsupported model provider: {config.provider}")
        reasoning = {"effort": config.reasoning_effort} if config.reasoning_effort else None
        return OpenAIResponsesModel(
            model=config.model or self.default_model,
            base_url=config.base_url or self.default_base_url,
            allow_web_search=(
                allow_web_search_override
                if allow_web_search_override is not None
                else bool(config.allow_web_search)
            ),
            reasoning=reasoning,
            max_output_tokens=config.max_output_tokens,
            parallel_tool_calls=bool(config.parallel_tool_calls),
            timeout=config.timeout,
        )

    @staticmethod
    def describe_config(config: AgentModelConfig) -> dict[str, Any]:
        return {
            "provider": config.provider,
            "model": config.model,
            "reasoning_effort": config.reasoning_effort,
            "max_output_tokens": config.max_output_tokens,
            "allow_web_search": config.allow_web_search,
            "parallel_tool_calls": config.parallel_tool_calls,
            "timeout": config.timeout,
            "base_url": config.base_url,
        }

    @staticmethod
    def _agent_env_prefix(agent_name: str) -> str:
        slug = "".join(ch if ch.isalnum() else "_" for ch in agent_name.upper())
        return f"KAIVU_{slug}"



