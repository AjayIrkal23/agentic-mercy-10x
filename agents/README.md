# Cursor Agents — Lifecycle Routing

Agents live in `~/.claude/agents/`. GSD workflows spawn via `$HOME/.claude/agents/<name>.md`.

## When to use which agent

| Intent | Agent | Paired skill |
|--------|-------|--------------|
| **Adversarial bug-hunt review (Santa Method)** | **`santa-reviewer`** (Opus) — BREAKER + SIMPLIFIER + VERIFIER; `/invoke-review` (closer on every code-mutating invoke) or `/santa-review` | `santa-review` skill; satisfies Gate 4 (writes `.santa.json`) |
| **Author failing tests first (TDD red)** | **`test-author`** — behavior-first, edge-complete tests seen RED before code; `/invoke-test` | `test-driven-development`, `golang-testing`, `webapp-testing` |
| **Behavior-preserving refactor** | **`refactor-specialist`** — blast-radius-aware, test-guarded restructuring; `/invoke-refactor` | `code-simplification`, `improve-codebase-architecture` |
| Pre-merge PR review | `code-reviewer` (Task) — Superpowers plugin: `plugins/.../superpowers/.../agents/code-reviewer.md` | Santa gate writes `.santa.json` |
| Deep quality audit | `thermo-nuclear-code-quality-review` | Plugin rubric |
| Figma → code | `figma-implementation`, `figma-code-connect` | UI six-skill stack |
| Design parity | `figma-design-parity-reviewer` | Figma comparison |
| Frontend polish | `frontend-uiux-designer` | `frontend-ui-engineering` |
| Vercel AI apps | `vercel-ai-architect` | `architect-system-design` |
| Deploy / perf | `vercel-deployment-expert`, `vercel-performance-optimizer` | `shipping-and-launch` |

## Orphans wired here

These agents are **not** deprecated — invoke via Task when the handoff table in [`agent-lifecycle-routing.md`](../rules/agent-lifecycle-routing.md) applies:

- `frontend-uiux-designer` — UI polish when requested
- Figma agents — when user provides Figma URLs (MCP + agent)
- Vercel agents — deployment/architecture questions

## Plugins

Superpowers, shadcn, GSAP, MongoDB, Redis plugins **stay enabled** — they support planning and implementation layers. Do not disable for "simplicity."

The manual entrypoints are the 20 `/invoke` commands (parametric `/invoke <acts...>` + 10 single-act delegators + `invoke-fullstack` + 5 muscle-memory aliases + 3 utilities); the keyword auto-router dispatches these same specialist agents from `autonomous-skill-router.config.json`. **Figma agents are DORMANT** (require a Figma MCP server — register one to activate). **Vercel agents** (vercel-ai-architect, vercel-deployment-expert, vercel-performance-optimizer) are available and surface via `/invoke design|ship` suggestions.
