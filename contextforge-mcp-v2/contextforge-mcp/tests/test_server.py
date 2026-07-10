"""Tests for ContextForge MCP server v2."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from contextforge_mcp.compressor import CompressionResult


class TestToolsRegistered:
    def test_compression_tools(self):
        from contextforge_mcp import server as srv
        tools = {t.name for t in srv.mcp._tool_manager._tools.values()}
        assert "cf_compress_cbm" in tools
        assert "cf_compress" in tools

    def test_stats_tools(self):
        from contextforge_mcp import server as srv
        tools = {t.name for t in srv.mcp._tool_manager._tools.values()}
        assert "cf_stats" in tools
        assert "cf_reset_stats" in tools

    def test_speckit_tools(self):
        from contextforge_mcp import server as srv
        tools = {t.name for t in srv.mcp._tool_manager._tools.values()}
        assert "cf_read_spec" in tools
        assert "cf_read_plan" in tools
        assert "cf_read_tasks" in tools
        assert "cf_read_artifact" in tools
        assert "cf_implement_context" in tools
        assert "cf_speckit_status" in tools

    def test_total_tool_count(self):
        from contextforge_mcp import server as srv
        count = len(srv.mcp._tool_manager._tools)
        assert count == 9  # 2 compress + 2 stats + 5 speckit

    def test_no_cbm_proxy_tools(self):
        """v2 should NOT have cbm_* tools — those come from codebase-memory-mcp directly."""
        from contextforge_mcp import server as srv
        tools = {t.name for t in srv.mcp._tool_manager._tools.values()}
        cbm_tools = {t for t in tools if t.startswith("cbm_")}
        assert len(cbm_tools) == 0


class TestCFCompressCBM:
    @pytest.mark.asyncio
    async def test_passthrough_when_headroom_unavailable(self):
        from contextforge_mcp import server as srv

        mock_result = CompressionResult(
            original_tokens=100, compressed_tokens=100,
            tokens_saved=0, ratio=0.0,
            content="original content", elapsed_ms=1.0, skipped=True,
        )
        with patch.object(srv._compressor, "compress", return_value=mock_result):
            with patch.object(srv._compressor, "_available", False):
                result = await srv.cf_compress_cbm("original content", "search_graph")
        assert "headroom-ai not installed" in result

    @pytest.mark.asyncio
    async def test_shows_savings_when_compressed(self):
        from contextforge_mcp import server as srv

        mock_result = CompressionResult(
            original_tokens=1000, compressed_tokens=100,
            tokens_saved=900, ratio=0.9,
            content="compressed content", elapsed_ms=5.0, skipped=False,
        )
        with patch.object(srv._compressor, "compress", return_value=mock_result):
            result = await srv.cf_compress_cbm("large content " * 100, "search_graph")

        assert "90%" in result
        assert "1000→100" in result
        assert "compressed content" in result


class TestCFStats:
    @pytest.mark.asyncio
    async def test_returns_valid_json(self):
        from contextforge_mcp import server as srv
        result = await srv.cf_stats()
        data = json.loads(result)
        assert "contextforge_mcp_version" in data
        assert data["contextforge_mcp_version"] == "0.2.0"
        assert "compression" in data
        assert "workflow" in data

    @pytest.mark.asyncio
    async def test_architecture_field(self):
        from contextforge_mcp import server as srv
        result = await srv.cf_stats()
        data = json.loads(result)
        assert "middleware" in data["architecture"]


class TestCFResetStats:
    @pytest.mark.asyncio
    async def test_resets_counters(self):
        from contextforge_mcp import server as srv
        srv._compressor.stats.total_calls = 99
        await srv.cf_reset_stats()
        assert srv._compressor.stats.total_calls == 0

    @pytest.mark.asyncio
    async def test_returns_confirmation(self):
        from contextforge_mcp import server as srv
        result = await srv.cf_reset_stats()
        data = json.loads(result)
        assert data["status"] == "stats reset"
