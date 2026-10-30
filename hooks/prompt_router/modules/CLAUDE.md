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
- Never start a process that outlives the hook; `mcp_routes.dev_server_port(root)` only
  PROBES `ss -ltnp` (1 s timeout) and returns a port only when the listener's process cwd
  (`/proc/<pid>/cwd`) is inside `root` (no root, Windows, or another user's/Docker's listener:
  no port; seams `_listeners` / `_pid_cwd`). The context7-import guard skips a local package
  dir / module and stdlib modules. `workflow_routes._changed_files` only runs
  `git diff --name-only HEAD` (0.4 s cap, skipped under `CLAUDE_HOOK_DOCTOR`). Never start
  a dev server.
- Vocabulary regexes are lookaround-bounded (`(?<!\w)…(?!\w)`), never bare substrings.

## Key files

| File | Role |
|------|------|
| `surface.py` | `detect(payload, text) -> (surfaces∪tags, source, weak)`: prompt paths → prompt vocab → cwd → repo stack fingerprint (react/vite/next/vue/svelte/three/motion vs go.mod/express/prisma/migrations/*.sql/clickhouse), plus the ECC stack indicators of `router.config.json` `additions.stack_indicators` (`rust`, `python`, `docker`, `java`, … ; `file` glob on the marker name, optional `contains` body substring) and the package manager (`pm`: `packageManager` field, else the first lockfile; tag `pm:<name>`); cached on marker mtimes, `sig["_v"]` 4; `stack_fingerprint` returns `{surfaces, tags, pm}` |
| `mcp_routes.py` | `items(profile, ctx)`: availability-aware "call X now" lines from `tool-intelligence.json.mcp_routes` (memory, sequential-thinking, semgrep, context7 + context7-import, browser = reticle/playwright only with a dev port owned by the active repo (reticle only where the repo is instrumented; skipped on `policy.infra_routing`), higgsfield, github, clickhouse, db-supabase/db-mongodb); list order = priority; skips servers absent from `~/.claude.json` user scope AND the active repo's project scope (`.mcp.json`, `projects[root].mcpServers` — `project_servers(root)`), or in `mcp-needs-auth-cache.json`; ≤4 lines. claude.ai connectors listed in `tool-intelligence.json` `connectors` (`claude_ai_higgsfield`) count as available. `server_available` is also used by `router._substrate_items` and `hooks/mcp-post-hints.py` |
| `code_intel.py` | indexed-symbol lookup in the repo's jcodemunch sqlite index (≤5 symbols, 150 ms budget); `is_repo_symbol` guards the context7 route; with unpopulated summaries the tail says index-lifecycle fills them in the background |
| `model_advice.py` | (owned by package model-routing) heavy-task line for the MODEL (never a `/model` the user types): "dispatch the `<agent>` agent (Opus, via the Agent tool) for the heavy part now", only when task_matrix + heavy_qualifiers hit; the agent per row is `model-policy.json` `main_session_advice.agents` (all Opus-pinned) |
| `asset_auth.py` | `item(profile, ctx)`: for an asset-looking prompt (image/logo/video/3D/audio/hero …) when the user-scope Higgsfield is registered but listed in `mcp-needs-auth-cache.json` (key names only, via `mcp_routes`), ONE ROUTING line `route:higgsfield-auth`: ask the user once (batched with any other login, OpenArt joins the line with `mcp__openart__authenticate` when it waits too) to connect the Higgsfield connector in claude.ai (`mcp__claude_ai_higgsfield__*`), say assets are pending, no placeholders. The manifest dedup makes it once per session; once the user-scope entry is gone the line retires itself |
| `workflow_routes.py` | `items(profile, ctx)`: ONE `WORKFLOW: run saved workflow <name> with args {…} (size X, n acts)` ROUTING line (tier 2, id `route:workflow:<name>:<acts>`) from `<claude_dir>/workflows/index.json` (package workflows writes it; missing → no line). Rules, first wins: `invoke` for ≥2 acts at size M/L, ≥2 acts scoring ≥ `auto_dispatch_threshold` at any size, or size L with one act and no corpus trigger ("fix the failing test", two score-1 acts at size S, stays inline); `review` for REVIEW with ≥3 changed files (prompt paths or `git diff`); any other entry on a trigger hit + a named corpus (path, URL, "this repo") + size ≥ `min_size` (beats a single-act size-L invoke, never a multi-act one: final-fix 5). `tier_hint: "escalate"` when `lib.model_mode.escalation_reason` applies. `run` is `<repo root>/.claude/runs/<UTC ts>-<slug>` (the cwd when no repo). 80 ms soft budget (`prompt_router.workflow_slow`) |
| `library_routes.py` | owned by package `library` (contract only here): `items(profile, cwd, manifest) -> [{id, tier, section, text}]`, text starts `LIBRARY:`; the router keeps ≤2 as ROUTING lines; absent module → no lines |

## Gotchas / fragile spots

- `surface.py` tags from the stack (`go`, `sql`, `clickhouse`, `three`, `motion`,
  `shadcn`, `tailwind`) attach only when their side (backend/frontend) is in the
  final code surface and are reported in `weak` unless the prompt named them. Indicator
  tags follow the same side rule; side `any` / `mobile` tags and `pm:*` attach whenever
  the repo has them; all weak unless the prompt names the word. `python` is side `any`
  (a helper script's `requirements.txt` is not a service; the `_PY_BE` web-framework rule
  still makes Django/FastAPI repos backend). `ruby`, `java`, `kotlin` are side `any` too
  (every RN / Flutter / Android app has a Gemfile or Gradle files; `springboot` carries the
  backend side). A package.json with RN deps never matches a frontend indicator (`react`),
  and `_mobile_shell` skips a backend-side marker under `android/` / `ios/` or next to an
  RN package.json / pubspec.yaml (per marker, so a `server/` beside the app stays backend).
- `surface.py` "migration(s)" in a prompt adds `sql` only when the repo is not
  Mongo-only (`mongo` stack tag from `mongoose`/`mongodb` deps without `sql`).
  `stack_fingerprint` caches on marker mtimes: bump `sig["_v"]` whenever
  `_compute` derives a new tag, or old caches never recompute.
- `surface.py`: stack tag `mobile` from a package.json with expo / react-native /
  expo-router (that package's `react` is not a web frontend); prompt vocab expo*/react
  native/android/ios/mobile app → surface `mobile` (source prompt); bare "mobile" only in a
  repo with an RN app and no FE/BE word. Stack cache `_v` is 5.
- `mcp_routes.py`: `server_available(…, root)` also honours `~/.claude.json
  projects[root].disabledMcpServers`; `root` may be a list — the router passes the git root
  and the launch folder (`payload.cwd`), because `projects` is keyed by the folder Claude
  started in. `surface.py`: "go cli/program/tool" is Go only after a determiner
  (`_GO_NOUN_PHRASE`); the path regex scans at most 255 chars before a file name; `reticle_instrumented(root)` (an `@reticlehq/*` dep or
  "reticle" in a root vite/next config) — without it the browser route skips reticle; routes
  may carry `text_by_server` (browser, higgsfield). No `plugin:context7` / `plugin:playwright`
  targets (they never match an installed server name).
- `code_intel.py`: symbol summaries capped at 72 chars; the router calls it only for
  code-shaped prompts (`policy.code_shaped`). The old tool-intelligence playbook renderer
  is gone; per-intent jcodemunch directives live in `router._JCM_BY_INTENT`.
- `mcp_routes.available_servers` treats an enabled plugin as `plugin:<name>`; a
  needs-auth entry `plugin:x:y` blocks `plugin:x`.
- `surface.py`: "hook(s)" is React vocabulary ONLY with React context (react /
  component / jsx / tsx / a `useX` identifier); with infra vocabulary (skills, MCPs,
  rules, dispatch, …) or a `.claude/` path the prompt is `claude-infra`
  (`prompt_is_claude_infra`).
- D17 was reversed 2026-09-28: sequential-thinking / graphify / jdocmunch are MUST
  again (`rules/00-tool-precedence.md`); the router emits them as "call X now" lines.

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children: none
