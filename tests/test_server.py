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
        for tool in ["cf_read_spec", "cf_read_plan", "cf_read_tasks",
                     "cf_read_artifact", "cf_implement_context", "cf_speckit_status"]:
            assert tool in tools

    def test_total_tool_count(self):
        from contextforge_mcp import server as srv
        count = len(srv.mcp._tool_manager._tools)
        assert count == 11  # 2 compress + 2 stats + 6 speckit

    def test_no_cbm_proxy_tools(self):
        from contextforge_mcp import server as srv
        tools = {t.name for t in srv.mcp._tool_manager._tools.values()}
        assert not any(t.startswith("cbm_") for t in tools)


class TestCFCompressCBM:
    @pytest.mark.asyncio
    async def test_passthrough_when_already_compact(self):
        from contextforge_mcp import server as srv
        mock_result = CompressionResult(
            original_tokens=10, compressed_tokens=10,
            tokens_saved=0, ratio=0.0,
            content="compact content", elapsed_ms=1.0, skipped=False,
        )
        with patch.object(srv._compressor, "compress", return_value=mock_result):
            result = await srv.cf_compress_cbm("compact content", "search_graph")
        assert "already compact" in result

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

    @pytest.mark.asyncio
    async def test_skipped_returns_original(self):
        from contextforge_mcp import server as srv
        mock_result = CompressionResult(
            original_tokens=10, compressed_tokens=10,
            tokens_saved=0, ratio=0.0,
            content="original", elapsed_ms=1.0, skipped=True,
        )
        with patch.object(srv._compressor, "compress", return_value=mock_result):
            result = await srv.cf_compress_cbm("original", "index_repository")
        assert result == "original"


class TestCFStats:
    @pytest.mark.asyncio
    async def test_returns_valid_json(self):
        from contextforge_mcp import server as srv
        result = await srv.cf_stats()
        data = json.loads(result)
        assert "contextforge_mcp_version" in data
        assert data["contextforge_mcp_version"] == "0.2.4"
        assert "compression" in data

    @pytest.mark.asyncio
    async def test_architecture_field(self):
        from contextforge_mcp import server as srv
        result = await srv.cf_stats()
        data = json.loads(result)
        assert "middleware" in data["architecture"]

    @pytest.mark.asyncio
    async def test_engine_field(self):
        from contextforge_mcp import server as srv
        result = await srv.cf_stats()
        data = json.loads(result)
        assert "native" in data["compression_engine"]


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
        assert data["status"] == "reset"
