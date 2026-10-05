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
| `context-engineering` | Long sessions, multi-phase | Compact at logical boundaries. |
| `verification-before-completion` | Before declaring done | Run verification loop. |
| `finishing-a-development-branch` | All tasks complete | Merge, PR, or cleanup options. |

## Domain Skills (Invoke Second)

| Skill | Trigger | When to Use |
|-------|---------|-------------|
| `frontend-standards-always-follow` | ANY frontend work | Web frontend baseline; names the companions to load. |
| `frontend-ui-engineering` | UI components, pages | Design system, accessibility, patterns. |
| `frontend-design:frontend-design` | Design, audit, polish | Production-grade interface craft. |
| `design-taste-frontend` | Landing pages, redesigns | Anti-template visual direction. |
| `ui-styling` | shadcn/ui implementation | Component implementation with Tailwind. |
| `expo-react-native` | React Native / Expo screens | Mobile routes, styling, native modules. |
| `backend-standards-always-follow` | API, server, database | Backend baseline; names the companions to load. |
| `test-driven-development` | New features, bug fixes | Failing test first, then minimal code. |
| `postgres-patterns` | PostgreSQL work | Query optimization, schema design. |
| `mongoose-patterns` | Mongoose / MongoDB work | Lean reads, indexes, aggregation. |
| `golang-patterns` | Go code | Idiomatic Go patterns. |

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
Domain skill (frontend-standards-always-follow / backend-standards-always-follow / test-driven-development)
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
| "Build a dashboard" | brainstorming → writing-plans | frontend-standards-always-follow |
| "Fix this bug" | systematic-debugging | (domain-specific) |
| "Add auth" | brainstorming → writing-plans | backend-standards-always-follow + owasp-security |
| "Refactor this" | writing-plans | code-simplification |
| "Make it look better" | brainstorming | frontend-design:frontend-design + design-taste-frontend |
| "Add tests" | test-driven-development | (domain-specific) |
| "Deploy this" | writing-plans | ci-cd-and-automation, shipping-and-launch |
