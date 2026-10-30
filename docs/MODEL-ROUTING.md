# Model routing

`hooks/model-policy.json` is the only source of truth. `rules/04-model-routing.md` is the short
pointer that loads every session; this page is the full reference.

## 1. What decides a subagent's model

Every `Agent` call passes through `hooks/opus-guard.py` and every `Workflow` call through
`hooks/workflow-model-guard.py`. Both use one resolver, `lib/model_mode.resolve()`. First match wins:

```
session flag > per-project pin > explicit model/[label] with your phrase > role x tier
  > escalation > usage step-down > tier ceiling (always last)
```

Your `/model` and your per-turn phrase always win **within the plan ceiling**: on Pro "use opus"
cannot lift (the ceiling is Sonnet), "use sonnet" does, on every tier, usage guard on or off. A plan
cannot run a model it does not include.

## 2. Plan tiers

`hooks/plan-tier-detect.py` runs at every SessionStart (and from `installer/render.py`); a detected
change spawns `installer/render.py` so `model`/`fallbackModel`/`CLAUDE_CODE_SUBAGENT_MODEL` follow the tier
without waiting for the daily self-heal. It calls
`lib/plan_tier.detect()`, the only code in the workbench that opens `~/.claude/.credentials.json`.
It reads two keys, `claudeAiOauth.subscriptionType` and `claudeAiOauth.rateLimitTier`, falling back
to `oauthAccount.organizationRateLimitTier` in `~/.claude.json`. It never iterates the file and never
reads, copies, hashes or logs a token; `tests/test_plan_tier.py` checks the state file, stdout,
stderr and telemetry against fixture tokens.

| Login | Tier |
|---|---|
| `pro` | `pro` |
| `max` + `..._5x` | `max5` |
| `max` + `..._20x` | `max20` |
| `max` + an unknown tier string | `max5` |
| team, enterprise, API key, macOS keychain, no file | `api` (uses the `max5` rules) |

The result lands in `state/plan-tier.json`. When the tier differs from the previous file, the state
carries a one-line notice that the session-start notices show once. If the file is missing, every
reader falls back to `max20` (the behaviour before tiers existed). A file older than 24 h is still
trusted and marked `stale`; the next session start refreshes it.

## 3. The matrix

Rows are roles (`roles.agents` maps each `subagent_type`); columns are tiers (`tiers.<tier>.roles`).

| Role | Agents | pro | max5 / api | max20 |
|---|---|---|---|---|
| explore | explore, claude-code-guide | haiku | haiku | haiku |
| docs | docs-sync-agent, deadcode-reaper, memory-codex | haiku | haiku | haiku |
| verify | qa-verifier | haiku | haiku | haiku (sonnet at size L) |
| test | test-author | haiku (sonnet on escalation) | sonnet | sonnet |
| impl | implementation-engineer, BE/FE implementors, refactor-specialist | haiku (sonnet on escalation) | sonnet; haiku with a plan marker at size S/M | sonnet (opus on escalation) |
| integrate, security | integrator-specialist, security-sentinel | haiku (sonnet on escalation) | sonnet | sonnet (opus on escalation) |
| judge | santa-reviewer, frontend-uiux-designer, planning-director, spec-architect, debug-detective, audit-specialist, Plan | sonnet | sonnet; opus when your turn says "use opus" | opus |
| default | general-purpose (the plain `Agent` type) and any other agent type | haiku | sonnet | sonnet |

A per-turn phrase ("use haiku/sonnet/opus/fable") overrides the row for that turn, up to the ceiling.

| Tier setting | pro | max5 / api | max20 |
|---|---|---|---|
| ceiling | sonnet | opus | fable |
| main session `model` | sonnet | sonnet | opus |
| `CLAUDE_CODE_SUBAGENT_MODEL` | haiku | sonnet | sonnet |
| `fallbackModel` | haiku | haiku | sonnet, haiku |

Fable appears in no column. It runs only on max20 and only when your turn says "use fable".
Agent frontmatter `model:` mirrors the max20 column.
A general-purpose call that only reads runs on Haiku when its description starts with `[haiku]` or
your turn says "use haiku": general-purpose is unguarded, so the label is honoured within the ceiling.

## 4. Escalation

Triggers: a retry marker in the prompt ("previous attempt failed"), or no plan marker and
`prompt_router.classify` rates the work size L with risk 2 or more. Only executor roles (those with a
`tiers.<tier>.escalate` entry: test, impl, integrate, security) escalate, and only to the model in
that entry, inside the ceiling. A very complex task on pro therefore gets Sonnet, never Opus. On max5
a planned small impl task drops to Haiku; on max20 qa-verifier moves to Sonnet for size-L work.

## 5. Usage guard

`lib/usage_guard.state()` reads the newest `state/session-bridge/<sid>.json` younger than 10 minutes
(`five_hour_pct`, `five_hour_resets_at`, written by the statusline). It turns on at 80 % of the
5-hour window and off below 70 % or once `resets_at` has passed. While it is on:

| | pro | max5 / api | max20 |
|---|---|---|---|
| executors | haiku | one step down, at most sonnet | one step down, at most sonnet |
| judges | haiku | sonnet | sonnet |
| fable | - | - | paused, runs as sonnet |

A flip rewrites `state/usage-guard.json` and regenerates the saved workflows in the background.
The statusline shows a down arrow while the guard is on. The guard never raises a model (a judge
pinned to haiku stays haiku). Explicit models you asked for in your own turn, any role your per-turn
phrase names (inside the ceiling), and a global `<model>-only-mode` flag are not stepped down (fable still
pauses); a per-project pin is, in opus-guard and in Workflow scripts alike. API-key logins have no 5-hour window, so the guard
never activates for them.

## 6. Forcing a model

