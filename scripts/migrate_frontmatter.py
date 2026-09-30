#!/usr/bin/env python3
"""
migrate_frontmatter.py — one-shot, idempotent skill frontmatter migration to the
native Claude Code schema (2026-09-27).

For every targeted user-authored skill:
  * legacy custom keys (schema, triggers, surfaces, category, platforms, token-cost,
    keywords, intents, origin, requires, model-hint, links, version) move under
    ``metadata:`` (the sanctioned home; Claude Code ignores them elsewhere)
  * ``disable-model-invocation: false`` lines are dropped (no-op noise)
  * ``tools:`` becomes ``allowed-tools:`` (the real skill key)
  * native ``paths:`` globs (rule-style, any depth) and a ``when_to_use:`` line are
    added from the tables below so file-bound skills surface natively
  * inflated descriptions ("ALWAYS invoke"/"MUST use"/"MANDATORY") are replaced by a
    <=300-char statement of what the skill IS; the trigger phrasing lives in
    ``when_to_use:``
  * bogus ``triggers.paths`` on three process skills are cleared; domain vocabulary
    keywords are added where the plan calls for them

Targets: every user-authored skill EXCEPT the frontend set (WP-4 runs
``--only <dirs>`` for those), santa-review / invoke* (WP-8) and mcp-usage-standards
(WP-10). ``--only a,b`` overrides the target set. Locked (vendored) skills are never
written. Re-running is a byte-for-byte no-op. Rebuilds hooks/skills-index.json.
"""
from __future__ import annotations

import argparse
import sys

import yaml

import skills_lib as sl
from build_skills_index import LEGACY_META_KEYS, write_index

# --------------------------------------------------------------------------- #
# target selection
# --------------------------------------------------------------------------- #
FRONTEND_SET_WP4 = {
    "animejs-motion", "brand", "composition-patterns", "design", "frontend-response-handling",
    "frontend-server-data-patterns", "frontend-standards-always-follow",
    "frontend-structure-standards", "frontend-ui-engineering", "kokonutui", "motion-dev",
    "react-hooks-patterns", "shadcn", "slides", "tailwind-design-system", "ui-styling",
    "webapp-testing", "taste-skill", "threejs-r3f",
}
OTHER_OWNERS = {"santa-review", "mcp-usage-standards"}


def default_targets() -> list[str]:
    out = []
    for n in sl.user_authored_skills():
        if n in FRONTEND_SET_WP4 or n in OTHER_OWNERS or n.startswith("invoke"):
            continue
        out.append(n)
    return out


# --------------------------------------------------------------------------- #
# tables (plan WP-3 steps 7-8)
# --------------------------------------------------------------------------- #
PATHS: dict[str, list[str]] = {
    "golang-patterns": ["**/*.go", "**/go.mod"],
    "golang-testing": ["**/*_test.go"],
    "postgres-patterns": ["**/*.sql", "**/migrations/**", "**/migrate/**", "**/db/**"],
    "backend-api-standards": ["**/routes/**", "**/handlers/**", "**/controllers/**", "**/*.routes.ts"],
    "api-contract-standards": ["**/schemas/**", "**/types/**", "**/dto/**", "**/*.proto",
                               "**/openapi*.{yaml,yml,json}"],
    "backend-error-handling": ["**/errors/**", "**/middleware/**", "**/*error*.{go,ts,py}"],
    "backend-performance-standards": ["**/repository/**", "**/store/**", "**/*.sql"],
    "backend-standards-always-follow": ["**/internal/**", "**/server/**", "**/cmd/**", "**/*.go"],
    "service-layer-standards": ["**/service/**", "**/services/**"],
    "scaffold-standards": ["**/routes/**", "**/router/**"],
    "owasp-security": ["**/auth/**", "**/middleware/**", "**/*auth*.{go,ts,py}", "**/*session*.{go,ts,py}"],
    "ci-cd-and-automation": [".github/workflows/**", "**/Dockerfile*", "**/.gitlab-ci.yml", "**/Makefile"],
    "fix-lint-format": ["**/.golangci.y*ml", "**/eslint.config.*", "**/biome.json", "**/.prettierrc*"],
    "domain-modeling": ["**/CONTEXT.md", "**/docs/adr/**"],
    "dox-doc-tree": ["**/CLAUDE.md", "**/AGENTS.md"],
    "tdd-auto-init": ["**/.claude/tdd-guard/**"],
    "update-docs": ["**/docs/**", "**/*_docs/**", "**/README.md"],
    "skill-linkage-story": ["**/.claude/hooks/**", "**/.claude/agents/**", "**/.claude/skills/**"],
    "agent-development": ["**/.claude/hooks/**", "**/.claude/agents/**", "**/.claude/skills/**"],
    "command-development": ["**/.claude/hooks/**", "**/.claude/agents/**", "**/.claude/skills/**"],
    "mcp-builder": ["**/*mcp*/**"],
    "test-driven-development": ["**/*_test.go", "**/*.test.{ts,tsx}", "**/test_*.py"],
}

