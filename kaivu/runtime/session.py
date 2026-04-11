from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class RuntimeMessage:
    role: str
    content: str
    name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["created_at"]:
            data["created_at"] = datetime.now(timezone.utc).isoformat()
        return data


@dataclass(slots=True)
class RuntimeSession:
    session_id: str = field(default_factory=lambda: str(uuid4()))
    mode: str = "interactive"
    user_id: str = ""
    project_id: str = ""
    group_id: str = ""
    topic: str = ""
    messages: list[RuntimeMessage] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = ""

    def append_message(self, role: str, content: str, *, name: str = "", metadata: dict[str, Any] | None = None) -> None:
        self.messages.append(RuntimeMessage(role=role, content=content, name=name, metadata=metadata or {}))
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "mode": self.mode,
            "user_id": self.user_id,
            "project_id": self.project_id,
            "group_id": self.group_id,
            "topic": self.topic,
            "messages": [message.to_dict() for message in self.messages],
            "state": self.state,
            "created_at": self.created_at,
            "updated_at": self.updated_at or self.created_at,
        }
