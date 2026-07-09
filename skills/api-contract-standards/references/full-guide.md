---
name: api-contract-standards
description: Use when backend response envelopes, list metadata, error shapes, versioning, or separation between table, card, and summary contracts are being defined or reviewed.
metadata:
  author: ajayirkal
  version: "2.0"
  compliance: "Architectural Standards and Modular Development Protocol"
---

# API Contract Standards (OPTIMIZED + STRICT)

## 0. Purpose
Use this skill as the single source of truth for all backend API contracts.

Goals:
- prevent frontend breakage
- enforce stable response shapes
- keep pagination/filtering backend-driven
- separate table data from card/summary data
- avoid repeating instructions on every task

If an endpoint contract changes without versioning, it is a violation.

---

## 1. Auto-Apply Defaults (No Need to Repeat)
When the user asks to build or update an API and does not specify details, automatically apply:

- JSON response only
- standard success/error envelope
- query validation schema (query/params/body)
- backend pagination for list/table endpoints
- sort whitelist
- reject unknown filters (unless explicitly allowed)
- separate endpoints for table/list vs card/summary
- thin controller + service-owned business logic

Default list query values:
- `page = 1`
- `limit = 20`
- `maxLimit = 100`
- `sortBy = "createdAt"`
- `sortOrder = "desc"`

---

## 2. Non-Negotiable Global Rules

1. Every endpoint returns JSON.
2. Every response contains `success`.
3. Success responses contain `data`.
4. Errors use `error.code` + safe `error.message`.
5. List/table endpoints must be paginated.
6. Filtering/sorting/pagination must run at DB level.
7. Never expose stack traces/raw DB errors.
8. Never rename existing response keys without versioning.
9. Unknown query keys are rejected by default.
10. Controllers stay thin; services own business logic.

---

## 3. Standard Response Envelopes

### 3.1 Success Envelope (All Endpoints)
```json
{
  "success": true,
  "data": {},
  "message": "",
  "meta": {}
}
```

Rules:
- `message` and `meta` are optional but recommended where relevant.
- Keep key names stable across domains.

### 3.2 Error Envelope (All Endpoints)
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

Rules:
- never return stack traces/internal paths/raw driver errors
- keep `error.code` machine-readable and stable

---

## 4. Endpoint Intent Types (Mandatory Separation)

Do not mix endpoint purposes. Each endpoint must have one contract intent:

### A) Table/List Endpoint (Paginated Records)
Use for data tables with filters/sorting/pagination.

Example:
- `GET /licenses`

### B) Summary/Card KPI Endpoint (Aggregates/Counters)
Use for dashboard cards like totals/status counts/trends.

Example:
- `GET /licenses/summary`

### C) Card Collection Endpoint (UI Cards of Entities)
Use only when cards display entity previews (grid/list card UI), not table rows.

Example:
- `GET /licenses/cards`

Hard rule:
- A table endpoint response must not be reused as the summary/cards contract.
- Summary KPI data must come from dedicated summary service logic.

---

## 5. Contract Templates by Endpoint Type

### 5.1 Table/List Contract (Required for tables)
```json
{
  "success": true,
  "data": [
    {
      "id": "lic_001",
      "name": "Enterprise Plan",
      "status": "active",
      "owner": "Acme Corp",
      "startDate": "2026-01-01",
      "endDate": "2026-12-31"
    }
  ],
  "meta": {
    "view": "table",
    "page": 1,
    "limit": 20,
    "total": 125,
    "totalPages": 7,
    "sortBy": "createdAt",
    "sortOrder": "desc",
    "hasNextPage": true,
    "hasPrevPage": false
  }
}
```

### 5.2 Summary/Card KPI Contract (Required for dashboard KPIs)
```json
{
  "success": true,
  "data": {
    "totalLicenses": 125,
    "activeLicenses": 98,
    "expiredLicenses": 12,
    "expiringIn30Days": 15
  },
  "meta": {
    "view": "summary",
    "generatedAt": "2026-03-15T10:30:00.000Z"
  }
}
```

