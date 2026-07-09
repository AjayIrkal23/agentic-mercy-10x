# Skill Harmonization — Precedence (All Skills Kept)

Document when overlapping skills fire. **Do not delete** — router and hooks select by context.

## TDD cluster

| Skill | When |
|-------|------|
| `tdd` | Router on `fe_test` / `be_test` paths; local red-green-refactor |
| Superpowers `test-driven-development` | Active Superpowers planning/build path |
| `test-driven-development` (skills/) | Explicit user TDD request |

## Debug cluster

| Skill | When |
|-------|------|
| `investigate` (gstack) | Proactive root-cause on production/live issues |
| `diagnose` | Structured diagnose loop keyword trigger |
| `debug-investigation` | Mandatory hook cross_cutting + router `be_debug` |
| Superpowers `systematic-debugging` | Superpowers debug path |

## QA cluster

| Skill | When |
|-------|------|
| `webapp-testing` | FE test files and Playwright flows |
| `qa` / `qa-only` (gstack) | Full ship / report-only site QA |
| `browser-testing-with-devtools` | DevTools MCP debugging |

## Plan cluster (complementary — do not collapse)

| Layer | Skill / hook | When |
|-------|----------------|------|
| 1 | `workflow-orchestrator` | Surfaces BE/FE/fullstack, phase map |
| 2 | `plan-mode-gate` | PLAN_GATE checklist when planning or >2 files |
| 3a | GSD chain | `.planning/` active → discuss → plan → execute |
| 3b | Superpowers | Greenfield → brainstorming → writing-plans |
| 3c | `architect-system-design` | Contract / architecture before code |
| Coding | Phases 2–3 after user approval | Agent mode |
| Post | Phases 4–7 sequential | After every coding task |

**Plan / Ask:** jcodemunch and Read/Grep are **never hard-blocked** for exploration.  
**Agent coding:** prefer jcodemunch symbols; enforce after plan approval.

See [`plan-exec-unified-stack.md`](../rules/plan-exec-unified-stack.md).

## Mandatory FE/BE coverage (hooks)

| Mechanism | Behavior |
|-----------|----------|
| `skill_router` | Path-ranked primary skills (`max_primary_skills_by_rule`; UI rule uses 6) |
| `fullstack-skills-reminder` | First Write per surface + **session manifest** batches remaining **28 FE / 27 BE** slugs |
| Stop hook | Re-verify all slugs touched this session |

`manifest_mode: true` in `skill_router.config.json` — not "top-3 only."

## API contract cluster

| Skill | When |
|-------|------|
| `api-contract-standards` | **Canonical** envelope — BE router `be_contract`, FE `fe_types` |
| `backend-api-standards` | List/search endpoint rules |
| `api-and-interface-design` | Greenfield API design only |

## Security cluster

| Skill | When |
|-------|------|
| `owasp-security` | Auth/API changes; Gate 3 semgrep |
| `security-and-hardening` | Middleware/auth paths |
| `cso` (gstack) | "security audit" / CSO review intents |

## Discovery filter

`~/.cursor/skills/.skill-routing.json` — set `all_active: false` to reduce discovery noise. **Mandatory FE/BE lists in hooks are unaffected.**
