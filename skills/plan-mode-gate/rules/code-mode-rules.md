---
paths:
  - "**/*.js"
  - "**/*.jsx"
  - "**/*.ts"
  - "**/*.tsx"
  - "**/*.py"
  - "**/*.go"
  - "**/*.java"
  - "**/*.rs"
  - "server/**/*"
  - "client/**/*"
  - "src/**/*"
  - "app/**/*"
---

# Code Mode Rules

## Rule 1: No Code Changes Without Gates

**No code file may be created, edited, or deleted until the PLAN_GATE pre-flight checklist is complete.**

This applies to ALL source files regardless of language or framework.

## Rule 2: jcodemunch Before Implementation

Before editing ANY code:
- `plan_turn` MUST be run for task context
- `get_ranked_context` SHOULD be run for relevant code snippets
- `get_blast_radius` MUST be run when modifying existing symbols
- `get_impact_preview` MUST be run when deleting or renaming symbols

## Rule 3: Skill-Driven Implementation

Implementation MUST follow the skill identified as most relevant:
- Frontend → `frontend-design-gate` workflow
- Backend → `backend-patterns` workflow
- Bug fix → `systematic-debugging` (root cause first)
- Testing → `tdd-workflow` or `test-driven-development`
- Database → `postgres-patterns`, `jpa-patterns`, etc.

## Rule 4: Sequential Thinking for Complex Changes

`sequentialthinking` MUST be used when:
- The change touches >3 files
- The change modifies existing architecture
- The change requires coordination across modules
- The user request is vague

## Rule 5: Context7 for Library Usage

`resolve-library-id` + `query-docs` MUST be used when:
- Using a library API for the first time in the project
- Upgrading a library version
- Using an advanced or obscure API
- The library's behavior is version-sensitive

## Rule 6: TodoWrite Tracking

Multi-step implementations MUST use `TodoWrite`:
- Create todos before starting
- Mark in_progress before each step
- Mark done after verification
- Never proceed without updating status

## Rule 7: Verification Before Completion

Before declaring any task complete:
- Run `verification-before-completion` skill
- Run tests if they exist
- Check for lint errors
- Review diff for unintended changes
