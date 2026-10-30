# MCP inventory (generated)

Regenerated once a day by the self-heal step `mcp-inventory` (`hooks/tools/selfheal-daily.py`),
or by hand: `python3 ~/.claude/scripts/mcp_inventory.py` (source of truth: `~/.claude.json`
user scope + `plugins/installed_plugins.json`; D13). Home paths are written as `~`;
project-scope rows are machine data and left out. Everything above the table is hand-written
and kept on regeneration. Snapshot 2026-10-30 (`higgsfield` leaves at go-live: it is the
claude.ai connector `mcp__claude_ai_higgsfield__*`, not an MCP here).

Removed 2026-09-28 (do not re-add): `fetch`, `ast-grep`, `figma`, `gbrain`; plugin servers
`playwright`/`context7` (duplicates), `clickhouse`, `claude-mermaid`.

| Server | Scope | Transport | Target | Reach for it when |
|---|---|---|---|---|
| `browser-tools-mcp` | user | stdio | `npx -y @agentdeskai/browser-tools-mcp@2.0.2` | DevTools console/network/audits of the user's open tab |
| `context7` | user | stdio | `npx -y @upstash/context7-mcp@4.1.1` | current library/framework/SDK/CLI docs |
| `drawio` | user | stdio | `npx -y @drawio/mcp@1.6.3` | — |
| `github` | user | stdio | `sh -c GITHUB_PERSONAL_ACCESS_TOKEN=$(gh auth token) exec npx -y @modelcontextprotocol/server-github@2025.4.8` | GitHub issues/PRs/files via API (gh CLI is often simpler) |
| `graphify` | user | stdio | `python3 ~/.claude/hooks/graphify_launcher.py` | architecture graph: god nodes, neighbors, paths (FIRST for architecture; needs graphify-out/) |
| `jcodemunch` | user | stdio | `~/.local/bin/jcodemunch-mcp` | code symbols, callers, blast radius, reading source (FIRST for code) |
| `jdocmunch` | user | stdio | `~/.local/bin/jdocmunch-mcp` | section-level search/read over indexed doc sets (FIRST for docs) |
| `lean-ctx` | user | stdio | `~/.local/bin/lean-ctx` | optional compressed ctx_read/ctx_shell/ctx_patch |
| `markdownify` | user | stdio | `npx -y mcp-markdownify-server@1.1.0` | convert pdf/docx/pptx/xlsx/web/youtube to markdown |
| `memory` | user | stdio | `npx -y @modelcontextprotocol/server-memory@2026.8.31` | durable cross-session facts (pattern::/decision::/fragile::) |
| `openart` | user | http | `https://mcp.openart.ai/mcp` | secondary asset engine (only where a project says so) |
| `playwright` | user | stdio | `npx -y @playwright/mcp@0.0.83 --browser chromium` | drive a real browser: flows, clicks, a11y snapshots |
| `reticle` | user | stdio | `npx -y @reticlehq/server@3.5.0 mcp` | in-app state/network truth of the user's running dev app (attach only) |
| `semgrep` | user | stdio | `~/.local/bin/semgrep mcp` | security scanning (THE security path; satisfies Gate 3) |
| `sequential-thinking` | user | stdio | `npx -y @modelcontextprotocol/server-sequential-thinking@2026.8.31` | MUST for non-trivial reasoning: plan/spec/audit/design/debug/decide |
| `firecrawl` | plugin:firecrawl@claude-plugins-official | http | `https://mcp.firecrawl.dev/v2/mcp-search` | — |

15 user-scope, 1 project/plugin-scope servers.
