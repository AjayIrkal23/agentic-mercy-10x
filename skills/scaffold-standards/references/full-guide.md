---
name: scaffold-standards
description: Use when scaffolding a new backend or full-stack domain, route/controller/service/schema skeleton, or standard list and CRUD feature structure.
metadata:
  version: "1.0"
  compliance: "Architectural Standards and Modular Development Protocol"
---

# Scaffold Standards (STRICT)

## 0. Purpose
Every new domain/feature must be created using a **repeatable skeleton** so future projects remain:
- consistent
- easy to extend
- easy to debug
- fast to build

This standard defines the **minimum required files**, **naming**, and **contracts** for any new module.

---

# 1. Mandatory Domain Naming
A "domain" is a business module like:
- users
- cameras
- healthLogs
- receipts
- violations
- reports

Rules:
- Domain name MUST be kebab-case for folders: `camera-health`, `vehicle-parking`
- Code identifiers MUST be camelCase / PascalCase:
  - `cameraHealthService`
  - `CameraHealthTable`

---

# 2. Backend Scaffolding (Required)

## 2.1 Required Files for a New Backend Feature

For every new endpoint/action:

### Routes
`/routes/index.ts` for the root registry when the project does not already have one

`/routes/{domain}/index.ts` for the owning domain registry and prefix

`/routes/{domain}/{action}.route.ts` for the leaf route plugin

### Controller
`/controllers/index.ts` for the root controller registry when the project does not already have one

`/controllers/{domain}/index.ts` for the owning controller domain registry

`/controllers/{domain}/{action}.controller.ts` (single controller in each file)
`/controllers/{domain}/{feature}/{action}.controller.ts` when the repo groups related actions under feature folders

### Schema (Query/Params/Body)
`/schemas/{domain}/{action}.schema.ts` (single schema in each file)
`/schemas/{domain}/{feature}/{action}.schema.ts` plus `/schemas/{domain}/{feature}/index.ts` when the repo uses feature folders

### Types (Request/Response/DTOs/Options)
`/types/{domain}/{name}.ts` (shared backend types only)

### Service
`/services/{domain}/{action}.service.ts` (single service in each file for flat repos)
`/services/{domain}/{feature}/index.ts` with action entry files and helper modules such as `shared.ts`, `audit.ts`, `reference.ts`, `constraints.ts`, `deleteGuards.service.ts`, `lookupToken.service.ts`, `mapping.ts`, `normalization.ts`, `snapshot.ts`, or `core.ts` when the repo uses controller-mirror feature folders

### Model (If new entity)
`/models/{domain}/{ModelName}.ts`

### Query Helpers (If list/table)
`/utils/{domain}/query.ts`
- filter normalization
- sort whitelist

Rule:
- reusable backend types MUST live under `/types/{domain}/...`
- do NOT leave request generics, DTOs, service contracts, or plugin option interfaces inline in runtime files
- query builder

### Mapper (If DTO needed)
`/utils/{domain}/mapper.ts`
- DB doc → API DTO mapping

---

## 2.2 Mandatory Backend Action Types

Every domain must support (when applicable):

- `list` (paginated + backend filters)
- `getById`
- `create`
- `update`
- `delete` (optional)

Naming convention:
- list: `list{Entity}`
- get: `get{Entity}ById`
- create: `create{Entity}`
- update: `update{Entity}`
- delete: `delete{Entity}`

---

## 2.3 Required Backend Contracts (STRICT)

### Success Response (All)
{
  "success": true,
  "data": {},
  "message": "",
  "meta": {}
}

### List Response (Tables)
{
  "success": true,
  "data": [],
  "meta": {
    "page": 1,
    "limit": 20,
    "total": 0,
    "totalPages": 0,
    "sortBy": "createdAt",
    "sortOrder": "desc"
  }
}

### Error Response
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Safe message",
    "details": {}
  }
}

---

# 3. Frontend Scaffolding (Required)

## 3.1 Required Files for a New Frontend Domain

### API Layer
`/api/{domain}/{functionname}.ts` or `/apis/{domain}/{functionname}.ts` (single api function each file; follow repo-local docs for the exact path)
Must include:
- `list(query)`
- `getById(id)`
- `create(payload)`
- `update(id, payload)`
- `remove(id)` (if supported)

### Store Layer
`/store/{domain}/`
- `slice.ts`
- `types.ts`
- `selectors.ts`
- `thunks.ts`

Rules:
- Thunks call API layer only
- Components never call API directly

### Feature Hooks
`/components/{domain}/{feature}/hooks/{useHook}.ts` for feature-owned orchestration, form state, dialog state, and query wiring

Use `/hooks/{domain}/{useHook}.ts` only when a hook is shared across multiple features.

### Frontend Types
`/types/{domain}/{feature}-ui.ts` for feature props, dialog state, and local UI contracts

Rules:
- Components and hooks import these UI contracts instead of declaring them inline
- Keep API/domain contracts in focused domain type files, not in component files

### Components
`/components/{domain}/`
Minimum:
- `{Entity}Table.tsx`
- `{Entity}Filters.tsx`
- `{Entity}Form.tsx` (create/edit)
- `{Entity}Details.tsx` (optional)

### Page
`/pages/{domain}/index.tsx` (or `/app/{domain}/page.tsx` in Next app router)

---

## 3.2 Mandatory Query State Pattern (List Screens)

Every list screen MUST manage a `query` object:

{
  page: 1,
  limit: 20,
  sortBy: "createdAt",
  sortOrder: "desc",
  q: "",
  ...domainFilters
}

Rules:
- Query drives API refetch
- Filters update query only
- Reset page to 1 when filters/search change
- Sorting updates sortBy/sortOrder and refetches
- Pagination is backend-driven

---

# 4. Required UI States (List Screens)

Every table screen MUST implement:
- Loading state
- Empty state
- Error state (with retry)
- Pagination controls
- Filter controls (backend-driven)

No UI should assume "data exists".

---

# 5. Mandatory Implementation Order (Agentic Flow)

When scaffolding a new domain:

1) Define API contract (schema + response shape)
2) Implement backend schema
3) Implement service (filters, pagination, sort whitelist)
4) Implement controller + leaf route + domain registration
5) Implement frontend API wrapper
6) Implement store (query + thunk)
7) Implement filters component
8) Implement table component
9) Wire page
10) Verify with checklist

---

# 6. MCP Usage During Scaffolding (If available)

Use MCP when:
- verifying existing patterns in repo (GitHub MCP)
- checking Mongo collections/fields (Mongo MCP)
- confirming docs/config (fetch/web-reader/search)

Never assume project patterns; align with existing code.

---

# 7. 250-Line Rule (Mandatory)
Any file exceeding 250 lines must be split into:
- helpers
- services
- mappers
- query utils
- UI subcomponents

---

# 8. Verification Checklist (Mandatory)

Before marking scaffold complete:

Backend:
- [ ] root route registry exists or is updated
- [ ] domain route registry exists or is updated
- [ ] leaf route file exists
- [ ] controller file exists (thin)
- [ ] schema file exists (query/params/body)
- [ ] service file exists (business logic)
- [ ] list endpoint paginated + backend filters
- [ ] error handling conforms to standard
- [ ] response contract consistent

Frontend:
- [ ] api wrapper exists
- [ ] store slice/selectors/thunks exist
- [ ] query state implemented
- [ ] filters are backend-driven
- [ ] pagination is backend-driven
- [ ] loading/empty/error states present
- [ ] no direct API calls in components/pages

---

# 9. Golden Rule

Scaffold once.
Reuse forever.

All domains must look and behave the same to stay scalable.
