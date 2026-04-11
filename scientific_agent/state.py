from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from time import time
from typing import Any, Literal
from uuid import uuid4

from .messages import Message


TaskStatus = Literal["pending", "running", "completed", "failed"]


@dataclass(slots=True)
class TaskRecord:
    kind: str
    description: str
    id: str = field(default_factory=lambda: uuid4().hex[:10])
    status: TaskStatus = "pending"
    started_at: float = field(default_factory=time)
    ended_at: float | None = None
    result: Any = None
    error: str | None = None

    def mark_running(self) -> None:
        self.status = "running"

    def mark_completed(self, result: Any) -> None:
        self.status = "completed"
        self.ended_at = time()
        self.result = result

    def mark_failed(self, error: Exception) -> None:
        self.status = "failed"
        self.ended_at = time()
        self.error = str(error)


@dataclass
class AgentState:
    cwd: Path
    messages: list[Message] = field(default_factory=list)
    tasks: dict[str, TaskRecord] = field(default_factory=dict)
    scratchpad: dict[str, Any] = field(default_factory=dict)
    session_meta: dict[str, Any] = field(default_factory=dict)

    def add_message(self, message: Message) -> None:
        self.messages.append(message)

    def create_task(self, kind: str, description: str) -> TaskRecord:
        task = TaskRecord(kind=kind, description=description)
        self.tasks[task.id] = task
        return task

    def record_model_usage(self, usage_record: dict[str, Any]) -> None:
        usage_log = self.scratchpad.setdefault("model_usage_records", [])
        usage_log.append(usage_record)

        totals = self.scratchpad.setdefault(
            "model_usage_totals",
            {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "estimated_cost_usd": 0.0,
                "rounds": 0,
            },
        )
        totals["input_tokens"] += int(usage_record.get("input_tokens", 0))
        totals["output_tokens"] += int(usage_record.get("output_tokens", 0))
        totals["total_tokens"] += int(usage_record.get("total_tokens", 0))
        totals["estimated_cost_usd"] = round(
            float(totals.get("estimated_cost_usd", 0.0))
            + float(usage_record.get("estimated_cost_usd", 0.0)),
            6,
        )
        totals["rounds"] += 1
