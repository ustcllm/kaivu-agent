from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from ..tools import ToolRegistry
from .client import MCPClient
from .tool_adapter import MCPToolAdapter
from .types import MCPPromptSpec, MCPResourceSpec, MCPServerConfig


@dataclass(slots=True)
class MCPDiscoveryCatalog:
    tools: dict[str, list[str]] = field(default_factory=dict)
    resources: dict[str, list[MCPResourceSpec]] = field(default_factory=dict)
    prompts: dict[str, list[MCPPromptSpec]] = field(default_factory=dict)


class MCPRegistry:
    def __init__(self, configs: Iterable[MCPServerConfig] | None = None) -> None:
        self.configs = list(configs or [])
        self.clients: dict[str, MCPClient] = {}
        self.catalog = MCPDiscoveryCatalog()

    async def start(self) -> None:
        for config in self.configs:
            client = MCPClient(config)
            await client.start()
            self.clients[config.name] = client
        await self.refresh_catalog()

    async def close(self) -> None:
        for client in self.clients.values():
            await client.close()
        self.clients.clear()
        self.catalog = MCPDiscoveryCatalog()

    async def build_tool_registry(self) -> ToolRegistry:
        tools = []
        for client in self.clients.values():
            specs = await client.list_tools()
            tools.extend(MCPToolAdapter(client, spec) for spec in specs)
        return ToolRegistry(tools)

    async def refresh_catalog(self) -> None:
        catalog = MCPDiscoveryCatalog()
        for client in self.clients.values():
            try:
                tool_specs = await client.list_tools()
            except Exception:
                tool_specs = []
            try:
                resource_specs = await client.list_resources()
            except Exception:
                resource_specs = []
            try:
                prompt_specs = await client.list_prompts()
            except Exception:
                prompt_specs = []
            catalog.tools[client.config.name] = [spec.name for spec in tool_specs]
            catalog.resources[client.config.name] = resource_specs
            catalog.prompts[client.config.name] = prompt_specs
        self.catalog = catalog

    async def read_resource(self, server_name: str, uri: str) -> dict:
        client = self.clients[server_name]
        return await client.read_resource(uri)

    async def get_prompt(
        self,
        server_name: str,
        prompt_name: str,
        arguments: dict | None = None,
    ) -> dict:
        client = self.clients[server_name]
        return await client.get_prompt(prompt_name, arguments)

    def build_prompt_instructions(self, topic: str = "") -> str:
        lines: list[str] = []
        if topic:
            lines.append(f"MCP context for topic: {topic}")
            lines.append("")
        for server_name, tool_names in sorted(self.catalog.tools.items()):
            lines.append(f"Server: {server_name}")
            if tool_names:
                lines.append(f"- tools: {', '.join(sorted(tool_names))}")
            resources = self.catalog.resources.get(server_name, [])
            if resources:
                lines.append("- resources:")
                for resource in resources[:5]:
                    description = f" - {resource.description}" if resource.description else ""
                    lines.append(
                        f"  - {resource.name} ({resource.uri}){description}"
                    )
            prompts = self.catalog.prompts.get(server_name, [])
            if prompts:
                lines.append("- prompts:")
                for prompt in prompts[:5]:
                    arg_names = [
                        str(argument.get("name", "arg"))
                        for argument in prompt.arguments
                    ]
                    argument_text = (
                        f" args={', '.join(arg_names)}" if arg_names else ""
                    )
                    description = f" - {prompt.description}" if prompt.description else ""
                    lines.append(
                        f"  - {prompt.name}{argument_text}{description}"
                    )
            lines.append("")
        return "\n".join(lines).strip()


