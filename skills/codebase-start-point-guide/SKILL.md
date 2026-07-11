---
name: codebase-start-point-guide
description: Deterministic startup flow for engineers and agents to read the right docs, confirm contracts,
  scope impacted layers, and create an execution plan before making changes in any repository.
disable-model-invocation: false
schema: 1
category: general
surfaces:
- general
platforms:
- linux
- darwin
- windows
token-cost: 1856
triggers:
  keywords:
  - agents
  - changes
  - codebase
  - confirm
  - contracts
  - create
  - deterministic
  - docs
  - engineers
  - execution
  - flow
  - guide
  - impacted
  - layers
  - making
  - plan
  - point
  - read
  - repository
  - right
  - scope
  - start
  - startup
  paths: []
  intents:
  - general
---
# Start point guide (repository-agnostic)

## OBJECTIVE

Defines a **baseline startup process** for engineers and agents before implementation.

Ensures work begins with:

- architectural context from **this** repo’s docs
- a documented reading order when one exists
- contract awareness across layers when APIs change
- explicit scope and validation planning

Do not begin implementation before following this guide **as far as the repo’s documentation allows**.

---

## MANDATORY READING ORDER

### RULE 0 — READ `AGENTS.md` FIRST

If `AGENTS.md` is present in the repository:

- Read it first
- Treat it as the primary instruction source for agent behavior and constraints

If `AGENTS.md` is not present:

- Continue using `README.md`, `CONTRIBUTING.md`, and `docs/` (or equivalent)

---

### RULE 1 — FRONTEND DOCS (BEFORE TOUCHING FRONTEND SOURCE)

Locate the frontend handbook for **this** repo. Common locations:

- `frontend_docs/`, `docs/frontend/`, `apps/<app>/docs/`, or sections in `docs/`.

If the repo defines an **agent reading order** or playbook under those trees, follow **that** order exactly (filenames vary).

Otherwise:

1. Read the frontend area **README** or overview
2. Read routing and data-fetching guides if the task touches navigation or APIs
3. Read domain-specific pages only for the features you change

**Do not** assume product-specific domain doc names (e.g. a single app’s “admin” or “devices” guides). Use whatever domain docs **your** tree actually contains.

Do not edit frontend code before reading the **relevant** docs for the task.

---

### RULE 2 — BACKEND DOCS (BEFORE TOUCHING BACKEND SOURCE)

Locate the backend/server handbook: e.g. `server_docs/`, `docs/backend/`, `docs/api/`, or service READMEs.

Before changing backend code, identify the **real source root** for this repo (`cmd/`, `internal/`, `server/`, `src/`, `api/`, etc.) from existing layout and `AGENTS.md`—not every repo uses `server/src/`.

If a playbook defines order, follow it. If not:

1. Read backend overview / runtime entrypoints when relevant
2. Read routing and contract docs when endpoints change
3. Read data and domain docs when persistence or business rules change

Do not edit backend code before reading the **relevant** docs for the task.

---

### RULE 3 — CROSS-CHECK CONTRACTS ACROSS LAYERS

Whenever request or response shapes may change:

1. Find the **canonical API contract doc** on the server (whatever path your repo uses).
2. Find the **canonical client contract or API integration doc** on the frontend.
3. Update **both** (and shared linkage / changelog files your project maintains) so they stay consistent.

Never change one side of a contract without validating the other.

**Example** of one possible doc pairing (yours may differ): see [references/examples/sample-doc-tree.md](references/examples/sample-doc-tree.md).

---

## REQUIRED SKILL STACK

### ALWAYS APPLY

- `project-reference-linkage`

### FOR FRONTEND CHANGES

Apply the Frontend Core Compliance Set:

- matching Build Web Apps plugin skill first when available; use `build-web-apps:frontend-app-builder` for new UI/redesign/dashboard/game/site/hero/visual surfaces and default narrow React/Vite/UI/code work to `build-web-apps:react-best-practices`
- `frontend-standards-always-follow`
- `frontend-structure-standards`
- `frontend-response-handling`
- `frontend-server-data-patterns`
- `frontend-api-standards`
- `react-hooks-patterns`

