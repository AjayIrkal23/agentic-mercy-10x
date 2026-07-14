<!-- dox:child v1 -->
# `hooks/` — local rules (dox)

> Local doc for this directory only. Read after the root `CLAUDE.md`. Update this
> file whenever you add, remove, or rename files here, or change a local convention.

## What lives here

Every Claude Code hook: gates, advisories, mutators, exec side-effects, the prompt
router, the index-lifecycle state machine, and the dispatcher that ties them
together. See `README.md` in this directory for the full dispatch architecture.
Only hook logic and hook config belong here — no skill bodies, no app code.

## Local conventions

- **One dispatcher per event.** `settings.json` registers 8 entries
  (`dispatch.py <event>`); individual hooks are declared as links in
  `dispatch.config.json` (`chains.<event>`), NOT re-added to `settings.json`.
- **Every hook stays its own file** (Charter §3). To add behavior, add a link
  (own `.py`/`.js`), never merge logic into an existing file.
- **Portability:** shell out via `{PY}`/`{HOOKS}`/`{NODE}` tokens resolved by
  `lib/platform.py`; no raw `.sh` in the live path (ports live as `*.py`/`*.js`).
- **Never remove a trigger rule** — `trigger-floor.json` is a verbatim superset;
  `build-trigger-floor.py --check` fails CI on any dropped keyword/path/intent.
- **Model truth is single-sourced** in `model-policy.json`; guards read it, never
  hardcode ids or pins.

## Key files

| File | Role |
|------|------|
| `dispatch.py` / `dispatch.config.json` | Universal per-event chain-runner + link declarations (8 events, 70 links) |
| `prompt_router/router.py` | Single-process prompt router (classify → rank → 24k priority budget → manifest dedup); **LIVE UserPromptSubmit handler** since 2026-07-12. `--shadow` is now only a test/parity mode |
| `trigger-floor.json` / `build-trigger-floor.py` | Verbatim superset of all 4 legacy taxonomies + 139 command names; `--check` = CI floor guard |
| `model-policy.json` | Single model-routing truth (sonnet default / opus UI+heavy / fable explicit) — consumed by `opus-guard.py`, `workflow-model-guard.py`, `gen-invoke-commands.py` |
| `index-lifecycle.py` / `.config.json` | Active-repo-only, event-driven index freshness (journal → detached single-shot builder); zero daemons |
| `lib/platform.py`, `lib/hook_telemetry.py`, `lib/repo_context.py` | Shared foundation: interpreter/token resolution, per-link telemetry, active-repo detection + git-remote identity helpers (`git_root`, `git_remote_identity`, `sanitize_name`) |
| `jdocmunch-index-guard.py` / `.config.json` / `jdocmunch-reindex-hook.py` | Doc-index twin of the jcodemunch guard; run via the dispatch session-start / post-tool-use chains |
| `graphify_launcher.py`, `graphify-enforce.py`, `jdocmunch-enforce.py` | Tri-tool code/doc intelligence (2026-07-14): prompt-time tri-tool routing lives in **`prompt_router/router.py`** (SUBSTRATE section, availability-aware); `graphify_launcher.py` = claude-native graphify MCP launcher (off the cursor venv, repo-identity validated, fail-open); `graphify-enforce`/`jdocmunch-enforce` = per-surface pre-tool-use read advisories |

## Gotchas / fragile spots

- **UserPromptSubmit is handled LIVE by `prompt_router/router.py`** (settings.json;
  user-directed flip 2026-07-12, commit c865377). The dispatch `user-prompt-submit`
  chain (legacy injectors) is **no longer invoked on prompts** — retained only for
  flip-back (`flip-dispatch.py --legacy`). The router is a provable superset
  (classify/select consume the entire `trigger-floor.json`). Verify the live wiring
  in **settings.json**, NOT these dispatch comments (that stale claim caused a real
  agent error on 2026-07-14).
- The legacy prompt-stack (UPS injectors: `model-router.py`, `autonomous-skill-router.py`,
  `sequential-thinking-mandate.py`, the delegate wrappers, etc.) was **fully retired and
  deleted 2026-07-14** (v2.4.0). The router + `dispatch.py` are the whole architecture;
  recover the old stack only via git (`pre-100x` / `pre-legacy-retirement`). The
  session-start/post-write aggregators + the 3 index guards remain LIVE — they were never
  part of the UPS injector stack.
- Dispatcher and every link **fail open** — a crashing link logs to telemetry and
  the chain continues; never let a link raise past its own try/except.

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children: [`lib/CLAUDE.md`](lib/CLAUDE.md)
- Related repo docs: `README.md` (dispatch architecture); `../rules/agent-lifecycle-routing.md` (phase→hook map); `../plans/PLAN-2026-07-11-100x.md` (the overhaul).
