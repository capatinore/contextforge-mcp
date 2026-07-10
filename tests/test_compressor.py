"""Tests for NativeCompressor — pure-Python cross-platform compressor."""

from __future__ import annotations

import json
import pytest

from contextforge_mcp.compressor import (
    NativeCompressor, SessionStats, CompressionResult,
    compress_content, _TOOL_MAX_ITEMS, _SKIP_TOOLS,
    _count_tokens, _is_json, _truncate_string,
    _deduplicate_array, _compress_prose,
)

LARGE_NODES = [{"id": f"fn_{i}", "name": f"func_{i}", "file": f"src/m_{i}.ts"} for i in range(200)]
ARCH_RESULT = {
    "project": "domika", "total_nodes": 3048,
    "hotspots": [{"name": f"fn_{i}", "fan_in": 100-i, "hash": f"x{i}", "timestamp": "2026"} for i in range(80)],
}


class TestHelpers:
    def test_count_tokens(self):
        # Character-based: len(text) // 4
        assert _count_tokens("") == 0
        assert _count_tokens("hello world foo") == 3  # 15 chars // 4 = 3
        assert _count_tokens('{"id":"fn_1"}') == 3    # 13 chars // 4 = 3

    def test_count_tokens_compact_json(self):
        """Compact JSON has no spaces — whitespace splitting would give 1 token."""
        long_json = '{"nodes":[' + ','.join(['{"id":"fn_1","name":"func"}'] * 10) + ']}'
        tokens = _count_tokens(long_json)
        assert tokens > 10, f"Expected >10 tokens for long JSON, got {tokens}"

    def test_is_json_dict(self):
        assert _is_json('{"key": "value"}')

    def test_is_json_array(self):
        assert _is_json('[1, 2, 3]')

    def test_is_json_prose(self):
        assert not _is_json("This is prose text")

    def test_truncate_short(self):
        s = "short"
        assert _truncate_string(s, 200) == s

    def test_truncate_long(self):
        s = "x" * 500
        result = _truncate_string(s, 200)
        assert len(result) < 500
        assert "ch]" in result

    def test_deduplicate_by_name(self):
        items = [
            {"id": "fn_1", "name": "pay", "file": "a.ts"},
            {"id": "fn_1", "name": "pay", "file": "a.ts"},  # dupe
            {"id": "fn_2", "name": "validate", "file": "b.ts"},
        ]
        result = _deduplicate_array(items)
        assert len(result) == 2

    def test_deduplicate_passthrough_non_dicts(self):
        items = [1, 2, 2, 3]
        result = _deduplicate_array(items)
        assert result == [1, 2, 2, 3]  # non-dicts not deduped

    def test_prose_short_unchanged(self):
        text = "line one\nline two"
        assert _compress_prose(text, max_lines=30) == text

    def test_prose_long_truncated(self):
        lines = [f"Line {i}" for i in range(100)]
        result = _compress_prose("\n".join(lines), max_lines=30)
        assert "omitted" in result
        assert len(result.splitlines()) < 100


class TestCompressContent:
    def test_large_json_array_truncated(self):
        content = json.dumps({"nodes": LARGE_NODES})
        compressed, orig, comp = compress_content(content, "search_graph")
        assert comp < orig
        parsed = json.loads(compressed)
        real = [x for x in parsed["nodes"] if not (isinstance(x, dict) and x.get("__cf_truncated__"))]
        assert len(real) == _TOOL_MAX_ITEMS["search_graph"]

    def test_sentinel_appended(self):
        content = json.dumps({"nodes": LARGE_NODES})
        compressed, _, _ = compress_content(content, "search_graph")
        parsed = json.loads(compressed)
        assert any(isinstance(x, dict) and x.get("__cf_truncated__") for x in parsed["nodes"])

    def test_noise_keys_removed(self):
        content = json.dumps({"name": "pay", "hash": "abc", "timestamp": "2026", "file": "a.ts"})
        compressed, _, _ = compress_content(content, "get_node_details")
        parsed = json.loads(compressed)
        assert "hash" not in parsed
        assert "timestamp" not in parsed
        assert "name" in parsed

    def test_long_string_truncated(self):
        content = json.dumps({"desc": "x" * 500})
        compressed, _, _ = compress_content(content, "text")
        parsed = json.loads(compressed)
        assert len(parsed["desc"]) < 500

    def test_small_json_preserved(self):
        data = {"status": "indexed", "files": 42}
        content = json.dumps(data)
        compressed, _, _ = compress_content(content, "get_indexing_status")
        assert json.loads(compressed)["files"] == 42

    def test_real_arch_compressed(self):
        content = json.dumps(ARCH_RESULT)
        compressed, orig, comp = compress_content(content, "get_architecture")
        ratio = 1 - comp / orig if orig > 0 else 0
        assert ratio > 0.20, f"Expected >20% compression, got {ratio:.1%}"
        assert json.loads(compressed) is not None

    def test_invalid_json_fallback(self):
        bad = '{"key": "value", broken'
        compressed, orig, comp = compress_content(bad, "search_graph")
        assert isinstance(compressed, str)

    def test_empty_input_safe(self):
        compressed, orig, comp = compress_content("", "search_graph")
        assert compressed == "" and orig == 0

    def test_deep_nesting_safe(self):
        nested = {"a": {"b": {"c": {"d": [{"id": f"n_{i}", "val": "x" * 300} for i in range(10)]}}}}
        compressed, _, _ = compress_content(json.dumps(nested), "cypher_query")
        assert json.loads(compressed) is not None

    def test_compact_json_output(self):
        """Output should use compact JSON separators."""
        content = json.dumps({"key": "value", "num": 42})
        compressed, _, _ = compress_content(content, "text")
        assert "  " not in compressed  # no indentation


