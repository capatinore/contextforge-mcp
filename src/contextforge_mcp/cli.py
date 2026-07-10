"""ContextForge MCP CLI."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="contextforge-mcp",
    help="MCP compression middleware: codebase-memory-mcp + headroom + Spec Kit",
    no_args_is_help=True,
)
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
        console.print(f"  ❌  Python {major}.{minor} — need 3.10+")
        ok = False

    try:
        import mcp
        console.print("  ✅  mcp (Model Context Protocol SDK)")
    except ImportError:
        console.print("  ❌  mcp — run: pip install mcp")
        ok = False

    try:
        import headroom
        console.print("  ✅  headroom-ai (compression enabled)")
    except ImportError:
        console.print("  ⚠️   headroom-ai not installed — compression disabled")
        console.print("       Fix: pip install 'headroom-ai[all]'")

    cbm = shutil.which("codebase-memory-mcp") or shutil.which("codebase-memory-mcp.exe")
    if cbm:
        console.print(f"  ✅  codebase-memory-mcp → {cbm}")
    else:
        console.print("  ❌  codebase-memory-mcp not found")
        console.print("       Fix: npm install -g codebase-memory-mcp")
        ok = False

    specify = shutil.which("specify")
    if specify:
        console.print(f"  ✅  specify (Spec Kit) → {specify}")
    else:
        console.print("  ⚠️   specify not found — optional")
        console.print("       Fix: pip install specify")

    console.print()
    if ok:
        console.print("[green]✅  Everything looks good![/green]")
        console.print()
        console.print("[dim]Workflow:[/dim]")
        console.print("  1. Add contextforge-mcp to .mcp.json")
        console.print("  2. In Claude Code: cbm_search_graph(...) → cf_compress_cbm(result, 'search_graph')")
        console.print("  3. cf_stats() to see token savings")
    else:
        console.print("[yellow]⚠️   Some dependencies missing. See above.[/yellow]")
        raise typer.Exit(code=1)


@app.command()
def install(
    target: str = typer.Option("claude", help="claude | speckit | all"),
    project_dir: Path = typer.Option(Path("."), help="Project directory"),
) -> None:
    """Configure ContextForge for Claude Code and/or Spec Kit."""

    if target in ("claude", "all"):
        _install_claude(project_dir)

    if target in ("speckit", "all"):
        _install_speckit(project_dir)

    if target not in ("claude", "speckit", "all"):
        console.print(f"[yellow]Unknown target: {target!r}. Use: claude | speckit | all[/yellow]")


def _install_claude(project_dir: Path) -> None:
    """Write .mcp.json with both codebase-memory-mcp and contextforge-mcp."""
    import shutil as sh

    mcp_path = project_dir / ".mcp.json"
    config: dict = {}
    if mcp_path.exists():
        try:
            config = json.loads(mcp_path.read_text())
        except json.JSONDecodeError:
            pass

    config.setdefault("mcpServers", {})

    # Add codebase-memory-mcp if not already present
    cbm_bin = sh.which("codebase-memory-mcp") or "codebase-memory-mcp"
    if "codebase-memory-mcp" not in config["mcpServers"]:
        config["mcpServers"]["codebase-memory-mcp"] = {
            "command": cbm_bin,
            "args": [],
        }

    # Add/update contextforge-mcp
    config["mcpServers"]["contextforge-mcp"] = {
        "command": "contextforge-mcp",
        "args": ["run"],
    }

    # Remove old contextforge entry if present
    config["mcpServers"].pop("contextforge", None)

    mcp_path.write_text(json.dumps(config, indent=2))
    console.print(f"✅  Updated {mcp_path}")
    console.print()
    console.print("[bold]Two MCP servers configured:[/bold]")
    console.print("  codebase-memory-mcp  → graph queries (cbm_* tools)")
    console.print("  contextforge-mcp     → compression middleware (cf_* tools)")
    console.print()
    console.print("[dim]Workflow in Claude Code:[/dim]")
    console.print("  result = cbm_search_graph(name_pattern='.*Payment.*')")
    console.print("  compressed = cf_compress_cbm(result=result, tool_name='search_graph')")
    console.print("  cf_stats()  # see token savings")


def _install_speckit(project_dir: Path) -> None:
    import shutil as sh
    pkg_dir = Path(__file__).parent.parent.parent
    ext_src = pkg_dir / "extensions" / "speckit"

    if not ext_src.exists():
        console.print("[yellow]Extension source not found — clone the repo and run from there.[/yellow]")
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

    table = Table(title="ContextForge MCP", show_header=False)
    table.add_column("Key", style="bold cyan")
    table.add_column("Value")
    table.add_row("Version", __version__)
    table.add_row("Architecture", "Middleware — runs alongside codebase-memory-mcp")
    table.add_row("Tools", "cf_compress_cbm, cf_compress, cf_stats + Spec Kit tools")
    table.add_row("", "")
    table.add_row("Built on", "")
    table.add_row("  codebase-memory-mcp", "github.com/DeusData/codebase-memory-mcp")
    table.add_row("  headroom-ai", "github.com/headroomlabs-ai/headroom")
    table.add_row("  spec-kit", "github.com/github/spec-kit")
    table.add_row("", "")
    table.add_row("Repo", "github.com/capatinore/contextforge-mcp")
    table.add_row("PyPI", "pip install contextforge-mcp")
    console.print(table)


if __name__ == "__main__":
    app()