### 5.3 Card Collection Contract (Entity cards)
```json
{
  "success": true,
  "data": [
    {
      "id": "lic_001",
      "title": "Enterprise Plan",
      "subtitle": "Acme Corp",
      "badge": "Active",
      "expiryDate": "2026-12-31"
    }
  ],
  "meta": {
    "view": "card",
    "page": 1,
    "limit": 12,
    "total": 48,
    "totalPages": 4
  }
}
```

Rules:
- Card collection DTO must be leaner than table DTO.
- Do not expose table-only columns in card DTO by default.
- Card and table services may share base query utilities, but not identical response contracts.

---

## 6. Query Parameter Contract (List/Card Collection)

Allowed common query params:
- `page` (number, min 1, default 1)
- `limit` (number, min 1, max 100, default 20 for table, 12 for cards if UI requires)
- `sortBy` (must be whitelisted)
- `sortOrder` (`asc` | `desc`)
- `q` (optional search)
- explicit domain filters (whitelisted + typed)

Validation rules:
- trim string inputs
- convert empty strings to undefined
- cast number/boolean types
- reject unknown keys unless explicitly allowed

---

## 7. Performance Rules (Required)

- pagination/filter/sort must execute in DB queries
- never fetch-all then filter/sort in memory
- use projection/select to return only required fields
- enforce index planning for new filter/sort fields
- summary endpoints should use aggregate queries, not full table fetches

---

## 8. Versioning & Breaking Changes

A change is breaking if it:
- renames existing keys
- changes data type of existing keys
- changes envelope structure
- removes previously returned required fields

For breaking changes:
- introduce a versioned endpoint (for example `/v2/licenses`)
- keep old contract operational until migration completes
- document migration mapping clearly

---

## 9. Backend Structure Rules

For each endpoint intent, create matching schema + service + controller path:

- route root registry: `/routes/index.ts`
- route domain registry: `/routes/{domain}/index.ts`
- leaf route: `/routes/{domain}/{action}.route.ts`
- schema: `/schemas/{domain}/{action}.schema.ts`
- schema feature folders: `/schemas/{domain}/{feature}/{action}.schema.ts` plus `/schemas/{domain}/{feature}/index.ts` when the repo uses controller-mirror feature folders
- types: `/types/{domain}/{name}.ts`
- controller root registry: `/controllers/index.ts`
- controller domain registry: `/controllers/{domain}/index.ts`
- controller leaf: `/controllers/{domain}/{action}.controller.ts`
- controller feature folders: `/controllers/{domain}/{feature}/{action}.controller.ts` when the repo groups related actions under feature folders
- service: `/services/{domain}/{action}.service.ts` for flat repos, or `/services/{domain}/{feature}/index.ts` with action entry files and feature-local helpers when the repo uses controller-mirror feature folders

Recommended naming:
- `list{Entity}` for table endpoints
- `get{Entity}Summary` for KPI summary endpoint
- `list{Entity}Cards` for card collection endpoint

Do not route all UI views through one generic list service.

---

## 10. Anti-Patterns (Forbidden)

- using table endpoint payload directly for dashboard KPIs
- returning unbounded lists
- allowing arbitrary `sortBy` fields
- frontend-side filtering/sorting for large datasets
- inconsistent error formats across endpoints
- returning `200` with `success: false`

---

## 11. Acceptance Checklist (Before Merge)

- [ ] endpoint intent identified (`table`, `summary`, or `card`)
- [ ] schema validates query/params/body
- [ ] unknown query keys rejected (or explicitly allowed)
- [ ] table/card list endpoints are paginated
- [ ] summary endpoint is separate from table endpoint
- [ ] sort keys are whitelisted
- [ ] filters run at DB level
- [ ] error response matches standard envelope
- [ ] no raw internal errors leaked
- [ ] response keys unchanged or versioned properly

---

## 12. Golden Rule

One endpoint = one clear contract intent.

Tables are paginated records.
Summary cards are aggregates.
Card collections are UI card DTOs.

Do not mix them.
