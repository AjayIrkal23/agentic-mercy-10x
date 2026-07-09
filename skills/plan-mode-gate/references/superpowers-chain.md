# Superpowers Skill Chain Reference

## Process Skills (Invoke First)

| Skill | Trigger | When to Use |
|-------|---------|-------------|
| `using-superpowers` | EVERY session | Before ANY action. Skill discipline. |
| `brainstorming` | New features, UI, components | Before plan writing. Get design approval. |
| `systematic-debugging` | Bugs, errors, failures | Before proposing fixes. Find root cause. |
| `writing-plans` | Multi-step tasks | After design approval. Create bite-sized plan. |
| `executing-plans` | Have written plan | Inline execution with checkpoints. |
| `subagent-driven-development` | Have written plan, independent tasks | Fresh subagent per task + two-stage review. |
| `strategic-compact` | Long sessions, multi-phase | Compact at logical boundaries. |
| `verification-before-completion` | Before declaring done | Run verification loop. |
| `finishing-a-development-branch` | All tasks complete | Merge, PR, or cleanup options. |

## Domain Skills (Invoke Second)

| Skill | Trigger | When to Use |
|-------|---------|-------------|
| `frontend-design-gate` | ANY frontend work | Enforces design skills consultation. |
| `ui-ux-pro-max` | UI components, pages | Design system, accessibility, patterns. |
| `impeccable` | Design, audit, polish | Production-grade interface craft. |
| `huashu-design` | Visual exploration, prototypes | HTML-based hi-fi design, motion. |
| `ui-styling` | shadcn/ui implementation | Component implementation with Tailwind. |
| `backend-patterns` | API, server, database | Backend architecture and patterns. |
| `tdd-workflow` | New features, bug fixes | Test-driven development with 80%+ coverage. |
| `postgres-patterns` | PostgreSQL work | Query optimization, schema design. |
| `python-patterns` | Python code | Pythonic idioms and best practices. |
| `golang-patterns` | Go code | Idiomatic Go patterns. |
| `springboot-patterns` | Java Spring Boot | REST API, layered services, caching. |
| `django-patterns` | Django apps | ORM, signals, middleware. |

## Execution Flow

```
User Request
    ↓
plan-mode-gate (this skill)
    ↓
using-superpowers
    ↓
Process skill (brainstorming / systematic-debugging / writing-plans)
    ↓
Domain skill (frontend-design-gate / backend-patterns / tdd-workflow)
    ↓
Execution skill (executing-plans / subagent-driven-development)
    ↓
Verification skill (verification-before-completion)
    ↓
Finishing skill (finishing-a-development-branch)
```

## Quick Trigger Table

| User Says | Process Skill | Domain Skill |
|-----------|---------------|--------------|
| "Build a dashboard" | brainstorming → writing-plans | frontend-design-gate |
| "Fix this bug" | systematic-debugging | (domain-specific) |
| "Add auth" | brainstorming → writing-plans | backend-patterns + security |
| "Refactor this" | writing-plans | (domain-specific) |
| "Make it look better" | brainstorming | impeccable + ui-ux-pro-max |
| "Add tests" | tdd-workflow | (domain-specific) |
| "Deploy this" | writing-plans | deployment-patterns |
