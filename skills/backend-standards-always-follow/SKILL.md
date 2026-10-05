---
name: backend-standards-always-follow
description: Always-on backend baseline for APIs, routes, controllers, schemas, services, persistence, auth, validation, workers, queues, and integrations.
when_to_use: Use for any backend or server-side task (planning, implementing, debugging, reviewing) before the other backend skills.
paths:
- '**/*.go'
- '**/server/**/*.{ts,js,mjs,cjs,py}'
metadata:
  schema: 1
  category: backend
  surfaces:
  - backend
  platforms:
  - linux
  - darwin
  - windows
  token-cost: 711
  triggers:
    keywords:
    - backend task
    - backend change
    - backend endpoint
    - server-side
    - api endpoint
    - new endpoint
    - add an endpoint
    - controller
    - route handler
    - service layer
    - background worker
    - queue worker
    - backend baseline
    paths:
    - /models/
    - controller
    - internal/
    - internal/models/
    - server/
    - service
    intents:
    - backend
---
# Backend Standards Always Follow

> **Companions load lazily.** Load a companion only when the task needs what it owns,
> and only the ones that match the repo's stack (check `go.mod` / `package.json` /
> `pyproject.toml` first):
>
> | Need | Skill |
> |---|---|
> | list/search endpoints, pagination, filters | `backend-api-standards` |
> | controller/service boundaries | `service-layer-standards` |
> | error taxonomy, central handler | `backend-error-handling` |
> | slow queries, N+1, indexes | `backend-performance-standards` |
> | envelopes, contract compatibility | `api-contract-standards` |
> | new domain or feature skeleton | `scaffold-standards` |
> | Fastify routes, hooks, Ajv | `fastify-patterns` |
> | Mongoose models, queries, aggregations | `mongoose-patterns` |
> | Go code / Go tests | `golang-patterns` / `golang-testing` |
> | SQL / Postgres | `postgres-patterns` |
> | reviewing a diff | `code-review-and-quality` |

## Overview

This is the always-on backend baseline. Examples are Go-first; Node/TS/Fastify/Mongo variants live in `references/node-stack.md`. Pick the block that matches the repo's actual stack.

## Always Apply

- Inspect existing routes, controllers, schemas, services, models, and helpers before changing behavior.
- Preserve current response shapes, DB fields, and domain behavior unless the task explicitly changes them.
- Keep controllers thin and keep business logic in services.
- Keep filtering, sorting, pagination, and search backend-driven for list endpoints.
- Validate request shapes with schemas instead of scattered ad hoc checks.
- Keep manually maintained backend source files at or below 250 lines. If a touched file is already over 250 lines, split or reduce it before adding more behavior unless the user explicitly scopes that cleanup out.
- Remove stale imports, replaced logic, and dead backend paths while you work.

## Non-Negotiables

- No guessing when the repo already shows the pattern.
- No business logic hidden in controllers.
- No unbounded list endpoints for real datasets.
- No raw internal errors, stack traces, or driver errors leaking to clients.
- No touched manually maintained backend source file may remain over 250 lines without an explicit blocker.
- No partial old/new backend implementations left behind without a reason.

## Load Next When Needed

- `service-layer-standards` for controller/service boundaries and service contracts.
- `backend-api-standards` for detailed list/search endpoint semantics.
- `api-contract-standards` for success/error envelopes and contract compatibility.
- `backend-error-handling` for centralized handler rules and error taxonomy.
- `backend-performance-standards` for query-efficiency or scalability review.
- `scaffold-standards` for new domain or feature skeletons.

## Completion Checklist

- Existing backend patterns were inspected first.
- Controllers stayed thin.
- Business logic stayed in services.
- Query behavior remained backend-driven.
- No stale backend code was left behind.
