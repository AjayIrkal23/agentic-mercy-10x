# MCP Usage Standards — full reference

Read after routing into **`mcp-usage-standards`** per [`SKILL.md`](../SKILL.md).

Upstream docs worth bookmarking:

- Playwright MCP: [installation](https://playwright.dev/mcp/installation) · [options](https://playwright.dev/mcp/configuration/options)

## Per-server guides (installed in `~/.claude/settings.json`)

### `context7`

- **Use:** current official docs for frameworks, libs, CLI tools, APIs.
- **Avoid:** pure repo internals; refactor-only churn.

### `sequential-thinking`

- **Use:** hard tradeoffs; multi-hypothesis debugging; phased plans.
- **Avoid:** trivial one-path fixes.

### `fetch`

- **Use:** lightweight HTTP GET/HTML where no JS/session is implied.
- **Avoid:** SPA post-login UX, redirects needing cookies unless you deliberately handle auth.

### `memory`

- **Use:** reusable durable snippets (patterns, glossary) without secrets.
- **Avoid:** one-off chatter; credential storage.

### `browser-tools-mcp`

- **Use:** when AgentDesk/browser-tools lens (console/network) is explicitly requested or known to be the shortest path for that symptom.
- **Avoid:** duplicated run alongside `playwright` for the same simple DOM snapshot.

### `playwright`

- **Use:** drive real browser sessions (`@playwright/mcp`): navigation, forms, deterministic UI regressions; accessibility snapshots.
- **Avoid:** answering from source alone suffices; **`fetch`** can satisfy static pages.
- **Note:** First run installs browsers/binaries; Cursor MCP panel shows connection health.

### `markdownify`

- **Use:** convert external or local-ish documents to markdown pipelines.
- **Avoid:** Respect `MD_ALLOWED_PATHS`/server env documented upstream if you tightened paths.

### `graphify`

- **Use:** after **`graphify-out/graph.json`** exists (`graphify` CLI / runner).
- **Launcher:** `$HOME/.claude/hooks/graphify_launcher.py` (fail-open; comes up empty on a missing graph instead of exiting). Build with `graphify update <root>`, then reconnect the MCP.

## Priority ladder (reuse)

1. Local repo reads + deterministic shell for one-off proofs.
2. **`context7`** / **`fetch`** for external truth on static/simple pages.
3. **`playwright`** for rendered/automation proofs.
4. **`browser-tools-mcp`** for its-specific diagnostics path.
5. **`sequential-thinking`** / **`memory`** only where reasoning or persistence clearly pays rent.

## Safety

Never echo tokens; prune attachments; cite what MCP proved.

## Appendix — not configured in current `~/.claude/settings.json`

These MCPs appear in some workspaces or installs but are **absent locally** unless you add stanzas:

- **`deepvue-docs`** — add only when you have product-specific Deepvue doc MCP.
- **`jcodemunch`** — add only when you intentionally install/connect that repo indexer.

If you introduce new servers, duplicate the pattern above and sync **`SKILL.md`**, **`user-mcp-inventory.mdc`**, and **`session-start-aggregator.py`** MCP list behavior.
