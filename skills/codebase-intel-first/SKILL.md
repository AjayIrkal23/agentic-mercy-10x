---
name: codebase-intel-first
description: 'Code intelligence first: build a structural model with the jcodemunch symbol index and graphify graph before reading files, grepping, or spawning Explore agents. Defines the precedence between jcodemunch/graphify (discovery) and lean-ctx (residual file I/O).'
when_to_use: 'Use at the start of any codebase task: planning, auditing, review, implementing, refactoring, debugging, or ''help me understand X''.'
metadata:
  schema: 1
  category: intel
  surfaces:
  - codebase
  platforms:
  - linux
  - darwin
  - windows
  token-cost: 935
  triggers:
    keywords:
    - jcodemunch
    - graphify
    - code intelligence
    - how is wired
    - how does work
    - who calls
    - where is defined
    - where is used
    - blast radius
    - find references
    - call hierarchy
    - dependency graph
    - codebase map
    - understand the codebase
    - unfamiliar codebase
    paths: []
    intents:
    - intel
---
# Codebase Intel First

The orchestration layer over jcodemunch (symbol index; toolbox in
`references/jcodemunch-toolbox.md`) and `graphify` (dependency graph). Those tell you HOW to use each tool.
This one tells you WHEN and IN WHAT ORDER — so code intelligence is the FIRST
move in every phase, not an afterthought.

## The precedence rule (MUST — standing user directive)

> **Code → jcodemunch FIRST. Architecture / "how is X wired" / who depends on X →
> graphify FIRST. Doc sets (docs/, md trees, READMEs) → jdocmunch FIRST. Non-trivial
> reasoning over those facts → sequential-thinking. A single non-code file → `Read`
> or `ctx_read` (both fine).**

Exemption: a trivial one-line answer or a single lookup (a path, a version). Order:
facts (jcodemunch / graphify / jdocmunch) → reasoning (sequential-thinking) → action.
Never `grep -r` / `find` / `ls -R` across source to learn how the code is shaped —
query the index or the graph. The prompt router and post-write hooks print "call X
now" lines; follow them.

## Phase playbook — run these BEFORE anything else

### Planning / "understand X" / architecture
1. `mcp__graphify__graph_stats` — size + shape
2. `mcp__graphify__god_nodes` — entry points & most-connected modules
3. `mcp__graphify__query_graph "<your question>"` — NL structural query
4. `mcp__jcodemunch__get_repo_map` / `get_repo_outline` — layout
5. `mcp__jcodemunch__get_context_bundle` / `search_symbols "<name>"` — the relevant code
→ Now write the plan. The graph IS your codebase map; don't rebuild it by reading dirs.

### Auditing / review / dead-code / impact
1. `mcp__jcodemunch__find_dead_code` / `get_dead_code_v2`
2. `mcp__jcodemunch__get_blast_radius "<symbol>"`
3. `mcp__jcodemunch__get_coupling_metrics` / `get_hotspots`
4. `mcp__jcodemunch__find_references` / `find_importers "<symbol>"`
5. `mcp__graphify__god_nodes` + `get_neighbors "<node>"`
→ Complete + ranked. A grep-based audit silently misses cross-module call sites.

### Implementing / changing code
1. `mcp__jcodemunch__search_symbols "<name>"` + `get_symbol_source` — locate precisely
2. `mcp__jcodemunch__find_references` / `find_importers` — EVERY caller before a signature change
3. `mcp__jcodemunch__get_blast_radius "<symbol>"` — before touching anything shared
4. `mcp__graphify__get_neighbors "<file>"` — downstream dependents
→ Then edit. Native Read/Grep on source is blocked during coding until jcodemunch is used.

### Debugging
1. `mcp__jcodemunch__get_call_hierarchy "<fn>"` — callers + callees
2. `mcp__jcodemunch__find_implementations` / `find_references`
3. `mcp__jcodemunch__get_signal_chains` — data/control flow
4. `mcp__graphify__shortest_path "<A>" "<B>"` — connect two points

### Docs work
1. `mcp__jdocmunch__get_toc` / `search_sections "<topic>"` — locate sections
2. `mcp__jdocmunch__get_section` / `get_section_context` — read only what you need
→ Repo not in `~/.doc-index` → `Read` the file.
→ `search_sections` is hybrid (local ollama `all-minilm`) only for an index built with embeddings — `doc_list_repos` shows `has_embeddings: true`; otherwise it is lexical. Scope with `path_glob="docs/**"` (lockfiles and empty headings otherwise rank high).

## After the graph points you somewhere

Read the EXACT files/symbols surfaced — jcodemunch `get_symbol_source` for code,
`Read` or `ctx_read` (both fine) for docs/config, `Bash` for git/build/lint/test.
Read narrowly — jcodemunch already gave you byte-precise locations.

## Freshness — do NOT rebuild unless told

Event-driven `index-lifecycle.py` + SessionStart guards keep the index/graph fresh. Rebuild
ONLY when a guard prints STALE/MISSING:
- jcodemunch: `mcp__jcodemunch__index_folder({"path": "<root>", "incremental": true})`
- graphify: `graphify update <root>` (Bash, cheap, no LLM)

## Red flags (you are doing it wrong)

| Thought | Correct move |
|---|---|
| "Let me grep the repo to find where X is" | `mcp__jcodemunch__search_symbols "X"` |
| "Let me read this whole file to understand it" | `get_symbol_source` / `ctx_read mode=signatures` |
| "Let me Explore-agent the architecture" | `mcp__graphify__query_graph` / `god_nodes` |
| "I'll just change this function" | `find_references` + `get_blast_radius` first |
| "The symbol summary says what it does" | Summaries are a small model's gloss and miss tenancy/auth checks; read `get_symbol_source` before any security claim |
| "ctx_read is mandatory so I'll read to discover" | ctx_read is for files you LOCATED; discover via the graph |
| "I'll skim the docs folder" | `mcp__jdocmunch__search_sections` / `get_toc` |
| "I'll reason it through inline" (plan/debug/design) | `mcp__sequential-thinking__sequentialthinking` |

See also: `graphify`, `references/jcodemunch-toolbox.md`, `references/rules-codebase-intel-first.md` (precedence rule).
