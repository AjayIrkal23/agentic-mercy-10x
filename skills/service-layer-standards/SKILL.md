---
name: service-layer-standards
description: "ALWAYS invoke when any backend API, route, controller, schema, service, contract, persistence, auth, validation, worker, queue, integration, or server behavior task is requested."
disable-model-invocation: false
schema: 1
category: general
surfaces:
- general
platforms:
- linux
- darwin
- windows
token-cost: 1028
triggers:
  keywords:
  - api
  - auth
  - backend
  - behavior
  - contract
  - controller
  - integration
  - layer
  - persistence
  - queue
  - requested
  - route
  - schema
  - server
  - service
  - standards
  - task
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
  - general
---
# Service Layer Standards

## Overview

Controllers orchestrate.
Services own business logic.

Load this together with `backend-standards-always-follow` for every backend trigger surface.

If important backend logic sits in controllers, the boundary is broken.

## Use When

- Deciding whether logic belongs in a controller, service, model helper, helper, or mapper.
- Reviewing thin-controller discipline.
- Defining service inputs, outputs, and transaction ownership.
- Splitting large backend modules into cleaner layers.

## Do Not Use

- Response envelope design by itself.
- Detailed list/search query semantics by itself.
- Pure performance tuning without service-boundary questions.

## Controller Rules

Controllers may:

- read already-validated params, query, and body input
- call services
- return transport responses
- pass errors to centralized handling

Controllers must not:

- perform DB queries
- implement business rules
- build complex filters
- heavily transform domain data
- call external systems directly unless the controller is only delegating to a service wrapper

## Service Rules

Services must:

- own business logic
- own DB access directly or through collection model helpers
- own filtering, sorting, pagination, and domain-rule enforcement
- throw typed domain errors when business rules fail
- stay deterministic relative to their inputs

Services must not:

- depend on `req`, `res`, `reply`, `next`, or transport objects
- set cookies or headers
- return framework-specific response objects

## Input And Output Contracts

- Prefer one typed input object for service calls.
- Inputs should already be validated and normalized.
- Outputs should be plain JSON-safe objects or DTOs.
- Do not return raw DB documents when internal fields should stay private.

## Typical Layout

```text
/routes/index.ts
/routes/{domain}/index.ts
/routes/{domain}/{action}.route.ts
/controllers/index.ts
/controllers/{domain}/index.ts
/controllers/{domain}/{action}.controller.ts
/controllers/{domain}/{feature}/{action}.controller.ts
/schemas/{domain}/{action}.schema.ts
/schemas/{domain}/{feature}/{action}.schema.ts
/schemas/{domain}/{feature}/index.ts
/types/{domain}/{name}.ts
/services/{domain}/{action}.service.ts
/services/{domain}/{feature}/index.ts
/services/{domain}/{feature}/{action}.service.ts
/services/{domain}/{feature}/shared.ts
/services/{domain}/{feature}/audit.ts
/services/{domain}/{feature}/reference.ts
/services/{domain}/{feature}/constraints.ts
/services/{domain}/{feature}/deleteGuards.service.ts
/services/{domain}/{feature}/lookupToken.service.ts
/services/{domain}/{feature}/mapping.ts
/services/{domain}/{feature}/normalization.ts
/services/{domain}/{feature}/snapshot.ts
/services/{domain}/{feature}/core.ts
/models/<collectionName>.model.ts
/utils/{domain}/query.ts
/utils/{domain}/mappers.ts
```

If the repo uses controller-mirror feature folders, prefer the repo-local feature layout and feature barrels over inventing flat per-action service files.
If the repo uses a different but consistent service location, follow that local pattern rather than inventing a new one.

## Cross-Cutting Concerns

- Transactions belong in services.
- External integrations should be wrapped in dedicated services.
- Minimal business-event logging is fine in services; request-context logging belongs closer to transport boundaries.

## File Size Rule

- Treat 250 lines as the hard limit for manually maintained backend source files.
- If a touched service, controller, route, schema, worker, or helper exceeds 250 lines, split it before adding more behavior unless the user explicitly scopes that cleanup out.
- Split large services into query builders, mappers, policies, validators, or integration helpers before they become opaque.

## References

- Use `references/full-guide.md` when you need the full strict version with examples and edge-case notes.

## Completion Checklist

- Controller and service responsibilities are clean.
- Service contracts are typed and transport-free.
- Business logic sits in services.
- Large service files were decomposed where needed.
