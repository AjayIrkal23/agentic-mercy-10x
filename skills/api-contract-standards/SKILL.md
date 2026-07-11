---
name: api-contract-standards
description: Use when backend response envelopes, list metadata, error shapes, versioning, or the separation
  between table, card, and summary contracts are being defined or reviewed.
disable-model-invocation: false
schema: 1
category: general
surfaces:
- general
platforms:
- linux
- darwin
- windows
token-cost: 642
triggers:
  keywords:
  - api
  - apis
  - backend
  - boundaries
  - card
  - contract
  - contracts
  - creating
  - defined
  - defining
  - design
  - designing
  - endpoints
  - envelopes
  - error
  - establishing
  - frontend
  - graphql
  - guides
  - interface
  - list
  - metadata
  - module
  - modules
  - public
  - response
  - rest
  - reviewed
  - separation
  - shapes
  - stable
  - standards
  - summary
  - table
  - type
  - versioning
  paths:
  - src/schemas/
  - src/types/
  intents:
  - general
---
## Use When

- Defining or reviewing backend response envelope shapes (`data`, `meta`, `error` fields).
- Reviewing list endpoint contracts (pagination metadata, filter keys, sort contracts).
- Any API change that could break existing frontend consumers (field renames, type changes, removals).
- Creating a new API route that must conform to the project's existing contract conventions.
- Reviewing versioning decisions or backward-compatibility boundaries.

## Do Not Use

- For frontend-only implementation details (component state, local UI state).
- For reviewing Go/TS logic that does not touch public API response shapes.
- As a replacement for `backend-api-standards` which covers route-level implementation rules.

# API Contract Standards

## Overview

This is the backend contract source of truth.

Use it when the public wire shape matters: success envelopes, error envelopes, list metadata, compatibility, and contract separation by endpoint intent.

## Non-Negotiables

1. Every endpoint returns JSON.
2. Every response includes `success`.
3. Success responses include `data`.
4. Error responses use `error.code` and a safe `error.message`.
5. List endpoints are paginated.
6. Filtering, sorting, and pagination happen in the backend.
7. Existing response keys do not change casually.
8. Unknown query keys are rejected by default unless explicitly allowed.

## Standard Success Envelope

```json
{
  "success": true,
  "data": {},
  "message": "",
  "meta": {}
}
```

## Standard Error Envelope

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Safe user-facing message",
    "details": {}
  }
}
```

## Endpoint Intent Separation

Do not mix these contract types:

- table/list endpoints
- summary or KPI endpoints
- card/grid preview endpoints

If the UI needs a different intent, give it a dedicated contract instead of reusing a list shape for everything.

## List Contract Defaults

Recommended defaults:

- `page = 1`
- `limit = 20`
- `maxLimit = 100`
- `sortBy = "createdAt"`
- `sortOrder = "desc"`

List metadata should stay stable across domains.

## Compatibility Rule

If a contract changes in a way that can break consumers, version it or plan a migration explicitly.

## Combine With

- `backend-api-standards` for query semantics.
- `backend-error-handling` for error taxonomy and centralized handling.
- `service-layer-standards` for thin-controller ownership boundaries.

## References

- Use `references/full-guide.md` for the longer strict version with more detailed endpoint intent and examples.