# Cleared: these three carried ``.claude/hooks/`` / ``.claude/rules/`` as trigger paths.
BOGUS_TRIGGER_PATHS = {"debug-investigation", "dead-code-and-change-audit", "tool-and-doc-selection"}

DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "api-contract-standards": ["openapi", "graphql", "grpc", "endpoint", "envelope"],
    "postgres-patterns": ["migration", "index", "rls"],
    "backend-api-standards": ["endpoint", "pagination", "rest"],
}

HIDE_FROM_MODEL = {"context7-mcp"}

# De-inflated descriptions (what the skill IS, <=300 chars). Trigger phrasing -> WHEN_TO_USE.
DESCRIPTIONS: dict[str, str] = {
    "agent-development":
        "Create or revise reusable agent definitions: trigger text, system prompts, tool grants and "
        "frontmatter for autonomous helpers.",
    "api-contract-standards":
        "Backend response envelopes, list metadata, error shapes, versioning, and the separation "
        "between table, card, and summary contracts.",
    "architect-system-design":
        "Architecture shell: classify the touched surfaces, decompose the system, plan interfaces "
        "and implementation order before code changes.",
    "backend-api-standards":
        "Rules for list and search endpoints: filtering, sorting, pagination, stable response "
        "shapes, and query validation.",
    "backend-error-handling":
        "Backend error taxonomy, centralized handler behavior, safe logging, redaction, and "
        "client-safe error mapping.",
    "backend-performance-standards":
        "Backend query efficiency, repeated DB work, file-size pressure, scaling risk, and safe "
        "optimization boundaries.",
    "backend-standards-always-follow":
        "Always-on backend baseline for APIs, routes, controllers, schemas, services, persistence, "
        "auth, validation, workers, queues, and integrations.",
    "caveman":
        "Ultra-compressed communication mode for user-facing text only: drops filler, articles and "
        "pleasantries (~75% fewer tokens) while keeping full technical accuracy. Never affects code "
        "output, reasoning, routing, or subagent prompts.",
    "code-review-and-quality":
        "Multi-axis code review (correctness, design, security, performance, maintainability) with "
        "quality gates before a change enters the main branch.",
    "code-simplification":
        "Simplifies working code for clarity without changing behavior: removes accidental "
        "complexity, dead flexibility, and over-abstraction.",
    "codebase-intel-first":
        "Code intelligence first: build a structural model with the jcodemunch symbol index and "
        "graphify graph before reading files, grepping, or spawning Explore agents. Defines the "
        "precedence between jcodemunch/graphify (discovery) and lean-ctx (residual file I/O).",
    "command-development":
        "Create or update command definitions: frontmatter, arguments, and reusable command workflows.",
    "context-engineering":
        "Optimizes agent context setup: rules files, project context layout, compaction points, and "
        "what to load when.",
    "context7-mcp":
        "Pointer: fetch current library/framework docs through the Context7 MCP "
        "(resolve-library-id, then query-docs). The full procedure lives in rules/context7.md.",
    "dead-code-and-change-audit":
        "Change-scoped hygiene audit: dead code, stale references, orphaned logic, unused imports "
        "and files, broken linkages, and partial refactors left behind by a change.",
    "debug-investigation":
        "Evidence-first debugging: reproduce, classify the failing surface, form hypotheses, and "
        "demonstrate the root cause before proposing a fix.",
    "doubt-driven-development":
        "Fresh-context adversarial review of non-trivial decisions before they stand; cheaper to "
        "verify now than to debug later.",
    "dox-doc-tree":
        "Establishes and maintains the dox CLAUDE.md documentation tree: read root to target before "
        "editing, follow local rules, update the local CLAUDE.md after edits.",
    "eval-harness":
        "Eval-driven development for Claude Code sessions: pass/fail criteria, pass@k reliability "
        "metrics, and regression suites for prompt or agent changes.",
    "git-workflow-and-versioning":
        "Git workflow practices: atomic commits, branching, conflict resolution, and organizing "
        "parallel streams of work.",
    "golang-patterns":
        "Idiomatic Go: error wrapping, interface design, package layout, concurrency safety, and "
        "common review pitfalls.",
    "golang-testing":
        "Go testing: table-driven tests, benchmarks, fuzz targets, test helpers, and coverage review.",
    "graphify":
        "Knowledge graph over code, docs, papers, images and video: god nodes, community detection, "
        "and query/path/explain tools. Architecture questions become graph queries when "
        "graphify-out/ exists.",
    "grill-with-docs":
        "Stress-tests a plan against the project's domain language and documented decisions, "
        "sharpens terminology, and updates CONTEXT.md/ADRs inline as decisions crystallise.",
    "idea-refine":
        "Refines ideas through structured divergent and convergent thinking.",
    "lean-ctx":
        "Optional lean-ctx ctx_* MCP tools for compressed non-code reads, shell output, and "
        "directory trees. Source-code discovery and reading go to jcodemunch first.",
    "owasp-security":
        "Security review and hardening: OWASP Top 10:2025, ASVS 5.0, LLM Top 10 (2025), and "
        "Agentic AI security (2026) across auth, input handling, sessions, and secrets.",
    "plan-mode-gate":
        "Pre-flight gate for planning and implementation: superpowers discipline, jcodemunch "
        "codebase analysis, sequential-thinking decomposition, and Context7 lookup before code "
        "changes.",
    "planning-and-task-breakdown":
        "Breaks a spec or clear requirements into ordered, implementable, verifiable tasks with "
        "scope estimates.",
    "postgres-patterns":
        "PostgreSQL queries, schema design, indexes, migrations, and row-level security with "
        "prepared statements; query efficiency and index coverage.",
    "project-reference-linkage":
        "Cross-module navigation: how components, hooks, API layers, controllers, routes, schemas, "
        "and store slices link across a project.",
    "scaffold-standards":
        "Minimum skeleton for a new backend or full-stack domain: route/controller/service/schema "
        "files and a standard list/CRUD feature structure per stack.",
    "service-layer-standards":
        "Service-layer rules for backend business logic: boundaries between routes, controllers, "
        "services, and persistence; where validation and transactions live.",
    "skill-linkage-story":
        "How skills reach the model in this setup: dispatch.py events, the prompt router, native "
        "paths: activation, write-time reminders, and stop gates.",
    "source-driven-development":
        "Grounds implementation decisions in official documentation (Context7 and upstream "
        "sources) so code is source-cited and free of outdated patterns.",
    "tdd-auto-init":
        "Operates the auto-initialized tdd-guard: per-project config, stack detection "
        "(Go/Vitest/Jest/pytest), reporter wiring, warn mode, pause/force/troubleshoot.",
    "tech-debt-audit":
        "Whole-repo tech debt and architecture audit producing TECH_DEBT_AUDIT.md with file-cited "
        "findings, severity, effort, and a 'looks bad but is fine' section. User-invoked; does not "
        "auto-fire.",
    "test-driven-development":
        "Red-green-refactor: write the failing test first, make it pass, then refactor, with "
        "language-specific test conventions.",
    "to-issues":
        "Breaks a plan, spec, or PRD into independently-grabbable issues on the project tracker "
        "using tracer-bullet vertical slices.",
    "to-prd":
        "Turns the current conversation context into a PRD and publishes it to the project issue "
        "tracker.",
    "tool-and-doc-selection":
        "Chooses the right source of truth (workspace files, local docs, installed doc tools, MCP "
        "integrations, or web search) and keeps evidence retrieval disciplined.",
    "triage":
        "Triages issues through a state machine driven by triage roles: intake, classification, "
        "and preparation for an AFK agent.",
    "update-docs":
        "Documentation lifecycle: read repo docs before substantive coding (Phase A) and sync "
        "Markdown/MDX, changelogs, READMEs, and PR docs after implementation (Phase B). "
        "Stack-neutral; Next.js monorepo mapping in references/.",
    "using-agent-skills":
        "Meta-skill: how to discover which skill applies to the current task and invoke it before "
        "starting work.",
    "verification-loop":
        "Verification before claiming done: run the real build, tests, lint, and checks and read "
        "the output. Evidence before assertions.",
    "workflow-orchestrator":
        "Coordination shell for multi-phase work: identifies touched surfaces and routes each phase "
        "to Architect, Code, or Debug mode with explicit ownership and quality gates.",
}

