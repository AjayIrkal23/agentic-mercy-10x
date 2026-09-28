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
