"""Headroom compression layer with per-tool profiles and session stats."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Tools that return large payloads — compress aggressively
COMPRESS_PROFILES: dict[str, dict[str, Any]] = {
    "search_graph":        {"max_items": 50},
    "search_code":         {"max_items": 30},
    "get_architecture":    {"max_items": 100},
    "find_dead_code":      {"max_items": 80},
    "find_similar_code":   {"max_items": 40},
    "cypher_query":        {"max_items": 60},
    "get_impact":          {"max_items": 40},
    "trace_path":          {"max_items": 30},
    "trace_call_path":     {"max_items": 30},
    "get_cross_service_links": {"max_items": 50},
}

# Tools that return small status payloads — skip compression
SKIP_COMPRESS: set[str] = {
    "index_repository",
    "get_indexing_status",
    "manage_adr",
    "get_node_details",
}


@dataclass
class CompressionResult:
    original_tokens: int
    compressed_tokens: int
    tokens_saved: int
    ratio: float
    content: str
    elapsed_ms: float
    skipped: bool = False


@dataclass
class SessionStats:
    total_calls: int = 0
    total_original_tokens: int = 0
    total_compressed_tokens: int = 0
    total_elapsed_ms: float = 0.0
    errors: int = 0

    @property
    def tokens_saved(self) -> int:
        return self.total_original_tokens - self.total_compressed_tokens

    @property
    def overall_ratio(self) -> float:
        if self.total_original_tokens == 0:
            return 0.0
        return 1.0 - (self.total_compressed_tokens / self.total_original_tokens)

    @property
    def estimated_cost_saved_usd(self) -> float:
        """Estimate at $3/M tokens (Claude Sonnet input pricing)."""
        return (self.tokens_saved / 1_000_000) * 3.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_calls": self.total_calls,
            "total_original_tokens": self.total_original_tokens,
            "total_compressed_tokens": self.total_compressed_tokens,
            "tokens_saved": self.tokens_saved,
            "overall_compression_ratio": f"{self.overall_ratio:.1%}",
            "estimated_cost_saved_usd": f"${self.estimated_cost_saved_usd:.4f}",
            "total_elapsed_ms": round(self.total_elapsed_ms, 1),
            "errors": self.errors,
        }


class HeadroomCompressor:
    """
    Wraps headroom-ai compress() with per-tool profiles and session stats.
    Falls back gracefully when headroom-ai is not installed.
    """

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.model = model
        self.stats = SessionStats()
        self._available = self._check_availability()

    async def compress(
        self,
        content: Any,
        tool_name: str = "text",
        *,
        force: bool = False,
    ) -> CompressionResult:
        """
        Compress content from a CBM tool or arbitrary text.

        Args:
            content:   Raw result (str, dict, list).
            tool_name: CBM tool name or hint (text/code/json/logs).
            force:     Compress even skip-marked tools.
        """
        t0 = time.perf_counter()
        self.stats.total_calls += 1

        content_str = content if isinstance(content, str) else json.dumps(content, indent=2)

        should_skip = (tool_name in SKIP_COMPRESS and not force) or not self._available

        if should_skip:
            return self._passthrough(content_str, t0)

        try:
            return await self._run_headroom(content_str, tool_name, t0)
        except Exception as exc:
            logger.warning("Headroom compression failed [%s]: %s", tool_name, exc)
            self.stats.errors += 1
            return self._passthrough(content_str, t0)

    def get_stats(self) -> dict[str, Any]:
        return {
            "headroom_available": self._available,
            "model": self.model,
            **self.stats.to_dict(),
        }

    def reset_stats(self) -> None:
        self.stats = SessionStats()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _passthrough(self, content: str, t0: float) -> CompressionResult:
        elapsed = (time.perf_counter() - t0) * 1000
        tokens = len(content.split())
        self.stats.total_original_tokens += tokens
        self.stats.total_compressed_tokens += tokens
        self.stats.total_elapsed_ms += elapsed
        return CompressionResult(
            original_tokens=tokens, compressed_tokens=tokens,
            tokens_saved=0, ratio=0.0,
            content=content, elapsed_ms=elapsed, skipped=True,
        )

    async def _run_headroom(self, content: str, tool_name: str, t0: float) -> CompressionResult:
        import asyncio
        from headroom import compress  # type: ignore[import]

        profile = COMPRESS_PROFILES.get(tool_name, {})
        messages = [{"role": "tool", "tool_call_id": f"cf_{tool_name}", "content": content}]

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: compress(
                messages,
                model=self.model,
                headroom_tool_profiles={tool_name: profile} if profile else None,
            ),
        )

        elapsed = (time.perf_counter() - t0) * 1000
        compressed_content = content
        if result.messages:
            msg = result.messages[0]
            if isinstance(msg, dict):
                compressed_content = msg.get("content", content)

        orig = getattr(result, "tokens_before", len(content.split()))
        comp = getattr(result, "tokens_after", len(compressed_content.split()))
        saved = orig - comp
        ratio = saved / orig if orig > 0 else 0.0

        self.stats.total_original_tokens += orig
        self.stats.total_compressed_tokens += comp
        self.stats.total_elapsed_ms += elapsed

        logger.info("[%s] %d→%d tokens (%.0f%% saved) %.1fms", tool_name, orig, comp, ratio * 100, elapsed)

        return CompressionResult(
            original_tokens=orig, compressed_tokens=comp,
            tokens_saved=saved, ratio=ratio,
            content=compressed_content, elapsed_ms=elapsed,
        )

    @staticmethod
    def _check_availability() -> bool:
        try:
            import headroom  # noqa: F401
            return True
        except ImportError:
            logger.warning("headroom-ai not installed — compression disabled. pip install 'headroom-ai[all]'")
            return False
