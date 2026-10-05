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
| `model_advice.py` | heavy-task line for the MODEL (never a `/model` the user types): "dispatch the `<agent>` agent (Opus, via the Agent tool) for the heavy part now", only when task_matrix + heavy_qualifiers hit; the agent per row is `model-policy.json` `main_session_advice.agents` (all Opus-pinned) |
| `asset_auth.py` | `item(profile, ctx)`: for an asset-looking prompt (image/logo/video/3D/audio/hero …) when Higgsfield is registered but listed in `mcp-needs-auth-cache.json` (key names only, via `mcp_routes`), ONE ROUTING line `route:higgsfield-auth`: ask the user once (batched with any other login, OpenArt joins the line when it waits too), use `mcp__higgsfield__authenticate`, say assets are pending, no placeholders. The manifest dedup makes it once per session |

## Gotchas / fragile spots

- `surface.py` tags from the stack (`go`, `sql`, `clickhouse`, `three`, `motion`,
  `shadcn`, `tailwind`) attach only when their side (backend/frontend) is in the
  final code surface and are reported in `weak` unless the prompt named them.
- `surface.py` "migration(s)" in a prompt adds `sql` only when the repo is not
  Mongo-only (`mongo` stack tag from `mongoose`/`mongodb` deps without `sql`).
  `stack_fingerprint` caches on marker mtimes: bump `sig["_v"]` whenever
  `_compute` derives a new tag, or old caches never recompute.
- `surface.py`: stack tag `mobile` from a package.json with expo / react-native /
  expo-router (that package's `react` is not a web frontend); prompt vocab expo*/react
  native/android/ios/mobile app → surface `mobile` (source prompt); bare "mobile" only in a
  repo with an RN app and no FE/BE word. Stack cache `_v` is 3.
- `mcp_routes.py`: `server_available(…, root)` also honours `~/.claude.json
  projects[root].disabledMcpServers`; `root` may be a list — the router passes the git root
  and the launch folder (`payload.cwd`), because `projects` is keyed by the folder Claude
  started in. `surface.py`: "go cli/program/tool" is Go only after a determiner
  (`_GO_NOUN_PHRASE`); the path regex scans at most 255 chars before a file name; `reticle_instrumented(root)` (an `@reticlehq/*` dep or
  "reticle" in a root vite/next config) — without it the browser route skips reticle; routes
  may carry `text_by_server`. No `plugin:context7` / `plugin:playwright` targets (they never
  match an installed server name).
- `code_intel.py`: symbol summaries capped at 72 chars; the router calls it only for
  code-shaped prompts (`policy.code_shaped`).
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
