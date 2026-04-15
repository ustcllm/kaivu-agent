from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class RuntimeManifest:
    run_id: str
    agent_name: str
    model: str = ""
    topic: str = ""
    project_id: str = ""
    user_id: str = ""
    group_id: str = ""
    prompt_sha256: str = ""
    memory_namespace: str = ""
    tool_names: list[str] = field(default_factory=list)
    workspace: dict[str, Any] = field(default_factory=dict)
    permission_policy: dict[str, Any] = field(default_factory=dict)
    usage_summary: dict[str, Any] = field(default_factory=dict)
    trajectory: dict[str, Any] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    status: str = "completed"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RuntimeManifestStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, manifest: RuntimeManifest) -> Path:
        path = self.root / f"{_safe_name(manifest.run_id)}.json"
        path.write_text(
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return path

    def latest(self) -> dict[str, Any] | None:
        files = sorted(self.root.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        for path in files:
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(value, dict):
                value["_path"] = str(path)
                return value
        return None

    def list(self, *, limit: int = 50) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        files = sorted(self.root.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        for path in files[: max(1, min(limit, 500))]:
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(value, dict):
                value["_path"] = str(path)
                rows.append(value)
        return rows


def build_runtime_manifest_summary(manifest: RuntimeManifest) -> dict[str, Any]:
    return {
        "run_id": manifest.run_id,
        "agent_name": manifest.agent_name,
        "model": manifest.model,
        "project_id": manifest.project_id,
        "tool_count": len(manifest.tool_names),
        "memory_namespace": manifest.memory_namespace,
        "status": manifest.status,
        "usage_summary": manifest.usage_summary,
    }


def _safe_name(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value).strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "runtime-manifest"


