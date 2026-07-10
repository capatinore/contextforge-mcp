# contextforge-mcp

**MCP compression middleware** that connects [codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) + [headroom](https://github.com/headroomlabs-ai/headroom) + [Spec Kit](https://github.com/github/spec-kit) into a unified, token-efficient workflow.

## Architecture

```
Claude Code
  ├── codebase-memory-mcp   ← graph queries (cbm_* tools)
  │         │
  │         └── large result
  │                   │
  └── contextforge-mcp  ← YOU ARE HERE
            │
            cf_compress_cbm(result, tool_name)
            │
            └── compressed result (60-95% fewer tokens)
```

**ContextForge does NOT proxy codebase-memory-mcp** — both servers run independently. The agent calls CBM for graph queries, then passes results through ContextForge for compression. This design is reliable, cross-platform, and works with any MCP client.

## Install

```bash
npm install -g codebase-memory-mcp
pip install "headroom-ai[all]"
pip install contextforge-mcp
```

## Setup

```bash
# Health check
contextforge-mcp doctor

# Configure Claude Code (writes .mcp.json with both servers)
contextforge-mcp install --target claude
```

## Workflow

```python
# 1. Query the graph (via codebase-memory-mcp)
result = cbm_search_graph(name_pattern=".*Payment.*", label="Function")

# 2. Compress the result (via contextforge-mcp)
compressed = cf_compress_cbm(result=result, tool_name="search_graph")
# → [ContextForge ✓ search_graph: 8420→612 tokens (93% saved in 45ms)]

# 3. Use compressed result in your context
# 4. Check savings
cf_stats()
```

## Tools (9 total)

### Compression
| Tool | Description |
|------|-------------|
| `cf_compress_cbm(result, tool_name)` | Compress CBM tool output |
| `cf_compress(text, hint)` | Compress arbitrary text |

### Stats
| Tool | Description |
|------|-------------|
| `cf_stats()` | Session token savings + cost estimate |
| `cf_reset_stats()` | Reset session counters |

### Spec Kit
| Tool | Description |
|------|-------------|
| `cf_read_spec(feature_id)` | Compressed spec.md |
| `cf_read_plan(feature_id)` | Compressed plan.md |
| `cf_read_tasks(feature_id)` | Compressed tasks.md |
| `cf_read_artifact(artifact, feature_id)` | Any artifact |
| `cf_implement_context(feature_id)` | Full bundle (spec+plan+tasks) |
| `cf_speckit_status()` | List all features + phase |

## Supported CBM tool names for cf_compress_cbm

`search_graph` · `search_code` · `get_architecture` · `find_dead_code` · `find_similar_code` · `get_impact` · `trace_path` · `trace_call_path` · `cypher_query` · `get_cross_service_links` · `get_node_details`

## Add to CLAUDE.md

```markdown
## ContextForge MCP — Compression Workflow

After EVERY codebase-memory-mcp tool call that returns a large result,
immediately call cf_compress_cbm(result, tool_name) to compress it.

| CBM Query | Then compress with |
|-----------|-------------------|
| cbm_search_graph(…) | cf_compress_cbm(result, "search_graph") |
| cbm_get_architecture() | cf_compress_cbm(result, "get_architecture") |
| cbm_search_code(…) | cf_compress_cbm(result, "search_code") |
| cbm_trace_path(…) | cf_compress_cbm(result, "trace_path") |
| cbm_get_impact(…) | cf_compress_cbm(result, "get_impact") |

Call cf_stats() at end of session to measure total savings.
```

## Credits
- [codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) — MIT
- [headroom](https://github.com/headroomlabs-ai/headroom) — Apache 2.0
- [spec-kit](https://github.com/github/spec-kit) — MIT

## License
MIT
