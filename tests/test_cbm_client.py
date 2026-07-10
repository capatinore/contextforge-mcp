"""Tests for CBMClient."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from contextforge_mcp.cbm_client import CBMClient, CBM_TOOLS, HIGH_TOKEN_TOOLS


class TestRegistry:
    def test_14_tools(self):
        assert len(CBM_TOOLS) == 14

    def test_high_token_subset(self):
        assert HIGH_TOKEN_TOOLS.issubset(set(CBM_TOOLS))

    def test_is_high_token(self):
        c = CBMClient(binary_path="/fake")
        assert c.is_high_token_tool("search_graph") is True
        assert c.is_high_token_tool("get_indexing_status") is False

    def test_unknown_tool_raises(self):
        import asyncio
        c = CBMClient(binary_path="/fake")
        with pytest.raises(ValueError, match="Unknown CBM tool"):
            asyncio.get_event_loop().run_until_complete(c.call_tool("bad_tool", {}))


class TestBinaryDiscovery:
    def test_explicit_path(self, tmp_path):
        f = tmp_path / "cbm"
        f.write_text("#!/bin/sh")
        f.chmod(0o755)
        c = CBMClient(binary_path=str(f))
        assert c.binary_path == str(f)
        assert c.available is True

    def test_none_when_not_found(self):
        with patch("shutil.which", return_value=None):
            c = CBMClient()
        assert isinstance(c.available, bool)


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_missing_binary_raises(self):
        c = CBMClient(binary_path=None)
        c.binary_path = None
        with pytest.raises(RuntimeError, match="not found"):
            await c.start()
