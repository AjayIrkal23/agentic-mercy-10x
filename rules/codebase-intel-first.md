# Codebase Intel First — jcodemunch + graphify precedence

> Always-on rule. Resolves the priority conflict between the **lean-ctx** mandate
> ("ALWAYS use ctx_read/ctx_search instead of Read/Grep") and the **jcodemunch /
> graphify** mandate. Both are correct — they own *different jobs*. This file
> defines who owns what, so code-intelligence tools are actually used in
> planning, auditing, coding, and debugging — every time, on easy and complex
> tasks alike.

## The one rule

**For anything about CODE — what exists, where it lives, who calls it, what a
change breaks, how the system is wired — reach for jcodemunch / graphify FIRST.
Only then drop to file I/O.** jcodemunch reads its own finds too
(`get_symbol_source`, `get_file_outline`, `get_file_content`) — don't re-read a
source file through lean-ctx once jcodemunch already returned it, that's a
wasted second hop. lean-ctx (`ctx_read` / `ctx_search` / `ctx_shell` / `ctx_tree`)
owns non-code (docs, config, markdown, env, lockfiles), shell output, and dir
trees. It is NOT the tool for *discovering* code, and not the tool for reading
source once jcodemunch has it.

The pre-computed symbol index (jcodemunch) and dependency graph (graphify) answer
structural questions in **one call** that would otherwise cost dozens of
Read/grep round-trips — and they don't miss cross-module edges the way a manual
grep does.

## Peak jcodemunch — the full toolbox (reach past `search_symbols`)

Use the RIGHT specialized tool, not just the basics. Grouped by intent:

- **Discover / search** — `search_symbols`, `search_ast` (structural pattern),
  `search_text`, `search_columns` (DB), `find_similar_symbols`, `suggest_queries`.
- **Read code (instead of `ctx_read` on source)** — `get_symbol_source` (one
  fn/class), `get_file_outline` (skeleton), `get_file_content`,
  `get_context_bundle` / `get_ranked_context` / `assemble_task_context`
  (everything relevant to a task in ONE call), `winnow_symbols` (trim to essentials).
- **References & impact** — `find_references`, `find_importers`,
  `find_implementations`, `get_call_hierarchy`, `get_class_hierarchy`,
  `get_related_symbols`, `get_signal_chains`, `find_hot_paths`,
  `get_blast_radius`, `get_impact_preview`.
- **Architecture & maps** — `get_repo_map`, `get_repo_outline`, `get_file_tree`,
  `get_dependency_graph`, `get_dependency_cycles`, `get_layer_violations`,
  `get_tectonic_map`, `get_group_contracts`, `get_cross_repo_map`, `render_diagram`.
- **Audit / quality / risk** — `find_dead_code` / `get_dead_code_v2`,
  `find_unused_paths`, `get_coupling_metrics`, `get_hotspots`, `get_churn_rate`,
  `get_symbol_complexity`, `get_file_risk`, `get_repo_health`,
  `get_extraction_candidates`, `get_untested_symbols`, `diff_health_radar`,
  `analyze_perf`, `get_pr_risk_profile`, `get_changed_symbols`, `get_symbol_diff`.
- **Before you edit (safety)** — `check_rename_safe`, `check_delete_safe`,
  `check_references`, `get_symbol_importance`, `get_symbol_provenance`,
  `plan_refactoring`, `plan_turn` (plan the whole change), `get_impact_preview`.
- **Index / session** — `index_folder` (rebuild only if STALE),
  `get_watch_status`, `get_session_context`, `register_edit`, `invalidate_cache`,
  `resolve_repo`, `list_repos`.

**Default opener for a non-trivial task:** `plan_turn` or
`assemble_task_context` / `get_context_bundle` — they assemble the relevant
code slice in ONE call, so you rarely need a blind file read at all.

## Routing table (who owns the job)

