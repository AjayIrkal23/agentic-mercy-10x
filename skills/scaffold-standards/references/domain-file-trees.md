# domain-scaffold-patterns

> Absorbed into `scaffold-standards` (P5 consolidation). Method content preserved verbatim below.

---

# Domain Scaffold Patterns

## Use When
- Creating a new domain or feature skeleton.
- Establishing the minimum file tree before business logic is written.
- Standardizing backend and frontend module entry points for new work.

## Do Not Use
- Fixing a bug in an existing domain.
- Refactoring a single existing file.
- Defining response envelopes, error taxonomy, or UI polish in detail.

## Owns
- Required and optional file tree patterns for new domains.
- Naming conventions for domain folders and action files.
- Skeleton-level checklists for backend, frontend, and shared contract work.

## Does Not Own
- Canonical response envelope rules.
- Error taxonomy or centralized error behavior.
- Visual design direction or detailed component styling.

## Combine With
- `project-structure-map` for current codebase paths.
- `scaffold-standards` for concrete backend route/controller/service/schema skeleton details.
- `service-layer-standards`, `backend-api-standards`, and `api-contract-standards` for backend scaffolds.
- `frontend-structure-standards` and `frontend-server-data-patterns` for frontend scaffolds.

## Workflow
1. Confirm the work is truly a new domain or a new feature slice.
2. Choose the smallest scaffold that fits the task: backend, frontend, or full stack.
3. Create only the required entry points and leave optional pieces explicit.
4. Apply naming conventions before adding business logic.
5. Hand off detailed implementation to the relevant implementation skill.

## Output Contract
- A scaffold checklist or file tree plan for the new domain.
- Required versus optional files called out clearly.
- Any follow-up skills needed to finish the implementation.
