"""ContextForge MCP Server — codebase-memory-mcp + headroom + Spec Kit."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from .cbm_client import CBMClient, CBM_TOOLS
from .compressor import HeadroomCompressor
from .speckit import read_and_compress, implement_context, status as speckit_status

logging.basicConfig(level=os.environ.get("CF_LOG_LEVEL", "WARNING").upper())
logger = logging.getLogger("contextforge-mcp")

mcp = FastMCP("contextforge-mcp")

_cbm = CBMClient(binary_path=os.environ.get("CBM_BINARY_PATH"))
_compressor = HeadroomCompressor(
    model=os.environ.get("CF_MODEL", "claude-sonnet-4-6")
)


async def _cbm_call(tool_name: str, arguments: dict[str, Any]) -> str:
    if not _cbm.available:
        return json.dumps({"error": "codebase-memory-mcp not found", "hint": "npm install -g codebase-memory-mcp"})
    if _cbm._process is None:
        await _cbm.start()
    try:
        raw = await _cbm.call_tool(tool_name, arguments)
    except Exception as exc:
        return json.dumps({"error": str(exc), "tool": tool_name})
    compressed = await _compressor.compress_tool_result(tool_name, raw)
    if compressed.skipped:
        return compressed.content
    return (
        f"[ContextForge: {compressed.original_tokens}→{compressed.compressed_tokens} "
        f"tokens ({compressed.ratio:.0%} saved)]\n\n{compressed.content}"
    )


# ── CBM Tools ────────────────────────────────────────────────────────────────

@mcp.tool()
async def cbm_index_repository(repo_path: str, incremental: bool = True) -> str:
    """Index a repository into the knowledge graph. Run before any other cbm_* tool."""
    return await _cbm_call("index_repository", {"repo_path": repo_path, "incremental": incremental})

@mcp.tool()
async def cbm_search_graph(name_pattern: str, label: str = "Function", limit: int = 50, file_pattern: str | None = None) -> str:
    """Search the knowledge graph by name pattern (regex). label: Function|Class|Method|Interface."""
    args: dict[str, Any] = {"name_pattern": name_pattern, "label": label, "limit": limit}
    if file_pattern:
        args["file_pattern"] = file_pattern
    return await _cbm_call("search_graph", args)

@mcp.tool()
async def cbm_search_code(query: str, mode: str = "compact", limit: int = 30) -> str:
    """Full-text + graph-ranked code search. mode: compact|full|files."""
    return await _cbm_call("search_code", {"query": query, "mode": mode, "limit": limit})

@mcp.tool()
async def cbm_trace_path(function_name: str, direction: str = "both", depth: int = 5) -> str:
    """Trace call paths for a function. direction: inbound|outbound|both."""
    return await _cbm_call("trace_path", {"function_name": function_name, "direction": direction, "depth": depth})

@mcp.tool()
async def cbm_trace_call_path(function_name: str, direction: str = "both") -> str:
    """Trace the full call chain for a function across the knowledge graph."""
    return await _cbm_call("trace_call_path", {"function_name": function_name, "direction": direction})

@mcp.tool()
async def cbm_get_architecture(include_external: bool = False, service_filter: str | None = None) -> str:
    """Get high-level architecture view: modules, services, HTTP routes."""
    args: dict[str, Any] = {"include_external": include_external}
    if service_filter:
        args["service_filter"] = service_filter
    return await _cbm_call("get_architecture", args)

@mcp.tool()
async def cbm_get_node_details(node_id: str) -> str:
    """Get detailed information about a specific graph node."""
    return await _cbm_call("get_node_details", {"node_id": node_id})

@mcp.tool()
async def cbm_find_dead_code(confidence: str = "high", label: str | None = None) -> str:
    """Detect unreachable/unused code. confidence: high|medium|low."""
    args: dict[str, Any] = {"confidence": confidence}
    if label:
        args["label"] = label
    return await _cbm_call("find_dead_code", args)

@mcp.tool()
async def cbm_find_similar_code(node_id: str, threshold: float = 0.8, limit: int = 20) -> str:
    """Find code clones and similar implementations in the codebase."""
    return await _cbm_call("find_similar_code", {"node_id": node_id, "threshold": threshold, "limit": limit})

@mcp.tool()
async def cbm_get_impact(node_id: str, depth: int = 3) -> str:
    """Analyze what would break if this function/class changes."""
    return await _cbm_call("get_impact", {"node_id": node_id, "depth": depth})

@mcp.tool()
async def cbm_cypher_query(query: str, limit: int = 100) -> str:
    """Run a raw Cypher-like query against the knowledge graph."""
    return await _cbm_call("cypher_query", {"query": query, "limit": limit})

@mcp.tool()
async def cbm_manage_adr(action: str, title: str | None = None, content: str | None = None, adr_id: str | None = None) -> str:
    """Manage Architecture Decision Records. action: create|list|get|update."""
    args: dict[str, Any] = {"action": action}
    if title: args["title"] = title
    if content: args["content"] = content
    if adr_id: args["adr_id"] = adr_id
    return await _cbm_call("manage_adr", args)

@mcp.tool()
async def cbm_get_cross_service_links(service_name: str | None = None, protocol: str | None = None) -> str:
    """Get cross-service HTTP/gRPC/GraphQL links detected in the codebase."""
    args: dict[str, Any] = {}
    if service_name: args["service_name"] = service_name
    if protocol: args["protocol"] = protocol
    return await _cbm_call("get_cross_service_links", args)

@mcp.tool()
async def cbm_get_indexing_status() -> str:
    """Get the current indexing status."""
    return await _cbm_call("get_indexing_status", {})


# ── ContextForge Meta Tools ───────────────────────────────────────────────────

@mcp.tool()
async def cf_stats() -> str:
    """Show ContextForge session compression statistics and token savings."""
    return json.dumps({
        "contextforge_mcp_version": "0.1.0",
        "cbm_available": _cbm.available,
        "cbm_binary": _cbm.binary_path,
        "compression": _compressor.get_stats(),
    }, indent=2)

@mcp.tool()
async def cf_compress(text: str, hint: str = "text") -> str:
    """Compress arbitrary text through headroom. hint: text|code|json|logs."""
    compressed = await _compressor.compress_tool_result(f"cf_{hint}", text, force=True)
    if compressed.skipped:
        return f"[headroom unavailable]\n\n{text}"
    return (
        f"[ContextForge: {compressed.original_tokens}→{compressed.compressed_tokens} "
        f"tokens ({compressed.ratio:.0%} saved)]\n\n{compressed.content}"
    )

@mcp.tool()
async def cf_reset_stats() -> str:
    """Reset ContextForge session compression counters."""
    _compressor.reset_stats()
    return json.dumps({"status": "reset"})


# ── Spec Kit Tools ────────────────────────────────────────────────────────────

@mcp.tool()
async def cf_read_spec(feature_id: str | None = None) -> str:
    """Read and compress spec.md for a Spec Kit feature."""
    return await read_and_compress(_compressor, feature_id, "spec.md")

@mcp.tool()
async def cf_read_plan(feature_id: str | None = None) -> str:
    """Read and compress plan.md for a Spec Kit feature."""
    return await read_and_compress(_compressor, feature_id, "plan.md")

@mcp.tool()
async def cf_read_tasks(feature_id: str | None = None) -> str:
    """Read and compress tasks.md for a Spec Kit feature."""
    return await read_and_compress(_compressor, feature_id, "tasks.md")

@mcp.tool()
async def cf_read_artifact(artifact: str, feature_id: str | None = None) -> str:
    """Read and compress any Spec Kit artifact. artifact: filename like data-model.md."""
    return await read_and_compress(_compressor, feature_id, artifact)

@mcp.tool()
async def cf_implement_context(feature_id: str | None = None) -> str:
    """Load compressed spec+plan+tasks+context bundle for /speckit.cf-implement."""
    return await implement_context(_compressor, feature_id)

@mcp.tool()
async def cf_speckit_status() -> str:
    """List all Spec Kit features and their current phase."""
    return json.dumps(await speckit_status(), indent=2)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
