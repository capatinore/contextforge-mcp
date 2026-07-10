"""
ContextForge MCP Server v2 — Pure compression middleware.

Architecture:
  Claude Code
    ├── codebase-memory-mcp  (direct — graph queries)
    └── contextforge-mcp     (this server — compression + Spec Kit)

Workflow:
  1. Agent calls cbm_search_graph() → codebase-memory-mcp returns large result
  2. Agent calls cf_compress_cbm(result, "search_graph") → contextforge compresses
  3. Agent uses compressed result (60-95% fewer tokens)

Tools exposed:
  Compression:  cf_compress_cbm, cf_compress
  Stats:        cf_stats, cf_reset_stats
  Spec Kit:     cf_read_spec, cf_read_plan, cf_read_tasks,
                cf_read_artifact, cf_implement_context, cf_speckit_status
"""

from __future__ import annotations

import json
import logging
import os

from mcp.server.fastmcp import FastMCP

from .compressor import HeadroomCompressor, COMPRESS_PROFILES
from .speckit import read_and_compress, implement_context, status as speckit_status

logging.basicConfig(level=os.environ.get("CF_LOG_LEVEL", "WARNING").upper())
logger = logging.getLogger("contextforge-mcp")

mcp = FastMCP(
    "contextforge-mcp",
    instructions=(
        "ContextForge is a compression middleware. After EVERY codebase-memory-mcp "
        "tool call that returns a large result, call cf_compress_cbm(result, tool_name) "
        "to compress it before using it. This reduces token usage by 60-95%.\n\n"
        "For Spec Kit artifacts (spec/plan/tasks), use cf_read_* tools instead of "
        "reading files directly.\n\n"
        "Check cf_stats() at any time to see total tokens saved this session."
    ),
)

_compressor = HeadroomCompressor(
    model=os.environ.get("CF_MODEL", "claude-sonnet-4-6")
)


# ── Compression Tools ─────────────────────────────────────────────────────────

@mcp.tool()
async def cf_compress_cbm(result: str, tool_name: str) -> str:
    """
    Compress the output of a codebase-memory-mcp tool call.

    Call this immediately after ANY cbm_* tool that returns a large result.
    Reduces token usage by 60-95% while preserving all relevant information.

    Args:
        result:    The raw string output from the codebase-memory-mcp tool.
        tool_name: The CBM tool name (e.g. "search_graph", "get_architecture").
                   Used to select the optimal compression profile.

    Returns:
        Compressed result with a header showing tokens saved.

    Example:
        # After: graph_result = cbm_search_graph(name_pattern=".*Payment.*")
        compressed = cf_compress_cbm(result=graph_result, tool_name="search_graph")
        # Use `compressed` instead of `graph_result`

    Supported tool_name values:
        search_graph, search_code, get_architecture, find_dead_code,
        find_similar_code, get_impact, trace_path, trace_call_path,
        cypher_query, get_cross_service_links, get_node_details
    """
    compressed = await _compressor.compress(result, tool_name)

    if compressed.skipped:
        if not _compressor._available:
            return f"[ContextForge: headroom-ai not installed — install with: pip install 'headroom-ai[all]']\n\n{result}"
        return result

    return (
        f"[ContextForge ✓ {tool_name}: "
        f"{compressed.original_tokens}→{compressed.compressed_tokens} tokens "
        f"({compressed.ratio:.0%} saved in {compressed.elapsed_ms:.0f}ms)]\n\n"
        f"{compressed.content}"
    )


@mcp.tool()
async def cf_compress(text: str, hint: str = "text") -> str:
    """
    Compress arbitrary text through headroom before including it in context.

    Use this for any large text that isn't a CBM tool output:
    logs, documentation, file contents, API responses, etc.

    Args:
        text: The text to compress.
        hint: Content type hint — helps headroom pick the right algorithm.
              Values: text | code | json | logs | markdown

    Returns:
        Compressed text with token savings header.
    """
    compressed = await _compressor.compress(text, f"hint_{hint}", force=True)

    if compressed.skipped:
        if not _compressor._available:
            return f"[ContextForge: headroom-ai not installed]\n\n{text}"
        return text

    return (
        f"[ContextForge ✓ compress: "
        f"{compressed.original_tokens}→{compressed.compressed_tokens} tokens "
        f"({compressed.ratio:.0%} saved)]\n\n"
        f"{compressed.content}"
    )


