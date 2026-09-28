# Hooks — dispatch architecture

**Registry:** `settings.template.json` (rendered to `settings.json` by
`installer/render.py`). It registers `dispatch.py <event>` once for each of 12 events,
plus `prompt_router/router.py` for UserPromptSubmit — 13 hook events in total. Every hook
still lives in its own file; `dispatch.py` only orchestrates.

## Events and chains

`hooks/dispatch.config.json` → `chains.<event>` (ordered links) and `budgets.<event>`.

| Event (`dispatch.py` arg) | Links |
|---|---|
| `session-start` | settings-permissions-selfheal, state-cleanup (async), session-start-aggregator, memory-load-on-start, session-lifecycle-start, ponytail-session, skills-index-guard (async) |
| `pre-tool-use` | dangerous-bash-gate, first-write-skill-gate, gateguard-write-gate, dox-write-gate-write, bash-write-gate, blocking-doc-enforcer, jcm-gate-read, jcm-gate-leanctx, jdoc-doc-steer, tdd-guard-launcher-pre, graphify-enforce, opus-guard, workflow-model-guard |
| `post-tool-use` | skill-invocation-tracker, fullstack-post, codex-capture, post-write-aggregator, desloppify-cleanup, santa-method-writer, security-semgrep-tracker, jcm-mcp-used, mcp-post-hints |
| `post-tool-use-failure` | tool-failure-hint |
| `stop` | hard-completion-gate, invoke-suite-gate, index-flush (async), session-lifecycle-stop (async), weights-loop (async) |
| `subagent-start` | subagent-context |
| `subagent-stop` | session-lifecycle-subagent |
| `pre-compact` / `post-compact` | session-lifecycle-precompact / -postcompact |
| `config-change` | permissions-deny-guard |
| `teammate-idle` | teammate-idle-gate |
| `session-end` | settings-permissions-selfheal-end, index-session-end |

## Link taxonomy

| type | semantics |
|------|-----------|
| `gate` | sequential; first `deny`/block short-circuits; never budget-dropped |
| `mutator` | sequential; each returns `updatedInput`, threaded to the next |
| `advisory` | parallel; `additionalContext` merged in priority order |
| `exec` | side effects; with `"async": true` spawned detached and never waited on |

Per-link fields: `id`, `type`, `cmd` (`{PY}`/`{HOOKS}`/`{NODE}` tokens), optional
`tools` regex (full-match on `tool_name`), `priority` (0 = never dropped), `timeout_ms`,
`enabled`.

## Guarantees

- Per-link isolation, fail-open; the dispatcher always emits valid JSON.
- Per-link telemetry via `lib/hook_telemetry.py` → `telemetry/hook-fires-*.jsonl`
  (14-day retention, purged by `tools/state-cleanup.py`).
- `CLAUDE_HOOK_DOCTOR=1` makes disk-writing links no-op; `tools/link-doctor.py` (run by
  `installer/doctor.py`) fires a synthetic event through every enabled link.

## Prompt router

`prompt_router/router.py` classifies once, detects the surface, ranks ≤5 skills, adds
availability-aware MCP lines and an agent suggestion, and emits
`hookSpecificOutput.additionalContext`. Its trigger surface is frozen in
`trigger-floor.json` (`build-trigger-floor.py --check` in CI). Details:
[`prompt_router/CLAUDE.md`](prompt_router/CLAUDE.md).

## Generated config

- `gen-invoke-skills.py` — `/invoke` skill family from `autonomous-skill-router.config.json`
  + `model-policy.json`.
- `gen-agent-skill-blocks.py` — agent `skills:` frontmatter.
- `build-skills-index.py`, `build-trigger-floor.py` — catalogs.
- `skills-sources.json` — vendored skill sources for `scripts/vendor_skill.py`;
  `skills-provenance.json` is built from it (`scripts/build_provenance.py`).

## Index freshness (zero daemons)

`index-lifecycle.py` journals writes in the active repo and flushes one detached
incremental builder (jcodemunch, jdocmunch, graphify, dox) at N writes / T seconds and
at Stop. `$HOME`, `~/.claude` and `~/.codex` are never indexed.
