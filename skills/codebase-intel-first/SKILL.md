---
name: codebase-intel-first
description: MANDATORY orchestration step for ANY task that touches a codebase — planning, auditing, code
  review, implementing, refactoring, debugging, or "help me understand X". Run the jcodemunch symbol index
  + graphify dependency graph FIRST to build a structural mental model, BEFORE reading files, grepping,
  or spawning Explore agents. Resolves the precedence between lean-ctx (ctx_read/ctx_search, which owns
  file I/O) and code-intelligence retrieval (jcodemunch/graphify, which own discovery/understanding).
  Trigger at the START of every plan, audit, or coding task on easy and complex work alike — the graph/index
  answer structural questions in one call instead of dozens of round-trips and never miss cross-module
  edges. Use together with jcodemunch-token-saver and graphify.
disable-model-invocation: false
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
  - agent
  - agents
  - alike
  - already
  - analysis
  - answer
  - ast
  - audit
  - auditing
  - bigger
  - blast
  - body
  - boundaries
  - broader
  - build
  - call
  - callees
  - callers
  - change
  - changes
  - code
  - code-intelligence
  - codebase
  - coding
  - complex
  - config
  - confirm
  - context
  - contracts
  - create
  - cross-file
  - cross-module
  - ctx_read/ctx_search
  - dead
  - dead-code
  - debugging
  - dependency
  - deterministic
  - discovery/understanding
  - docs
  - dozens
  - dramatically
  - easy
  - edges
  - engineers
  - env
  - every
  - exact
  - execution
  - explore
  - fast
  - file
  - files
  - first
  - fits
  - flow
  - function/class/method
  - give
  - graph
  - graph/index
  - graphify
  - graphs
  - grepping
  - help
  - higher-level
  - i/o
  - identify
  - impacted
  - implementing
  - index
  - instead
  - intel
  - jcodemunch
  - jcodemunch-token-saver
  - jcodemunch/graphify
  - json
  - know
  - known
  - layer
  - layers
  - lean-ctx
  - likely
  - locate
  - lookup
  - making
  - mandatory
  - map
  - markdown
  - mcp
  - mental
  - miss
  - model
  - need
  - never
  - non-code
  - orchestration
  - owns
  - path
  - pattern
  - perspective
  - picture
  - plan
  - planning
  - precedence
  - problem
  - progressively
  - questions
  - radius
  - read
  - read/grep/find
  - reading
  - reads
  - reduces
  - refactoring
  - refining
  - repository
  - resolves
  - retrieval
  - review
  - right
  - round-trips
  - scope
  - search
  - section
  - server
  - single-file
  - size
  - skip
  - small
  - solve
  - spawning
  - start
  - startup
  - step
  - structural
  - structure
  - subagent
  - symbol
  - task
  - tell
  - text
  - time
  - together
  - token
  - touches
  - trace
  - trigger
  - trivial
  - understand
  - unfamiliar
  - usage
  - whole
  - wire
  - work
  - zoom
  paths: []
  intents:
  - intel
---
# Codebase Intel First

The orchestration layer over `jcodemunch-token-saver` (symbol index) and
`graphify` (dependency graph). Those two skills tell you HOW to use each tool.
This one tells you WHEN and IN WHAT ORDER — so code intelligence is the FIRST
move in every phase, not an afterthought.

## The precedence rule (memorize this)

> **Discovering or understanding code → jcodemunch / graphify FIRST.
> Reading a file you already located, or any non-code file → lean-ctx `ctx_read`.**

lean-ctx's "ALWAYS use ctx_read instead of Read" mandate is about *file I/O
efficiency*. It does NOT mean "read files to discover structure." Discovery is
the graph's job. Never `grep -r` / `find` / `ls -R` across source to learn how
the code is shaped — query the graph.

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

## After the graph points you somewhere

Use lean-ctx to read the EXACT files/symbols surfaced:
- `ctx_read "<path>" mode=signatures|map|lines:N-M` for the pinpointed file
- `ctx_read` for any doc / config / `.env` / markdown
- `ctx_shell` for git / build / lint / test
Read narrowly — jcodemunch already gave you byte-precise locations.

## Freshness — do NOT rebuild unless told

systemd watch daemons + SessionStart guards keep the index/graph fresh. Rebuild
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
| "ctx_read is mandatory so I'll read to discover" | ctx_read is for files you LOCATED; discover via the graph |

See also: `jcodemunch-token-saver`, `graphify`, rule `~/.claude/rules/codebase-intel-first.md`.