| You need to… | Use FIRST | Not |
|---|---|---|
| Find a symbol / function / type | `mcp__jcodemunch__search_symbols` | grep, ctx_search |
| Read a function's body | `mcp__jcodemunch__get_symbol_source` | Read / ctx_read whole file |
| First-read a source file's shape | `mcp__jcodemunch__get_file_outline` / `get_file_content` | ctx_read blind |
| Pull all code relevant to a task | `mcp__jcodemunch__assemble_task_context` / `get_context_bundle` | many ctx_reads |
| Find every caller / importer | `mcp__jcodemunch__find_references` / `find_importers` | grep -r |
| Know what a change breaks | `mcp__jcodemunch__get_blast_radius` | guessing |
| Dead / unused code | `mcp__jcodemunch__find_dead_code` / `get_dead_code_v2` | manual sweep |
| Coupling / hotspots / churn | `mcp__jcodemunch__get_coupling_metrics` / `get_hotspots` | — |
| Call hierarchy / flow | `mcp__jcodemunch__get_call_hierarchy` / `get_signal_chains` | grep |
| Repo layout / orientation | `mcp__jcodemunch__get_repo_map` / `get_repo_outline` | ls -R |
| Architecture / entry points | `mcp__graphify__god_nodes` / `graph_stats` | reading dirs |
| "Who depends on X?" | `mcp__graphify__get_neighbors` | grep imports |
| "How do A and B connect?" | `mcp__graphify__shortest_path` | tracing by hand |
| Natural-language structure Q | `mcp__graphify__query_graph` | Explore agent |
| Read a doc / config / .env / md (non-code) | `ctx_read` (lean-ctx) | jcodemunch |
| Run git / build / lint / test | `ctx_shell` (lean-ctx) | — |
| List a directory / any path | `ctx_tree` (lean-ctx) | ls -R |

**Decision shortcut:** "Am I discovering/understanding code, reading a source
file, or reading something non-code?" Discovering or reading source → jcodemunch
(it returns the content in the same call, no second read needed). Non-code
(docs/config/env/lockfiles), shell output, or directory listing → lean-ctx.
Never `grep -r` / `find` / `ls -R` across source to discover structure — that's
what the graph is for.

## Per-phase playbook

- **Planning** — `graphify graph_stats` + `god_nodes` + `query_graph`, and
  `jcodemunch get_repo_map` + `get_context_bundle`, BEFORE writing the plan or
  spawning Explore agents. The graph IS the codebase map.
- **Auditing** — `jcodemunch find_dead_code`, `get_blast_radius`,
  `get_coupling_metrics`, `get_hotspots`; `graphify god_nodes` + `get_neighbors`.
  Complete + ranked beats a grep that misses edges.
- **Coding** — `jcodemunch search_symbols` + `get_symbol_source` to locate,
  `find_references` to find ALL call sites, `get_blast_radius` before touching a
  shared symbol, `graphify get_neighbors` for downstream impact. Native Read/Grep
  on source is blocked during active coding until jcodemunch is consulted.
- **Debugging** — `jcodemunch get_call_hierarchy` + `find_implementations` +
  `get_signal_chains`; `graphify shortest_path` to connect two points.

## Freshness (they are kept fresh automatically)

The index + graph are rebuilt by systemd **watch daemons** and verified by the
SessionStart guards (`jcodemunch-index-guard`, `graphify-index-guard`). You do
NOT normally rebuild them. Act only if a guard prints **STALE / MISSING** at
session start:
- jcodemunch stale → `mcp__jcodemunch__index_folder({"path": "<root>", "incremental": true})`
- graphify stale → `graphify update <root>` (Bash; cheap, no LLM)

## Enforcement layer (so this isn't just advice)

- `codebase-intel-router.py` (UserPromptSubmit) injects a task-specific directive
  the first time each task-type appears in a session.
- `jcodemunch-enforce.py pre-tool-use` gates blind source reads — native
  Read/Grep/Glob **and** lean-ctx `ctx_read`/`ctx_search`/`ctx_multi_read` on
  source files — in **every phase** (planning/audit/debug/coding, not just after
  a code write) until you make at least one jcodemunch call this conversation.
  One jcodemunch call unlocks all subsequent reads; the gate fails open after a
  small block budget so you are never stuck. Non-code (md/config/env/`~/.claude`)
  is always exempt.
- `graphify-enforce.py pre-tool-use` nudges before Explore agents / broad Bash
  searches.

Deep playbook: skill `codebase-intel-first` (and `jcodemunch-token-saver`,
`graphify`).
