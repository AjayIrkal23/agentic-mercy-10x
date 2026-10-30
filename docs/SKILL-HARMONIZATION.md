# Skill precedence — overlapping clusters

Alias stub skills were deleted on 2026-09-27. Old names still resolve at runtime to one
canonical skill through `hooks/skill-aliases.json` (read by `hooks/lib/skill_aliases.py`),
so each cluster below now has exactly one local skill plus optional plugin companions.

| Cluster | Canonical local skill | Resolved aliases | Plugin companion |
|---|---|---|---|
| TDD | `test-driven-development` (Go: `golang-testing`) | `tdd` | `superpowers:test-driven-development` |
| Debug | `debug-investigation` | `diagnose`, `debugging-and-error-recovery` | `superpowers:systematic-debugging` |
| Browser QA | `webapp-testing` | `browser-testing-with-devtools` | reticle skills (`debug-broken-ui`, `test-error-states`) |
| API contract | `api-contract-standards` (+ `backend-api-standards` for list/search endpoints) | `api-and-interface-design` | — |
| Security | `owasp-security` | `security-and-hardening` | semgrep MCP |
| Code review | `code-review-and-quality` | `frontend-code-review`, `backend-code-review` | `santa-review` for adversarial review |

## Planning stack (complementary, not rivals)

`workflow-orchestrator` (surfaces, phases) → `plan-mode-gate` (pre-flight) →
`superpowers:writing-plans` or `architect-system-design`. Lifecycle: `rules/02-lifecycle.md`.

## How skills surface

Prompt router (≤5 per prompt), native `paths:` when matching files are read, the
write-time FE/BE reminder, and agent `skills:` preload. Mechanics: skill
`skill-linkage-story`.

## Other resolved aliases

| Alias(es) | local skill |
|---|---|
| `frontend-api-standards` | `frontend-response-handling` |
| `documentation-and-adrs` | `update-docs` |
| `jcodemunch-token-saver`, `project-structure-map`, `iterative-retrieval`, `zoom-out`, `codebase-start-point-guide` | `codebase-intel-first` |
| `forensic-change-coupling`, `forensic-complexity-trends`, `forensic-debt-quantification`, `forensic-hotspot-finder`, `improve-codebase-architecture` | `tech-debt-audit` |
| `plan-exec-stack-guide`, `gsd-execute-phase` | `workflow-orchestrator` |
| `strategic-compact` | `context-engineering` |
| `incremental-implementation` | `code-execution-standard` |
| `domain-scaffold-patterns` | `scaffold-standards` |

## ECC cluster map (ecc @25278e7d)

Every ECC skill or agent name below resolves to one local home; nothing landed as a second
skill. "graft" = `references/ecc-*.md` in the local skill plus one pointer line; "vendored
prepend graft" = a blockquote in that skill's `prepend_body` in `hooks/skills-sources.json`.

