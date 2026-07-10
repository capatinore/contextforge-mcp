# /speckit.cf-index

Index the codebase into the ContextForge knowledge graph before implementing.

## Steps

1. Call `cf_stats()` — confirm ContextForge is connected
2. Call `cbm_index_repository(repo_path=".")` — build the knowledge graph
3. Call `cbm_get_indexing_status()` — confirm completion
4. Call `cbm_get_architecture()` — show compressed architecture overview
5. Report: files indexed, modules detected, token savings, ready for `/speckit.cf-implement`

## Notes
- Re-run after significant refactoring
- Use `cbm_*` tools instead of grep/Read for ALL structural queries after indexing
