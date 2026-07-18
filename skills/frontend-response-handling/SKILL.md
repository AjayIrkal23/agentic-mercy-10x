---
name: frontend-response-handling
description: "ALWAYS invoke when frontend API work needs success parsing, normalized error handling, or backend-driven list, filter, sort, and pagination behavior."
disable-model-invocation: false
schema: 1
category: frontend
surfaces:
- frontend
platforms:
- linux
- darwin
- windows
token-cost: 792
triggers:
  keywords:
  - api
  - backend
  - backend-driven
  - behavior
  - calls
  - conform
  - contracts
  - error
  - errors
  - fetch
  - flows
  - frontend
  - frontend-response-handling
  - handle
  - handling
  - have
  - implementing
  - instead
  - layer
  - layers
  - limit
  - list
  - list/query
  - must
  - needs
  - normalization
  - normalize
  - normalized
  - page
  - parse
  - parsing
  - prefer
  - query
  - raw
  - response
  - responses
  - sdk
  - sortby
  - sortorder
  - success
  - success/error
  - work
  - wrappers
  - yet
  paths:
  - /api-client
  - /api/
  - /auth/
  - /guard/
  - /login/
  - api.js
  - api.ts
  - protected
  - session
  intents:
  - frontend
---
# Frontend Response Handling

## Overview

This is the canonical frontend API integration skill.

It combines backend-driven list/query behavior with success-envelope parsing and normalized error handling.

## Use When

- Touching `src/api/**`, `src/apis/**`, thunks, async query layers, or API-backed list/table screens.
- Adapting frontend code to an existing backend contract.
- Normalizing transport failures into frontend-safe errors.

## Do Not Use

- Pure visual work.
- General module layout without async data.
- Backend-side query validation or DB strategy.

## Owns

- Parsing success envelopes.
- Normalizing frontend-safe error objects.
- Backend-driven list/query behavior on the frontend.
- Layer responsibilities between component, store/query layer, API module, and API client.

## Contract Lock First

1. Read the relevant frontend API docs and existing API client/types/pattern file. Use repo-local docs to confirm whether the repo standard is `src/api/**` or `src/apis/**`.
2. Inspect backend `route -> schema -> controller -> service`.
3. Lock request keys, success envelope, error envelope, and pagination metadata before coding.

## Success Rules

Expected backend success envelope:

```json
{
  "success": true,
  "data": {},
  "message": "",
  "meta": {}
}
```

- API modules must parse the envelope explicitly.
- Return typed domain data, not raw transport objects.
- Use an adapter if the backend still exposes a legacy shape.

## Error Rules

Expected backend error envelope:

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Safe message",
    "details": {}
  }
}
```

Frontend normalized error shape:

```ts
type NormalizedApiError = {
  code: string
  message: string
  statusCode: number
  details?: Record<string, unknown>
  isRetryable: boolean
}
```

- Map timeout, network, and unknown failures to stable fallback codes.
- Never leak raw transport or internal backend details to UI.

## Backend-Driven Query Rules

- The query object is the single source of truth.
- Filters, sort, and pagination update query state only.
- Any meaningful query change triggers a refetch.
- Reset page when filter/search changes invalidate the current page.
- Never do client-side filtering or pagination for server datasets.

## Layer Boundaries

- API layer: call backend, parse success, normalize and throw typed errors.
- Store/query layer: map normalized results into user-facing state and messages.
- Component/page layer: render state only; no raw `error.response` or raw payload parsing.

## Workflow

1. Lock the contract first.
2. Implement the API adapter once.
3. Normalize errors once.
4. Wire query-driven state.
5. Verify loading, empty, error, and success states together.

## References

- Use `references/api-module-template.md` for a reusable API module template.
- Use `frontend-server-data-patterns` when the main question is screen-level query-state design.

## Completion Checklist

- Backend contract was verified before implementation.
- Success envelope is parsed explicitly.
- Query behavior is backend-driven.
- One normalized error shape is used.
- No raw internal errors leak to UI.
