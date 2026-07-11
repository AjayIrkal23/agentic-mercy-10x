---
name: backend-standards-always-follow
description: Use when any backend API, route, controller, schema, service, contract, persistence, auth,
  validation, worker, queue, integration, server/Fastify behavior, backend bugfix, or implementation is
  requested. Backend Core Compliance Set member for the always-on backend baseline As part of the Backend
  Core Compliance Set for any backend/server trigger surface before planning, debugging, implementation,
  review, delegation, or completion acceptance.
disable-model-invocation: false
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
  - acceptance
  - always
  - always-on
  - api
  - auth
  - backend
  - backend/server
  - baseline
  - behavior
  - bugfix
  - completion
  - compliance
  - contract
  - controller
  - core
  - debugging
  - delegation
  - follow
  - implementation
  - integration
  - member
  - part
  - persistence
  - planning
  - queue
  - requested
  - review
  - route
  - schema
  - server/fastify
  - service
  - standards
  - surface
  - trigger
  - validation
  - worker
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

> ## 🔒 MANDATORY COMPANION BUNDLE — load ALL now, every time, no exceptions
>
> Reading this skill is the trigger. Before doing ANY backend work you MUST
> immediately `Skill`-invoke **all** of the following, end to end. Not "when the
> work clearly needs them" — **always**, as a set, the moment this baseline loads:
>
> 1. `backend-api-standards`
> 2. `service-layer-standards`
> 3. `backend-error-handling`
> 4. `backend-performance-standards`
> 5. `backend-code-review`
> 6. `api-contract-standards`
> 7. `scaffold-standards`
> 8. `golang-patterns`
> 9. `golang-testing`
> 10. `postgres-patterns`
>
> This is non-negotiable. Do not skip, defer, or sample a subset. If any one is
> not yet loaded this turn, load it now before writing backend code.

## Overview

This is the always-on backend baseline.

Start here for any backend task. The companion bundle above is loaded in full alongside it — every time, not conditionally.

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
