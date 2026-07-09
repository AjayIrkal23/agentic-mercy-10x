# /invoke-impl → implementation ALWAYS on Opus

> Always-on. User directive (2026-07-03): the **IMPLEMENT** suite implements on **Opus
> only**. An explicit, user-authorized carve-out to the sonnet-by-default policy in
> CLAUDE.md (§ "Agent tool — REQUIRED prefix"). Scope: implementation work only.

## Rule

Any command that loads the **IMPLEMENT** suite — `/invoke-impl`, `/invoke-implementation`,
and every combo whose name contains `impl` (`/invoke-spec-plan-impl`, `/invoke-impl-clean`,
`/invoke-audit-impl-debug`, …) — does its implementation on **Opus**:

- Spawn every implementation subagent with an `[opus]` description prefix **and**
  `model:"opus"`. `opus-guard.py` (PreToolUse, Agent matcher) then pins it to Opus.
- If the main loop is not on Opus, **delegate** the implementation to an Opus subagent
  rather than writing it inline on a smaller model.
- Read-only / non-implementation helpers (search, explore, lint, docs) keep their
  default (Sonnet). Only the implementation itself is forced to Opus.

## Enforcement (self-carrying, survives regeneration)

Single source of truth: `~/.claude/hooks/autonomous-skill-router.config.json` →
`categories.IMPLEMENT.model: "opus"`. `gen-invoke-commands.py` renders that into a
`⚠️ RUNS ON OPUS (mandatory)` callout at the top of the IMPLEMENT block of every
generated `/invoke-*impl*` command, so the directive is in front of the agent every
time the command runs.

To change: edit the config (NOT the generated `.md`) and re-run
`python3 ~/.claude/hooks/gen-invoke-commands.py`. Setting any category's `model` field
makes the same callout fire for that category.

Related: `rules/agent-lifecycle-routing.md`, CLAUDE.md model-routing section,
`hooks/opus-guard.py`, `hooks/workflow-model-guard.py`, memory `skill-router-full-suites`.