| ECC name(s) | local skill | how it landed |
|---|---|---|
| `tdd-workflow` | `test-driven-development` | graft `references/ecc-tdd.md` |
| `e2e-testing` | `webapp-testing` | alias only (server-start text fixed) |
| `security-review` | `owasp-security` | graft `references/ecc-minimum-bar.md` |
| `backend-patterns` | `backend-standards-always-follow` | graft `references/ecc-patterns.md` |
| `frontend-patterns`, `coding-standards` | `frontend-standards-always-follow` | graft `references/ecc-typescript.md` |
| `api-design`, `contract-first` | `api-contract-standards` | graft `references/ecc-api-design.md` |
| `error-handling` | `backend-error-handling` | graft `references/ecc-silent-failures.md` |
| `react-patterns` | `react-hooks-patterns` | graft `references/ecc-react-rules.md` |
| `react-native-patterns` | `expo-react-native` | graft `references/ecc-rn-rules.md` |
| `react-testing` | `vitest-rtl` | graft `references/ecc-coverage-tiers.md` |
| `react-performance`, `vite-patterns`, `nextjs-turbopack` | `vite-react-best-practices` | vendored prepend graft |
| `motion-foundations`, `motion-patterns`, `motion-advanced` | `motion-dev` | graft `references/ecc-motion.md` |
| `accessibility`, `frontend-a11y` | `fixing-accessibility` | vendored prepend graft |
| `council` | `doubt-driven-development` | graft `references/ecc-council.md` |
| `database-migrations` | `deprecation-and-migration` | graft `references/ecc-db-migrations.md` |
| `deployment-patterns`, `production-audit` | `shipping-and-launch` | graft `references/ecc-release.md` |
| `docker-patterns` | `docker-compose` | graft `references/ecc-docker.md` |
| `frontend-slides` | `slides` | note only |
| `brand-voice` | `brand` | graft `references/ecc-voice-bans.md` |
| `design-system` | `design-system-compliance` | vendored prepend graft |
| `frontend-design-direction` | `design-taste-frontend` | vendored prepend graft |
| `make-interfaces-feel-better` | `improve-ui` | vendored prepend graft |
| `click-path-audit` | `debug-broken-ui` | vendored prepend graft |
| `browser-qa` | `verify-ui-change` | vendored prepend graft |
| `benchmark-optimization-loop` | `performance-optimization` | graft `references/ecc-benchmark-loop.md` |
| `change-impact` | `dead-code-and-change-audit` | graft `references/ecc-change-impact.md` |
| `hexagonal-architecture` | `codebase-design` | graft `references/ecc-hexagonal.md` |
| `documentation-lookup`, `docs-lookup` | `context7-mcp` | note only |
| `skill-scout` | `find-skills` | vendored prepend graft |
| `living-docs-governance` | `update-docs` | graft `references/ecc-living-docs.md` |
| `docs-governance` | `ensure-repo-docs` | note only |
| `search-first` | `codebase-intel-first` | graft `references/ecc-explorer.md` |
| `intent-driven-development`, `product-capability` | `spec-driven-development` | graft `references/ecc-intent-and-prd.md` |
| `architecture-decision-records`, `context-and-decisions` | `grill-with-docs` | graft `references/ecc-adr.md` |
| `config-gc`, `automation-audit-ops`, `workspace-surface-audit`, `harness-audit` | `workflow-audit` | graft `references/ecc-harness-audit.md` |
| `mcp-server-patterns` | `mcp-builder` | graft `references/ecc-mcp-server.md` |
| `santa-method` | `santa-review` | convergence-loop section in SKILL.md |
| `git-workflow`, `conventional-commit-review` | `git-workflow-and-versioning` | graft `references/ecc-git.md` |
| `blueprint` | `planning-and-task-breakdown` | graft `references/ecc-blueprint.md` |
| `agent-eval` | `eval-harness` | graft `references/ecc-pass-at-k.md` |
| `orch-pipeline`, `plan-orchestrate` | `invoke` | size-tier section (generated) |
| `feature-dev` | `workflow-orchestrator` | graft `references/ecc-feature-dev.md` |
| `code-reviewer`, `architect`, `planner`, `doc-updater`, `e2e-runner`, `refactor-cleaner`, `security-reviewer`, `tdd-guide`, `build-error-resolver` | `santa-reviewer` and the other agents | agent merges: see `agents/README.md` § ECC equivalents |

`security-review` is also a Claude Code built-in slash command; the alias only affects
hook-side name resolution (router pushes, generators), not native skill lookup.

## Placement and provenance rules (ecc:docs/SKILL-DEVELOPMENT-GUIDE.md, docs/SKILL-PLACEMENT-POLICY.md, docs/skill-adaptation-policy.md @25278e7d)

- A new capability is a skill — not a command, not an agent — unless it needs its own context.
- Same-name upstream material is grafted as `references/ecc-*.md` (≤ 60 lines, cited), never
  a second skill.
- Vendored skills change only through `hooks/skills-sources.json` (`patches`, `prepend_body`),
  then re-vendor and rebaseline.
- Aliases are permanent; stub directories are never recreated.
- Long-form vendor text goes to `library/` (zero always-on tokens).
