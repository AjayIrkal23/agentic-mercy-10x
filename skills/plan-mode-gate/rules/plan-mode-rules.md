---
paths:
  - "**/*.md"
  - "docs/superpowers/plans/**"
  - "docs/superpowers/specs/**"
  - "plan-*.md"
---

# Plan Mode Rules

## Rule 1: No Plan Without Gates

**No plan may be written or approved until the PLAN_GATE pre-flight checklist is complete.**

This applies to:
- Any `.md` file in `docs/superpowers/plans/`
- Any `.md` file in `docs/superpowers/specs/`
- Any `plan-YYYY-MM-DD-*.md` file at the project root
- Any plan file created via `EnterPlanMode`
- Any design document created via `brainstorming`

## Rule 2: Mandatory Skill Chain

When `EnterPlanMode` is called, the following skill chain MUST be invoked in order:

1. `plan-mode-gate` (this skill)
2. `using-superpowers`
3. `brainstorming` (if creative work)
4. `systematic-debugging` (if bug fix)
5. `writing-plans`
6. `executing-plans` or `subagent-driven-development`

## Rule 3: jcodemunch Before Planning

Before writing ANY plan:
- `plan_turn` MUST be run for task-oriented planning context
- `assemble_task_context` MUST be run for auto-extracted relevant code
- `get_repo_health` SHOULD be run for codebase state awareness
- Results MUST be referenced in the plan's "Context" section

## Rule 4: Sequential Thinking Threshold

`sequentialthinking` MUST be used when:
- The plan touches >5 files
- The plan spans >3 subsystems
- The user request is vague or underspecified
- Architecture decisions are required

## Rule 5: Context7 for External Libraries

`resolve-library-id` + `query-docs` MUST be used for:
- Any dependency in package.json involved in the task
- Any framework or library mentioned by the user
- Any API whose behavior is uncertain

## Rule 6: Plan Quality Standards

Every plan MUST:
- Start with exact file paths
- Contain complete code in every step (no "add error handling" without code)
- Include exact commands with expected output
- Have no placeholders ("TBD", "TODO", "implement later")
- Include verification steps after each task
- Pass self-review: spec coverage, placeholder scan, type consistency

## Rule 7: Brainstorming Hard Gate

For creative work (new features, UI, components):
- Brainstorming MUST complete BEFORE plan writing
- User MUST approve design BEFORE plan writing
- Design doc MUST be saved before transitioning to `writing-plans`

## Rule 8: Dual Plan Save (Project Root + Docs)

Every plan document MUST be saved to two locations:

1. **Project root (primary):** `<project-root>/plan-YYYY-MM-DD-<feature-name>.md`
2. **Docs directory (secondary):** `docs/superpowers/plans/YYYY-MM-DD-<feature-name>.md`

Both saves use the same `<feature-name>` slug. The root save is the primary artifact and is committed with the project. The docs save is the organized archive copy.

**Failure to write the root plan file is a rule violation.** The PLAN_GATE pre-flight is not complete until both files exist.
