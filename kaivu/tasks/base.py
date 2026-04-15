from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ScientificTask:
    """Normalized task input consumed by the shared scientific lifecycle."""

    task_id: str
    task_type: str
    topic: str
    discipline: str = "general_science"
    problem_statement: str = ""
    constraints: dict[str, Any] = field(default_factory=dict)
    inputs: dict[str, Any] = field(default_factory=dict)
    expected_outputs: dict[str, Any] = field(default_factory=dict)
    environment: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TaskAdapterResult:
    """Adapter output plus governance artifacts proposed for runtime handling."""

    task: ScientificTask
    memory_items: list[dict[str, Any]] = field(default_factory=list)
    graph_facts: list[dict[str, Any]] = field(default_factory=list)
    quality_gates: list[dict[str, Any]] = field(default_factory=list)
    capability_requirements: dict[str, list[str]] = field(default_factory=dict)
    adapter_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task.to_dict(),
            "memory_items": self.memory_items,
            "graph_facts": self.graph_facts,
            "quality_gates": self.quality_gates,
            "capability_requirements": self.capability_requirements,
            "adapter_metadata": self.adapter_metadata,
        }


class TaskAdapter:
    """Translate task-specific inputs into Kaivu's shared ScientificTask shape."""

    task_type = "general"
    discipline = "general_science"

    def adapt(self, data: dict[str, Any]) -> TaskAdapterResult:
        topic = str(data.get("topic", data.get("problem_statement", ""))).strip() or "untitled research task"
        return TaskAdapterResult(
            task=ScientificTask(
                task_id=str(data.get("task_id", self.task_type)).strip() or self.task_type,
                task_type=str(data.get("task_type", self.task_type)).strip() or self.task_type,
                topic=topic,
                discipline=str(data.get("discipline", self.discipline)).strip() or self.discipline,
                problem_statement=str(data.get("problem_statement", topic)).strip(),
                constraints=data.get("constraints", {}) if isinstance(data.get("constraints", {}), dict) else {},
                inputs=data.get("inputs", {}) if isinstance(data.get("inputs", {}), dict) else {},
                expected_outputs=data.get("expected_outputs", {}) if isinstance(data.get("expected_outputs", {}), dict) else {},
                environment=data.get("environment", {}) if isinstance(data.get("environment", {}), dict) else {},
                metadata=data.get("metadata", {}) if isinstance(data.get("metadata", {}), dict) else {},
            )
        )
