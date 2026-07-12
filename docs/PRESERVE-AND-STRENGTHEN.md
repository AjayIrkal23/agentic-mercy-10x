# Preserve & Strengthen — Design Principles

This document locks the non-negotiables for the Cursor agent stack. Fixes may change **wiring**; they must not degrade **rigor**.

## Never Degrade

| Area | Requirement |
|------|-------------|
| **Lifecycle** | [`mandatory-skill-protocol.mdc`](../rules/mandatory-skill-protocol.mdc) phases 0–7 remain authoritative |
| **Frontend skills** | All **28** mandatory FE skills in [`fullstack-skills-reminder.py`](../hooks/fullstack-skills-reminder.py) stay enforced: path-ranked on each Write + session manifest covers full list + stop re-verify |
| **Backend skills** | All **27** mandatory BE skills stay enforced; router gaps are filled, not trimmed |
| **Scaffold** | [`scaffold-standards`](../skills/scaffold-standards/SKILL.md), [`frontend-structure-standards`](../skills/frontend-structure-standards/SKILL.md), [`service-layer-standards`](../skills/service-layer-standards/SKILL.md) win over subsidiary layout advice |
| **Planning layers** | mandatory Phase 1 + `workflow-orchestrator` + `plan-mode-gate` + GSD + Superpowers are **complementary** — see [`plan-exec-unified-stack.md`](../rules/plan-exec-unified-stack.md) |
| **UI/UX** | Six-skill stack per [`ui-ux-playbook.mdc`](../rules/ui-ux-playbook.mdc); Impeccable precedence on layout/motion bans |
| **Completion** | Doc gate (Gate 2) stays hard; Santa gate (Gate 4) requires real review completion, not removal |

## Fix Wiring Only

- False Santa blocks → implement `.santa.json` writer
- Stale User Rules duplication → bootstrap pointer; skills load from Project Rules + hooks
- Missing routing docs → [`agent-lifecycle-routing.md`](../rules/agent-lifecycle-routing.md), [`skill-linkage-story`](../skills/skill-linkage-story/SKILL.md)
- `.claude` path drift → canonical `~/.cursor/` paths
- Contract contradictions → [`api-contract-standards`](../skills/api-contract-standards/SKILL.md) wins
- Hook latency → debounce duplicate reminders; remove dead spawns; **do not** reduce skill injection

## Token Budget Reinvestment

Slim User Rules (~400 tokens) free budget for skill/planning context. FE/BE lists live in hook source — not duplicated in User Rules.

## Planning Handoff Order

1. `workflow-orchestrator` — surfaces, phases, mermaid
2. `plan-mode-gate` — formal gate when planning
3. Layer choice: GSD (`.planning/`), Superpowers (`docs/superpowers/`), or architect-system-design
4. User approval before Phase 2 coding
5. `fullstack-skills-reminder` + `skill_router` on first Write; session manifest surfaces remaining FE/BE skills over the conversation

See [`agent-lifecycle-routing.md`](../rules/agent-lifecycle-routing.md) for phase → skill → hook map.

---

> **Vindication (2026-07-11 · 100x overhaul).** The overhaul in
> [`../plans/PLAN-2026-07-11-100x.md`](../plans/PLAN-2026-07-11-100x.md) rebuilt the
> routing/dispatch/index/model layers **without dropping a single trigger**: every
> legacy keyword/path/intent was reverse-imported verbatim into
> `hooks/trigger-floor.json` (checksum-guarded in CI), 65 hook registrations became
> 8 isolated `dispatch.py` orchestrators with every hook keeping its own file, and
> the cutover runs behind a one-flip 30-day revert. That is this doc's thesis —
> preserve the trigger surface, strengthen the machinery around it — proven at scale.
