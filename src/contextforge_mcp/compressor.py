"""
ContextForge Native Compressor
================================
Pure-Python context compression for CBM tool outputs.
No ML models, no external backends — works on Windows, Linux, macOS.

Compression strategies:
  JSON arrays   → deduplicate + keep top N items + summary sentinel
  Noise keys    → remove low-value fields (hashes, timestamps, internal IDs)
  Long strings  → truncate to _MAX_STRING_LEN chars
  Prose/logs    → keep head + tail lines, omit middle
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

# Keys that add noise but little value in CBM output
_NOISE_KEYS: frozenset[str] = frozenset({
    "hash", "checksum", "uuid", "timestamp", "created_at", "updated_at",
    "internal_id", "raw", "metadata", "debug", "trace", "span_id",
    "correlation_id", "request_id", "etag", "last_modified",
    # CBM-specific fingerprint fields (opaque hashes, no informational value)
    "fp", "sp", "bt", "fingerprint", "signature", "embedding",
})

# Per-tool: max array items to keep after deduplication
_TOOL_MAX_ITEMS: dict[str, int] = {
    "search_graph":            30,
    "search_code":             20,
    "get_architecture":        60,
    "find_dead_code":          40,
    "find_similar_code":       25,
    "get_impact":              25,
    "trace_path":              20,
    "trace_call_path":         20,
    "cypher_query":            40,
    "get_cross_service_links": 30,
    "get_node_details":        50,
}
_DEFAULT_MAX_ITEMS: int = 50
_MAX_STRING_LEN:    int = 200   # chars per string value before truncation
_MAX_PROSE_LINES:   int = 30    # lines to keep for prose/log content

# Tools that return small status payloads — skip compression overhead
_SKIP_TOOLS: frozenset[str] = frozenset({
    "index_repository",
    "get_indexing_status",
    "manage_adr",
})


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class CompressionResult:
    original_tokens:    int
    compressed_tokens:  int
    tokens_saved:       int
    ratio:              float    # 0.0 = no compression, 0.9 = 90% saved
    content:            str      # compressed content
    elapsed_ms:         float
    skipped:            bool = False


@dataclass
class SessionStats:
    total_calls:              int   = 0
    total_original_tokens:    int   = 0
    total_compressed_tokens:  int   = 0
    total_elapsed_ms:         float = 0.0
    errors:                   int   = 0

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
            "total_calls":              self.total_calls,
            "total_original_tokens":    self.total_original_tokens,
            "total_compressed_tokens":  self.total_compressed_tokens,
            "tokens_saved":             self.tokens_saved,
            "overall_compression_ratio": f"{self.overall_ratio:.1%}",
            "estimated_cost_saved_usd": f"${self.estimated_cost_saved_usd:.4f}",
            "total_elapsed_ms":         round(self.total_elapsed_ms, 1),
            "errors":                   self.errors,
        }


# ── Core compression functions ────────────────────────────────────────────────

def _count_tokens(text: str) -> int:
    """
    Approximate LLM token count using character-based estimation.

    LLM tokenizers average ~4 characters per token for mixed content
    (code, JSON, prose). Whitespace splitting is inaccurate for compact
    JSON which has no spaces — the entire payload would count as 1 token.

    4 chars/token is a standard approximation used by OpenAI, Anthropic,
    and most tokenizer benchmarks for English + code content.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


def _is_json(text: str) -> bool:
    s = text.strip()
    return s.startswith(('{', '['))


def _truncate_string(value: str, max_len: int = _MAX_STRING_LEN) -> str:
    if len(value) <= max_len:
        return value
    return value[:max_len] + f"…[+{len(value) - max_len}ch]"


def _deduplicate_array(items: list[Any]) -> list[Any]:
    """Remove duplicate dicts from an array, keyed on common identity fields."""
    seen: set[tuple[str, ...]] = set()
    result: list[Any] = []
    for item in items:
        if not isinstance(item, dict):
            result.append(item)
            continue
        key = tuple(str(item.get(f, "")) for f in ("id", "name", "file", "path"))
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _compress_array(arr: list[Any], max_items: int, tool_name: str) -> list[Any]:
    """Deduplicate then truncate an array, appending a summary sentinel."""
    dedup = _deduplicate_array(arr)
    if len(dedup) <= max_items:
        return dedup
    omitted = len(dedup) - max_items
    kept = dedup[:max_items]
    kept.append({
        "__cf_truncated__": True,
        "omitted":          omitted,
        "hint":             f"Use a more specific query to retrieve the omitted {omitted} items.",
    })
    return kept


def _compress_json_obj(obj: Any, tool_name: str, max_items: int) -> Any:
    """Recursively compress a parsed JSON object."""
    if isinstance(obj, dict):
        # Strip noise keys
        cleaned = {k: v for k, v in obj.items() if k.lower() not in _NOISE_KEYS}
        return {k: _compress_json_obj(v, tool_name, max_items) for k, v in cleaned.items()}
    if isinstance(obj, list):
        compressed = [_compress_json_obj(item, tool_name, max_items) for item in obj]
        return _compress_array(compressed, max_items, tool_name)
    if isinstance(obj, str):
        return _truncate_string(obj)
    return obj


