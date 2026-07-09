---
name: backend-api-standards
description: Use when a backend task needs strict list or search endpoint rules for
  filtering, sorting, pagination, stable response shapes, query validation, or older
  prompts explicitly call for backend API standards. Backend Core Compliance Set member
  for list and search endpoint query rules As part of the Backend Core Compliance
  Set for backend/server work, especially list or search endpoint query semantics,
  sort and filter whitelists, and pagination rules.
disable-model-invocation: false
---
# Backend API Standards

## Overview

This skill owns strict backend list and search endpoint behavior.

Use it when filtering, sorting, pagination, stable list response shapes, thin controllers, or end-to-end query validation must be enforced. For general backend work, start with `backend-standards-always-follow`.

## Use When

- Adding or modifying list endpoints.
- Defining supported query params or sort whitelists.
- Standardizing backend-driven table or search behavior.
- Reviewing DB-level filtering, sorting, or search behavior.
- Locking pagination defaults and bounds.

## Do Not Use

- Envelope design by itself.
- Controller/service boundaries by themselves.
- Error taxonomy by itself.

## Core Rules

- Table and list endpoints must support backend-side pagination, filtering, and sorting.
- List responses must stay stable across domains.
- Filtering, sorting, and search must run in the DB layer, not in memory for real datasets.
- Query, body, and params input must be validated with schemas.
- Query params must be sanitized, normalized, type-cast, and whitelisted.
- Unknown filters are rejected by default unless explicitly allowed.
- Sort keys must be whitelisted.
- Controllers stay thin: validate, call service, return response.
- Services own query building, pagination, sort whitelists, and overflow handling.

## Default Query Behavior

```json
{
  "page": 1,
  "limit": 20,
  "sortBy": "createdAt",
  "sortOrder": "desc"
}
```

Recommended maximum:

- `maxLimit = 100`

## Stable List Response

```json
{
  "items": [],
  "page": 1,
  "limit": 20,
  "total": 0,
  "totalPages": 0,
  "sortBy": "createdAt",
  "sortOrder": "desc"
}
```

## Endpoint Expectations

List endpoints should typically support:

- `page`
- `limit`
- `sortBy`
- `sortOrder`
- `q` when search is supported
- explicit domain filters

## Preferred Structure

- Root route registry in `/routes/index.ts`
- Domain route registry in `/routes/{domain}/index.ts`
- Leaf route in `/routes/{domain}/{action}.route.ts`
- Root controller registry in `/controllers/index.ts`
- Domain controller registry in `/controllers/{domain}/index.ts`
- Leaf controller in `/controllers/{domain}/{action}.controller.ts` or repo-local feature folders like `/controllers/{domain}/{feature}/{action}.controller.ts`
- Schema in `/schemas/{domain}/{action}.schema.ts` or repo-local feature folders like `/schemas/{domain}/{feature}/{action}.schema.ts`
- Types in `/types/{domain}/{name}.ts`
- Service in `/services/{domain}/{action}.service.ts` for flat repos, or `/services/{domain}/{feature}/index.ts` with action entry files and helper modules when the repo uses controller-mirror feature folders
- Query helpers in `/utils/{domain}/query.ts`

## Safety Rules

- No fetch-all-then-filter for large datasets.
- No unbounded list responses.
- No in-memory sort for large result sets.
- No silent acceptance of unknown query keys.

## Performance Notes

- Check indexes for new filter or sort paths.
- Call out regex or search risks on large collections.
- Treat repeated list access as a performance-sensitive surface.
- Preserve response keys and query param names while optimizing.
- Treat manually maintained backend source files above 250 lines as a structural violation for touched API surfaces; split routes, schemas, controllers, services, query helpers, or mappers before adding more behavior unless the user explicitly scopes that cleanup out.

## Combine With

- `backend-standards-always-follow` for the default backend baseline.
- `service-layer-standards` for thin-controller execution.
- `api-contract-standards` for response envelope rules.
- `backend-performance-standards` when scale, repeated DB work, or hot-path efficiency is the main concern.

## References

- Use `references/full-guide.md` for the longer strict version and implementation details.
