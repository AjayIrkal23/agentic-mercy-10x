---
name: service-layer-standards
description: Use when deciding controller and service responsibilities, service input and output boundaries, or where backend business logic belongs.
metadata:
  version: "1.0"
  compliance: "Architectural Standards and Modular Development Protocol"
---

# Service Layer Standards (STRICT)

## 0. Purpose
The service layer exists to:
- keep controllers thin
- centralize business logic
- make features reusable across routes (API, cron, jobs, webhooks)
- enable testing without HTTP context
- enforce consistent patterns across domains

If business logic is in controllers, the architecture is considered broken.

---

# 1. Mandatory Layering & Responsibilities

## Controller (Thin Orchestrator Only)
Controllers may only:
- read validated inputs (query/params/body already validated by schema)
- call a service function
- return the response in standard API format
- pass thrown errors to the central error handler

Controllers must NOT:
- perform DB queries
- build complex filters
- implement business rules
- transform data heavily
- call external services directly (wrap in service)

---

## Service (Business Logic Owner)
Services must:
- implement business logic
- implement DB access (directly or via repository)
- implement filtering, sorting, pagination (DB-level)
- enforce domain rules (status transitions, validations beyond schema, conflict rules)
- throw typed domain errors (NotFound, Conflict, Unauthorized, Validation, ExternalServiceError)

Services must NOT:
- access `req`, `reply`, `res`, `next`, or HTTP-specific objects
- return Fastify-specific reply objects
- set headers/cookies
- do transport formatting (except minimal mapping to DTO)

Services must be deterministic given inputs.

---

## Model/Repository (Data Access)
Use models (Mongo/Mongoose or SQL queries) to:
- define schema/relationships
- encapsulate query primitives if needed

Optional repository layer:
- allowed for complex domains
- not mandatory unless it improves reuse

---

# 2. Mandatory File Structure (Domain-based)

Preferred:
- `/routes/index.ts`
- `/routes/{domain}/index.ts` (owns the domain prefix)
- `/routes/{domain}/{action}.route.ts`
- `/controllers/index.ts`
- `/controllers/{domain}/index.ts`
- `/controllers/{domain}/{action}.controller.ts` (single controller in each file)
- `/controllers/{domain}/{feature}/{action}.controller.ts` when the repo groups related actions under feature folders
- `/schemas/{domain}/{action}.schema.ts` (single schema in each file)
- `/schemas/{domain}/{feature}/{action}.schema.ts` plus `/schemas/{domain}/{feature}/index.ts` when the repo uses feature folders
- `/types/{domain}/{name}.ts` (shared request/response/service types)
- `/services/{domain}/{action}.service.ts` (single service in each file for flat repos)
- `/services/{domain}/{feature}/index.ts` with action entry files and helper modules such as `shared.ts`, `audit.ts`, `reference.ts`, `constraints.ts`, `deleteGuards.service.ts`, `lookupToken.service.ts`, `mapping.ts`, `normalization.ts`, `snapshot.ts`, or `core.ts` when the repo uses controller-mirror feature folders
- `/models/{domain}/{ModelName}.ts`
- `/utils/{domain}/query.ts` (query builders, whitelists)
- `/utils/{domain}/mappers.ts` (DTO mapping if needed)

If `services/` folder does not exist, use:
- `/controllers/{domain}/services/{action}.ts`

Rule: Keep naming consistent across layers.

---

# 3. Service Function Contract (Standard)

## Inputs
Service functions must accept:
- a single typed input object (recommended)
- or explicit typed parameters

Example:
- `listCamerasService({ tenantId, page, limit, sortBy, sortOrder, filters })`

Inputs must be:
- already validated (schemas)
- already normalized (trimmed, "ALL" -> undefined, numbers parsed)

---

## Outputs
Service functions must return:
- plain objects only (JSON-friendly)
- following standard response contracts

List services MUST return:
{
  items: [],
  page: 1,
  limit: 20,
  total: 0,
  totalPages: 0,
  sortBy: "createdAt",
  sortOrder: "desc"
}

Non-list services MUST return:
- domain entity DTO (object) or a simple `{ id }` / `{ updated: true }`

Never return raw DB documents if they contain internal fields.

---

# 4. Query Rules (Mandatory for List/Table)

List services must:
- enforce `limit` max (default 100)
- apply pagination in DB (skip/limit or cursor)
- apply filtering in DB
- apply sorting in DB
- whitelist `sortBy` keys
- project only required fields for large datasets

Forbidden:
- fetch all and filter in memory
- sort in memory for large datasets
- unbounded find()

---

# 5. Tenant & Security Scoping (Framework Rule)

If system is multi-tenant:
- Every service query MUST include `tenantId/clientId/siteId` filter
- Never rely on frontend to enforce tenant boundaries
- Any access checks belong in service layer

If auth exists:
- service must enforce role/permission checks where applicable

---

# 6. Error Rules (Strict)

Services must throw typed errors, never generic strings.

Minimum standard error types:
- ValidationError (400)
- UnauthorizedError (401)
- ForbiddenError (403)
- NotFoundError (404)
- ConflictError (409)
- RateLimitError (429) (if applicable)
- DatabaseError (500)
- ExternalServiceError (502/503)

Services must NOT:
- catch and swallow errors
- return `{ success: false }` directly
- return HTTP status codes

Controllers + global handler own the transport response.

---

# 7. Cross-Cutting Concerns Placement

## Logging
- Services may log key business events (minimal)
- Controllers should log request context (route/method/requestId)
- Never log secrets or full payloads with PII

## Transactions
- If using DB transactions, they belong in service layer
- Services must ensure rollback/cleanup on error

## External Integrations
- Wrap external calls in a dedicated service:
  `/services/{domain}/integrations/{name}.service.ts`
- Convert external errors to `ExternalServiceError`

---

# 8. Modularity & File Size Rule
- 250-line rule applies
- If service grows:
  split into:
  - `{domain}.query.ts` (filters/pagination builders)
  - `{domain}.mapper.ts` (DTO mapping)
  - `{domain}.policy.ts` (authorization rules)
  - `{domain}.validator.ts` (domain validations beyond schema)

---

# 9. Consistency Patterns (Recommended)

Create predictable actions:
- `list{Entity}`
- `get{Entity}ById`
- `create{Entity}`
- `update{Entity}`
- `delete{Entity}` (only if needed)

Avoid:
- `doStuff`, `processData`, `handleThing`

---

# 10. Verification Checklist (Mandatory)

Before marking feature complete:

- [ ] Controller only orchestrates (no DB queries, no business logic)
- [ ] Service has typed input + typed output
- [ ] List services implement DB pagination + filters + sort whitelist
- [ ] Tenant scoping applied in service queries
- [ ] Services throw typed errors (no raw strings)
- [ ] Response shape matches API contract standards
- [ ] Heavy transforms moved to mappers/helpers
- [ ] File sizes < 250 lines (split if needed)

---

# 11. Golden Rule

Controllers = Transport
Services = Business logic
DB layer = Data access

If logic leaks upward, the framework becomes unmaintainable.


## 6. Example
```javascript
// Good
class UserService {
  async create(userData) {
    if (userData.age < 18) throw new ValidationError();
    return db.create(userData);
  }
}

// Bad
class UserController {
  async create(req, res) {
    if (req.body.age < 18) return res.status(400).send();
    const user = await db.create(req.body);
    res.status(201).send(user);
  }
}     
