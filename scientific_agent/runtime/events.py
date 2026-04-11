from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4


@dataclass(slots=True)
class RuntimeEvent:
    event_id: str
    session_id: str
    event_type: str
    actor: str = "runtime"
    timestamp: str = ""
    project_id: str = ""
    user_id: str = ""
    group_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["timestamp"]:
            data["timestamp"] = datetime.now(timezone.utc).isoformat()
        return data


class RuntimeEventStream:
    def __init__(self, *, session_id: str, sink_path: str | Path | None = None) -> None:
        self.session_id = session_id
        self.sink_path = Path(sink_path).resolve() if sink_path else None
        self._subscribers: list[Callable[[RuntimeEvent], None]] = []
        self._events: list[RuntimeEvent] = []

    def subscribe(self, callback: Callable[[RuntimeEvent], None]) -> None:
        self._subscribers.append(callback)

    def emit(
        self,
        event_type: str,
        *,
        actor: str = "runtime",
        project_id: str = "",
        user_id: str = "",
        group_id: str = "",
        payload: dict[str, Any] | None = None,
    ) -> RuntimeEvent:
        event = RuntimeEvent(
            event_id=f"{event_type}::{uuid4()}",
            session_id=self.session_id,
            event_type=event_type,
            actor=actor,
            project_id=project_id,
            user_id=user_id,
            group_id=group_id,
            payload=payload or {},
        )
        self._events.append(event)
        if self.sink_path:
            self.sink_path.parent.mkdir(parents=True, exist_ok=True)
            with self.sink_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        for callback in list(self._subscribers):
            callback(event)
        return event

    def snapshot(self) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self._events]
