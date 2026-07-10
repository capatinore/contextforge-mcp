# ContextForge MCP — Reference

Use `cbm_*` tools for ALL structural queries. Never grep.

| Instead of...              | Use...                                  |
|----------------------------|-----------------------------------------|
| Grep for function name     | `cbm_search_graph(name_pattern="...")`  |
| Read files for callers     | `cbm_trace_path(direction="inbound")`   |
| Explore architecture       | `cbm_get_architecture()`                |
| Text search across files   | `cbm_search_code(query="...")`          |
| Read spec/plan/tasks       | `cf_read_spec/plan/tasks()`             |
| Full implement context     | `cf_implement_context(feature_id="...")`|

Run `cf_stats()` at end of session to see token savings.