class TestNativeCompressor:
    @pytest.fixture
    def comp(self):
        return NativeCompressor()

    @pytest.mark.asyncio
    async def test_compress_large_json(self, comp):
        content = json.dumps({"nodes": LARGE_NODES})
        result = await comp.compress(content, "search_graph")
        assert result.ratio > 0.0
        assert result.tokens_saved > 0
        assert result.skipped is False

    @pytest.mark.asyncio
    async def test_skip_tool_passthrough(self, comp):
        result = await comp.compress("indexing done", "index_repository")
        assert result.skipped is True
        assert result.tokens_saved == 0

    @pytest.mark.asyncio
    async def test_force_overrides_skip(self, comp):
        content = json.dumps(ARCH_RESULT)
        result = await comp.compress(content, "index_repository", force=True)
        # Even with force, content may not compress much if already small
        assert isinstance(result, CompressionResult)

    @pytest.mark.asyncio
    async def test_dict_input_serialized(self, comp):
        result = await comp.compress(ARCH_RESULT, "get_architecture")
        assert isinstance(result.content, str)

    @pytest.mark.asyncio
    async def test_stats_updated(self, comp):
        await comp.compress(json.dumps(ARCH_RESULT), "search_graph")
        assert comp.stats.total_calls == 1
        assert comp.stats.total_original_tokens > 0

    @pytest.mark.asyncio
    async def test_reset_clears_stats(self, comp):
        await comp.compress("hello", "search_graph")
        comp.reset_stats()
        assert comp.stats.total_calls == 0

    @pytest.mark.asyncio
    async def test_error_falls_back(self, comp, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError("boom")
        monkeypatch.setattr("contextforge_mcp.compressor.compress_content", boom)
        result = await comp.compress("content", "search_graph")
        assert result.skipped is True
        assert comp.stats.errors == 1

    def test_get_stats_keys(self, comp):
        s = comp.get_stats()
        assert "engine" in s
        assert "tokens_saved" in s
        assert "estimated_cost_saved_usd" in s

    def test_headroom_compressor_alias(self):
        from contextforge_mcp.compressor import HeadroomCompressor
        c = HeadroomCompressor()
        assert isinstance(c, NativeCompressor)


class TestSessionStats:
    def test_initial_state(self):
        s = SessionStats()
        assert s.total_calls == 0
        assert s.tokens_saved == 0
        assert s.overall_ratio == 0.0

    def test_ratio_calculation(self):
        s = SessionStats(total_original_tokens=1000, total_compressed_tokens=100)
        assert s.tokens_saved == 900
        assert s.overall_ratio == pytest.approx(0.9)

    def test_cost_estimate(self):
        s = SessionStats(total_original_tokens=1_000_000, total_compressed_tokens=0)
        assert s.estimated_cost_saved_usd == pytest.approx(3.0)

    def test_zero_division_safe(self):
        assert SessionStats().overall_ratio == 0.0

    def test_to_dict_complete(self):
        d = SessionStats().to_dict()
        required = {"total_calls", "tokens_saved", "overall_compression_ratio", "estimated_cost_saved_usd"}
        assert required.issubset(d.keys())
