---
name: dead-code-and-change-audit
description: Always-on code hygiene skill that runs on every task and every code change
  to detect dead code, stale references, orphaned logic, unused imports, unused files,
  broken linkages, and partial refactors. Enforces continuous cleanup so no dead code
  is left behind. Audit code changes for stale references, unused code, and partial
  refactors Use to audit code changes for dead code, stale references, orphaned logic,
  and partial refactors.
disable-model-invocation: false
---
# DEAD CODE AND CHANGE AUDIT

## OBJECTIVE

This skill must run on **every coding task** and **every code change**.

Its purpose is to continuously inspect the codebase for:

- dead code
- unused imports
- unused variables
- unused functions
- unused components
- unused hooks
- unused services
- unused API wrappers
- unused Redux slices/selectors/thunks
- unused routes
- stale types/interfaces
- orphaned helpers/utils
- outdated constants
- broken references after refactor
- partially removed flows
- leftover files from previous implementations
- duplicate logic introduced during changes
- unreachable branches
- modified code paths no longer referenced anywhere

This skill exists to ensure the codebase stays **clean, linked, minimal, and production-safe**.

---

## ALWAYS-ON RULE

Run this skill:

- on every task
- before implementation
- during implementation
- after implementation
- before final delivery

This is not optional.

Do not treat cleanup as a separate later task.

Code hygiene must happen continuously while working.

---

## PRIMARY PRINCIPLE

Whenever code is added, removed, moved, renamed, or refactored:

- verify all references
- verify all imports
- verify all exports
- verify all routes
- verify all store linkages
- verify all service/API usage
- verify all type usage
- verify all domain ownership

If something becomes unused, stale, duplicated, or orphaned, it must be cleaned immediately.

Do not leave dead code behind.

---

## ENFORCEMENT SCOPE

This skill applies to the full codebase, including but not limited to:

### Frontend
- pages
- routes
- layouts
- components
- subcomponents
- hooks
- API wrappers
- services
- Redux slices
- Redux thunks
- Redux selectors
- constants
- helpers
- utils
- types
- styles
- assets
- feature flags
- guards
- loaders
- empty/error state components

### Backend
- route registrations
- controllers
- services
- schemas
- validators
- models
- repositories
- jobs/workers
- queues
- event handlers
- middleware
- helpers
- constants
- DTOs/types
- cron logic
- integrations
- observability hooks

### Cross-layer
- request/response contracts
- route maps
- domain references
- feature toggles
- shared utilities
- shared types
- docs referring to removed flows

---

## MANDATORY EXECUTION FLOW

## PHASE 1 — PRE-CHANGE AUDIT

Before making any change:

1. Identify the exact feature, route, module, or domain being touched
2. Identify all linked layers
3. Identify likely dead or duplicate code around that area
4. Inspect whether the current flow is partially deprecated already
5. Confirm whether older files still exist from previous versions

Questions that must be answered:

- What files currently power this feature?
- Which files only appear related but are no longer used?
- Are there parallel implementations?
- Are there old slices/hooks/services still linked nowhere?
- Are there stale routes or menu entries?
- Are there backup components or old versions left in the repo?

Do not start editing blindly.

---

## PHASE 2 — DURING-CHANGE LINKAGE CONTROL

While implementing:

- remove replaced code paths
- remove stale imports immediately
- update all references when renaming
- check route registrations after moving files
- check selectors after slice changes
- check services after API refactors
- check schema/model references after backend refactors
- check all callers after changing function signatures

Do not allow:

- old and new logic to coexist without reason
- temporary duplicate implementations
- commented-out dead code
- “keep for later” unused files
- unreachable branches after condition changes
- partially migrated code paths

Temporary code must not be left behind.

---

## PHASE 3 — POST-CHANGE DEAD CODE SWEEP

After implementation, perform a structured cleanup sweep.

### Sweep 1 — File-Level
Check for:

- unused files
- duplicate replacement files
- legacy backup files
- old components no longer imported
- dead pages no longer routed
- dead services no longer called
- dead backend handlers no longer registered

### Sweep 2 — Symbol-Level
Check for:

- unused imports
- unused exports
- unused variables
- unused types
- unused interfaces
- unused enums
- unused constants
- unused helper functions
- unused selectors
- unused thunks
- unused hooks

### Sweep 3 — Flow-Level
Check for:

- broken route-to-page linkages
- broken controller-to-service linkages
- broken frontend-to-API contract usage
- broken domain ownership after file moves
- incomplete refactors
- stale references in navigation/sidebar/menu
- stale feature flags
- stale modal/dialog trigger paths
- stale validation schemas
- stale query params or filters no longer used

### Sweep 4 — Domain-Level
For the impacted domain, verify:

- all active files are still needed
- all removed behavior has been fully removed
- no old pattern remains beside the new pattern
- no store state is hanging without consumers
- no backend service exists without route/use-case
- no frontend component exists without usage

---

## CLEANUP RULES

### RULE 1 — DELETE UNUSED CODE
If code is confirmed unused and has no valid active purpose, remove it.

Do not keep dead code “just in case”.

Version control exists for history.

---

### RULE 2 — DO NOT COMMENT OUT DEAD CODE
Never leave old implementations commented out.

Delete them.

---

### RULE 3 — REMOVE PARTIAL REFACTOR LEFTOVERS
Whenever a flow is migrated:

- remove old wiring
- remove old state usage
- remove old hooks
- remove old API wrappers
- remove old route links
- remove old backend path registrations

A migration is incomplete if the old flow still lingers without purpose.

---

### RULE 4 — REMOVE UNUSED IMPORTS IMMEDIATELY
Unused imports must never remain after edits.

---

### RULE 5 — REMOVE DUPLICATE ABSTRACTIONS
If two helpers/services/components now do the same job because of refactor drift:

- consolidate them
- remove the stale one
- keep the canonical implementation only

---

### RULE 6 — CLEAN UNUSED TYPES
Types must be cleaned with the same discipline as logic.

Do not keep:

- stale interfaces
- outdated response types
- dead DTOs
- old form state types
- deprecated enums
- legacy payload shapes

---

### RULE 7 — CLEAN ROUTE AND NAVIGATION LEFTOVERS
When pages/features are removed or replaced, also remove:

- route definitions
- sidebar links
- menu entries
- guards
- breadcrumb config
- page titles/meta mappings
- role permission mappings tied only to dead routes

---

### RULE 8 — CLEAN STORE LEFTOVERS
When frontend state changes, also check:

- unused slice state
- dead reducers
- dead thunks
- dead selectors
- dead action creators
- state fields no longer consumed anywhere

---

### RULE 9 — CLEAN BACKEND LEFTOVERS
When backend logic changes, also check:

- dead controllers
- dead services
- dead schemas
- dead model methods
- dead queue jobs
- dead cron paths
- dead middleware
- dead route registrations
- dead validators
- dead mapper/transform helpers

---

### RULE 10 — CLEAN DOC LEFTOVERS
If architecture, route ownership, contracts, or flow paths changed:

- update the docs
- remove mentions of removed flows
- remove references to deleted modules
- keep docs aligned with actual active code

---

## CHANGE IMPACT CHECKLIST

For every task, explicitly verify:

- [ ] What files were modified?
- [ ] What files became obsolete because of those modifications?
- [ ] What imports became unused?
- [ ] What exports now have no consumers?
- [ ] What hooks/services/selectors are now unreferenced?
- [ ] What routes or controllers are now stale?
- [ ] What types/interfaces are now outdated?
- [ ] What duplicated logic was introduced or exposed?
- [ ] What old flow was replaced and must be removed?
- [ ] What docs now need cleanup?

This checklist must be completed every time.

---

## REQUIRED ACTION STYLE

When performing changes:

- prefer full cleanup over partial cleanup
- prefer canonical implementations over duplicates
- prefer removal over accumulation
- prefer clear ownership over historical leftovers
- prefer small focused files over stale large files

Every change should leave the codebase cleaner than before.

---

## DELIVERY REQUIREMENT

Before marking any task complete, confirm:

- no dead imports remain
- no dead code introduced by this task remains
- no replaced code path is left behind
- no stale route/store/service wiring remains
- no orphaned file remains in the impacted flow
- no stale contract/type remains in the impacted area

If any of the above fails, the task is not complete.

---

## ABSOLUTE RULE

Never finish a coding task by only making the new code work.

A task is complete only when:

1. the feature/change works
2. the linkage is correct
3. the old/stale/dead code is removed
4. the impacted domain is cleaner than before

Dead code cleanup is part of implementation, not an optional follow-up.