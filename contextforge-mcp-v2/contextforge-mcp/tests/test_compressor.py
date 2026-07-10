"""Tests for HeadroomCompressor."""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from contextforge_mcp.compressor import (
    CompressionResult, HeadroomCompressor, SessionStats,
    COMPRESS_PROFILES, SKIP_COMPRESS,
)

LARGE_RESULT = {"nodes": [{"id": f"fn_{i}", "name": f"func_{i}"} for i in range(200)]}
SMALL_RESULT = {"status": "indexed", "files": 42}


class TestSessionStats:
    def test_initial_state(self):
        s = SessionStats()
        assert s.total_calls == 0
        assert s.tokens_saved == 0
        assert s.overall_ratio == 0.0

    def test_ratio(self):
        s = SessionStats(total_original_tokens=1000, total_compressed_tokens=100)
        assert s.tokens_saved == 900
        assert s.overall_ratio == pytest.approx(0.9)

    def test_cost_estimate(self):
        s = SessionStats(total_original_tokens=1_000_000, total_compressed_tokens=0)
        assert s.estimated_cost_saved_usd == pytest.approx(3.0)

    def test_zero_division_safe(self):
        assert SessionStats().overall_ratio == 0.0

    def test_to_dict_keys(self):
        d = SessionStats().to_dict()
        assert "tokens_saved" in d
        assert "overall_compression_ratio" in d
        assert "estimated_cost_saved_usd" in d


class TestProfiles:
    def test_high_token_tools_have_profiles(self):
        for tool in ["search_graph", "search_code", "get_architecture"]:
            assert tool in COMPRESS_PROFILES

    def test_skip_tools_defined(self):
        assert "index_repository" in SKIP_COMPRESS
        assert "get_indexing_status" in SKIP_COMPRESS


class TestFallback:
    @pytest.fixture
    def c(self):
        comp = HeadroomCompressor()
        comp._available = False
        return comp

    @pytest.mark.asyncio
    async def test_passthrough_when_unavailable(self, c):
        content = json.dumps(LARGE_RESULT)
        result = await c.compress(content, "search_graph")
        assert result.skipped is True
        assert result.content == content
        assert result.tokens_saved == 0

    @pytest.mark.asyncio
    async def test_skip_tool_passthrough(self, c):
        result = await c.compress("indexing...", "index_repository")
        assert result.skipped is True

    @pytest.mark.asyncio
    async def test_force_overrides_skip(self, c):
        result = await c.compress("indexing...", "index_repository", force=True)
        assert result.skipped is True  # still skipped because unavailable

    @pytest.mark.asyncio
    async def test_dict_input_serialized(self, c):
        result = await c.compress(LARGE_RESULT, "search_graph")
        assert isinstance(result.content, str)

    @pytest.mark.asyncio
    async def test_stats_updated_on_call(self, c):
        await c.compress("hello world", "search_graph")
        assert c.stats.total_calls == 1

    @pytest.mark.asyncio
    async def test_reset_clears_stats(self, c):
        await c.compress("hello", "search_graph")
        c.reset_stats()
        assert c.stats.total_calls == 0

    @pytest.mark.asyncio
    async def test_error_falls_back(self):
        c = HeadroomCompressor()
        c._available = True
        with patch.object(c, "_run_headroom", side_effect=Exception("boom")):
            result = await c.compress("content", "search_graph")
        assert result.skipped is True
        assert c.stats.errors == 1

    @pytest.mark.asyncio
    async def test_multiple_calls_accumulate(self, c):
        for _ in range(5):
            await c.compress("x", "search_graph")
        assert c.stats.total_calls == 5

    def test_get_stats_keys(self):
        c = HeadroomCompressor()
        c._available = False
        s = c.get_stats()
        assert "headroom_available" in s
        assert "total_calls" in s
        assert "estimated_cost_saved_usd" in s
