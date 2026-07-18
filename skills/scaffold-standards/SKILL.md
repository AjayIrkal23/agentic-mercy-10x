---
name: scaffold-standards
description: "ALWAYS invoke when scaffolding a new backend or full-stack domain, a route/controller/service/schema skeleton, or a standard list and CRUD feature structure."
disable-model-invocation: false
schema: 1
category: backend
surfaces:
- backend
platforms:
- linux
- darwin
- windows
token-cost: 1908
triggers:
  keywords:
  - backend
  - crud
  - domain
  - entry
  - feature
  - file
  - frontend
  - full-stack
  - implementation
  - list
  - minimum
  - plan
  - planning
  - points
  - route/controller/service/schema
  - scaffold
  - scaffolding
  - skeleton
  - skeletons
  - standard
  - standards
  - structure
  - tree
  paths:
  - /router/
  - /routes/
  - route.ts
  - route.tsx
  - routes.ts
  intents:
  - backend
---
# Scaffold Standards

## Overview

This skill defines the standard skeleton for new domains and features.

Use it when consistency of file layout, naming, and build order matters more than one-off speed.

## Use When

- Creating a new backend domain.
- Adding a new route/controller/service/schema flow.
- Scaffolding a new full-stack CRUD or list feature.
- Defining the minimum skeleton before implementation starts.

## Backend Skeleton

Pick the block matching the repo's actual stack — confirmed against 3 reference codebases (site-sync-vista = Fastify/TS, MARKETING REPORT AUTOMATION = FastAPI/Python, GO_UDP/UDP_PLATFORM = Go/chi). Don't force one stack's file-naming onto another.

### Node/TypeScript (Fastify/Express style)

```text
/routes/{domain}.routes.ts
/controller/{domain}/{verb}-{domain}.controller.ts
/schemas/{domain}/{verb}-{domain}.schema.ts
/schemas/{domain}/{domain}-response.schema.ts
/models/{domain}.model.ts
/models/schema/{shared-subschema}.schema.ts
/services/{domain}/{verb}{Domain}.ts
/utils/{domain}/{helper}.ts
/types/{domain}/{name}.ts
```

- Controller folder is singular `controller/` in some repos, plural `controllers/` in others — check the existing repo before scaffolding, don't assume.
- Controller and schema files are kebab-case, verb-first: `create-camera-type.controller.ts`, `list-expenses.schema.ts`.
- Service files are either bare verb+noun (`createCameraType.ts`) or explicitly suffixed (`createProjectMapFeature.service.ts`) — match the existing repo's convention within that domain, don't mix both inside one domain folder.
- Model files are kebab-case, one per collection (`{resource}.model.ts`); shared embedded sub-schemas live in `models/schema/`.
- Centralize errors in one `utils/errors.ts` (`AppError` class + `isAppError()` guard) consumed by a single app-level `setErrorHandler` — not per-route try/catch.
- If no real queue library is wired (check for actual consumers, not just an installed dependency), background jobs are polling loops under `/jobs/{job-name}.job.ts` guarded by a DB-backed distributed lock (`acquireLock`/`releaseLock`), not BullMQ workers.

### Python (FastAPI)

```text
/app/routes/{domain}.py              # APIRouter, registered into routes/__init__.py's api_router
/app/controllers/{domain}.py         # thin handlers: {verb}_{domain}_controller
/app/controllers/{domain}_{variant}.py   # config/admin variants get a suffixed sibling file, not a subfolder
/app/schemas/{domain}.py             # pydantic request/query DTOs + Literal[...] sort/filter whitelists
/app/schemas/{domain}_record.py      # response ("Public") DTO, kept separate from the request DTO
/app/models/{domain}.py              # Beanie/ORM Document
/app/services/{domain}/{verb}.py     # one file per verb: list.py, create.py, update.py, delete.py, export.py
/app/services/cron/{domain}.py       # thin scheduled-job entrypoint only; real logic stays in services/{domain}/
/app/utils/{domain}/{helper}.py
/app/core/{errors,responses,exception_handlers,scheduler}.py   # cross-cutting infra, not per-domain
```

