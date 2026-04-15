from __future__ import annotations

import asyncio
from contextlib import suppress
import json
import os
from dataclasses import dataclass
from typing import Any

from .types import (
    MCPPromptSpec,
    MCPResourceSpec,
    MCPServerConfig,
    MCPToolCallResult,
    MCPToolSpec,
)


@dataclass(slots=True)
class _PendingRequest:
    future: asyncio.Future[dict[str, Any]]


class MCPClient:
    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._request_id = 0
        self._pending: dict[int, _PendingRequest] = {}

    async def start(self) -> None:
        if self._process is not None:
            return
        env = os.environ.copy()
        env.update(self.config.env)
        self._process = await asyncio.create_subprocess_exec(
            *self.config.command,
            cwd=self.config.cwd,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        await self._initialize()

    async def close(self) -> None:
        if self._reader_task is not None:
            self._reader_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._reader_task
        if self._process is not None:
            if self._process.stdin:
                self._process.stdin.close()
            with suppress(ProcessLookupError):
                self._process.terminate()
            await self._process.wait()
        self._process = None
        self._reader_task = None

    async def list_tools(self) -> list[MCPToolSpec]:
        result = await self._request("tools/list", {})
        tools = result.get("tools", [])
        return [
            MCPToolSpec(
                server_name=self.config.name,
                name=tool["name"],
                description=tool.get("description", ""),
                input_schema=tool.get(
                    "inputSchema",
                    {
                        "type": "object",
                        "properties": {},
                        "required": [],
                        "additionalProperties": False,
                    },
                ),
            )
            for tool in tools
        ]

    async def list_resources(self) -> list[MCPResourceSpec]:
        result = await self._request("resources/list", {})
        resources = result.get("resources", [])
        return [
            MCPResourceSpec(
                server_name=self.config.name,
                uri=resource["uri"],
                name=resource.get("name", resource["uri"]),
                description=resource.get("description", ""),
                mime_type=resource.get("mimeType", ""),
            )
            for resource in resources
        ]

    async def read_resource(self, uri: str) -> dict[str, Any]:
        return await self._request("resources/read", {"uri": uri})

    async def list_prompts(self) -> list[MCPPromptSpec]:
        result = await self._request("prompts/list", {})
        prompts = result.get("prompts", [])
        return [
            MCPPromptSpec(
                server_name=self.config.name,
                name=prompt["name"],
                description=prompt.get("description", ""),
                arguments=prompt.get("arguments", []),
            )
            for prompt in prompts
        ]

    async def get_prompt(
        self, prompt_name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return await self._request(
            "prompts/get",
            {"name": prompt_name, "arguments": arguments or {}},
        )

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> MCPToolCallResult:
        result = await self._request(
            "tools/call",
            {"name": tool_name, "arguments": arguments},
        )
        return MCPToolCallResult(
            server_name=self.config.name,
            tool_name=tool_name,
            content=result.get("content", result),
            is_error=bool(result.get("isError", False)),
        )

    async def _initialize(self) -> None:
        await self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "kaivu",
                    "version": "0.1.0",
                },
            },
        )
        await self._notify("notifications/initialized", {})

    async def _notify(self, method: str, params: dict[str, Any]) -> None:
        if self._process is None or self._process.stdin is None:
            raise RuntimeError("MCP client is not started")
        message = {"jsonrpc": "2.0", "method": method, "params": params}
        self._process.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
        await self._process.stdin.drain()

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._process is None or self._process.stdin is None:
            raise RuntimeError("MCP client is not started")
        self._request_id += 1
        request_id = self._request_id
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[request_id] = _PendingRequest(future=future)
        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        self._process.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
        await self._process.stdin.drain()
        try:
            return await asyncio.wait_for(
                future,
                timeout=self.config.timeout_seconds,
            )
        finally:
            self._pending.pop(request_id, None)

    async def _read_loop(self) -> None:
        if self._process is None or self._process.stdout is None:
            return
        while True:
            line = await self._process.stdout.readline()
            if not line:
                break
            try:
                payload = json.loads(line.decode("utf-8"))
            except Exception:
                continue
            if "id" not in payload:
                continue
            request_id = payload["id"]
            pending = self._pending.get(request_id)
            if pending is None:
                continue
            if "error" in payload:
                pending.future.set_exception(
                    RuntimeError(f"MCP error: {payload['error']}")
                )
            else:
                pending.future.set_result(payload.get("result", {}))


