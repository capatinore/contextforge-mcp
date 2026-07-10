# /speckit.cf-implement

Graph-aware implementation. Uses ContextForge instead of file reads.

## Arguments
- `$FEATURE_ID` — feature directory under `specs/`
- `$TASK_ID` — (optional) specific task number

## Steps

### Phase 0 — Load context
```
cf_implement_context(feature_id="$FEATURE_ID")
```

### Phase 1 — Understand the task
For each task, query the graph:
```
cbm_search_graph(name_pattern="<function from task>")
cbm_trace_path(function_name="<target>", direction="inbound")
cbm_get_impact(node_id="<node>")
```
Only read the actual file when you need to edit it.

### Phase 2 — Implement
- Make minimum change that satisfies the task
- Mark task complete in `tasks.md`
- Check `cbm_find_similar_code` before writing new functions

### Phase 3 — Validate
```
cbm_trace_path(function_name="<modified>", direction="both")
cbm_find_dead_code(confidence="high")
```

### Phase 4 — Report
- Mark task complete
- `cf_stats()` — show token savings
- State next task

## Rule: never grep. Always use `cbm_*` for discovery.