- One file per domain per layer (not one-file-per-action) — the folder name (`routes/`, `controllers/`, `schemas/`) already disambiguates the layer, so files are just `{domain}.py`, snake_case.
- Compound/config domains get a suffixed sibling file (`credit_report_config.py`), not a nested subfolder.
- Response DTOs suffixed `Public`; query/sort DTOs suffixed `Query`/`SortBy`.
- Centralized error taxonomy: `core/errors.py` (`AppError` base with `status_code`/`code`, subclassed per error kind) + `core/exception_handlers.py` mapping to the shared envelope in `core/responses.py`.
- Scheduling (APScheduler) lives in `core/scheduler.py` as a start/shutdown-managed singleton with string job-id constants — no top-level `jobs/`/`workers/` folder; `services/cron/{domain}.py` is a thin entrypoint that delegates to the domain's own `services/{domain}/poller.py`/`ingest.py`.

### Go (chi or similar router)

```text
/internal/routes/{domain}/register.go          # func Register(router chi.Router, service ...)
/internal/controllers/{domain}/{verb}.controller.go
/internal/controllers/{domain}/service_interfaces.go   # controller-owned, narrow interface onto the service
/internal/services/{domain}/{verb}.service.go
/internal/services/{domain}/store.go           # persistence — distinguished from business logic by filename, not folder
/internal/schemas/{domain}/{verb}.schema.go     # wire-level request/response structs
/internal/types/{domain}/{verb}_params.go       # internal params passed controller -> service
/internal/models/{resource}.go                  # DB-facing struct (GORM/etc.)
```

- Package name = folder name, all-lowercase-no-separator (`locoeventpacket`, `superadmin`) — applied consistently across every layer folder for the same domain.
- Three-tier data-shape split: `schemas` (wire-level request/response) -> `types` (internal params) -> `models` (persistence) — don't collapse these into one struct.
- One `routes/{domain}/register.go` per domain exposing a single `Register(router chi.Router, ...)`; a top-level `routes/routes.go` aggregates every domain's `Register` call under auth-scoped `router.Group` blocks.
- Centralized error/envelope contracts live in `internal/contracts/` (`errors.go` -> `DomainError` + `NormalizeError`; `envelope.go` -> `SuccessResponse`/`ErrorResponse` + `WriteSuccess`/`WriteJSON`) — not redefined per domain.
- Tests are standard `_test.go`, colocated in the same package as the code under test — never a parallel `tests/` tree.
- A protocol-specific ingestion/listener layer (UDP/TCP/etc.), if the service has one, stays fully separate from the `controllers/services/routes` HTTP layers, organized by pipeline stage (decode -> process -> sink), and is wired from `internal/app/`, not from any domain's `routes/`.

Keep reusable backend types in the stack's types layer (`/types/{domain}/{name}.ts`, `app/schemas/{domain}.py`, or `internal/types/{domain}/*.go`) instead of declaring them inline inside config, routes, controllers, services, or queue modules.

If the repo already uses controller-mirror feature folders, scaffold into that feature-folder pattern instead of forcing flat per-action service files.

Use the query helper and mapper files when the domain needs list/query logic or DTO conversion.

## Standard Action Set

Where applicable:

- `list`
- `getById`
- `create`
- `update`
- `delete`

## Contract Expectations

- Success responses follow the standard envelope.
- List features use paginated backend-driven query behavior.
- Errors follow the shared error envelope.

## Suggested Build Order

1. Lock the contract.
2. Add schema.
3. Add service.
4. Add controller and route.
5. Add helpers or mappers if needed.
6. Add frontend integration if the feature is full-stack.

## Naming Rules

- TypeScript/Node: folders kebab-case, identifiers camelCase/PascalCase, controller/schema files verb-first kebab-case.
- Python: folders and files snake_case, one file per domain per layer.
- Go: package/folder names lowercase-no-separator (no underscore or hyphen); files snake_case with a `.controller.go`/`.service.go`/`.schema.go` suffix.
- Whichever stack: keep route/controller/service naming aligned across the stack (same domain name in every layer).

## Combine With

- `api-contract-standards` for envelope and compatibility rules.
- `service-layer-standards` for boundary discipline.
- `backend-api-standards` for list/query semantics.

## References

- Use `references/full-guide.md` for the longer strict version with full-stack scaffolding details and extended examples.
