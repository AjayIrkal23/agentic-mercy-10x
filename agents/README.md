# Cursor Agents — Lifecycle Routing

Agents live in `~/.cursor/agents/`. GSD workflows spawn via `$HOME/.cursor/agents/<name>.md`.

## When to use which agent

| Intent | Agent | Paired skill |
|--------|-------|--------------|
| Pre-merge PR review | `code-reviewer` (Task) — Superpowers plugin: `plugins/.../superpowers/.../agents/code-reviewer.md` | Santa gate writes `.santa.json` |
| GSD phase code review | `gsd-code-reviewer` | `gsd-code-review` skill |
| Deep quality audit | `thermo-nuclear-code-quality-review` | Plugin rubric |
| Figma → code | `figma-implementation`, `figma-code-connect` | UI six-skill stack |
| Design parity | `figma-design-parity-reviewer` | `impeccable` audit |
| Frontend polish | `frontend-uiux-designer` | `frontend-ui-engineering` |
| Vercel AI apps | `vercel-ai-architect` | `architect-system-design` |
| Deploy / perf | `vercel-deployment-expert`, `vercel-performance-optimizer` | `shipping-and-launch` |
| GSD planning | `gsd-planner`, `gsd-phase-researcher` | `gsd-plan-phase` |
| GSD execution | `gsd-executor` | `gsd-execute-phase` |
| Codebase map | `gsd-codebase-mapper` | `gsd-map-codebase` |
| Intel / docs | `gsd-intel-updater`, `gsd-doc-writer` | `gsd-docs-update` |
| Security phase | `gsd-security-auditor` | `owasp-security`, `cso` |
| UI phase | `gsd-ui-researcher`, `gsd-ui-auditor` | UI stack |

## Orphans wired here

These agents are **not** deprecated — invoke via Task when the handoff table in [`agent-lifecycle-routing.md`](../rules/agent-lifecycle-routing.md) applies:

- `frontend-uiux-designer` — UI polish after `impeccable shape`
- `gsd-intel-updater` — after `gsd-map-codebase` or milestone audits
- Figma agents — when user provides Figma URLs (MCP + agent)
- Vercel agents — deployment/architecture questions

## Plugins

Superpowers, shadcn, GSAP, MongoDB, Redis plugins **stay enabled** — they support planning and implementation layers. Do not disable for "simplicity."

See [`ECC-CLAUDE-BUNDLE-NOTES.md`](../ECC-CLAUDE-BUNDLE-NOTES.md) for path migration notes.
