# contextforge-mcp

**MCP orchestrator combining [codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) + [headroom](https://github.com/headroomlabs-ai/headroom) + [Spec Kit](https://github.com/github/spec-kit) into a single pipeline.**

```
Agent (Claude Code / Cursor / Codex)
  │
  ▼
contextforge-mcp  ←── single MCP server
  │
  ├── codebase-memory-mcp  (knowledge graph: 99% fewer retrieval tokens)
  ├── headroom             (compression: 60–95% fewer prompt tokens)
  └── Spec Kit             (SDD workflow: spec → plan → tasks → implement)
```

---

## Install

```bash
# Prerequisites
npm install -g codebase-memory-mcp
pip install "headroom-ai[all]"
pip install spec-kit

# Install contextforge-mcp
pip install contextforge-mcp
```

## Setup

```bash
# Health check
contextforge-mcp doctor

# Configure Claude Code (writes .mcp.json)
contextforge-mcp install --target claude

# Configure Spec Kit extension
contextforge-mcp install --target speckit

# Both at once
contextforge-mcp install --target all
```

## Usage in Claude Code

```
# 1. Index the codebase (once per session)
cbm_index_repository(repo_path=".")

# 2. Query the graph (instead of grep/read)
cbm_search_graph(name_pattern=".*Payment.*")
cbm_trace_path(function_name="processPayment")
cbm_get_architecture()

# 3. Check token savings
cf_stats()
```

## Spec Kit workflow

```
/speckit.constitution
/speckit.specify
/speckit.cf-analyze      ← analyze codebase before planning
/speckit.plan
/speckit.tasks
/speckit.cf-index        ← index before implementing
/speckit.cf-implement    ← graph-aware implementation
/speckit.cf-stats        ← token savings report
```

## Tools (23 total)

| Prefix | Count | Description |
|--------|-------|-------------|
| `cbm_*` | 14 | codebase-memory-mcp graph tools |
| `cf_*` | 9 | ContextForge meta + Spec Kit tools |

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CBM_BINARY_PATH` | auto | Path to codebase-memory-mcp binary |
| `CF_MODEL` | `claude-sonnet-4-6` | Model hint for headroom |
| `CF_LOG_LEVEL` | `WARNING` | Log level |

## Credits

- [codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) — MIT
- [headroom](https://github.com/headroomlabs-ai/headroom) — Apache 2.0
- [spec-kit](https://github.com/github/spec-kit) — MIT

## License

MIT