# ── Stats Tools ───────────────────────────────────────────────────────────────

@mcp.tool()
async def cf_stats() -> str:
    """
    Show ContextForge compression statistics for this session.

    Returns a JSON summary including:
    - Total tokens processed and saved
    - Overall compression ratio
    - Estimated cost savings (at $3/M tokens)
    - headroom-ai availability status
    - Number of compression calls and errors

    Call this at the end of a work session to measure token efficiency.
    """
    stats = _compressor.get_stats()
    return json.dumps({
        "contextforge_mcp_version": "0.2.0",
        "architecture": "middleware — works alongside codebase-memory-mcp",
        "workflow": "cbm_tool() → cf_compress_cbm(result, tool_name) → use compressed",
        "compression": stats,
        "supported_cbm_tools": list(COMPRESS_PROFILES.keys()),
    }, indent=2)


@mcp.tool()
async def cf_reset_stats() -> str:
    """Reset ContextForge session compression counters to zero."""
    _compressor.reset_stats()
    return json.dumps({"status": "stats reset", "message": "Session counters cleared."})


# ── Spec Kit Tools ────────────────────────────────────────────────────────────

@mcp.tool()
async def cf_read_spec(feature_id: str | None = None) -> str:
    """
    Read and compress spec.md for a Spec Kit feature.

    Use instead of reading spec.md directly — compresses the file through
    headroom before returning, reducing tokens by 60-95%.

    Args:
        feature_id: Directory name under specs/ (e.g. "001-map-view" or "001").
                    If omitted, uses the most recently modified feature.
    """
    return await read_and_compress(_compressor, feature_id, "spec.md")


@mcp.tool()
async def cf_read_plan(feature_id: str | None = None) -> str:
    """
    Read and compress plan.md for a Spec Kit feature.

    Use instead of reading plan.md directly.

    Args:
        feature_id: Directory name under specs/ — omit for most recent feature.
    """
    return await read_and_compress(_compressor, feature_id, "plan.md")


@mcp.tool()
async def cf_read_tasks(feature_id: str | None = None) -> str:
    """
    Read and compress tasks.md for a Spec Kit feature.

    Use at the start of /speckit.cf-implement to load the task list efficiently.

    Args:
        feature_id: Directory name under specs/ — omit for most recent feature.
    """
    return await read_and_compress(_compressor, feature_id, "tasks.md")


@mcp.tool()
async def cf_read_artifact(artifact: str, feature_id: str | None = None) -> str:
    """
    Read and compress any Spec Kit artifact file for a feature.

    Args:
        artifact:   Filename to read (e.g. "data-model.md", "research.md", "context.md").
        feature_id: Directory name under specs/ — omit for most recent feature.
    """
    return await read_and_compress(_compressor, feature_id, artifact)


@mcp.tool()
async def cf_implement_context(feature_id: str | None = None) -> str:
    """
    Load a complete compressed context bundle for implementing a Spec Kit feature.

    Combines spec.md + plan.md + tasks.md + context.md into one optimized payload.
    Use at the start of /speckit.cf-implement instead of reading files individually.

    Args:
        feature_id: Directory name under specs/ — omit for most recent feature.

    Returns:
        All available artifacts compressed and combined, with total token savings.
    """
    return await implement_context(_compressor, feature_id)


@mcp.tool()
async def cf_speckit_status() -> str:
    """
    List all Spec Kit features and their current phase.

    Shows which artifacts exist (spec/plan/tasks/context) and task completion
    progress for each feature in the specs/ directory.
    """
    return json.dumps(await speckit_status(), indent=2)


# ── Entry Point ───────────────────────────────────────────────────────────────

def main() -> None:
    """Start ContextForge as a stdio MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
