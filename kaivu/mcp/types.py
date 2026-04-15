from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


TransportType = Literal["stdio"]


@dataclass(slots=True)
class MCPServerConfig:
    name: str
    transport: TransportType
    command: list[str]
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 60.0
    read_only_tools: list[str] = field(default_factory=list)
    destructive_tools: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MCPToolSpec:
    server_name: str
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(slots=True)
class MCPResourceSpec:
    server_name: str
    uri: str
    name: str
    description: str
    mime_type: str = ""


@dataclass(slots=True)
class MCPPromptSpec:
    server_name: str
    name: str
    description: str
    arguments: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class MCPToolCallResult:
    server_name: str
    tool_name: str
    content: Any
    is_error: bool = False


