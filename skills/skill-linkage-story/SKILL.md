---
name: skill-linkage-story
description: End-to-end story of how Claude Code hooks inject skills from sessionStart through stop — sessionStart,
  beforeSubmit, preToolUse, postToolUse, stop. Use when onboarding to this config or debugging missing
  skill reminders.
schema: 1
category: general
surfaces:
- general
platforms:
- linux
- darwin
- windows
token-cost: 580
triggers:
  keywords:
  - beforesubmit
  - config
  - cursor
  - debugging
  - end-to-end
  - hooks
  - inject
  - linkage
  - missing
  - onboarding
  - posttooluse
  - pretooluse
  - reminders
  - sessionstart
  - skill
  - skills
  - stop
  - story
  - through
  paths: []
  intents:
  - general
---
# Skill Linkage Story — Hook → Skill E2E

## 1. sessionStart

| Hook | Injects |
|------|---------|
| `session-start-aggregator.py` | Plan gate hint, doc lifecycle, graphify/jcodemunch guards, lifecycle routing path, Superpowers roster, MCP names |
| `session-lifecycle.py` | GSD resume breadcrumb, fe/be touched from prior session |

**Skills implied:** `plan-mode-gate`, `using-superpowers`, `mcp-usage-standards`, `codebase-start-point-guide`

## 2. beforeSubmitPrompt

| Hook | Injects |
|------|---------|
| `ui-ux-stack-orchestrator.py` | Full 6-skill UI stack + Impeccable context + designlang hints on UI prompts |
| `token-stack-prompt-reminder.py` | jcodemunch/graphify/ast-grep routing on code-intent prompts |
| `gsd-context-monitor.js` | GSD context budget when `.planning/` active |

## 3. preToolUse

| Hook | Effect |
|------|--------|
| `blocking-doc-enforcer.py` | **Deny** git commit if docs missing |
| `gateguard-write-gate.py` | Importer/signature checks on bulk writes |
| GSD guards | Prompt injection / workflow protection |

## 4. postToolUse (Write/StrReplace)

| Hook | Injects |
|------|---------|
| `fullstack-skills-reminder.py` | **First Write:** path-ranked skills + cross_cutting; **session manifest** batches remaining 28 FE / 27 BE slugs on later writes |
| `skill_router.py` | Ranked MUST/SHOULD/REFERENCE paths |
| `doc-update-enforcer.py` | Doc update reminder (debounced per surface) |
| `desloppify-cleanup.py` | De-sloppify @8 writes |
| `security-scan-gate.py` | Semgrep reminder on auth/API paths |
| `santa-method-writer.py` | Marks Santa complete on code-reviewer Task |
| `ui-ux-stack-orchestrator.py` | Post-UI-write audit reminder |

## 5. stop

| Hook | Effect |
|------|--------|
| `fullstack-skills-reminder.py` | Re-verify skills from first Write |
| `hard-completion-gate.py` | Gate 2 docs hard; Gate 3 security semi-hard; Gate 4 Santa semi-hard |
| `session-lifecycle.py` | Save breadcrumb for next session |

## Debugging missing skills

1. Confirm path hits FE/BE segments in `fullstack-skills-reminder.py`.
2. Check `skill_router.config.json` rule order (first match wins).
3. Verify `frontend_start_sent` / `backend_start_sent` in `.state/{cid}.fullstack-skills.json`.
4. Read [`agent-lifecycle-routing.md`](../../rules/agent-lifecycle-routing.md) for rule IDs.
