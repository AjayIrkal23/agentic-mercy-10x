# ADR 0001 — 2026-09-28 upgrade: routing, models, teams, rules, installer

Status: accepted (2026-09-27). Full decision table: master plan §0.3 (D1–D18).

## Context

Hook-based routing had silently stopped working (mutations dropped, invalid router
output, gates looping) while always-on context grew to ~45k tokens. Several choices below
are hard to reverse and would surprise a reader of older docs.

## Decisions (condensed)

| # | Decision | Trade-off accepted |
|---|---|---|
| D1 | Deliberate teams: teams stay enabled, `name` optional, teams only for teammate messaging via `agents/team-lead.md` + TeammateIdle gate | teammates lose `skills:`/`mcpServers` preload; lead must hand them baseline skills |
| D2/D3 | Model routing = `CLAUDE_CODE_SUBAGENT_MODEL=sonnet` + agent `model:` pins + `opus-guard` label aligner; write protocol via SubagentStart, never `updatedInput.prompt` | routing no longer depends on one hook, but pins now live in agent files too |
| D5 | Native skill `paths:` first; alias stubs deleted, resolved at runtime | old alias names only work through `hooks/lib/skill_aliases.py` |
| D6 | Native `rules/**/*.md` loader; no `.mdc`, no `@import` | long doctrine moved into skills (loaded on demand) |
| D8 | lean-ctx hooks removed; settings never contain "lean-ctx" | lose lean-ctx shell compression on Bash |
| D11 | dox: git repos only, `~/.claude` and `$HOME` refused, all-dirs is opt-in | per-directory docs no longer appear automatically everywhere |
| D12 | `/invoke` moved from slash-command files to generated skills with run folders | any external reference to the old command files breaks |
| D13 | MCP truth = `installer/manifest.json` → `~/.claude.json` (user scope) | template can no longer carry MCP config |
| D14 | One `vendored-git` provenance family (`hooks/skills-sources.json`) | vendored skill edits must go through overrides/patches |
| D17 | Originally downgraded MCP mandates; **reversed 2026-09-28** — jcodemunch/graphify/jdocmunch/sequential-thinking/memory/context7/semgrep are MUST | more tool calls per task |

## 3-part test

Hard to reverse (settings/agent/skill layout, deleted files): yes. Surprising (teams on
but unnamed by default; MCP not in template; `~/.claude` has no dox tree): yes. Real
trade-off: yes (table above).

## Consequences

Docs and dox files updated in the same change set; see `docs/CHANGELOG.md`.
