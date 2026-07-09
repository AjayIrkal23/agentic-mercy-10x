---
name: backend-api-standards
description: Use when a backend task needs strict list or search endpoint rules for filtering, sorting, pagination, stable response shapes, query validation, or older prompts explicitly call for backend API standards.
metadata:
  version: "1.1"
  compliance: "Architectural Standards and Modular Development Protocol"
---

# Backend API Standards (STRICT)

## 0. Goal
Every "table/list" endpoint MUST support:
- pagination (page + limit)
- backend-side filtering (no frontend filtering for datasets)
- backend-side sorting
- stable response shape
- schema validation for query/body
- consistent controller -> service -> model flow

Frontend MUST NEVER filter large datasets client-side. Frontend only sends query params and renders server results.

## 1. Mandatory File Structure (Domain-based)
- Route root registry: `/routes/index.ts`
- Domain route registry: `/routes/{domain}/index.ts`
- Leaf route: `/routes/{domain}/{action}.route.ts`
- Controller root registry: `/controllers/index.ts`
- Controller domain registry: `/controllers/{domain}/index.ts`
- Controller leaf: `/controllers/{domain}/{action}.controller.ts` with one controller function per file, or repo-local feature folders like `/controllers/{domain}/{feature}/{action}.controller.ts`
- Schema: `/schemas/{domain}/{action}.schema.ts` or repo-local feature folders like `/schemas/{domain}/{feature}/{action}.schema.ts`
- Types: `/types/{domain}/{name}.ts`
- Model: `/models/{domain}/{ModelName}.ts`
- Service: `/services/{domain}/{action}.service.ts` for flat repos, `/services/{domain}/{feature}/index.ts` with action entry files and helper modules when the repo uses controller-mirror feature folders, OR `/controllers/{domain}/services/{action}.ts` only when the repo has no dedicated `services/` tree
- Helpers: `/utils/{domain}/query.ts` (filters/pagination builders)

## 2. Endpoint Patterns
### List endpoints (table views)
- MUST be GET
- MUST accept:
  - `page` (default 1)
  - `limit` (default 20, max 100)
  - `sortBy` (whitelist)
  - `sortOrder` ("asc"|"desc")
  - `q` (optional search)
  - domain filters (strictly typed + whitelisted)

### Read single
- GET `/:id`

### Create
- POST `/`

### Update
- PATCH `/:id` (preferred)
- Must validate body via schema

### Delete
- DELETE `/:id` (only if required)

## 3. Query Validation (STRICT)
- Every endpoint MUST have a schema file.
- Query params must be:
  - sanitized (trim strings)
  - normalized (empty → undefined)
  - type-cast (numbers, booleans)
  - validated against enums/whitelists
- Reject unknown filters by default (unless explicitly allowed).

## 4. Pagination & Response Shape (NON-NEGOTIABLE)
All list endpoints MUST return:

{
  "items": [],
  "page": 1,
  "limit": 20,
  "total": 0,
  "totalPages": 0,
  "sortBy": "createdAt",
  "sortOrder": "desc"
}

Rules:
- `total` MUST be the total matching documents/rows (without pagination).
- `items.length` <= limit.
- `totalPages` = ceil(total/limit).
- MUST be stable across all domains.

## 5. Filter Implementation Rules
- All filters MUST be applied at DB query level (Mongo query / SQL WHERE).
- Sorting MUST be DB-level.
- Searching MUST be DB-level (indexed preferred).

Do NOT:
- fetch-all-then-filter in service/controller
- do in-memory sort on large lists
- return unbounded lists

## 6. Controller Rules (Thin Only)
Controllers may only:
- parse/validate input (schema already validated)
- call service
- return response

No business logic in controllers.

## 7. Service Rules
Service must:
- build query from validated filters
- whitelist sort keys
- apply pagination
- handle edge cases (page overflow → return empty items with correct totals)

## 8. MongoDB specifics (if using Mongo)
Preferred approach:
- Build a `match` object from validated filters
- Use `countDocuments(match)` for total
- Use `find(match).sort().skip().limit()`

For complex joins:
- Use aggregation pipeline with `$match`, `$sort`, `$skip`, `$limit`
- Total via a second pipeline or `$facet`

## 9. Performance & Indexing (Required)
For every new filter/sort on large collections:
- confirm index exists or add it
- search fields should be indexed or use text index only where needed
- avoid regex on huge fields unless indexed strategy is planned
- avoid repeated DB calls across loops when batching or reuse is possible
- preserve response shapes, DB fields, and query param names while optimizing
- treat manually maintained backend source files above 250 lines as a structural violation on touched API surfaces and split helpers/services early

## 10. Naming & Safety
- Never rename API response fields.
- Never change existing query param names without a migration plan.
- Use consistent naming: camelCase in query params and response keys.

## 11. Verification Checklist (Before merge)
- [ ] Schema exists for route (query/body/params)
- [ ] Unknown query keys rejected or explicitly handled
- [ ] Pagination works (page, limit, total, totalPages)
- [ ] Filters applied in DB query (not frontend)
- [ ] Sorting whitelisted
- [ ] Response matches standard shape
- [ ] Controller is thin
- [ ] File size < 250 lines (split helpers/services if needed)

## 12. Combine With
- `backend-standards-always-follow` for the default backend baseline
- `service-layer-standards` for controller/service boundaries
- `api-contract-standards` when response envelopes or contract change review matters
- `backend-performance-standards` when query efficiency, repeated DB work, or scaling risk is the main concern
