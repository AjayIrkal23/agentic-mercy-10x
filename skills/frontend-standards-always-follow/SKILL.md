---
name: frontend-standards-always-follow
description: Use when any web/frontend UI, React, Next.js, Vite, dashboard, component,
  CSS, client data, hook, state, styling, browser UX, or frontend performance work
  is requested. Apply the always-on frontend baseline Use after the matching Build
  Web Apps plugin skill for any web/frontend task.
disable-model-invocation: false
---
# Frontend Standards Always Follow

> ## 🔒 MANDATORY COMPANION BUNDLE — load ALL now, every time, no exceptions
>
> Reading this skill is the trigger. Before doing ANY frontend work you MUST
> immediately `Skill`-invoke **all** of the following, end to end. Not "when the
> surface is touched" — **always**, as a set, the moment this baseline loads:
>
> 1. `frontend-structure-standards`
> 2. `frontend-api-standards`
> 3. `frontend-response-handling`
> 4. `frontend-server-data-patterns`
> 5. `frontend-code-review`
> 6. `frontend-ui-engineering`
> 7. `react-hooks-patterns`
> 8. `tailwind-design-system`
> 9. `browser-testing-with-devtools`
> 10. `vite-react-best-practices`
>
> This is non-negotiable. Do not skip, defer, or sample a subset. If any one is
> not yet loaded this turn, load it now before writing frontend code.

## Overview

This is the always-on frontend baseline.

Apply it immediately after the matching Build Web Apps plugin skill for any frontend task. The companion bundle above is loaded in full alongside it — every time, not conditionally.

## Always Apply

- Inspect existing route pages, components, hooks, API modules, and stores before changing behavior.
- Preserve current contracts and business logic unless the task explicitly changes them.
- Preserve the route-page vs feature-component split: default to `src/pages/<domain>/<route>/index.tsx` for route entry parents and `src/components/<domain>/<feature>/*` for route-owned UI unless repo-local docs override it.
- Prefer Tailwind utilities first for layout, spacing, sizing, typography, breakpoints, and common state classes.
- Prefer component-local `*.module.css` files for feature-local visuals, pseudo-elements, keyframes, layered backgrounds, and complex selectors.
- Keep `src/index.css` limited to Tailwind import, domain stylesheet imports, and global base/reset selectors.
- Keep shared non-module domain styling in `src/styles/<domain>/index.css`.
- Keep UI components free of direct API calls.
- Keep app-owned frontend types in central domain files under `src/types/<domain>/...`
- Import custom types into components, hooks, API modules, and stores instead of declaring them inline
- When feature UI grows stateful or JSX-heavy, extract feature-local hooks and keep the component as a thin orchestrator.
- Prefer `src/components/<domain>/<feature>/hooks/*` for feature-owned hooks and `src/hooks/<domain>/*` only when the hook is reused across features.
- Prefer focused UI type files such as `src/types/<domain>/<feature>-ui.ts` for feature props and local UI state.
- Keep manually maintained frontend source files at or below 250 lines. If a touched file is already over 250 lines, split or reduce it before adding more behavior unless the user explicitly scopes that cleanup out.
- Reuse existing primitives, helpers, and patterns before creating new ones.
- Keep files focused and split obvious multi-responsibility files.
- Remove duplication, stale imports, and replaced UI logic while you work.

## Non-Negotiables

- No guessing when the repo already shows a pattern.
- No client-side filtering or pagination for server-backed datasets.
- No response-shape changes without explicit intent.
- No inline ownership of app-owned custom `type` or `interface` declarations inside frontend modules.
- No touched manually maintained frontend source file may remain over 250 lines without an explicit blocker.
- No monolithic frontend files when decomposition is straightforward.
- No feature or page selectors added directly to `src/index.css` once domain and module styling ownership exists.
- No CSS Modules routed through root CSS or domain CSS.
- No mixed old/new implementations left behind without a reason.

## Load Next When Needed

- `frontend-structure-standards` for folder layout, component boundaries, file decomposition, and the detailed `src/types/<domain>/...` ownership model.
- `frontend-response-handling` for API parsing, normalized errors, and backend-driven list behavior.
- `frontend-server-data-patterns` for tables, lists, search, and query-state flows.
- `react-hooks-patterns` for complex local state, effects, refs, reducers, or custom hook extraction.
- `tailwind-design-system`, `ui-ux-pro-max`, `gsap-ui-motion`, or `agentation-react` only when the task explicitly needs them.

## Completion Checklist

- Existing frontend patterns were inspected first.
- Route entry parents remained separate from feature-owned UI unless the repo explicitly uses a different convention.
- Reuse beat reinvention where possible.
- Data access stayed outside presentational UI.
- Files remained focused and readable.
- Root, domain, and feature styling ownership stayed in the correct layer.
- No stale frontend code was left behind.
