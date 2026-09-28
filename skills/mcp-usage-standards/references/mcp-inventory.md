# MCP inventory (generated)

Regenerate after any `claude mcp add/remove` or plugin change:
`python3 ~/.claude/scripts/mcp_inventory.py` (source of truth: `~/.claude.json` user scope +
`plugins/installed_plugins.json`; D13). Snapshot 2026-09-28:

| Server | Scope | Transport | Target | Reach for it when |
|---|---|---|---|---|
| `browser-tools-mcp` | user | stdio | `npx -y @agentdeskai/browser-tools-mcp@2.0.2` | DevTools console/network/audits of the user's open tab |
| `context7` | user | stdio | `npx -y @upstash/context7-mcp` | current library/framework/SDK/CLI docs |
| `github` | user | stdio | `sh -c GITHUB_PERSONAL_ACCESS_TOKEN=$(gh auth token) exec npx -y @modelcontextprotocol/server-github` | GitHub issues/PRs/files via API (gh CLI is often simpler) |
| `graphify` | user | stdio | `python3 ~/.claude/hooks/graphify_launcher.py` | architecture graph: god nodes, neighbors, paths (FIRST for architecture; needs graphify-out/) |
| `higgsfield` | user | http | `https://mcp.higgsfield.ai/mcp` | DEFAULT asset engine: image/video/3D/audio generation |
| `jcodemunch` | user | stdio | `~/.local/bin/jcodemunch-mcp` | code symbols, callers, blast radius, reading source (FIRST for code) |
| `jdocmunch` | user | stdio | `~/.local/bin/jdocmunch-mcp` | section-level search/read over indexed doc sets (FIRST for docs); semantic search ON via local ollama `all-minilm` (`openai-compatible` provider, `jdocmunch-mcp[openai]`); re-index with `use_embeddings=true` to embed a set |
| `lean-ctx` | user | stdio | `~/.local/bin/lean-ctx` | optional compressed ctx_read/ctx_shell/ctx_patch |
| `markdownify` | user | stdio | `npx -y mcp-markdownify-server` | convert pdf/docx/pptx/xlsx/web/youtube to markdown |
| `memory` | user | stdio | `npx -y @modelcontextprotocol/server-memory` | durable cross-session facts (pattern::/decision::/fragile::) |
| `openart` | user | http | `https://mcp.openart.ai/mcp` | secondary asset engine (only where a project says so) |
| `playwright` | user | stdio | `npx -y @playwright/mcp@0.0.82` | drive a real browser: flows, clicks, a11y snapshots |
| `reticle` | user | stdio | `npx -y @reticlehq/server@3.3.0 mcp` (env `RETICLE_TELEMETRY=0`) | in-app state/network truth of the user's running dev app (attach only) |
| `semgrep` | user | stdio | `~/.local/bin/semgrep mcp` | security scanning (THE security path; satisfies Gate 3) |
| `sequential-thinking` | user | stdio | `npx -y @modelcontextprotocol/server-sequential-thinking` | MUST for non-trivial reasoning: plan/spec/audit/design/debug/decide |
| `supabase` | project:~/CODE_FILES/CONCORD-WEBSITE | http | `https://mcp.supabase.com/mcp` | that project's Supabase only |

15 user-scope, 1 project-scope. No plugin currently ships an MCP server.

Removed 2026-09-28 (do not re-add): `fetch`, `ast-grep`, `figma`, `gbrain`; plugin servers
`playwright`/`context7` (duplicates), `clickhouse`, `claude-mermaid`.
