# Agent Lifecycle Routing — Phase → Skill → Hook Map

Reference (moved from `rules/` 2026-09-27). Phase → hook → skill map for phases 0–7, FE/BE skill-set enforcement, and hook injection points.

See also: skill `skill-linkage-story`; `~/.claude/rules/02-lifecycle.md`.

## Phase → Hook → Skill

> **Authority note:** Phase 0–7 lifecycle steps are defined in `~/.claude/rules/02-lifecycle.md`. This table maps phases to hooks and skills only — it does not define lifecycle steps.

> **Dispatch reality (100x overhaul):** the hooks named below are no longer separate `settings.json` registrations — they run as **links inside the `dispatch.py <event>` orchestrators** (one per Claude Code event), declared in `hooks/dispatch.config.json` with per-link isolation, telemetry, and enable flags. The hook *names* below still identify the logic (each keeps its own file, Charter §3); only the registration shape changed. Prompt-time skill injection is handled by `hooks/prompt_router/router.py` (UserPromptSubmit). See `hooks/README.md`.

| Phase | Hooks | Primary skills |
|-------|-------|----------------|
| **0 Session** | `session-start-aggregator`, `session-lifecycle`, `index-lifecycle` (jcodemunch/graphify/jdocmunch freshness) | `codebase-intel-first`, `using-agent-skills`, Superpowers `using-superpowers` |
| **1 Plan** | prompt router (plan intent) | `workflow-orchestrator` → `plan-mode-gate` → Superpowers planning chain |
| **2–3 Code** | `fullstack-skills-reminder` (first Write + session manifest), `skill_router` (path-ranked + cross_cutting) | The FE/BE slugs in `fullstack-skills-reminder.py`; manifest batches pending skills on later writes |
| **4 Dead code** | `post-write-aggregator` → `desloppify-cleanup` @8 writes | `dead-code-and-change-audit` — **your changes only** for deletes |
| **5 Lint/security** | `security-scan-gate`, Semgrep via Shell | `owasp-security`, `fix-lint-format` |
| **6 Review** | `santa-reviewer` agent (Santa Method — `/santa-review`), `santa-method-writer` (flag), stop re-verify | `santa-review`, `code-review-and-quality`, Superpowers review skills |
| **7 Docs** | `post-write-aggregator` → `doc-update-enforcer`, `blocking-doc-enforcer`, Gate 2 (repo-aware) | `update-docs`, `project-reference-linkage` |

## Frontend and backend skill sets

The write-time baselines are the `FRONTEND_SKILLS` and `BACKEND_SKILLS` tuples in
`~/.claude/hooks/fullstack-skills-reminder.py`; that file is the only source of truth
(this doc used to copy them and drifted). Native `paths:` frontmatter on each skill
surfaces the rest when a matching file is read. Print the current sets with:

```bash
python3 -c "import importlib.util as u; s=u.spec_from_file_location('f','$HOME/.claude/hooks/fullstack-skills-reminder.py'); m=u.module_from_spec(s); s.loader.exec_module(m); print(m.FRONTEND_SKILLS, m.BACKEND_SKILLS, sep='\n')"
```

## Stop gate summary

`hard-completion-gate.py`: Gate 2 docs (hard), Gate 3 security (semi-hard when auth files touched), Gate 4 Santa (semi-hard @3+ writes, skipped for infra-only `.claude/` sessions).

## Agent wiring (infrastructure, non-sequential)

> Note: this section describes infrastructure agent wiring, not a sequential lifecycle phase. The lifecycle is Phases 0–7 only (defined in `~/.claude/rules/02-lifecycle.md`).

| Flow | Agent | Skill |
|------|-------|-------|
| UI polish (ad-hoc) | `frontend-uiux-designer` | Six-skill UI stack |

Full table: `~/.claude/agents/README.md`.