WHEN_TO_USE: dict[str, str] = {
    "agent-development": "Use when adding or editing files under .claude/agents/ or writing an agent's description or prompt.",
    "api-contract-standards": "Use when defining or reviewing an API contract: envelope, pagination metadata, error shape, OpenAPI/GraphQL/gRPC schema, DTO or shared types.",
    "architect-system-design": "Use when the task is design, decomposition, interface planning, or an implementation plan that precedes coding.",
    "backend-api-standards": "Use when adding or changing a REST endpoint, route handler, or controller, especially list/search with pagination.",
    "backend-error-handling": "Use when defining error types, middleware error handlers, logging or redaction, or how errors map to HTTP responses.",
    "backend-performance-standards": "Use when reviewing repositories, stores, SQL, or hot paths for N+1 queries, missing indexes, or scaling risk.",
    "backend-standards-always-follow": "Use for any backend or server-side task (planning, implementing, debugging, reviewing) before the other backend skills.",
    "caveman": "Always active for user-facing prose; no trigger phrase needed.",
    "ci-cd-and-automation": "Use when creating or changing CI/CD pipelines, Dockerfiles, Makefiles, or deployment automation.",
    "code-review-and-quality": "Use when reviewing code written by you, another agent, or a human, or before merging any change.",
    "code-simplification": "Use when code works but is harder to read, maintain, or extend than it should be, or a review flags unnecessary complexity.",
    "codebase-intel-first": "Use at the start of any codebase task: planning, auditing, review, implementing, refactoring, debugging, or 'help me understand X'.",
    "command-development": "Use when adding or editing .claude/commands/ or turning a command into a skill.",
    "context-engineering": "Use when starting on a new project, when output quality degrades, when switching tasks, or when configuring CLAUDE.md/rules for a repo.",
    "context7-mcp": "Not model-invoked; the always-on rules/context7.md already routes library questions to Context7.",
    "dead-code-and-change-audit": "Use after any code change to audit what the diff orphaned; deletions stay scoped to your own changes.",
    "debug-investigation": "Use when the cause of a bug, regression, crash, or unexpected behavior is unknown.",
    "domain-modeling": "Use when pinning down domain terminology, recording an architectural decision, or editing CONTEXT.md / docs/adr.",
    "doubt-driven-development": "Use when correctness matters more than speed: unfamiliar code, production or security-sensitive logic, irreversible operations.",
    "dox-doc-tree": "Use when a repo's CLAUDE.md tree is missing or stubbed, when scaffolding project docs, or before editing code in an undocumented directory.",
    "eval-harness": "Use when defining or running evaluations of agent behavior, prompts, or skills.",
    "fix-lint-format": "Use on lint errors, formatting failures, CI red on style checks, or before committing; also when editing linter/formatter configs.",
    "git-workflow-and-versioning": "Use when committing, branching, rebasing, resolving conflicts, or planning parallel work streams.",
    "golang-patterns": "Use when writing, reviewing, or refactoring any .go file in a service or CLI.",
    "golang-testing": "Use before creating or modifying any _test.go file, or when reviewing Go test coverage.",
    "graphify": "Use for questions about a codebase's architecture, file relationships, or project content, especially when graphify-out/ is present.",
    "grill-with-docs": "Use when the user wants a plan grilled against existing docs and the domain model before implementation.",
    "idea-refine": "Use when the user says 'idea-refine' or 'ideate', or a need is too vague to spec.",
    "lean-ctx": "Use for residual non-code file I/O, compressed shell output, or directory maps when the lean-ctx MCP server is connected.",
    "mcp-builder": "Use when building or changing an MCP server (FastMCP or the TypeScript SDK) or its tool definitions.",
    "owasp-security": "Use when reviewing for vulnerabilities, implementing authentication/authorization, handling user input, or touching auth, session, or middleware files.",
    "plan-mode-gate": "Use before entering plan mode, before writing a plan, and before direct implementation of a multi-file change.",
    "planning-and-task-breakdown": "Use when a task feels too large to start, when scope needs estimating, or when parallel work is possible.",
    "postgres-patterns": "Use when writing SQL, designing schemas, creating indexes, or reviewing migration files.",
    "project-reference-linkage": "Use when you need the directory structure and cross-layer relationships of a repo before changing a shared surface.",
    "scaffold-standards": "Use when scaffolding a new domain, route, controller, service, or schema, or a standard CRUD feature.",
    "service-layer-standards": "Use when adding or changing code under service/ or services/, or deciding where business logic lives.",
    "skill-linkage-story": "Use when onboarding to this ~/.claude config or debugging a skill reminder that did not appear.",
    "source-driven-development": "Use when building with a framework or library where API correctness matters.",
    "tdd-auto-init": "Use when tdd-guard is not activating (or fires where it should not), when adding a test stack or reporter, or when a TDD advisory appears.",
    "tech-debt-audit": "Use only when the user asks for a debt audit, codebase health check, or architecture review of an entire repo.",
    "test-driven-development": "Use when implementing logic, fixing a bug, or changing behavior that needs proof it works.",
    "to-issues": "Use when the user wants a plan converted into issues or implementation tickets.",
    "to-prd": "Use when the user asks for a PRD from the current context.",
    "tool-and-doc-selection": "Use when deciding which docs or tools to consult for a task, before reaching for web search.",
    "triage": "Use when the user wants to create, triage, or prepare issues, or review incoming bugs and feature requests.",
    "update-docs": "Use when asked what docs a change affects, to sync docs with code, to scaffold docs for a feature, or when editing docs/, *_docs/, or README files.",
    "using-agent-skills": "Use at session start or whenever you are unsure which skill applies.",
    "verification-loop": "Use before claiming any work complete, fixed, or passing.",
    "workflow-orchestrator": "Use when work spans multiple phases, domains, or specialist roles.",
}

