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
| `prompt_router/router.py` | Single-process prompt router (classify → rank → 24k priority budget → manifest dedup); runs `--shadow` during the retention window |
| `trigger-floor.json` / `build-trigger-floor.py` | Verbatim superset of all 4 legacy taxonomies + 139 command names; `--check` = CI floor guard |
| `model-policy.json` | Single model-routing truth (sonnet default / opus UI+heavy / fable explicit) — consumed by `opus-guard.py`, `workflow-model-guard.py`, `gen-invoke-commands.py` |
| `index-lifecycle.py` / `.config.json` | Active-repo-only, event-driven index freshness (journal → detached single-shot builder); zero daemons |
| `lib/platform.py`, `lib/hook_telemetry.py`, `lib/repo_context.py` | Shared foundation: interpreter/token resolution, per-link telemetry, active-repo detection |
| `jdocmunch-index-guard.py` / `.config.json` / `jdocmunch-reindex-hook.py` | Doc-index twin of the jcodemunch guard; run via the dispatch session-start / post-tool-use chains |

## Gotchas / fragile spots

- During the 30-day shadow window, `user-prompt-submit` runs the **legacy injector
  set + `router.py --shadow`** together; the live injection you see is the legacy
  stack. Do not "fix" that — cutover is `flip-dispatch.py --router` after ≥10
  zero-miss sessions.
- The legacy prompt-stack + aggregator links (the prompt-reminder injector, the
  session-start and post-write aggregators, `model-router.py`, the 3 index guards)
  are still wired during the retention window but retire in P7-T4 — do not cite
  them as the architecture; the architecture is `dispatch.py` + the router.
- Dispatcher and every link **fail open** — a crashing link logs to telemetry and
  the chain continues; never let a link raise past its own try/except.

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children: [`lib/CLAUDE.md`](lib/CLAUDE.md)
- Related repo docs: `README.md` (dispatch architecture); `../rules/agent-lifecycle-routing.md` (phase→hook map); `../plans/PLAN-2026-07-11-100x.md` (the overhaul).
