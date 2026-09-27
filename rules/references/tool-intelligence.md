# Tool-Intelligence Map — intent → jcodemunch/graphify/jdocmunch playbook

> Human-readable mirror of the machine source of truth
> [`hooks/tool-intelligence.json`](../../hooks/tool-intelligence.json). The prompt
> router (`code_intel.py`) consumes the JSON; rules and skills link **here**. Keep
> the two in sync (small file). Part of making jcodemunch the primary smart engine
> — see [[codebase-intel-first]].

**Pipeline:** facts (jcodemunch structure + graphify architecture + jdocmunch docs, in parallel) → reasoning (sequential-thinking) → action (Edit/ctx_patch → index stays fresh). Tools are bare names; prefix `mcp__jcodemunch__` / `mcp__graphify__` / `mcp__jdocmunch__`.

## Intent → ordered playbook

### understand / plan / orient / architecture
1. `plan_turn` · alt `assemble_task_context` / `get_context_bundle` — whole slice in ONE call
2. graphify `graph_stats` · `god_nodes` · `query_graph` — architecture shape
3. `get_repo_map` · `get_repo_outline` — layout (never `ls -R`)
4. `get_file_outline` → `get_symbol_source` — read located files
5. **`search_symbols(semantic=true)`** · `find_similar_symbols` — find by MEANING ⟵ embeddings
6. jdocmunch `get_toc` / `search_sections` — docs

### audit / tech-debt / dead-code / health
1. `find_dead_code` · `get_dead_code_v2` · `find_unused_paths`
2. `get_hotspots` · `get_churn_rate` · `get_coupling_metrics`
3. `get_repo_health` · `get_file_risk` · `get_architecture_metrics`
4. `get_blast_radius` (per symbol)
5. `get_extraction_candidates` · `get_symbol_complexity` · `get_layer_violations` · `get_untested_symbols`
6. graphify `god_nodes` · `get_neighbors`
7. jdocmunch `get_doc_coverage` · `get_stale_pages`

### implement / build / add feature
1. `assemble_task_context` · `get_context_bundle` — the slice
2. `search_symbols` → `get_symbol_source` — locate precisely
3. **`find_similar_symbols(semantic)`** — REUSE patterns, don't reinvent ⟵ embeddings
4. `find_references` · `find_importers` · `get_call_hierarchy` — every call site
5. `get_blast_radius` · `get_impact_preview` — impact before edit
6. `check_edit_safe` · `check_rename_safe` · `check_delete_safe` — pre-edit gate
7. `register_edit` / `index_file` — keep index fresh (also automatic)

### debug / root-cause / regression
1. `get_call_hierarchy` · `get_signal_chains` · `find_hot_paths` — trace the path
2. `find_implementations` · `find_references` — impls + callers
3. **`search_symbols(semantic=true)`** — culprit by MEANING when name unknown ⟵ embeddings
4. graphify `shortest_path` · `get_neighbors` — connect two points cross-module
5. `get_blast_radius` — before the fix
6. `get_symbol_provenance` · `get_changed_symbols` — regression forensics

### review / PR / santa
1. `get_changed_symbols` · `get_symbol_diff` · `diff_health_radar` — what changed
2. `get_pr_risk_profile` · `get_file_risk` — diff risk
3. `get_blast_radius` · `find_references` — broke any callers?
4. `get_untested_symbols` · `get_runtime_coverage` — coverage gaps
5. `get_symbol_complexity` · `get_coupling_metrics` — quality regressions

### refactor / rename / extract (safety FIRST)
1. `check_rename_safe` · `check_delete_safe` · `check_edit_safe` · `check_references`
2. `find_references` · `find_importers` — every site
3. `get_blast_radius` · `get_impact_preview` · `plan_refactoring`
4. **`find_similar_symbols(semantic)`** — dedupe semantic clones ⟵ embeddings
5. `get_extraction_candidates` · `get_dependency_cycles` · `get_layer_violations`

### navigate_docs (jdocmunch)
1. `search_sections` · `get_toc` · `get_toc_tree` · `search_titles`
2. `get_section` · `get_sections` · `get_section_context`
3. `get_document_outline`
4. `find_code_examples` · `find_endpoint` · `lookup_term`

## Cross-cutting

- **Semantic search (NEW):** use whenever the exact symbol name is unknown, or to find related/similar code by meaning — `search_symbols(semantic=true)`, `find_similar_symbols`, `get_related_symbols`. Backend: ollama `all-minilm` (384-dim). Lazily embeds on first call; `embed_repo` pre-warms. Verify: `check_embedding_drift`.
- **Safety before edit:** `check_edit_safe` / `check_rename_safe` / `check_delete_safe` / `get_blast_radius`.
- **Freshness:** `index-lifecycle.py` auto-keeps the active repo fresh (symbols + AI summaries; embeddings warm-up — Phase 1). Manual if STALE: `index_folder(incremental=true)`, `graphify update <root>`.
