"""Tests for Spec Kit integration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from contextforge_mcp.compressor import HeadroomCompressor
from contextforge_mcp.speckit import (
    _specs_dir, _feature_dir,
    read_and_compress, implement_context, status,
)


@pytest.fixture
def project(tmp_path) -> Path:
    specs = tmp_path / "specs"
    f1 = specs / "001-map-view"
    f1.mkdir(parents=True)
    (f1 / "spec.md").write_text("# Map View\n\nAdd a map to property listings.\n")
    (f1 / "plan.md").write_text("# Plan\n\nUse Google Maps API.\n")
    (f1 / "tasks.md").write_text("# Tasks\n\n- [x] Install lib\n- [ ] Add markers\n- [ ] Navigation\n")
    (f1 / "context.md").write_text("# Context\n\nRelevant graph nodes found.\n")
    f2 = specs / "002-payments"
    f2.mkdir(parents=True)
    (f2 / "spec.md").write_text("# Payments\n\nWompi integration.\n")
    return tmp_path


@pytest.fixture
def compressor() -> HeadroomCompressor:
    c = HeadroomCompressor()
    c._available = False
    return c


class TestFeatureDir:
    def test_exact_match(self, project):
        specs = _specs_dir(str(project))
        assert _feature_dir("001-map-view", specs).name == "001-map-view"

    def test_prefix_match(self, project):
        specs = _specs_dir(str(project))
        assert _feature_dir("001", specs).name == "001-map-view"

    def test_none_returns_latest(self, project):
        specs = _specs_dir(str(project))
        assert _feature_dir(None, specs) is not None

    def test_not_found(self, project):
        specs = _specs_dir(str(project))
        assert _feature_dir("999", specs) is None


class TestReadAndCompress:
    @pytest.mark.asyncio
    async def test_reads_spec(self, project, compressor):
        result = await read_and_compress(compressor, "001", "spec.md", base=str(project))
        assert "Map View" in result
        assert "ContextForge:" in result

    @pytest.mark.asyncio
    async def test_error_missing_feature(self, project, compressor):
        result = await read_and_compress(compressor, "999", "spec.md", base=str(project))
        assert "error" in json.loads(result)

    @pytest.mark.asyncio
    async def test_error_missing_artifact(self, project, compressor):
        result = await read_and_compress(compressor, "001", "missing.md", base=str(project))
        data = json.loads(result)
        assert "error" in data
        assert "available" in data

    @pytest.mark.asyncio
    async def test_no_specs_dir(self, tmp_path, compressor):
        result = await read_and_compress(compressor, None, "spec.md", base=str(tmp_path))
        assert "error" in json.loads(result)


class TestImplementContext:
    @pytest.mark.asyncio
    async def test_bundles_all_artifacts(self, project, compressor):
        result = await implement_context(compressor, "001", base=str(project))
        assert "spec.md" in result
        assert "plan.md" in result
        assert "tasks.md" in result
        assert "context.md" in result

    @pytest.mark.asyncio
    async def test_shows_savings(self, project, compressor):
        result = await implement_context(compressor, "001", base=str(project))
        assert "saved" in result

    @pytest.mark.asyncio
    async def test_feature_not_found(self, project, compressor):
        result = await implement_context(compressor, "999", base=str(project))
        assert "error" in json.loads(result)

    @pytest.mark.asyncio
    async def test_partial_artifacts(self, project, compressor):
        """Feature 002 only has spec.md — should still work."""
        result = await implement_context(compressor, "002", base=str(project))
        assert "spec.md" in result
        assert "plan.md" not in result


class TestStatus:
    @pytest.mark.asyncio
    async def test_lists_features(self, project):
        s = await status(base=str(project))
        assert s["exists"] is True
        assert s["feature_count"] == 2

    @pytest.mark.asyncio
    async def test_detects_phase(self, project):
        s = await status(base=str(project))
        f = next(x for x in s["features"] if x["id"] == "001-map-view")
        assert f["phase"] == "tasked"
        assert f["cf_analyzed"] is True

    @pytest.mark.asyncio
    async def test_counts_tasks(self, project):
        s = await status(base=str(project))
        f = next(x for x in s["features"] if x["id"] == "001-map-view")
        assert f["tasks"]["total"] == 3
        assert f["tasks"]["done"] == 1

    @pytest.mark.asyncio
    async def test_no_specs_dir(self, tmp_path):
        s = await status(base=str(tmp_path))
        assert s["exists"] is False
        assert s["features"] == []
