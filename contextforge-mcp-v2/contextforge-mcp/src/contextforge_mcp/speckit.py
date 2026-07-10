"""Spec Kit integration — read and compress SDD artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .compressor import HeadroomCompressor


def _specs_dir(base: str = ".") -> Path:
    for parent in [Path(base), *Path(base).parents[:3]]:
        candidate = parent / "specs"
        if candidate.is_dir():
            return candidate
    return Path(base) / "specs"


def _feature_dir(feature_id: str | None, specs: Path) -> Path | None:
    if not specs.exists():
        return None
    if feature_id:
        exact = specs / feature_id
        if exact.is_dir():
            return exact
        matches = [d for d in specs.iterdir() if d.is_dir() and d.name.startswith(feature_id)]
        return matches[0] if matches else None
    dirs = [d for d in specs.iterdir() if d.is_dir()]
    return max(dirs, key=lambda d: d.stat().st_mtime) if dirs else None


def _read(feature_dir: Path, filename: str) -> str | None:
    path = feature_dir / filename
    return path.read_text(encoding="utf-8") if path.exists() else None


async def read_and_compress(
    compressor: "HeadroomCompressor",
    feature_id: str | None,
    artifact: str,
    base: str = ".",
) -> str:
    specs = _specs_dir(base)
    feat = _feature_dir(feature_id, specs)

    if feat is None:
        return json.dumps({
            "error": f"No feature found in {specs}",
            "hint": "Run /speckit.specify first.",
            "feature_id": feature_id,
        })

    content = _read(feat, artifact)
    if content is None:
        return json.dumps({
            "error": f"{artifact} not found in {feat.name}",
            "available": [f.name for f in feat.iterdir() if f.is_file()],
        })

    result = await compressor.compress(content, f"speckit_{artifact}", force=True)
    header = (
        f"[ContextForge: {artifact} — "
        f"{result.original_tokens}→{result.compressed_tokens} tokens "
        f"({result.ratio:.0%} saved) | {feat.name}]\n\n"
    )
    return header + result.content


async def implement_context(
    compressor: "HeadroomCompressor",
    feature_id: str | None,
    base: str = ".",
) -> str:
    specs = _specs_dir(base)
    feat = _feature_dir(feature_id, specs)

    if feat is None:
        return json.dumps({"error": "Feature not found", "specs_dir": str(specs)})

    artifacts = ["spec.md", "plan.md", "tasks.md", "context.md", "data-model.md"]
    sections = []
    total_orig = total_comp = 0

    for artifact in artifacts:
        content = _read(feat, artifact)
        if content is None:
            continue
        r = await compressor.compress(content, f"speckit_{artifact}", force=True)
        total_orig += r.original_tokens
        total_comp += r.compressed_tokens
        sections.append(f"## {artifact}\n\n{r.content}")

    if not sections:
        return json.dumps({"error": "No Spec Kit artifacts found", "feature_dir": str(feat)})

    ratio = 1 - (total_comp / total_orig) if total_orig > 0 else 0
    header = (
        f"[ContextForge: implement context — {feat.name} — "
        f"{total_orig}→{total_comp} tokens ({ratio:.0%} saved)]\n\n"
    )
    return header + "\n\n---\n\n".join(sections)


async def status(base: str = ".") -> dict[str, Any]:
    specs = _specs_dir(base)
    if not specs.exists():
        return {"exists": False, "specs_dir": str(specs), "features": []}

    features = []
    for feat in sorted(specs.iterdir()):
        if not feat.is_dir():
            continue
        files = {f.name for f in feat.iterdir() if f.is_file()}
        phase = "empty"
        if "spec.md" in files: phase = "specified"
        if "plan.md" in files: phase = "planned"
        if "tasks.md" in files: phase = "tasked"

        tasks_done = tasks_total = 0
        tasks_content = _read(feat, "tasks.md")
        if tasks_content:
            lines = tasks_content.splitlines()
            tasks_total = sum(1 for l in lines if l.strip().startswith("- ["))
            tasks_done = sum(1 for l in lines if l.strip().startswith("- [x]"))

        features.append({
            "id": feat.name, "phase": phase,
            "cf_analyzed": "context.md" in files,
            "tasks": {"done": tasks_done, "total": tasks_total},
        })

    return {"exists": True, "feature_count": len(features), "features": features}