# --------------------------------------------------------------------------- #
# frontmatter transform + ordered dump
# --------------------------------------------------------------------------- #
_NATIVE_ORDER = [
    "name", "description", "when_to_use", "argument-hint", "arguments",
    "disable-model-invocation", "user-invocable", "allowed-tools", "disallowed-tools",
    "model", "effort", "context", "agent", "background", "paths", "shell", "hooks",
    "license", "compatibility", "metadata",
]
_META_ORDER = ["schema", "category", "surfaces", "platforms", "token-cost", "origin",
               "requires", "model-hint", "links", "triggers", "version"]


def _ordered(d: dict, order: list[str]) -> dict:
    out = {k: d[k] for k in order if k in d}
    out.update({k: d[k] for k in sorted(d) if k not in out})
    return out


def dump(fm: dict, body: str) -> str:
    fm = dict(fm)
    if isinstance(fm.get("metadata"), dict):
        fm["metadata"] = _ordered(fm["metadata"], _META_ORDER)
    dumped = yaml.dump(_ordered(fm, _NATIVE_ORDER), sort_keys=False, default_flow_style=False,
                       allow_unicode=True, width=4096)
    return f"---\n{dumped}---\n{body}"


def migrate_fm(name: str, fm: dict) -> dict:
    fm = dict(fm)
    meta = dict(fm.get("metadata") or {}) if isinstance(fm.get("metadata"), dict) else {}
    for k in LEGACY_META_KEYS:
        if k in fm:
            meta.setdefault(k, fm.pop(k))
    if fm.get("disable-model-invocation") in (False, "false"):
        del fm["disable-model-invocation"]
    if "tools" in fm:
        fm["allowed-tools"] = fm.pop("tools")
    if name in HIDE_FROM_MODEL:
        fm["disable-model-invocation"] = True
    if name in PATHS:
        fm["paths"] = list(PATHS[name])
    if name in DESCRIPTIONS:
        fm["description"] = DESCRIPTIONS[name]
    if name in WHEN_TO_USE:
        fm["when_to_use"] = WHEN_TO_USE[name]
    trig = meta.get("triggers") if isinstance(meta.get("triggers"), dict) else None
    if name in BOGUS_TRIGGER_PATHS and trig is not None:
        trig["paths"] = []
    if name in DOMAIN_KEYWORDS:
        trig = trig if trig is not None else {}
        trig["keywords"] = sorted(set(trig.get("keywords") or []) | set(DOMAIN_KEYWORDS[name]))
        meta["triggers"] = trig
    if meta:
        fm["metadata"] = meta
    return fm