Additionally apply when relevant:

- `ui-ux-pro-max` for visual direction and design-system research
- `tailwind-design-system` when tokens, layout system, or shared components are touched

---

### FOR BACKEND OR API CHANGES

Apply the Backend Core Compliance Set:

- `backend-standards-always-follow`
- `service-layer-standards`
- `backend-api-standards`
- `backend-error-handling`
- `backend-performance-standards`

Additionally apply when relevant:

- `api-contract-standards` for response envelopes, list metadata, or contract compatibility
- `scaffold-standards` for new domain or feature scaffolding

---

### FOR NEW DOMAIN OR FEATURE SCAFFOLDING

Apply:

- `scaffold-standards`

---

### FOR TOOLING OR MCP-HEAVY WORKFLOWS

Apply:

- `mcp-usage-standards`

---

## 30-MINUTE STARTUP FLOW

### STEP 1 — CONTEXT LOCK (5 MINUTES)

- Read the mandatory docs available in **this** repo in the order defined above (or the repo-defined playbook).
- Determine whether the task is:
  - Frontend
  - Backend
  - Full-stack

Do not continue until task type is clear.

---

### STEP 2 — SCOPE MAP (5 MINUTES)

List all impacted layers before editing.
If the repo is indexed, use `jcodemunch` first to map routes, pages, controllers, services, schemas, components, API modules, stores, and direct dependencies for broad discovery. Use shell/file tools immediately for exact paths, literal text, dirty or untracked files, stale or ambiguous indexes, small known scopes, direct verification reads, and command execution.

Possible frontend layers:

- route
- page
- component
- store
- API layer

Possible backend layers:

- route
- controller
- service
- schema
- model

Confirm domain ownership from docs before making changes.

Do not guess ownership.

---

### STEP 3 — CONTRACT CHECK (5 MINUTES)

Validate all relevant contract details:

- request keys
- response keys
- query params
- pagination expectations
- sorting expectations
- filtering expectations

Explicitly mark whether the task has cross-layer contract impact.

---

### STEP 4 — EXECUTION PLAN (10 MINUTES)

Create a small ordered checklist before coding.

The plan must include:

- implementation steps
- validation steps
- documentation update steps if required

Rules:

- keep transport/adapters thin where that is the project norm
- keep domain logic in the layer the repo standard names (services, use-cases, etc.)
- keep client behavior aligned with server contracts

---

### STEP 5 — VALIDATION PLAN (5 MINUTES)

Define the verification scope before implementation.

Possible validation includes:

- unit tests
- integration tests
- UI tests
- manual verification

Manual verification must consider:

- success state
- error state
- empty state
- loading state

For list pages or endpoints also verify:

- pagination
- sorting
- filtering

---

## ACTION PLAN TEMPLATE

Use this template before implementation begins.

```md
## Task Action Plan

### 1) Task Summary
- Objective:
- Domain:
- Change type: Frontend / Backend / Full-stack

### 2) Mandatory Docs Read
- [ ] AGENTS.md (if present)
- [ ] Frontend handbook README / playbook (paths as defined in this repo)
- [ ] Backend handbook README / playbook (paths as defined in this repo)
- [ ] Contract / API docs (client + server) if shapes change

### 3) Impacted Files (Expected)
- Frontend:
- Backend:
- Contracts:

### 4) Implementation Steps
1.
2.
3.

### 5) Validation Steps
- [ ] Type/lint/tests pass
- [ ] Success path verified
- [ ] Error path verified
- [ ] Empty/loading states verified
- [ ] Pagination/filter/sort verified (if list endpoint/page)

### 6) Documentation Updates
- [ ] Updated frontend docs if route/state/api/component behavior changed
- [ ] Updated server docs if route/contract/data/ops behavior changed

### 7) Delivery Notes
- Risks:
- Follow-ups:
```

## References

- [examples/sample-doc-tree.md](references/examples/sample-doc-tree.md) — one possible numbered `frontend_docs/` / `server_docs/` layout (illustrative)
