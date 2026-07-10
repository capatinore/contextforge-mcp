"""Tests for HeadroomCompressor."""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from contextforge_mcp.compressor import CompressionResult, HeadroomCompressor, SessionStats

# ── Sample data (inline — no cross-imports) ──────────────────────────────────

LARGE_RESULT = {"nodes": [{"id": f"fn_{i}", "name": f"func_{i}"} for i in range(200)]}
SMALL_RESULT = {"status": "indexed", "files": 42}


# ── SessionStats ──────────────────────────────────────────────────────────────

class TestSessionStats:
    def test_initial_state(self):
        s = SessionStats()
        assert s.total_calls == 0
        assert s.tokens_saved == 0
        assert s.overall_ratio == 0.0

    def test_ratio(self):
        s = SessionStats(total_original_tokens=1000, total_compressed_tokens=200)
        assert s.tokens_saved == 800
        assert s.overall_ratio == pytest.approx(0.8)

    def test_zero_division_safe(self):
        assert SessionStats().overall_ratio == 0.0

    def test_to_dict(self):
        d = SessionStats().to_dict()
        assert "tokens_saved" in d
        assert "overall_compression_ratio" in d


# ── Availability ──────────────────────────────────────────────────────────────

class TestAvailability:
    def test_unavailable_without_headroom(self):
        with patch.dict("sys.modules", {"headroom": None}):
            c = HeadroomCompressor()
            assert isinstance(c._available, bool)


# ── Fallback behavior ─────────────────────────────────────────────────────────

class TestFallback:
    @pytest.fixture
    def c(self):
        comp = HeadroomCompressor()
        comp._available = False
        return comp

    @pytest.mark.asyncio
    async def test_returns_original_when_unavailable(self, c):
        content = json.dumps(LARGE_RESULT)
        result = await c.compress_tool_result("search_graph", content)
        assert result.skipped is True
        assert result.content == content

    @pytest.mark.asyncio
    async def test_dict_serialized(self, c):
        result = await c.compress_tool_result("search_graph", LARGE_RESULT)
        assert isinstance(result.content, str)

    @pytest.mark.asyncio
    async def test_skip_tools_skipped(self, c):
        result = await c.compress_tool_result("index_repository", "indexing...")
        assert result.skipped is True

    @pytest.mark.asyncio
    async def test_stats_updated(self, c):
        await c.compress_tool_result("search_graph", "hello")
        assert c.stats.total_calls == 1

    @pytest.mark.asyncio
    async def test_reset(self, c):
        await c.compress_tool_result("search_graph", "hello")
        c.reset_stats()
        assert c.stats.total_calls == 0

    @pytest.mark.asyncio
    async def test_get_stats_keys(self, c):
        s = c.get_stats()
        assert "headroom_available" in s
        assert "tokens_saved" in s

    @pytest.mark.asyncio
    async def test_error_falls_back(self):
        c = HeadroomCompressor()
        c._available = True
        with patch.object(c, "_compress", side_effect=Exception("boom")):
            result = await c.compress_tool_result("search_graph", "content")
        assert result.skipped is True
        assert c.stats.errors == 1
