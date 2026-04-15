from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ScientificAgentConfig:
    name: str
    role: str
    model: str = ""
    autonomy_level: str = "L2"
    memory_namespace: str = ""
    allowed_tools: list[str] = field(default_factory=list)
    denied_tools: list[str] = field(default_factory=list)
    required_skills: list[str] = field(default_factory=list)
    workspace_scope: str = "project"
    tool_policy: str = "observe"
    review_required_actions: list[str] = field(default_factory=list)
    notes: str = ""

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ScientificAgentConfig":
        return cls(
            name=str(value.get("name", "")).strip() or "scientific-agent",
            role=str(value.get("role", "")).strip() or "General scientific agent.",
            model=str(value.get("model", "")).strip(),
            autonomy_level=str(value.get("autonomy_level", "L2")).strip() or "L2",
            memory_namespace=str(value.get("memory_namespace", "")).strip(),
            allowed_tools=[str(item) for item in value.get("allowed_tools", []) if str(item).strip()],
            denied_tools=[str(item) for item in value.get("denied_tools", []) if str(item).strip()],
            required_skills=[str(item) for item in value.get("required_skills", []) if str(item).strip()],
            workspace_scope=str(value.get("workspace_scope", "project")).strip() or "project",
            tool_policy=str(value.get("tool_policy", "observe")).strip() or "observe",
            review_required_actions=[
                str(item) for item in value.get("review_required_actions", []) if str(item).strip()
            ],
            notes=str(value.get("notes", "")).strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def fingerprint(self) -> str:
        payload = json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_agent_config(path: str | Path) -> ScientificAgentConfig:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("agent config must be a JSON object")
    return ScientificAgentConfig.from_dict(value)


def save_agent_config(config: ScientificAgentConfig, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(config.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return target


def render_agent_config_prompt(config: ScientificAgentConfig) -> str:
    lines = [
        f"Agent name: {config.name}",
        f"Role: {config.role}",
        f"Autonomy level: {config.autonomy_level}",
        f"Workspace scope: {config.workspace_scope}",
        f"Tool policy mode: {config.tool_policy}",
    ]
    if config.allowed_tools:
        lines.append(f"Allowed tools: {', '.join(config.allowed_tools)}")
    if config.denied_tools:
        lines.append(f"Denied tools: {', '.join(config.denied_tools)}")
    if config.required_skills:
        lines.append(f"Required skills: {', '.join(config.required_skills)}")
    if config.review_required_actions:
        lines.append(f"Review-required actions: {', '.join(config.review_required_actions)}")
    if config.notes:
        lines.append(f"Notes: {config.notes}")
    return "\n".join(lines)


