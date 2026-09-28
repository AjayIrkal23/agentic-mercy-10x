# Plan / execution stack ordering

> Absorbed into `workflow-orchestrator` (P5 consolidation). Method content preserved verbatim below.

---

# Plan / execution stack guide

## Quick routing

| Phase | Load first |
|-------|------------|
| Plan, spec, architecture, brainstorm | Superpowers `writing-plans`, `brainstorming`, `verification-before-completion` (under `~/.claude/plugins/.../superpowers/*/skills/`) |
| Map repo + contracts | `codebase-intel-first`, `project-reference-linkage` |
| MCP / tool-heavy verification | `mcp-usage-standards` |
| Decomposition + gates | `workflow-orchestrator`, `architect-system-design` |
| Plan / design visualization | `claude-mermaid:mermaid-diagrams` (plugin path `~/.claude/plugins/marketplaces/claude-mermaid/skills/mermaid-diagrams/SKILL.md`) — flowchart, sequence, state, ER, class diagrams via `mermaid_preview`/`mermaid_save`. Pair with `writing-plans` / `architect-system-design` / `workflow-orchestrator`. |
| Clear-scope coding | `code-execution-standard` + mandatory FE/BE list from hooks |
| Unknown failure | `debug-investigation` (and Superpowers `systematic-debugging` when appropriate) |

**Linkage map:** Full hook/rule sequence diagrams, playbooks, and Superpowers↔agent matrix live in [`skill-linkage-story`](../../skill-linkage-story/SKILL.md) → [`references/graph-and-stories.md`](../../skill-linkage-story/references/graph-and-stories.md) and [`references/hooks-rules-e2e.md`](../../skill-linkage-story/references/hooks-rules-e2e.md). Plan vs execution layering: [`plan-exec-unified-stack.md`](plan-exec-unified-stack.md) (this folder).

## Ported ECC Claude bundle — when to load

Canonical orchestrator stays **`workflow-orchestrator`**; **`agent-skills-orchestrator`** from the source bundle was **not** copied (merge conflict).

| Intent | Skill under `~/.claude/skills/` |
|--------|----------------------------------|
| Refine vague ideas before a spec | `idea-refine` |
| Decompose work into tasks | `planning-and-task-breakdown` |
| Spec-first delivery | `spec-driven-development` |
| Code as source of truth / exploration | `source-driven-development` |
| Challenge assumptions | `doubt-driven-development` |
| Phased / incremental delivery | `code-execution-standard` |
| Context compaction discipline | `context-engineering` |
| Retrieval / search strategy | `codebase-intel-first` |
| ADRs and documentation structure | `update-docs`, `domain-modeling` |
| Git workflow and versioning | `git-workflow-and-versioning` |
| CI/CD and automation | `ci-cd-and-automation` |
| Security and hardening | `owasp-security` |
| Shipping and launch | `shipping-and-launch` |
| Cross-cutting performance | `performance-optimization` |
| Prompt and context design | `context-engineering` |
| Simplify and clarify code | `code-simplification` |
| Deprecation and migration | `deprecation-and-migration` |
| Eval / harness patterns | `eval-harness` |
| Verification loop (complements Superpowers) | `verification-loop` |
| Generic code review checklist | `code-review-and-quality` |
| API and interface design | `api-contract-standards` |
| Browser testing with DevTools | `webapp-testing` |
| PostgreSQL patterns | `postgres-patterns` |
| Meta: how to discover and use skills | `using-agent-skills` |
| Plan / code pre-flight gate | `plan-mode-gate` |
| Go idioms and structure | `golang-patterns` |
| Go testing patterns | `golang-testing` |

## Hooks and rules

- **Canonical E2E doc:** `~/.claude/skills/skill-linkage-story/references/hooks-rules-e2e.md` (pipeline order, configs, overlap notes).
- **Prompt-time routing:** `~/.claude/hooks/prompt_router/router.py` (≤5 skills per prompt)
- **Write hint:** `~/.claude/hooks/fullstack-skills-reminder.py` (canonical `FRONTEND_SKILLS` / `BACKEND_SKILLS` baselines; native `paths:` frontmatter surfaces the rest)
- **Plan vs execution layering:** [`plan-exec-unified-stack.md`](plan-exec-unified-stack.md) (this folder)
- **Session soft gate (ECC `plan-mode-gate` port):** plan-shaped prompts → the prompt router (`hooks/prompt_router/`) surfaces `plan-mode-gate`

## Superpowers path

If hooks cannot find the plugin, set `SUPERPOWERS_SKILLS_ROOT` to the `skills` directory inside your installed Superpowers bundle.
