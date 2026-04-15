from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class StageExecutionMode:
    """How a scientific lifecycle stage should be produced and governed."""

    llm_profile_driven: bool = True
    schema_driven: bool = True
    quality_gate_driven: bool = False
    capability_registry_driven: bool = False
    runtime_policy_driven: bool = False
    executor_handoff_driven: bool = False
    hook_override_allowed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StageSpec:
    """Stable lifecycle stage contract shared by scientific agents."""

    name: str
    hook: str
    goal: str
    output_contract: list[str] = field(default_factory=list)
    execution_mode: StageExecutionMode = field(default_factory=StageExecutionMode)
    default_capabilities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StagePlan:
    """Runtime-ready plan emitted by a ScientificAgent for one stage."""

    stage: str
    state: str
    hook: str
    prompt: dict[str, Any]
    output_contract: list[str]
    semantic_output: Any
    tool_capabilities: list[dict[str, Any]] = field(default_factory=list)
    transition: dict[str, Any] = field(default_factory=dict)
    execution_mode: dict[str, Any] = field(default_factory=dict)
    profile: dict[str, Any] = field(default_factory=dict)
    task: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
