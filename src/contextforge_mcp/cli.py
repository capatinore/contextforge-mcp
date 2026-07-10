"""ContextForge MCP CLI."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(name="contextforge-mcp", help="MCP orchestrator: codebase-memory-mcp + headroom + Spec Kit", no_args_is_help=True)
console = Console()


@app.command()
def run() -> None:
    """Start ContextForge as a stdio MCP server."""
    from .server import main
    main()


@app.command()
def doctor() -> None:
    """Check all dependencies."""
    console.rule("[bold]ContextForge MCP — Doctor[/bold]")
    ok = True

    major, minor = sys.version_info[:2]
    if major == 3 and minor >= 10:
        console.print(f"  ✅  Python {major}.{minor}")
    else:
        console.print(f"  ❌  Python {major}.{minor} — need 3.10+"); ok = False

    try:
        import mcp; console.print("  ✅  mcp")
    except ImportError:
        console.print("  ❌  mcp — pip install mcp"); ok = False

    try:
        import headroom; console.print("  ✅  headroom-ai")
    except ImportError:
        console.print("  ⚠️   headroom-ai not installed — pip install 'headroom-ai[all]'")

    cbm = shutil.which("codebase-memory-mcp") or shutil.which("codebase-memory-mcp.exe")
    if cbm:
        console.print(f"  ✅  codebase-memory-mcp → {cbm}")
    else:
        console.print("  ❌  codebase-memory-mcp — npm install -g codebase-memory-mcp"); ok = False

    specify = shutil.which("specify")
    if specify:
        console.print(f"  ✅  specify (Spec Kit) → {specify}")
    else:
        console.print("  ⚠️   specify not found — pip install spec-kit  (optional)")

    console.print()
    if ok:
        console.print("[green]✅  Everything looks good![/green]")
    else:
        console.print("[yellow]⚠️   Some dependencies missing. See above.[/yellow]")
        raise typer.Exit(code=1)


@app.command()
def install(
    target: str = typer.Option("claude", help="claude | speckit | all"),
    project_dir: Path = typer.Option(Path("."), help="Project directory"),
) -> None:
    """Configure ContextForge MCP for Claude Code and/or Spec Kit."""

    if target in ("claude", "all"):
        mcp_path = project_dir / ".mcp.json"
        config: dict = {}
        if mcp_path.exists():
            try:
                config = json.loads(mcp_path.read_text())
            except json.JSONDecodeError:
                pass
        config.setdefault("mcpServers", {})
        config["mcpServers"]["contextforge-mcp"] = {
            "command": "contextforge-mcp",
            "args": ["run"],
        }
        mcp_path.write_text(json.dumps(config, indent=2))
        console.print(f"✅  Updated {mcp_path}")

    if target in ("speckit", "all"):
        _install_speckit(project_dir)

    if target not in ("claude", "speckit", "all"):
        console.print(f"[yellow]Unknown target: {target!r}[/yellow]")


def _install_speckit(project_dir: Path) -> None:
    import shutil as sh
    pkg_dir = Path(__file__).parent.parent.parent
    ext_src = pkg_dir / "extensions" / "speckit"
    if not ext_src.exists():
        console.print("[yellow]Extension source not found — clone the repo first.[/yellow]")
        return
    ext_dst = project_dir / ".specify" / "extensions" / "contextforge-mcp"
    ext_dst.mkdir(parents=True, exist_ok=True)
    sh.copytree(ext_src, ext_dst, dirs_exist_ok=True)
    console.print(f"✅  Spec Kit extension → {ext_dst}")
    claude_commands = project_dir / ".claude" / "commands"
    if (project_dir / ".claude").exists():
        claude_commands.mkdir(parents=True, exist_ok=True)
        for f in (ext_src / "commands").glob("*.md"):
            sh.copy2(f, claude_commands / f.name)
        console.print(f"✅  Slash commands → {claude_commands}")


@app.command()
def info() -> None:
    """Show version and info."""
    from . import __version__
    console.print(f"[bold]contextforge-mcp[/bold] v{__version__}")
    console.print("  codebase-memory-mcp: github.com/DeusData/codebase-memory-mcp")
    console.print("  headroom:            github.com/headroomlabs-ai/headroom")
    console.print("  spec-kit:            github.com/github/spec-kit")
    console.print("  repo:                github.com/capatinore/contextforge-mcp")


if __name__ == "__main__":
    app()
