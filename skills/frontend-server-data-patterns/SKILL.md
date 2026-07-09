---
name: frontend-server-data-patterns
description: Use when building or changing API-backed tables, lists, search screens,
  or frontend query-state flows with server-driven filtering, sorting, and pagination.
  Model API-backed frontend query state Use to define query-state and async UI behavior
  for a server-backed screen.
disable-model-invocation: false
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
