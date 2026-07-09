---
name: code-execution-standard
description: Use this skill in Code Mode to implement features safely and cleanly with modular structure, tests, validation, security, and strict quality gates. This skill is aware of and enforces all configured project skills.
metadata:
  author: ajayirkal
  version: "1.1"
  compliance: "Architectural Standards and Modular Development Protocol"
  depends_on_skills:
    - project-reference-linkage
    - api-contract-standards
    - backend-standards-always-follow
    - backend-error-handling
    - service-layer-standards
    - backend-api-standards
    - backend-performance-standards
    - scaffold-standards
    - frontend-standards-always-follow
    - frontend-structure-standards
    - frontend-response-handling
    - frontend-server-data-patterns
    - frontend-api-standards
    - react-hooks-patterns
    - mcp-usage-standards
    - ui-ux-pro-max
---

# Code Mode — Implementation Skill (Skill-Aware Production Standard)

You are in **Code Mode**.  
Your mission is to implement **production-ready, modular, and maintainable** code that strictly follows the project's architectural skills.

You are not just writing code — you are extending a structured framework.

---

# 0) Skill Context Awareness (MANDATORY)

All implementations MUST align with the configured routing matrix. Frontend implementation must load the matching Build Web Apps plugin plus the full Frontend Core Compliance Set before coding. Backend implementation must load the Backend Core Compliance Set before coding: `backend-standards-always-follow`, `service-layer-standards`, `backend-api-standards`, `backend-error-handling`, and `backend-performance-standards`.

### Structure (project-reference-linkage)
Use domain-based structure:

Backend:
- `/routes/index.ts`
- `/routes/{domain}/index.ts`
- `/routes/{domain}/{action}.route.ts`
- `/controllers/index.ts`
- `/controllers/{domain}/index.ts`
- `/controllers/{domain}/{action}.controller.ts`
- `/controllers/{domain}/{feature}/{action}.controller.ts`
- `/schemas/{domain}/{action}.schema.ts`
- `/schemas/{domain}/{feature}/{action}.schema.ts`
- `/types/{domain}/{name}.ts`
- `/services/{domain}/{action}.service.ts`
- `/services/{domain}/{feature}/index.ts` with action entry files and feature-local helpers when the repo uses controller-mirror feature folders
- `/models/{domain}/{ModelName}.ts`

Frontend:
- `/components/{domain}/`
- `/components/{domain}/{feature}/hooks/` for feature-owned UI logic
- `/hooks/{domain}/` for shared cross-feature hooks
- `/api/{domain}/` or `/apis/{domain}/` depending on repo-local docs
- `/store/{domain}/`
- `/types/{domain}/` including focused files such as `<feature>-ui.ts` for feature props and local UI state

Never invent new folder structures.

---

### API Contracts (api-contract-standards)
All endpoints MUST:
- Return consistent success/error structure
- Paginate list endpoints
- Use backend-driven filters and sorting

Never break response shapes.

---

### Backend Behavior (Backend Core Compliance Set)
- Filtering must be DB-level
- Pagination mandatory for lists
- Sort keys whitelisted
- Queries validated via schemas

---

### Error Handling (backend-error-handling)
- Use typed errors
- Do not expose stack traces
- Use centralized error handling

---

### Service Layer (service-layer-standards)
- Controllers must remain thin
- Business logic belongs in services
- Services must not depend on HTTP layer

---

### Scaffolding (scaffold-standards)
- Follow full domain skeleton
- Maintain consistent naming
- Implement list/get/create/update patterns where applicable

---

### Frontend State (`frontend-response-handling` and `frontend-server-data-patterns`)
- Query-driven API calls
- No client-side filtering for server datasets
- Page → store → api → backend flow

---

### Performance Rules
- No unbounded DB queries
- Use indexes for filters
- Avoid unnecessary rerenders
- Paginate large datasets

---

### MCP Usage (mcp-usage-standards)
Use MCP tools when:
- Schema or DB structure unclear
- Repo patterns unclear
- External documentation required

Never expose tokens or secrets.

---

### UI/UX Quality (`ui-ux-pro-max`)
If UI involved:
- Reuse components
- Maintain premium UI consistency
- Implement loading/empty/error states
- Ensure responsiveness and performance

---

# 1) Implementation Standards (Non-Negotiable)

### A) No Guessing
If required information is missing:
- Inspect repository first
- Use MCP if needed
- Ask minimal blocking questions only

Otherwise proceed with best-practice defaults and clearly state assumptions.

---

### B) Modularity & File Size
Keep files small:
- Split helpers
- Split query builders
- Split mappers
- Respect 250-line rule

---

### C) Match Existing Patterns
Always:
- Follow naming conventions
- Follow folder structure
- Follow error handling style
- Reuse existing utilities

Do NOT introduce new patterns unnecessarily.

---

### D) Types & Validation
- Strict typing
- No `any` unless unavoidable
- Validate API inputs at schema boundary
- Return typed DTOs

---

### E) Security Defaults
- Never log secrets
- Validate inputs
- Protect endpoints
- Enforce tenant/user scope if applicable

---

### F) Observability
Add logging where relevant:
- key service operations
- failures
- slow operations (if critical)

---

### G) Performance
Always consider:
- Query efficiency
- Pagination
- Index usage
- Avoid N+1 queries

---

# 2) Implementation Workflow (MANDATORY)

## Step 1 — Confirm Scope
Restate:
- What feature or fix is required
- Impacted modules
- APIs or UI involved

---

## Step 2 — Inspect Existing Code
Mandatory:
- Check folder structure
- Check similar modules
- Reuse patterns

If uncertain:
Use MCP tools.

---

## Step 3 — Plan Changes
List:
- Files to create/modify
- Contracts and schemas
- Acceptance criteria

---

## Step 4 — Implement
Implement in order:
1. Schema
2. Service
3. Controller
4. Route
5. Frontend API
6. Store
7. Components

Follow scaffold standards.

---

## Step 5 — Tests
Minimum:
- Backend service test or validation scenario
- At least one negative path
- Frontend critical behavior test (if UI)

---

## Step 6 — Verify
Check:
- Type errors
- Lint
- Runtime correctness
- Pagination and filters working

---

## Step 7 — Provide Summary
Always include:
- What changed
- Why it changed
- How to test
- Risks or rollback steps

---

# 3) Output Rules

If code requested:
- Provide complete files or patch
- Include file paths
- Keep explanation concise

If code not requested:
- Provide structured plan
- Ask approval before large implementation

---

# 4) Quality Gates (MANDATORY)

Before finalizing:

- [ ] Structure follows domain standards
- [ ] Controllers thin
- [ ] Services contain business logic
- [ ] Pagination implemented where needed
- [ ] Filters backend-driven
- [ ] Errors structured
- [ ] Types strict-friendly
- [ ] No secrets logged
- [ ] UI follows frontend skills (if applicable)
- [ ] Summary provided

---

# 5) Stop Conditions

Ask questions only if:
- Data contracts unclear
- DB schema unclear
- Auth/tenant rules unclear
- Change risks breaking existing APIs

Otherwise proceed safely.

---

# 6) Golden Rule

Code must:
- Fit the architecture
- Respect all skills
- Be maintainable
- Be predictable
- Be production-ready
