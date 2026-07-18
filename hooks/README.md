# Hooks — dispatch architecture

**Registry:** `~/.claude/settings.json` (the `hooks` block). After the 100x
overhaul, that block holds **8 entries** — one `dispatch.py <event>` per Claude
Code hook event — instead of 65 individual registrations. Every hook still lives
in its own `.py`/`.js`/binary; `dispatch.py` only *orchestrates* them (Charter §3
— orchestration, not fusion).

## One dispatcher per event

`settings.json` → for each event: `python3 ${HOME}/.claude/hooks/dispatch.py <event>`.
The 8 events: `session-start`, `user-prompt-submit`, `pre-tool-use`,
`post-tool-use`, `stop`, `subagent-stop`, `pre-compact`, `session-end`.

The chain for each event is declared in **`hooks/dispatch.config.json`**
(`chains.<event>` = ordered list of links; `budgets.<event>` = soft ms/char
budget). Today: 8 events, 70 enabled links.

## Link taxonomy

| type | semantics |
|------|-----------|
| `gate` | sequential; first `deny` short-circuits the chain; **never budget-dropped** |
| `mutator` | sequential; each returns `updatedInput`, threaded to the next |
| `advisory` | run in a `ThreadPoolExecutor` (parallel); `additionalContext` merged, priority-ordered |
| `exec` | fire-and-forget side effects (telemetry, journals, detached builders) |

Per-link fields: `id`, `type`, `cmd` (with `{PY}`/`{HOOKS}`/`{NODE}` tokens
resolved by `lib/platform.py`), optional `tools:` regex (replaces the old
per-matcher registrations), `priority`, `timeout_ms`, and **`enabled: true|false`**.

## Guarantees (Charter §3)

- **Per-link try/except isolation** — one link crashing logs to telemetry and the
  chain continues; the dispatcher always emits valid JSON (fail-open).
- **Per-link telemetry from day 1** — every fire logs `{ts, session, event,
  link_id, ms, exit, chars_out, decision, budget_hit, error}` via
  `lib/hook_telemetry.py` to `~/.claude/telemetry/hook-fires-*.jsonl` (14-day
  retention, purged by the `state-cleanup` session-start exec link).
- **Per-link enable flags** — flip `enabled:false` in `dispatch.config.json` to
  disable one link without touching `settings.json`.
- **Doctor fires synthetic events through every link** — `hooks/tools/link-doctor.py`
  (folded into `installer/doctor.py`) sends a matching payload to each enabled
  link and asserts exit 0 + parseable output + a telemetry line.

## Budgets

Per-event budgets in `dispatch.config.json` are **soft**: overruns are logged,
but gates and mandatory-trigger advisories are never dropped. The
`user-prompt-submit` injection budget is `~24,000` tokens, priority-ordered
(tier-0 gate-adjacent directives first) — the win is dedup + signal quality + one
subprocess, not raw shrinkage.

## Prompt router + trigger floor (router LIVE)

`user-prompt-submit` runs **`prompt_router/router.py` LIVE** (user-directed flip
2026-07-12; the legacy injector set is retained only for flip-back).
The router classifies once → ranks skills → priority-orders under the 24k budget →
dedups via the session manifest. Its trigger surface is a **verbatim superset** of
all four legacy taxonomies, frozen in **`hooks/trigger-floor.json`** (checksum-
guarded; `build-trigger-floor.py --check` runs in CI — removals are impossible to
merge). Cutover to router-only happened 2026-07-12 via `scripts/flip-router.py --router`;
flip back with `scripts/flip-router.py --legacy` if a regression appears.

## Flip / revert (one command each)

- `scripts/flip-dispatch.py --legacy` — restore the byte-identical 65-registration
  `settings.json` hooks block (revert the 65→8 rewrite).
- `scripts/flip-dispatch.py --dispatch` — install the 8 dispatcher entries.
- `scripts/flip-dispatch.py --status` — print which block is installed.
- `scripts/flip-router.py --router|--legacy` — swap the UserPromptSubmit block
  between the router and the snapshotted legacy prompt stack
  (`hooks/legacy-prompt-stack.json`).

Legacy hooks stay installed and runnable for 30 days after each cutover; nothing
is atticked until the retention window closes (P7-T4).

## Stacks in play

jcodemunch (index + `jcodemunch-enforce`), graphify (graph + `graphify-enforce`),
jdocmunch (doc index guard + reindex), lean-ctx (Bash `observe`/`rewrite`/
`redirect`), tdd-guard (`tdd_guard_launcher.py`, warn mode), dox
(`dox-tree-guard.py` + `dox-child-scaffold.py`), and the model-routing guards
(`opus-guard.py`, `workflow-model-guard.py`) driven by `hooks/model-policy.json`.

## Index freshness (zero daemons)

`index-lifecycle.py` journals writes inside the active repo (post-tool-use) and
flushes a single detached incremental builder at N=5 writes / T=45s and at Stop —
active-repo only, no persistent background processes.
