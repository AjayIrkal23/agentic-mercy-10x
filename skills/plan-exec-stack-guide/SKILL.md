---
name: plan-exec-stack-guide
description: Use when choosing between planning vs implementation stacks, Superpowers vs mandatory frontend/backend
  skills, or when Cursor Plan mode and Agent execution need explicit skill ordering. Triggers include
  plan vs implement, which skills first, superpowers routing, architect vs code vs debug phases.
schema: 1
category: planning
surfaces:
- planning
platforms:
- linux
- darwin
- windows
token-cost: 1069
triggers:
  keywords:
  - agent
  - architect
  - choosing
  - code
  - cursor
  - debug
  - exec
  - execution
  - explicit
  - first
  - frontend/backend
  - guide
  - implement
  - implementation
  - include
  - mandatory
  - mode
  - need
  - ordering
  - phases
  - plan
  - planning
  - routing
  - skill
  - skills
  - stack
  - stacks
  - superpowers
  - triggers
  paths: []
  intents:
  - planning
---
# Plan / execution stack guide

## Quick routing

| Phase | Load first |
|-------|------------|
| Plan, spec, architecture, brainstorm | Superpowers `writing-plans`, `brainstorming`, `verification-before-completion` (under `~/.claude/plugins/.../superpowers/*/skills/`) |
| Map repo + contracts | `project-structure-map`, `project-reference-linkage` |
| MCP / tool-heavy verification | `mcp-usage-standards` |
| Decomposition + gates | `workflow-orchestrator`, `architect-system-design` |
| Plan / design visualization | `claude-mermaid:mermaid-diagrams` (plugin path `~/.claude/plugins/marketplaces/claude-mermaid/skills/mermaid-diagrams/SKILL.md`) — flowchart, sequence, state, ER, class diagrams via `mermaid_preview`/`mermaid_save`. Pair with `writing-plans` / `architect-system-design` / `workflow-orchestrator`. |
| Clear-scope coding | `code-execution-standard` + mandatory FE/BE list from hooks |
| Unknown failure | `debug-investigation` (and Superpowers `systematic-debugging` when appropriate) |

**Linkage map:** Full hook/rule sequence diagrams, playbooks, and Superpowers↔agent matrix live in [`skill-linkage-story`](../skill-linkage-story/SKILL.md) → [`references/graph-and-stories.md`](../skill-linkage-story/references/graph-and-stories.md) and [`references/hooks-rules-e2e.md`](../skill-linkage-story/references/hooks-rules-e2e.md). Always-on summary of plan vs execution overlaps with **`~/.claude/rules/plan-exec-superpowers-stack.md`**.

## Ported ECC Claude bundle — when to load

Canonical orchestrator stays **`workflow-orchestrator`**; **`agent-skills-orchestrator`** from the source bundle was **not** copied (merge conflict). Decisions and source tree: **`~/.claude/ECC-CLAUDE-BUNDLE-NOTES.md`**.

| Intent | Skill under `~/.claude/skills/` |
|--------|----------------------------------|
| Refine vague ideas before a spec | `idea-refine` |
| Decompose work into tasks | `planning-and-task-breakdown` |
| Spec-first delivery | `spec-driven-development` |
| Code as source of truth / exploration | `source-driven-development` |
| Challenge assumptions | `doubt-driven-development` |
| Phased / incremental delivery | `incremental-implementation` |
| Context compaction discipline | `strategic-compact` |
| Retrieval / search strategy | `iterative-retrieval` |
| ADRs and documentation structure | `documentation-and-adrs` |
| Git workflow and versioning | `git-workflow-and-versioning` |
| CI/CD and automation | `ci-cd-and-automation` |
| Security and hardening | `security-and-hardening` |
| Shipping and launch | `shipping-and-launch` |
| Cross-cutting performance | `performance-optimization` |
| Prompt and context design | `context-engineering` |
| Simplify and clarify code | `code-simplification` |
| Deprecation and migration | `deprecation-and-migration` |
| Eval / harness patterns | `eval-harness` |
| Verification loop (complements Superpowers) | `verification-loop` |
| Generic code review checklist | `code-review-and-quality` |
| API and interface design | `api-and-interface-design` |
| Browser testing with DevTools | `browser-testing-with-devtools` |
| PostgreSQL patterns | `postgres-patterns` |
| Meta: how to discover and use skills | `using-agent-skills` |
| Plan / code pre-flight gate (rigid; see Cursor note in skill body) | `plan-mode-gate` |
| Go idioms and structure | `golang-patterns` |
| Go testing patterns | `golang-testing` |

## Hooks and rules

- **Canonical E2E doc:** `~/.claude/skills/skill-linkage-story/references/hooks-rules-e2e.md` (pipeline order, configs, overlap notes).
- **Submit hint:** `~/.claude/hooks/plan-exec-stack-hint.py` + `plan-exec-stack-hint.config.json`
- **Write hint:** `~/.claude/hooks/fullstack-skills-reminder.py` (frontend **20** / backend **15** skills, including `architect-system-design` and `mcp-usage-standards`)
- **Always-on rule:** `~/.claude/rules/plan-exec-superpowers-stack.md`
- **Paste copy:** `~/.claude/rules/plan-exec-superpowers.md`
- **Mandatory list:** `~/.claude/rules/fullstack-mandatory.md`
- **Session soft gate (ECC `plan-mode-gate` port):** `sessionStart` → `~/.claude/hooks/session-plan-gate-hint.py`

## Superpowers path

If hooks cannot find the plugin, set `SUPERPOWERS_SKILLS_ROOT` to the `skills` directory inside your installed Superpowers bundle.
