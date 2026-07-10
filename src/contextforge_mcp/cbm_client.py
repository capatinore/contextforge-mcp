"""Client for codebase-memory-mcp binary over stdio JSON-RPC 2.0."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CBM_TOOLS: list[str] = [
    "index_repository", "search_graph", "search_code", "trace_path",
    "trace_call_path", "get_architecture", "get_node_details", "find_dead_code",
    "find_similar_code", "get_impact", "cypher_query", "manage_adr",
    "get_cross_service_links", "get_indexing_status",
]

HIGH_TOKEN_TOOLS: set[str] = {
    "search_graph", "search_code", "get_architecture",
    "find_dead_code", "find_similar_code", "cypher_query",
}


class CBMClient:
    def __init__(self, binary_path: str | None = None):
        self.binary_path = binary_path or self._find_binary()
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if not self.binary_path:
            raise RuntimeError(
                "codebase-memory-mcp binary not found. "
                "Install with: npm install -g codebase-memory-mcp"
            )
        import sys
        use_shell = sys.platform == "win32" and self.binary_path.upper().endswith(".CMD")
        if use_shell:
            self._process = await asyncio.create_subprocess_shell(
                f'"{self.binary_path}"',
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        else:
            self._process = await asyncio.create_subprocess_exec(
                self.binary_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        await self._initialize()

    async def stop(self) -> None:
        if self._process and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()

    async def __aenter__(self) -> "CBMClient":
        await self.start()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.stop()

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if tool_name not in CBM_TOOLS:
            raise ValueError(f"Unknown CBM tool: {tool_name!r}")
        async with self._lock:
            return await self._send({
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            })

    def is_high_token_tool(self, tool_name: str) -> bool:
        return tool_name in HIGH_TOKEN_TOOLS

    @property
    def available(self) -> bool:
        return self.binary_path is not None

    async def _initialize(self) -> None:
        await self._send({
            "jsonrpc": "2.0", "id": self._next_id(), "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "contextforge-mcp", "version": "0.1.0"},
            },
        })
        await self._write({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    async def _send(self, payload: dict[str, Any]) -> Any:
        assert self._process and self._process.stdin and self._process.stdout
        await self._write(payload)
        target_id = payload.get("id")
        while True:
            line = await asyncio.wait_for(self._process.stdout.readline(), timeout=30.0)
            if not line:
                raise ConnectionError("codebase-memory-mcp subprocess closed")
            line = line.decode().strip()
            if not line:
                continue
            try:
                response = json.loads(line)
            except json.JSONDecodeError:
                continue
            if response.get("id") == target_id:
                if "error" in response:
                    raise RuntimeError(f"CBM error: {response['error']}")
                return response.get("result")

    async def _write(self, payload: dict[str, Any]) -> None:
        assert self._process and self._process.stdin
        self._process.stdin.write((json.dumps(payload) + "\n").encode())
        await self._process.stdin.drain()

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    @staticmethod
    def _find_binary() -> str | None:
        for name in ["codebase-memory-mcp", "codebase-memory-mcp.exe"]:
            found = shutil.which(name)
            if found:
                return found
        for p in [
            Path.home() / ".local" / "bin" / "codebase-memory-mcp",
            Path("/usr/local/bin/codebase-memory-mcp"),
        ]:
            if p.exists():
                return str(p)
        return None
