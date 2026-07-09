---
name: lean-ctx
description: Context compression for AI agents via shell hook. In this environment, lean-ctx runs as a shell hook only — it transparently intercepts Bash commands and compresses their output before Claude sees them. No special commands needed.
---

# lean-ctx — Shell Hook (This Environment)

> **IMPORTANT: In this environment, lean-ctx runs as a shell hook only.**
> The MCP tools (`ctx_read`, `ctx_search`, `ctx_shell`, `ctx_tree`, `ctx_edit`, etc.)
> described in the full lean-ctx documentation are NOT configured and NOT available.

## What the shell hook does

The lean-ctx shell hook transparently intercepts every Bash command and compresses its output through 95+ patterns before Claude sees it. This reduces token usage significantly on verbose commands.

**You do not need to do anything special.** Just run Bash commands normally.

Examples of what gets automatically compressed:
- `git log --oneline -20` — noisy commit history → condensed
- `git diff` — large diffs → only meaningful lines
- `npm install` / `npm run build` — strips progress bars and install noise
- `cargo build` / `cargo test` — condenses compiler output, shows only failures
- `go test ./...` — strips verbose pass lines, shows only failures + summary
- `docker ps` / `kubectl get pods` — tabular output compressed
- `ls -la` — grouped directory listings
- JSON from `curl` — reduced to schema outline

Supported tool ecosystems: git, npm, pnpm, yarn, bun, deno, cargo, docker, kubectl, gh, go, eslint, tsc, make, and many more.

The output suffix `[lean-ctx: N→M tok, -X%]` shows original vs compressed token count when compression fires.

## Enable / disable

```bash
lean-ctx-off    # Temporarily disable (output flows uncompressed — no breakage)
lean-ctx-on     # Re-enable
```

If the hook is off or broken, output flows uncompressed — graceful degradation, nothing breaks.

## Hook registration (settings.json)

The hook runs via these entries in `~/.claude/settings.json`:
- `PreToolUse` on `Bash` → `lean-ctx hook rewrite` (rewrites command for compression)
- `PostToolUse` on `Bash` → `lean-ctx hook observe` (records token savings)
- `SessionStart` / `SessionEnd` / `PreCompact` / `Stop` → `lean-ctx hook observe`

## Full MCP mode (NOT configured in this environment)

If you ever set up the full lean-ctx MCP server (`lean-ctx init --agent claude`), these tools become available — but they are NOT active now:

| Tool | What it does |
|------|--------------|
| `ctx_read` | Compressed file reading with 10 modes (map, signatures, aggressive, etc.) |
| `ctx_search` | Semantic + BM25 code search |
| `ctx_shell` | Compressed shell execution via MCP |
| `ctx_tree` | Directory tree with relevance scoring |
| `ctx_edit` | Search-and-replace file editing |
| `ctx_session` | Cross-session memory (CCP) |
| `ctx_graph` | Code dependency graph queries |

To set up full MCP mode:
```bash
lean-ctx init --agent claude
```

Until then, use the token-optimization routing in `~/.claude/rules/token-optimization-stack.md`
(jcodemunch + graphify + native Read/Bash) for efficient retrieval.
