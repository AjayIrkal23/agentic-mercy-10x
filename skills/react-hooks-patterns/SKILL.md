---
name: react-hooks-patterns
description: "React component state, effects, refs, reducers, memoization, and custom-hook extraction — including React 19 hooks (use, useActionState, useOptimistic, useFormStatus) and React Compiler-aware memoization guidance."
when_to_use: Use when implementing or reviewing useState/useReducer/useEffect/useRef logic, extracting a custom hook, checking effect safety or stale closures, or adopting React 19 Actions hooks.
paths:
  - "**/hooks/**/*.{ts,tsx}"
  - "**/use*.{ts,tsx}"
metadata:
  schema: 1
  category: frontend
  surfaces: [frontend]
  platforms: [linux, darwin, windows]
  token-cost: 700
  triggers:
    keywords: [hook, hooks, useState, useReducer, useEffect, useRef, useMemo, useCallback, custom hook, stale closure, derived state, useActionState, useOptimistic, useFormStatus, "use()", React Compiler, memoization]
    paths: [.hook., /hooks/use, /src/hooks/, use-, useHook, reducer., slice., selector.]
    intents: [frontend, implement, review]
---
# React Hooks Patterns

## Use When
- A React component needs local state or side effects.
- You are choosing between `useState`, `useReducer`, refs, memoization, or a custom hook.
- You are reviewing effect safety, stale closures, or derived state.
- A frontend architecture or planning task needs explicit decisions about state ownership, effect boundaries, or custom hook extraction.

## Do Not Use
- Styling-only changes.
- General frontend architecture without hook complexity.
- Framework-managed server data that should live outside local effects.

## Owns
- Safe hook selection and effect hygiene.
- Derived-state discipline and custom hook extraction.
- Memoization decisions that are justified by behavior, not habit.

## Does Not Own
- Module boundaries and file layout.
- Backend or API contract design.
- Visual styling or Tailwind implementation details.

## Combine With
- `architect-system-design` when frontend planning must account for state ownership, effect boundaries, or custom hook extraction.
- `frontend-standards-always-follow` for the always-on frontend baseline.
- `frontend-structure-standards` for where logic belongs.
- `frontend-server-data-patterns` when the component mirrors backend query state.
- `debug-investigation` for stale closure or effect regressions.

## Workflow
1. Prefer the simplest state model that matches the behavior.
2. Avoid effects when render or event logic is enough.
3. Do not store derived state that can be computed from current inputs.
4. Treat `useMemo` and `useCallback` as conditional tools, not defaults.
5. Extract a custom hook when logic becomes reusable or hard to read inline.

## React 19

- **`use(promise | context)`** reads a promise or context during render and may be called conditionally (unlike other hooks); pair promises with `<Suspense>`. Prefer `use(Ctx)` over `useContext` in new code.
- **Actions.** Pass an async function to `<form action>` or `startTransition`. `useActionState(action, initial)` → `[state, formAction, isPending]` owns submit state and errors; `useFormStatus()` reads the parent form's pending state from a child; `useOptimistic(value, reducer)` shows the expected result until the action settles and rolls back on error. No hand-rolled `isSubmitting` state.
- **Refs.** `ref` is a plain prop — no `forwardRef`; ref callbacks may return a cleanup function.
- **Memoization is conditional.** With the React Compiler on (`babel-plugin-react-compiler` via the Vite `react()` plugin's `babel` option), do not hand-write `useMemo`/`useCallback`/`memo` — keep them only when the compiler is off or a profiler shows a hot path. Never memoize "to be safe".
- **Context.** Render `<Ctx value={…}>` directly (no `.Provider`).
- **Document metadata / resources.** `<title>`, `<meta>`, `<link>` render anywhere and hoist to `<head>`; `preload`/`preinit` from `react-dom` for fonts and scripts.

## Output Contract
- The chosen hook pattern and why it fits.
- Any effect dependencies, cleanup needs, or stale-closure risks.
- A recommendation for custom hook extraction when appropriate.
