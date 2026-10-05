---
name: vitest-rtl
description: 'Vitest and React Testing Library conventions: one-shot vitest run, role-based queries, userEvent, async findBy, mocking at the network or module boundary, hook tests with renderHook and Redux-wrapped renders.'
when_to_use: Use when writing, fixing or reviewing Vitest tests, React component or hook tests, or when a test run hangs in watch mode.
metadata:
  schema: 1
  category: testing
  surfaces:
  - frontend
  platforms:
  - linux
  - darwin
  - windows
  triggers:
    keywords:
    - vitest
    - vitest run
    - react testing library
    - testing library
    - renderhook
    - userevent
    - getbyrole
    - jest-dom
    - vi.mock
    - component test
    - hook test
    - watch mode
    intents:
    - TEST
---
# Vitest + React Testing Library

Use the repo's existing config and helpers first (`vitest.config.*` or the `test` block
in `vite.config.*`, `setupTests`, a `renderWithProviders` helper). The repo wins.

## Run it once

Bare `vitest` starts **watch mode** and never exits. Always:

```bash
npx vitest run path/to/file.test.tsx      # one file
npx vitest run -t "rejects empty email"   # one test by name
npm test -- --run                          # when the script is plain "vitest"
```

Check `package.json` `scripts.test` first; if it already says `vitest run`, `npm test`
is fine.

## Component tests

- `render(<Comp />)` then query the way a user perceives the UI: `getByRole("button",
  { name: /save/i })` > `getByLabelText` > `getByText` > `getByTestId` (last resort).
- Interactions: `const user = userEvent.setup(); await user.click(...)`; type with
  `user.type`. Prefer it over `fireEvent`.
- Async UI: `await screen.findByText(...)` or `await waitFor(() => expect(...))`; never
  fixed sleeps. Assert absence with `queryBy...` + `not.toBeInTheDocument()`.
- Matchers like `toBeInTheDocument` need `@testing-library/jest-dom/vitest` imported in
  the setup file.

## Hooks and state

- `renderHook(() => useThing(args), { wrapper })` from `@testing-library/react`; drive
  updates inside `act` or by awaiting the resulting state.
- Redux Toolkit: build a fresh store per test with the real reducers and preloaded state,
  wrap with `<Provider store={store}>` (a shared `renderWithProviders` helper). Assert on
  rendered output or store state, not on dispatched action internals.

## Mocks: at the boundary

- Mock the network or the API module (`vi.mock("@/api/projects")`), not the component
  under test or the hook you are testing. A test that only proves the mock returned what
  you told it is a false green.
- `vi.mock` is hoisted; reference outer variables through `vi.hoisted`. Reset with
  `vi.restoreAllMocks()` / `vi.clearAllMocks()` in `afterEach`.
- Timers: `vi.useFakeTimers()` + `vi.advanceTimersByTime()`; restore real timers after.

## Shape

- One behaviour per test, named for the behaviour ("shows an error when the save
  fails"). Files sit beside the code (`X.test.tsx`) or in `__tests__/`, as the repo does.
- Watch it fail first (TDD): break the code path once and confirm the test goes red.

## Not this skill

Browser end-to-end flows (`webapp-testing`), TDD discipline itself
(`test-driven-development`), suites that pass while the app is broken
(`false-green-tests`).