def migrate(targets: list[str], dry: bool = False) -> tuple[int, list[str]]:
    locked = sl.locked_skills()
    edited = 0
    skipped: list[str] = []
    for name in targets:
        d = sl.SKILLS_DIR / name
        if name in locked or not (d / "SKILL.md").exists():
            skipped.append(name)
            continue
        fm, body, ok = sl.read_frontmatter(d / "SKILL.md")
        if not ok:
            skipped.append(f"{name} (unreadable frontmatter)")
            continue
        new_content = dump(migrate_fm(name, fm), body)
        current = (d / "SKILL.md").read_text(encoding="utf-8")
        if new_content == current:
            continue
        if not dry:
            (d / "SKILL.md").write_text(new_content, encoding="utf-8", newline="\n")
        edited += 1
        print(f"  migrated {name}")
    return edited, skipped


def _self_check() -> None:
    too_long = {k: len(v) for k, v in DESCRIPTIONS.items() if len(v) > 300}
    assert not too_long, f"descriptions over 300 chars: {too_long}"
    import re
    shouting = [k for k, v in DESCRIPTIONS.items() if re.search(r"\b(ALWAYS|MUST|MANDATORY)\b", v)]
    assert not shouting, f"inflated descriptions: {shouting}"
    assert all(isinstance(p, str) and "~" not in p for ps in PATHS.values() for p in ps)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated skill dir names (overrides the default target set)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-index", action="store_true", help="skip the skills-index rebuild")
    args = ap.parse_args()
    _self_check()
    targets = [t.strip() for t in args.only.split(",") if t.strip()] if args.only else default_targets()
    edited, skipped = migrate(targets, dry=args.dry_run)
    print(f"targets: {len(targets)}  edited: {edited}  unchanged: {len(targets) - edited - len(skipped)}"
          f"  skipped: {skipped or 0}{'  (dry-run)' if args.dry_run else ''}")
    if not args.dry_run and not args.no_index:
        payload = write_index()
        m = payload["_meta"]
        print(f"skills-index.json: {m['skill_count']} local + {m['plugin_count']} plugin skills")
    return 0


if __name__ == "__main__":
    sys.exit(main())
