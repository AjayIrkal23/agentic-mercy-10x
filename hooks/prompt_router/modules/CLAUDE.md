<!-- dox:child v1 -->
# `hooks/prompt_router/modules/` — local rules (dox)

> Local doc for this directory only. Read after the root `CLAUDE.md`. Update this
> file whenever you add, remove, or rename files here, or change a local convention.

## What lives here

Pure, import-safe helpers the router calls per prompt. No stdin handling, no
process-level side effects beyond the stack-fingerprint cache
(`state/<repo.key>.stack.json`). Each returns `[]`/`None`/empty on any error.

## Local conventions

- Import `lib.*` inside `try/except` and degrade (the package must import even when
  `lib` is unavailable, e.g. in a foreign checkout).
- Never start a process that outlives the hook; `mcp_routes.dev_server_port` only
  PROBES `ss -ltn` (1 s timeout). Never start a dev server.
- Vocabulary regexes are lookaround-bounded (`(?<!\w)…(?!\w)`), never bare substrings.

## Key files

| File | Role |
|------|------|
| `surface.py` | `detect(payload, text) -> (surfaces∪tags, source, weak)`: prompt paths → prompt vocab → cwd → repo stack fingerprint (react/vite/next/vue/svelte/three/motion vs go.mod/express/prisma/migrations/*.sql/clickhouse), cached on marker mtimes |
| `mcp_routes.py` | `items(profile, ctx)`: availability-aware "call X now" lines from `tool-intelligence.json.mcp_routes` (memory, sequential-thinking, semgrep, context7 + context7-import, browser = reticle/playwright only with a listening dev port, higgsfield, github, clickhouse, db-supabase/db-mongodb); list order = priority; skips servers absent from `~/.claude.json` user scope AND the active repo's project scope (`.mcp.json`, `projects[root].mcpServers` — `project_servers(root)`), or in `mcp-needs-auth-cache.json`; ≤4 lines. `server_available` is also used by `router._substrate_items` and `hooks/mcp-post-hints.py` |
| `code_intel.py` | indexed-symbol lookup in the repo's jcodemunch sqlite index (≤5 symbols, 150 ms budget); `is_repo_symbol` guards the context7 route |
| `model_advice.py` | `/model` nudge for heavy tasks only (task_matrix + heavy_qualifiers from `model-policy.json`) |

## Gotchas / fragile spots

- `surface.py` tags from the stack (`go`, `sql`, `clickhouse`, `three`, `motion`,
  `shadcn`, `tailwind`) attach only when their side (backend/frontend) is in the
  final code surface and are reported in `weak` unless the prompt named them.
- `mcp_routes.available_servers` treats an enabled plugin as `plugin:<name>`; a
  needs-auth entry `plugin:x:y` blocks `plugin:x`.
- `code_intel._TOOLMAP_PATH` is hooks-relative (not `$HOME`); `build_playbook_item`
  is kept for on-demand use but the router does not emit it (per-intent jcodemunch
  directives live in `router._JCM_BY_INTENT`).
- `surface.py`: "hook(s)" is React vocabulary ONLY with React context (react /
  component / jsx / tsx / a `useX` identifier); with infra vocabulary (skills, MCPs,
  rules, dispatch, …) or a `.claude/` path the prompt is `claude-infra`
  (`prompt_is_claude_infra`).
- D17 was reversed 2026-09-28: sequential-thinking / graphify / jdocmunch are MUST
  again (`rules/00-tool-precedence.md`); the router emits them as "call X now" lines.

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children: none
