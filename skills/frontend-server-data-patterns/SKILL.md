---
name: frontend-server-data-patterns
description: "Frontend query state for server-backed screens: the query object as source of truth, server-driven filtering/sorting/pagination/search, and the loading/empty/error/success states for API-backed tables, lists, and search pages."
when_to_use: Use when building or changing an API-backed table, list, or search screen, a use*-data hook, or a queries/ module with server-driven filter, sort, or pagination.
paths:
  - "**/hooks/use*.{ts,tsx}"
  - "**/*Table*.tsx"
  - "**/*List*.tsx"
  - "**/queries/**"
metadata:
  schema: 1
  category: frontend
  surfaces: [frontend]
  platforms: [linux, darwin, windows]
  token-cost: 468
  triggers:
    keywords: [table, list, search screen, query state, query object, server-driven, filtering, sorting, pagination, async ui, loading state, empty state, api-backed]
    paths: [/hooks/use, /src/hooks/, /queries/, Table, List, use-]
    intents: [frontend, implement]
---
# Frontend Server Data Patterns

## Use When
- Building or updating API-backed lists, tables, or search pages.
- Defining frontend query objects that map to backend filters.
- Handling loading, empty, error, and pagination states for server data.

## Do Not Use
- Structuring general frontend modules or hooks without server data.
- Styling or visual design work.
- Defining backend query validation or response envelopes.

## Owns
- Query object shape on the frontend.
- Server-driven filtering, sorting, pagination, and search behavior.
- UI state expectations for async server data screens.
- Request lifecycle between page, store or query layer, and API client.

## Does Not Own
- General component architecture or file organization.
- Backend whitelist, index, or DB execution strategy.
- Styling, animation, or visual system direction.

## Combine With
- `frontend-standards-always-follow` for the always-on frontend baseline.
- `frontend-structure-standards` for component and module boundaries.
- `frontend-response-handling` for envelope parsing and normalized errors.
- `api-contract-standards` for request and response shape stability.
- `backend-api-standards` when frontend and backend query semantics must match.

## Workflow
1. Define the query object as the source of truth for the screen.
2. Send filters, sort, search, and pagination to the backend instead of computing them locally.
3. Keep API access outside of UI components.
4. Reset page state when filter inputs change in a way that invalidates the current page.
5. Validate success, error, loading, and empty states together.

## Output Contract
- Frontend query-state shape and fetch flow.
- Mapping between UI controls and backend query params.
- Required user-visible states for server-backed screens.
- The point where `frontend-response-handling` should take over for API parsing and errors.
