---
name: frontend-structure-standards
description: Use when frontend work needs decisions about folder layout, module boundaries,
  file decomposition, or where app-owned frontend types should live. Organize maintainable
  frontend modules Use to plan frontend component, hook, and module boundaries.
disable-model-invocation: false
---
FRONTEND STRUCTURE STANDARDS

1. OBJECTIVE
- Maintain clean, scalable, production-grade code
- Preserve business logic and existing patterns
- Ensure maintainability, performance, and correctness

---

2. MODULARITY RULES

- Files should remain small and focused
- When a file grows large:
  - Extract UI subcomponents
  - Extract hooks for logic
  - Extract helpers/utilities
- Parent components should orchestrate, not contain heavy logic

---

3. PROJECT STRUCTURE

Use domain-based organization.

Example:

src/
  api/<domain>/
    get.ts (s) (single api each file)
    create.ts (s) (single api each file)
    update.ts (s) (single api each file)

  components/<domain>/<feature>/
    FeatureComponent.tsx
    hooks/
      useFeatureState.ts

  pages/<domain>/<route>/
    index.tsx

  hooks/<domain>/useSharedFeature.ts
  services/<domain>/serviceshere
  utils/
  types/<domain>/
    feature-ui.ts

Rules:
- One domain per folder
- Do not mix domains
- By default, route entry parents live under `src/pages/<domain>/<route>/index.tsx`
- Page files should orchestrate route concerns and compose feature UI, not own large UI trees
- Route-owned UI and related subcomponents should live under `src/components/<domain>/<feature>/*`
- Feature-owned hooks may live under `src/components/<domain>/<feature>/hooks/*` when the logic is only used by that feature
- Shared hooks used across multiple features may live under `src/hooks/<domain>/*`
- Shared domain support can stay in a repo's established shared folder pattern
- No API calls directly in components
- `src/types/<domain>/...` is the canonical home for app-owned frontend types
- Feature-specific UI prop/state contracts should use focused files such as `src/types/<domain>/<feature>-ui.ts` instead of inline component ownership
- Root global CSS belongs in `src/index.css` and should stay a thin shell
- Domain-shared non-module CSS belongs in `src/styles/<domain>/index.css`
- Feature-local styling belongs in `src/components/<domain>/<feature>/*.module.css`
- CSS Modules must be imported directly by the owning component, not routed through domain CSS or root CSS
- Tailwind utilities should own layout, spacing, sizing, typography, breakpoints, and common state classes by default
- CSS Modules are the escape hatch for pseudo-elements, keyframes, layered backgrounds, complex selectors, and feature-local skins
- Once a repo has domain and feature style ownership, monolithic app CSS files are a structural violation
- Repo-local docs may override this default when a project intentionally uses a different layout

Example style topology:

src/
  index.css
  styles/
    theme/
      index.css
    superadmin/
      index.css
  components/
    theme/
      theme-toggle.tsx
      theme-toggle.module.css
    superadmin/
      login/
        superadmin-login-page.tsx
        superadmin-login-page.module.css

---

4. TYPE OWNERSHIP

Frontend type ownership must mirror the backend pattern.

Canonical layout:

src/
  types/
    dashboard/
      dashboard-hero.ts
      endpoint-snapshot.ts
    readiness/
      status.ts
    api/
      error.ts
    theme/
      theme.ts

Rules:
- Put all app-owned frontend `type` and `interface` declarations in `src/types/<domain>/...`
- Components, hooks, API modules, store modules, and services must import custom types instead of declaring them inline
- This applies to all frontend types, including component props, domain models, API contracts, store contracts, and app/theme types
- Keep one domain folder per concern and one focused file per boundary
- Use focused UI-type files such as `src/types/<domain>/<feature>-ui.ts` for feature component props, dialog state, and other feature-local UI contracts
- Do not create catch-all `types.ts` dumping grounds
- If a file currently owns types such as `src/app/theme-types.ts`, `src/api/types.ts`, or `src/store/<domain>/types.ts`, move that ownership under `src/types/<domain>/...` unless the file itself already lives there

