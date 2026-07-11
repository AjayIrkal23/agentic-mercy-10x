---
name: react-hooks-patterns
description: Use when implementing or reviewing React component state, effects, refs, reducers, memoization,
  or custom hook extraction.
disable-model-invocation: false
schema: 1
category: frontend
surfaces:
- frontend
platforms:
- linux
- darwin
- windows
token-cost: 460
triggers:
  keywords:
  - component
  - custom
  - effects
  - extraction
  - hook
  - hooks
  - implementing
  - memoization
  - patterns
  - react
  - reducers
  - refs
  - reviewing
  - state
  paths:
  - .hook.
  - .jsx
  - .tsx
  - /components/
  - /hooks/use
  - /pages/
  - /src/hooks/
  - /store/
  - /views/
  - reducer.
  - redux
  - selector.
  - slice.
  - use-
  - useHook
  intents:
  - frontend
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

## Output Contract
- The chosen hook pattern and why it fits.
- Any effect dependencies, cleanup needs, or stale-closure risks.
- A recommendation for custom hook extraction when appropriate.
