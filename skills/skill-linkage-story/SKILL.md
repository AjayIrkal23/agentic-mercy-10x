---
name: skill-linkage-story
description: 'How skills reach the model in this setup: dispatch.py events, the prompt router, native paths: activation, write-time reminders, and stop gates.'
when_to_use: Use when onboarding to this ~/.claude config or debugging a skill reminder that did not appear.
paths:
- '**/.claude/hooks/**'
- '**/.claude/agents/**'
- '**/.claude/skills/**'
- 'hooks/**/*.py'
- 'skills/*/SKILL.md'
metadata:
  schema: 1
  category: general
  surfaces:
  - general
  platforms:
  - linux
  - darwin
  - windows
  triggers:
    keywords:
    - hooks
    - dispatch
    - prompt-router
    - paths
    - skill reminder
    - skill not loading
    - missing skill
    - linkage
    - onboarding
    - sessionstart
    - userpromptsubmit
    - pretooluse
    - posttooluse
    - stop
    paths: []
    intents:
    - general
---
# Skill Linkage Story — how a skill reaches the model

Every layer is declared in `~/.claude/hooks/dispatch.config.json` (one `dispatch.py <event>`
per Claude Code event) or in native skill/rule frontmatter. Skill names everywhere are
**canonical**; old alias names resolve at runtime through `hooks/lib/skill_aliases.py`
(`hooks/skill-aliases.json`). There are no alias stub directories.

## 1. SessionStart — `dispatch.py session-start`

| Link | Effect |
|------|--------|
| `session-start-aggregator.py` | Injects the always-active core set from `hooks/core-skill-set.json` (the `caveman` body, capped; one-line pointers for the rest, because only one short body fits the ~4.3k chars left of the 5,500-char budget), MCP roster, plan-gate hint |
| `memory-load-on-start.py` | Top memory entities for the repo |
| `skills-index-guard` (`build-skills-index.py --hook`) | Rebuilds `hooks/skills-index.json` when any SKILL.md, the alias map, or the plugin list is newer |

## 2. UserPromptSubmit — `prompt_router/router.py` (single process)

classify (word-boundary intents) → surface (repo stack fingerprint + prompt paths) →
rank ≤4 skills (`max_skill_pushes` in `router.config.json`) from `skills-index.json` (metadata keywords, aliases collapsed, plugin
skills as `plugin:skill`) → ≤1 deep body → MCP routes → agent suggestion → model advice →
`hookSpecificOutput.additionalContext`.

## 3. Reading files — native activation (no hook)

- Skill frontmatter `paths:` (rule-style globs) surfaces file-bound skills as matching
  files are read: `golang-patterns` on `**/*.go`, `postgres-patterns` on `**/*.sql` and
  `**/migrations/**`, `backend-api-standards` on `**/routes/**`, `owasp-security` on
  `**/auth/**`, FE skills on `**/*.tsx` etc. `when_to_use:` sharpens the trigger.
- Path-scoped rules: `rules/frontend.md`, `rules/backend.md`, `rules/claude-infra.md`
  load only when their `paths:` match; `rules/0*.md` are always on.

## 4. Writes — `dispatch.py pre-tool-use` / `post-tool-use`

| Link | Effect |
|------|--------|
| `first-write-skill-gate.py` (pre) | Blocks the first code write until the surface's baseline skills were read |
| `dangerous-bash-gate`, `dox-write-gate`, `gateguard-write-gate`, `tdd-guard-gate` (pre) | Safety gates; tdd-guard is advisory |
| `fullstack-skills-reminder.py post-tool-use` | **Once per surface:** top-3 skills for the written path (`skill_router.py` + `skill_router.config.json`, first matching rule wins, aliases collapsed) + cross-cuts, then "native `paths:` will surface the rest". No per-write manifest batches. |
| `post-write-aggregator.py` | doc-update reminder, desloppify @8 writes, security-scan reminder, trackers |

## 5. Agent spawn — `Agent` tool

`opus-guard.py` aligns the `[model]` label with `model:`; a `SubagentStart` hook injects the
write protocol. Specialist agents preload their skill sets through `skills:` frontmatter
(rendered by `hooks/gen-agent-skill-blocks.py` from `FRONTEND_SKILLS` / `BACKEND_SKILLS`
in `fullstack-skills-reminder.py`).

## 6. Stop — `dispatch.py stop`

`hard-completion-gate.py` (docs / security / Santa / dead-code gates, ≤1 block per turn)
and the reminder's re-verify line (skills captured at first write).

## Debugging a missing skill reminder

1. Is the name canonical? `python3 ~/.claude/hooks/lib/skill_aliases.py`; look the alias up in `hooks/skill-aliases.json`.
2. Is it indexed? `python3 ~/.claude/hooks/build-skills-index.py --check`, then grep `hooks/skills-index.json`.
3. Should it have surfaced natively? Check the skill's `paths:` globs against the file you read.
4. Write-time: `skill_router.config.json` rule order (first match wins); state flags `frontend_start_sent` / `backend_start_sent` in `hooks/.state/<cid>.fullstack.json`.
5. Did the link fire? `telemetry/hook-fires-<date>.jsonl`.
6. Frontmatter sane? `python3 ~/.claude/scripts/validate_skills.py` (R11: custom keys under `metadata:`; R12: `paths:` globs).
