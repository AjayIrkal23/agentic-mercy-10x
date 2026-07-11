# frontend-api-standards

> Absorbed into `frontend-response-handling` (P5 consolidation). Method content preserved verbatim below.

---

# Frontend API Standards

## Overview

This skill covers the backend-driven query contract rules for frontend API layers: filter, pagination, sorting, and search parameters belong on the backend for server-driven datasets.

For tasks that also need success/error response normalization, use `frontend-response-handling`, which includes these rules plus a full normalization layer.

## Core Rules

- Filters, pagination, sorting, and search belong to the backend for API-backed datasets.
- Pages and components should not fetch directly; use the project API/store/query layer.
- A single `query` object drives refetch behavior for list screens.
- Query changes should update backend params, not local shadow copies of server data.
- Response typing is required.

## Required Query Shape

```ts
{
  page,
  limit,
  sortBy,
  sortOrder,
  q,
  ...domainFilters,
}
```

## Non-Negotiables

- No client-side filtering or pagination for server datasets.
- Reset `page` to `1` when filters or search invalidate the current page.
- Use backend totals and pagination metadata; do not compute them locally.
- Keep query params aligned 1:1 with backend contract keys.

## Layer Expectations

- API modules accept a typed query object and serialize params.
- Store/query layers own loading, error, data, and last-query state.
- Components render state; they do not parse transport details.

## Use Next

- Prefer `frontend-response-handling` for current API work.
- Use `frontend-server-data-patterns` for screen-level query-state design.
