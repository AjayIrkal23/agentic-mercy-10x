---
name: project-reference-linkage
description: "ALWAYS invoke to understand the directory structure and cross-module relationships across components, feature hooks, frontend API layers, controllers, routes, schemas, and store slices — global project navigation and linkage standards."
disable-model-invocation: false
schema: 1
category: general
surfaces:
- general
platforms:
- linux
- darwin
- windows
token-cost: 1431
triggers:
  keywords:
  - api
  - components
  - controllers
  - cross-module
  - directory
  - feature
  - frontend
  - global
  - hooks
  - layers
  - linkage
  - navigation
  - project
  - reference
  - relationships
  - routes
  - schemas
  - slices
  - standards
  - store
  - structure
  - understand
  paths: []
  intents:
  - general
---
## Use When

- Before writing or modifying any file that imports from or exports to another module.
- When the agent needs to identify which controllers, routes, services, or store slices are affected by a schema or model change.
- On the first code write of any session — to anchor directory structure, naming conventions, and cross-module dependencies.
- When locating the correct file path for a new feature in an existing domain.

## Do Not Use

- As a replacement for running `jcodemunch` blast-radius checks — this skill describes the directory conventions; jcodemunch finds the actual dependents at runtime.
- For infrastructure-only sessions that do not touch application code.

# Project Reference & Linkage Standards

## 1. Mandatory Directory Map
To ensure "amazing" and "compact" code organization, all files must follow this domain-based structure. Use this map to locate files and verify linkages before making changes.

### Frontend Layers
- **Components:** `/components/{domain}/{filename}.tsx` — Reusable, memoized UI.
- **Feature Hooks:** `/components/{domain}/{feature}/hooks/{useHook}.ts` for feature-owned UI logic and `/hooks/{domain}/{useHook}.ts` for shared cross-feature hooks. Follow repo-local docs when a repository standardizes one path.
- **API Layer:** `/api/{domain}/{filename}.ts` or `/apis/{domain}/{filename}.ts` (single api in each file) — Domain-specific data fetching. Follow repo-local docs when a repository standardizes one path.
- **Redux Store:** `/store/{domain}/` — Contains `Slice.ts`, `Selectors.ts`, `Thunks.ts`, and `types.ts`.

### Backend Layers
- **Controllers:** `/controllers/index.ts`, `/controllers/{domain}/index.ts`, and either `/controllers/{domain}/{action}.controller.ts` or repo-local feature folders such as `/controllers/{domain}/{feature}/{action}.controller.ts` — Root registry, domain registry, and thin leaf handlers.
- **Routes:** `/routes/index.ts`, `/routes/{domain}/index.ts`, `/routes/{domain}/{action}.route.ts` — Root registry, domain-owned prefix registration, and leaf route plugins.
- **Schemas:** `/schemas/{domain}/{action}.schema.ts` for flat repos, or repo-local feature folders such as `/schemas/{domain}/{feature}/{action}.schema.ts` plus `/schemas/{domain}/{feature}/index.ts` — Validation definitions only.
- **Services:** `/services/{domain}/{action}.service.ts` for flat repos, or repo-local feature folders such as `/services/{domain}/{feature}/index.ts` with action entry files and helper modules like `shared.ts`, `audit.ts`, `reference.ts`, `constraints.ts`, `deleteGuards.service.ts`, `lookupToken.service.ts`, `mapping.ts`, `normalization.ts`, `snapshot.ts`, or `core.ts`.
- **Types:** `/types/{domain}/{name}.ts` — Domain contracts, DTOs, request generics, service I/O, and plugin options.
- **Mongo Models:** `/models/<collectionName>.model.ts` — Flat collection-specific Mongo definitions, indexes, and DB helpers.

Keep reusable backend types out of config, route, controller, service, and queue implementation files. Define them in the matching domain under `/types/**` and import them back.

---

## 2. Linkage & Context Awareness (STRICT)

Before writing or modifying code, the agent **MUST** perform the following checks to prevent broken references:

1. **Relationship Check:**  
   Review existing controllers, routes, models, and services to identify:
   - foreign key references  
   - shared utilities  
   - cross-module dependencies

   Use `jcodemunch-code-finder` as the code-discovery companion, then use `jcodemunch` when the repo is indexed to identify importers, references, dependency graphs, and related symbols for broad discovery. Use shell/file tools immediately for exact paths, literal text, dirty or untracked files, stale indexes, direct verification reads, and execution output.

2. **Impact Analysis:**  
   Determine whether changes to a:
   - schema  
   - model  
   - service  

   require updates to:
   - controllers  
   - routes  
   - frontend API layer  
   - store slices

   Use `jcodemunch-code-finder` and `jcodemunch` blast-radius, reference, and dependency tools when available for broad impacted-layer discovery, then verify candidate files with direct local reads.

3. **No Assumptions:**  
   Never guess project context.  
   Always infer relationships from the existing code structure.

---

## 3. Modularity & Performance Rules

- **The 250-Line Rule:**  
  ❌ NO file may exceed 250 lines.

- **Decomposition:**  
  If a file grows beyond 250 lines, split into logical subcomponents:
  - hooks  
  - helpers  
  - services  
  - utilities  

- **Frontend Rendering Optimization:**  
  Use:
  - `React.memo`
  - `useMemo`
  - `useCallback`

  to maintain frontend performance and prevent unnecessary re-renders.

---

## 4. Code Safety & Naming

- **Naming Conventions:**
  - camelCase → functions, variables
  - PascalCase → React components, classes, types

- **Safety Rule:**  
  ❌ Do NOT rename:
  - existing variables
  - API response fields
  - database columns
  - contract keys  

  These are system linkages and may break integrations.

- **Logic Integrity:**  
  Preserve:
  - business logic
  - validation rules
  - response formats  

  unless explicitly asked to refactor.

---

## 5. Verification Checklist

Before completing any change:

- [ ] Directory path matches `{layer}/{domain}/{file}` pattern  
- [ ] All cross-module dependencies reviewed  
- [ ] `jcodemunch-code-finder` plus `jcodemunch` or equivalent evidence used for linkage and impact checks when available  
- [ ] No file exceeds 250 lines  
- [ ] Naming consistent across API, Controller, and Service layers  
- [ ] No circular dependencies introduced  
- [ ] No broken references or imports  
