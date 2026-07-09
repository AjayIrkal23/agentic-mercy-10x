# Plan & Execution Unified Stack

How planning layers hand off — **complementary, not rivals**.

## Canonical order

1. **`workflow-orchestrator`** — Routes surfaces (BE/FE/fullstack), assigns Architect / Code / Debug modes, breaks multi-phase work.
2. **`plan-mode-gate`** — Formal `PLAN_GATE` checklist (Superpowers, jcodemunch mandatory unless index build attempted and confirmed absent, sequential thinking, Context7) before `mutation=open`.
3. **Domain planning** (pick by context):
   - **`architect-system-design`** — New domains, contracts, decomposition.
   - **GSD** (`gsd-discuss-phase`, `gsd-plan-phase`) — When `.planning/` exists in repo.
   - **Superpowers** (`brainstorming`, `writing-plans`) — Creative/feature depth; artifacts under `docs/superpowers/`.
4. **Mandatory Phase 1 baseline** — 3–5 sharpening questions, vertical slices, plan file paths (`plan-YYYY-MM-DD-*.md`, `docs/superpowers/plans/`).
5. **Execution** — Phases 2–3 with `fullstack-skills-reminder` + `skill_router` on first Write.

## When each layer leads

| Situation | Lead layer | Artifact |
|-----------|------------|----------|
| Ambiguous or multi-surface task | workflow-orchestrator | Phase list, mode assignment |
| Any build/fix/refactor >2 files | plan-mode-gate | PLAN_GATE line |
| Milestone in repo with `.planning/` | GSD discuss → plan | `.planning/phases/*/PLAN.md` |
| New feature / creative UI | Superpowers brainstorming | `docs/superpowers/specs/` |
| New API domain / contract | architect-system-design | Architecture spec |
| Straightforward single-file fix | plan-mode-gate (light) → code | Inline plan in chat |

## Handoff rules

- **Never skip user approval** after Phase 1 plan before Phase 2 code.
- GSD and Superpowers artifacts **nest under** mandatory plan paths — they do not replace `mandatory-skill-protocol.mdc`.
- `plan-exec-stack-guide` skill resolves conflicts between stacks; this doc is the source of truth for ordering.
- Session start: `session-plan-gate-hint.py` reminds of gate; full routing in [`agent-lifecycle-routing.md`](agent-lifecycle-routing.md).
- **Authority:** `mandatory-skill-protocol.mdc` is the canonical lifecycle source. This file describes planning stack ordering only. When they conflict, `mandatory-skill-protocol.mdc` wins.

## Post-coding (always sequential)

Phases 4–7 from mandatory protocol: dead-code audit → de-sloppify → lint/security → review (Santa) → docs. Hooks enforce at stop/commit.