Anti-patterns:
- No `interface Props` or equivalent custom prop contracts inside component files
- No feature-local dialog/page state interfaces inside `.tsx` files when a focused `src/types/<domain>/<feature>-ui.ts` file should own them
- No response or store contracts inside API modules, slice files, selector files, thunk files, hooks, or services
- No app-owned types left beside implementation files just because the type is small

---

5. COMPONENT DESIGN

Components must:
- Be reusable and focused
- Separate UI and logic
- Move repeated logic to hooks
- Move repeated UI to shared components
- Keep page and feature-shell components as thin orchestrators that delegate local state, query wiring, and dialog logic to hooks where appropriate

Performance discipline:
- Use React.memo when useful
- Use useMemo / useCallback for expensive or stable logic

Avoid:
- Large monolithic components
- Heavy calculations inside render
- Large inline functions in JSX
- Inline custom type ownership in `.tsx` files

---

6. API LAYER RULES

- Centralize API calls in api/ or services/
- Do not call APIs directly inside UI
- Normalize responses and type them
- Centralize error handling
- Keep API request and response contracts in `src/types/<domain>/...`, not inside API modules

---

7. STATE MANAGEMENT (IF USED)

Recommended structure:

store/<domain>/
  slice.ts
  selectors.ts
  thunks.ts (optional)

Rules:
- One domain per slice
- No UI logic in store
- Access state through selectors
- Side effects only in thunks or hooks
- Keep store-facing contracts in `src/types/<domain>/...`, not in `store/<domain>/types.ts`

Use global state only for:
- Auth/session
- Shared data
- Cached server data
- Configuration

---

8. CONTEXT AWARENESS

Before writing code:
1. Review existing components, hooks, and services
2. Review existing `src/types/<domain>/...` ownership before adding new types
3. Reuse logic when possible
4. Avoid duplication and circular dependencies

Never assume context.

---

9. PERFORMANCE PRINCIPLES

Prefer:
- Memoization
- Lazy loading
- Pagination or virtualization for large lists

Avoid:
- Large global state
- Unnecessary re-renders

---

10. TYPESCRIPT & NAMING

Naming:
- Components → PascalCase
- Hooks → useCamelCase
- Functions → camelCase
- Files → match export
- Type files → named for the owning UI boundary or contract, not generic `types`

Avoid:
- any unless unavoidable
- inconsistent naming
- hidden type ownership inside implementation files

---

11. CODE SAFETY

Do NOT:
- Change API response shapes
- Modify business logic without instruction
- Invent a colocated type pattern when a central domain type file should own the contract

You MAY:
- Improve readability
- Extract helpers
- Reduce duplication

---

12. FILE SIZE LIMIT

- No manually maintained frontend source file should be more than 250 lines.
- If a touched file exceeds 250 lines, it must be optimized and broken into:
  - Subcomponents
  - Custom hooks
  - Utility/helper files
  - Domain type files when inline contracts are contributing to file growth
  - Service/API layer separation where applicable
- Large frontend source files are considered a structural issue and must be refactored before adding more behavior unless the user explicitly scopes that cleanup out.

---

13. FINAL CHECK

- Structure is consistent
- Components are modular
- No direct API calls in UI
- No duplication
- App-owned frontend types live in `src/types/<domain>/...`
- Components, hooks, API modules, and stores import types instead of declaring them inline
- `src/index.css` contains only Tailwind import, domain CSS imports, and global base/reset rules
- Domain `index.css` files stay thin and shared
- Feature-local visuals live in colocated CSS Modules imported by the owner
- Imports are valid
- Code compiles logically

---

ABSOLUTE RULE

If unsure:
Inspect existing code first.
Never guess patterns.
