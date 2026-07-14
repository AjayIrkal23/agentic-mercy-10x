---
name: graphify
description: Build or use a graphify knowledge graph (graphify-out/) for codebase and architecture questions.
  If GRAPH_REPORT.md / graph.json exist, read them first; if not, run a scoped graphify pipeline (detect
  → extract → build → report) before brute-force repo reads.
schema: 1
category: intel
surfaces:
- codebase
platforms:
- linux
- darwin
- windows
token-cost: 690
triggers:
  keywords:
  - architecture
  - brute-force
  - build
  - codebase
  - detect
  - exist
  - extract
  - first
  - graph
  - graph.json
  - graph_report.md
  - graphify
  - graphify-out
  - knowledge
  - pipeline
  - questions
  - read
  - reads
  - repo
  - report
  - scoped
  paths: []
  intents:
  - intel
---
# Graphify (Cursor)

Turn a folder into **`graphify-out/graph.json`**, **`GRAPH_REPORT.md`**, **`graph.html`**, and optionally **`wiki/`**. Reduces exploratory reads by surfacing god nodes, communities, and suggested questions.

**Official upstream skill body (VS Code parity, full pipeline):** bundled in PyPI `graphifyy` at `site-packages/graphify/skill-vscode.md` — use it for verbatim step commands when invoked as `/graphify`.

## When to invoke

- Questions about architecture, domains, coupling, navigation, layers, surprising connections across files.
- Onboarding (“how does routing work?”) when the corpus is non-trivial.
- Any prompt where **`graphify-out/GRAPH_REPORT.md`** or **`graph.json`** already exists → **consult first**.

## Resolution order

1. **Discover artifacts** under the workspace root: `graphify-out/graph.json`, `graphify-out/GRAPH_REPORT.md`, `graphify-out/wiki/index.md`.
2. **If artifacts exist:**
   - Read **`GRAPH_REPORT.md`** (summarize god nodes & surprising connections in the reply).
   - Prefer **`wiki/index.md`** for navigation when present.
   - If MCP **graphify** is connected, query the graph instead of mass file reads where appropriate.
3. **If missing:**
   - Run **detect**; if corpus is huge (upstream thresholds: **`total_words` > 2M OR `total_files` > 200**), warn and ask for a subfolder scope.
   - Run the upstream pipeline (**structural extraction** → **semantic** where needed → **merge** → **build/cluster** → **report** → **`to_html`**), or CLI equivalents such as **`graphify <path>`** / **`graphify <path> --update`** after the initial build.

## Interpreter / portable launch

`hooks/graphify_launcher.py` is the portable, fail-open launcher (it replaced the old `graphify-runner.sh`, 2026-07-14). It discovers the serve interpreter and never takes the MCP offline on a missing graph. Manual checks:

```bash
graphify --help
python3 "$HOME/.claude/hooks/graphify_launcher.py"   # starts graphify.serve for the OPEN repo
```

Adjust **`GRAPHIFY_VENV`** (default `~/.local/share/claude-graphify-venv`) or **`GRAPHIFY_SITE_PACKAGES`** / **`GRAPHIFY_PYTHON`** only if your install path differs.
## MCP server

The graphify MCP server is registered in `~/.claude.json` (command: `hooks/graphify_launcher.py`) and comes up automatically. It serves the OPEN repo's `graphify-out/graph.json`, validated to belong to that repo by git-remote identity (a foreign/ancestor-repo graph is refused). If no graph exists it comes up empty (`graph_stats` reports "not built") instead of failing — build with `graphify update <root>`, then reconnect the MCP.

## Help-only guard

If the user sends **`/graphify --help`** or **`-h`** with no path, **print upstream Usage verbatim and stop** (no commands), per **`skill-vscode.md`**.

## After completion

Prefer citing paths:

- `graphify-out/GRAPH_REPORT.md`
- `graphify-out/graph.html`
- `graphify-out/graph.json`

and mention **`graphify update`** for cheap code-only refreshes after edits.
