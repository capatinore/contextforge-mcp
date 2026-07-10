"""Headroom compression layer with stats tracking."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

SKIP_TOOLS: set[str] = {"index_repository", "get_indexing_status"}


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_calls": self.total_calls,
            "total_original_tokens": self.total_original_tokens,
            "total_compressed_tokens": self.total_compressed_tokens,
            "tokens_saved": self.tokens_saved,
            "overall_compression_ratio": f"{self.overall_ratio:.1%}",
            "total_elapsed_ms": round(self.total_elapsed_ms, 1),
            "errors": self.errors,
        }


class HeadroomCompressor:
    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.model = model
        self.stats = SessionStats()
        self._available = self._check_availability()

    async def compress_tool_result(
        self, tool_name: str, result: Any, *, force: bool = False
    ) -> CompressionResult:
        t0 = time.perf_counter()
        self.stats.total_calls += 1
        content_str = result if isinstance(result, str) else json.dumps(result, indent=2)

        if (tool_name in SKIP_TOOLS and not force) or not self._available:
            elapsed = (time.perf_counter() - t0) * 1000
            token_est = len(content_str.split())
            self.stats.total_original_tokens += token_est
            self.stats.total_compressed_tokens += token_est
            return CompressionResult(
                original_tokens=token_est, compressed_tokens=token_est,
                tokens_saved=0, ratio=0.0, content=content_str,
                elapsed_ms=elapsed, skipped=True,
            )

        try:
            return await self._compress(content_str, t0)
        except Exception as exc:
            logger.warning("Headroom compression failed for %s: %s", tool_name, exc)
            self.stats.errors += 1
            elapsed = (time.perf_counter() - t0) * 1000
            token_est = len(content_str.split())
            return CompressionResult(
                original_tokens=token_est, compressed_tokens=token_est,
                tokens_saved=0, ratio=0.0, content=content_str,
                elapsed_ms=elapsed, skipped=True,
            )

    def get_stats(self) -> dict[str, Any]:
        return {"headroom_available": self._available, "model": self.model, **self.stats.to_dict()}

    def reset_stats(self) -> None:
        self.stats = SessionStats()

    async def _compress(self, content: str, t0: float) -> CompressionResult:
        import asyncio
        from headroom import compress  # type: ignore[import]

        messages = [{"role": "tool", "tool_call_id": "cf", "content": content}]
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: compress(messages, model=self.model)
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
            logger.warning("headroom-ai not installed — compression disabled.")
            return False
