# Agent Lifecycle Routing — Phase → Skill → Hook Map

Canonical reference for mandatory phases 0–7, **28 FE / 27 BE** enforcement, and hook injection points.

See also: [`plan-exec-unified-stack.md`](plan-exec-unified-stack.md), [`skill-linkage-story`](../skills/skill-linkage-story/SKILL.md), [`PRESERVE-AND-STRENGTHEN.md`](../docs/PRESERVE-AND-STRENGTHEN.md).

## Phase → Hook → Skill

> **Authority note:** Phase 0–7 lifecycle steps are defined exclusively in `mandatory-skill-protocol.mdc`. This table maps phases to hooks and skills only — it does not define lifecycle steps. For the authoritative Phase 0 procedure, see `mandatory-skill-protocol.mdc § PHASE 0`.

> **Dispatch reality (100x overhaul):** the hooks named below are no longer 65 separate `settings.json` registrations — they run as **links inside 8 `dispatch.py <event>` orchestrators** (one per Claude Code event), declared in `hooks/dispatch.config.json` with per-link isolation, telemetry, and enable flags. The hook *names* below still identify the logic (each keeps its own file, Charter §3); only the registration shape changed. Prompt-time skill injection is handled **LIVE** by `hooks/prompt_router/router.py` (settings.json UserPromptSubmit; user-directed flip 2026-07-12). The legacy injector chain is retained only for flip-back (`flip-dispatch.py --legacy`); the router is a provable superset (consumes the entire `trigger-floor.json`). See `hooks/README.md`.

| Phase | Hooks | Primary skills |
|-------|-------|----------------|
| **0 Session** | `session-start-aggregator`, `session-lifecycle`, `jcodemunch-index-guard`, `graphify-index-guard` | `codebase-start-point-guide`, `using-agent-skills`, Superpowers `using-superpowers` |
| **1 Plan** | `session-plan-gate-hint`, `ui-ux-stack-orchestrator` (beforeSubmit) | `workflow-orchestrator` → `plan-mode-gate` → GSD or Superpowers planning chain |
| **2–3 Code** | `fullstack-skills-reminder` (first Write + session manifest), `skill_router` (path-ranked + cross_cutting), `ui-ux-stack-orchestrator` (six-skill UI) | All **28 FE / 27 BE** slugs in `fullstack-skills-reminder.py`; manifest batches pending skills on later writes |
| **4 Dead code** | `post-write-aggregator` → `desloppify-cleanup` @8 writes | `dead-code-and-change-audit` — **your changes only** for deletes |
| **5 Lint/security** | `security-scan-gate`, Semgrep via Shell | `owasp-security`, `security-and-hardening`, `fix-lint-format` |
| **6 Review** | `santa-method-writer` (Task code-reviewer), stop re-verify | `code-review-and-quality`, Superpowers review skills |
| **7 Docs** | `post-write-aggregator` → `doc-update-enforcer`, `blocking-doc-enforcer`, Gate 2 (repo-aware) | `update-docs`, `project-reference-linkage` |

## Frontend mandatory skills (28)

Source: `~/.claude/hooks/fullstack-skills-reminder.py` → `FRONTEND_SKILLS`.

| Skill | Router rule ID(s) |
|-------|-------------------|
| agent-development | fe_default | (no skill_router route — map-only) |
| api-contract-standards | fe_types |
| dead-code-and-change-audit | cross_cutting always |
| debug-investigation | cross_cutting debug |
| domain-scaffold-patterns | fe_routes |
| frontend-api-standards | fe_api |
| frontend-code-review | fe_default |
| frontend-response-handling | fe_api (MUST-READ) |
| frontend-server-data-patterns | fe_api, fe_hooks |
| frontend-standards-always-follow | fe_default, fe_component_tsx |
| frontend-structure-standards | fe_store_redux, fe_routes |
| project-reference-linkage | cross_cutting first_write |
| project-structure-map | cross_cutting first_write | (no skill_router route — map-only) |
| react-hooks-patterns | fe_hooks, fe_component_tsx |
| scaffold-standards | fe_routes |
| tailwind-design-system | fe_component_tsx, fe_vite_config |
| tool-and-doc-selection | be_cursor_infra | (no skill_router route — map-only) |
| webapp-testing | fe_test |
| architect-system-design | cross_cutting first_write |
| mcp-usage-standards | session MCP roster |
| owasp-security | fe_auth |
| doubt-driven-development | cross_cutting debug |
| iterative-retrieval | manual / plan-mode-gate |
| verification-loop | cross_cutting verification |
| frontend-ui-engineering | fe_ui_design |
| vite-react-best-practices | fe_vite_config |
| browser-testing-with-devtools | fe_test |
| design-extract | fe_ui_design |

## Backend mandatory skills (27)

Source: `BACKEND_SKILLS` in same hook file.

| Skill | Router rule ID(s) |
|-------|-------------------|
| backend-api-standards | be_controller, be_route, be_schema |
| api-contract-standards | be_contract (MUST-READ) |
| backend-code-review | be_default |
| backend-error-handling | be_service, be_middleware |
| backend-performance-standards | be_review_perf, be_test |
| backend-standards-always-follow | be_default, be_go_file |
| dead-code-and-change-audit | cross_cutting always |
| debug-investigation | be_debug, cross_cutting debug |
| domain-scaffold-patterns | be_model |
| project-reference-linkage | cross_cutting first_write |
| project-structure-map | cross_cutting first_write | (no skill_router route — map-only) |
| scaffold-standards | be_route, be_schema |
| service-layer-standards | be_service, be_controller |
| tool-and-doc-selection | be_cursor_infra | (no skill_router route — map-only) |
| architect-system-design | cross_cutting first_write |
| mcp-usage-standards | session MCP roster |
| owasp-security | be_middleware |
| doubt-driven-development | be_debug |
| forensic-complexity-trends | be_review_perf |
| forensic-debt-quantification | be_review_perf |
| eval-harness | manual / GSD eval phases |
| source-driven-development | be_go_file, cross_cutting implementation |
| golang-patterns | be_go_file |
| golang-testing | be_go_test |
| postgres-patterns | be_migration |
| api-and-interface-design | greenfield only (see harmonization doc) |
| security-and-hardening | be_middleware, SECURITY intent |

## Stop gate summary

`hard-completion-gate.py`: Gate 2 docs (hard), Gate 3 security (semi-hard when auth files touched), Gate 4 Santa (semi-hard @3+ writes, skipped for infra-only `.claude/` sessions).

## Agent wiring (infrastructure, non-sequential)

> Note: this section describes infrastructure agent wiring, not a sequential lifecycle phase. The lifecycle is Phases 0–7 only (defined in `mandatory-skill-protocol.mdc`). "Phase 11" numbering below is legacy and does not imply phases 8–10 exist.

| Flow | Agent | Skill |
|------|-------|-------|
| Codebase map → intel | `gsd-codebase-mapper` → **`gsd-intel-updater`** | `gsd-map-codebase`, `gsd-graphify` |
| UI polish (ad-hoc) | `frontend-uiux-designer` | Six-skill UI stack |
| UI phase (GSD) | `gsd-ui-researcher`, `gsd-ui-auditor` | `gsd-ui-phase`, `gsd-ui-review` |
| Figma | `figma-implementation`, `figma-code-connect` | When Figma URL present |
| Vercel | `vercel-ai-architect`, `vercel-deployment-expert` | Deploy/architecture prompts |

Full table: `~/.claude/agents/README.md`.