**Main session.** `bin/claude` (the launcher on PATH) starts an interactive session with
`--model <tier main>` (Sonnet on Pro / Max 5x / API, Opus on Max 20x; `main` in
`state/plan-tier.json`) only when nothing else chose one: no `--model` on the command line, no
`ANTHROPIC_MODEL`, and no `"model"` key in `~/.claude/settings.json` (a saved `/model` pick wins across
launches; when Claude Code's org-default sync deletes it, the tier default returns). `-p`, `--bare`,
nested launches and subcommands (`claude mcp ...`, `claude logs <id>`, every name in `claude --help`
Commands) get nothing added. The launcher re-detects the tier when `.credentials.json` is newer than
`state/plan-tier.json` (a login since the last session). Doctor row `launcher-model`
shows which rule applied. The Windows replica has no launcher yet: its main session keeps the account
default.

- **This turn:** say "use opus", "use haiku", "use sonnet" or "use fable". An explicit `model` on a
  call (or a `[model]` label) moves any agent to a tier's ask-only model (Opus on max5/api, Fable on
  max20) or moves a judge, executor or pin only when your turn carries that phrase; otherwise it is
  honoured within the ceiling and the usage guard still applies.
- **This project:** "use opus for this project" or `scripts/model-mode.py opus|haiku|sonnet|fable|clear`.
  A pin above the ceiling is stored capped (`opus` on pro is stored as `sonnet`, with a one-line
  reason) and capped again on read if the tier drops later.
- **Everywhere:** `touch ~/.claude/state/<model>-only-mode` (haiku > sonnet > opus > fable). The
  flag is capped to the ceiling too.

Refused per tier: pro never runs Opus or Fable; max5 never runs Fable and lifts judges or
executors to Opus only on your phrase (or a pin or flag); max20 runs Fable only on your phrase.

## 7. Workflows

Inline scripts get an injected `__wfAgent` wrapper. It finds the role by `agentType`, then by an
`opts.label` word token that equals or starts with a `roles.labels` key (`review:pkg`, `integrator`
match; `preview-pages`, `inspect-logs`, `redesign` do not), then `default`, and applies the tier
model with the usage step-down and ceiling already computed. Escalation lifts executor roles only:
a retry marker in `args.task`/`args.brief` lifts every call; a retry marker in one call's prompt
lifts that call at run time (a fix-loop template in the script does not lift its first call); the
size/risk rule reads the script text plus task and brief once. An explicit `opts.model` is honoured
within the ceiling except a tier's ask-only model (Opus on max5/api, Fable on max20), which needs your
phrase this turn; fable always needs it, and the usage guard steps a bare literal down.

Saved scripts (`scriptPath`, `name`) are never rewritten. They were rendered per tier by
`scripts/build_workflows.py`, which records `workflows/.rendered.json`. When `args.task` or
`args.brief` escalates, the guard adds `args.tier_hint = "escalate"` and the script uses its `:up`
models. The guard says something only when `.rendered.json` is missing or disagrees with the current
tier or usage state; then it regenerates the library in the background.

Turn caps live in the same policy file: `turn_caps.agents` is the per-agent table that frontmatter
`maxTurns` must equal (the only cap a Workflow agent runs under), `turn_caps.schema_floor` the minimum
per role for every agentType a saved template calls, and `turn_caps.report_reserve` (6) the turns kept
for the report. `hooks/subagent-context.py` renders them as the SubagentStart line
`TURN CAP n: by turn d …` with `d = max(n - reserve, n // 2)`.

## 8. State files and telemetry

```
state/plan-tier.json      {"schema":1,"tier":"max20","source":"credentials","detected_at":<epoch s>,
                           "detail":"max/default_claude_max_20x","main":"opus","notice":"<line>"}   (no token, ever)
state/usage-guard.json    {"schema":1,"active":true,"five_hour_pct":83.0,"resets_at":<epoch s>,
                           "since":<epoch s>,"tier":"max20"}
state/session-bridge/<sid>.json   statusline output; read for five_hour_pct / five_hour_resets_at
state/model-modes/<repo_key>      per-project pin (one word)
```

`model` in settings.json is rendered from the tier on first render. If you remove it with `/model` →
Default, the installer keeps it removed (not drift); a tier change re-adds it only while the key is present.
Claude Code itself deletes a user-settings `model` when the org default-model record changes, so the
main session's tier model rides on the launcher instead (§6); `main` in `plan-tier.json` is what it reads.

Every decision appends a row to `hooks/.telemetry/<sid>.model-routing.jsonl`:
`{ts, agent, model, reason, tier, usage_guard, fallback}` from opus-guard and
`{ts, agent: "workflow:<name>", model, reason, tier, usage_guard, escalated, drift}` from the
workflow guard. The reason names `tier-cap`, `usage-guard`, `escalated` or `ignored` when they
applied. `plan-tier-detect` logs `{tier, source, changed, ok}` to the hook telemetry.

## 9. Cost notes

Haiku is the default worker. Above 100K prompt tokens it costs 5x, so Haiku roles keep
`autoCompactWindow` at 120000. The opus-guard note is one short sentence per Agent call; the
workflow guard says nothing on saved scripts unless something drifted.

## 10. Tests

```
python3 -m pytest hooks/tests/test_opus_guard.py hooks/tests/test_opus_guard_explicit.py \
  hooks/tests/test_model_policy_consistency.py hooks/tests/test_workflow_model_guard.py \
  hooks/tests/test_model_mode.py hooks/tests/test_model_advice.py hooks/tests/test_usage_guard.py \
  tests/test_plan_tier.py -q -p no:cacheprovider
```

Tests pin the tier with `tests/fixtures/plan-tier/tier_fixture.py` and never read real credentials.
