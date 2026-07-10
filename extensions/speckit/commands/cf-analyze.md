# /speckit.cf-analyze

Analyze the existing codebase and compress the current spec before planning.
Run after `/speckit.specify`, before `/speckit.plan`.

## Steps

1. `cf_read_spec()` — load and compress the current spec
2. `cbm_search_graph(name_pattern="<pattern from spec>")` — find related code
3. `cbm_get_architecture()` — understand where the feature fits
4. `cbm_find_similar_code(node_id="<key node>")` — avoid duplicating existing code
5. `cbm_get_impact(node_id="<key node>")` — identify risk areas
6. Write `specs/$FEATURE_ID/context.md` with findings
7. `cf_stats()` — report token savings
