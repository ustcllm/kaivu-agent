from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class RuntimeTrajectory:
    session_id: str
    topic: str = ""
    model: str = ""
    completed: bool = False
    messages: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    usage_summary: dict[str, Any] = field(default_factory=dict)
    evaluation_summary: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TrajectoryStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def append(self, trajectory: RuntimeTrajectory, *, filename: str = "runtime_trajectories.jsonl") -> Path:
        path = self.root / filename
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(trajectory.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        return path

    def load(self, *, filename: str = "runtime_trajectories.jsonl", limit: int = 100) -> list[dict[str, Any]]:
        path = self.root / filename
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except Exception:
                continue
            if isinstance(item, dict):
                rows.append(item)
        return rows[-max(1, min(limit, 1000)) :]
