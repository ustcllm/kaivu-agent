from __future__ import annotations

from typing import Any

from ..tools import Tool, ToolContext
from .client import MCPClient
from .types import MCPToolSpec


class MCPToolAdapter(Tool):
    def __init__(self, client: MCPClient, spec: MCPToolSpec) -> None:
        self.client = client
        self.server_name = spec.server_name
        self.spec = spec
        self.name = f"mcp__{spec.server_name}__{spec.name}"
        self.description = spec.description or f"MCP tool {spec.name} from {spec.server_name}"
        self.parameters_schema = spec.input_schema or {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        }
        self.read_only = spec.name in client.config.read_only_tools
        self.destructive = spec.name in client.config.destructive_tools
        self.concurrency_safe = self.read_only or not self.destructive

    def validate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return arguments

    async def call(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        result = await self.client.call_tool(self.spec.name, arguments)
        return {
            "server": result.server_name,
            "tool": result.tool_name,
            "is_error": result.is_error,
            "content": result.content,
        }