def _compress_prose(text: str, max_lines: int = _MAX_PROSE_LINES) -> str:
    """
    Keep the most informative lines from prose/log content.
    Strategy: first N/2 lines + last N/2 lines.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) <= max_lines:
        return text
    half = max_lines // 2
    head = lines[:half]
    tail = lines[-half:]
    omitted = len(lines) - max_lines
    return "\n".join(head + [f"... [{omitted} lines omitted by ContextForge] ..."] + tail)


def compress_content(content: str, tool_name: str = "text") -> tuple[str, int, int]:
    """
    Compress content from a CBM tool or arbitrary text.

    Returns:
        (compressed_content, original_tokens, compressed_tokens)

    Never raises — all errors fall back to returning the original content.
    """
    if not content or not content.strip():
        return content, 0, 0

    original_tokens = _count_tokens(content)
    max_items = _TOOL_MAX_ITEMS.get(tool_name, _DEFAULT_MAX_ITEMS)

    # ── JSON path ─────────────────────────────────────────────────────────────
    if _is_json(content):
        try:
            parsed = json.loads(content)
            compressed_obj = _compress_json_obj(parsed, tool_name, max_items)
            # Compact JSON serialization saves ~15% on whitespace alone
            compressed = json.dumps(
                compressed_obj,
                separators=(',', ':'),
                ensure_ascii=False,
            )
            compressed_tokens = _count_tokens(compressed)
            return compressed, original_tokens, compressed_tokens
        except (json.JSONDecodeError, RecursionError, MemoryError, TypeError) as exc:
            logger.debug("JSON compression failed for %s: %s", tool_name, exc)
            # Fall through to prose path

    # ── Prose / logs path ─────────────────────────────────────────────────────
    try:
        compressed = _compress_prose(content, _MAX_PROSE_LINES)
        compressed_tokens = _count_tokens(compressed)
        return compressed, original_tokens, compressed_tokens
    except Exception as exc:
        logger.warning("Prose compression failed for %s: %s", tool_name, exc)
        return content, original_tokens, original_tokens


# ── Compressor class (wraps compress_content with stats) ─────────────────────

class NativeCompressor:
    """
    Stateful wrapper around compress_content with per-session stats tracking.
    Drop-in replacement for the old HeadroomCompressor.
    """

    def __init__(self) -> None:
        self.stats = SessionStats()

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

        # Serialize to string if needed
        if not isinstance(content, str):
            try:
                content_str = json.dumps(content, ensure_ascii=False)
            except (TypeError, ValueError):
                content_str = str(content)
        else:
            content_str = content

        # Skip lightweight tools unless forced
        if tool_name in _SKIP_TOOLS and not force:
            return self._passthrough(content_str, t0)

        try:
            compressed, orig_tokens, comp_tokens = compress_content(content_str, tool_name)
            elapsed = (time.perf_counter() - t0) * 1000
            saved = orig_tokens - comp_tokens
            ratio = saved / orig_tokens if orig_tokens > 0 else 0.0

            self.stats.total_original_tokens   += orig_tokens
            self.stats.total_compressed_tokens += comp_tokens
            self.stats.total_elapsed_ms        += elapsed

            logger.info(
                "[%s] %d→%d tokens (%.0f%% saved) %.1fms",
                tool_name, orig_tokens, comp_tokens, ratio * 100, elapsed,
            )

            return CompressionResult(
                original_tokens=orig_tokens,
                compressed_tokens=comp_tokens,
                tokens_saved=saved,
                ratio=ratio,
                content=compressed,
                elapsed_ms=elapsed,
            )

        except Exception as exc:
            logger.warning("Compression error [%s]: %s", tool_name, exc)
            self.stats.errors += 1
            return self._passthrough(content_str, t0)

    def get_stats(self) -> dict[str, Any]:
        return {
            "engine":  "native (pure-Python, cross-platform)",
            **self.stats.to_dict(),
        }

    def reset_stats(self) -> None:
        self.stats = SessionStats()

    def _passthrough(self, content: str, t0: float) -> CompressionResult:
        elapsed = (time.perf_counter() - t0) * 1000
        tokens = _count_tokens(content)
        self.stats.total_original_tokens   += tokens
        self.stats.total_compressed_tokens += tokens
        self.stats.total_elapsed_ms        += elapsed
        return CompressionResult(
            original_tokens=tokens,
            compressed_tokens=tokens,
            tokens_saved=0,
            ratio=0.0,
            content=content,
            elapsed_ms=elapsed,
            skipped=True,
        )


# ── Module-level alias for backwards compatibility ────────────────────────────
HeadroomCompressor = NativeCompressor
