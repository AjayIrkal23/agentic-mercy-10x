---
name: verification-loop
description: 'Verification before claiming done: run the repo''s own build, type, lint and test commands, scan changed security-sensitive files with semgrep, and read the output before any claim.'
when_to_use: Use before claiming any work complete, fixed, or passing, and before opening a PR.
metadata:
  schema: 1
  category: general
  surfaces:
  - general
  platforms:
  - linux
  - darwin
  - windows
  token-cost: 560
  origin: ECC
  triggers:
    keywords:
    - verify it works
    - verify the change
    - run the checks
    - before claiming done
    - before i merge
    - is it passing
    - quality gates
    - verification
    paths: []
    intents:
    - VERIFY
---
# Verification Loop

Evidence before assertions. A claim ("fixed", "passing", "done") needs a command you ran
in this turn and its output, read by you.

## 1. Find the repo's commands (do not guess)

Read, in order: the repo's `CLAUDE.md` / `AGENTS.md` / `CODEX.md`, then the manifest
(`package.json` scripts, `Makefile`, `pyproject.toml`, `go.mod`, `Cargo.toml`), then CI
(`.github/workflows/*`). Use exactly what they declare, from the package root they declare
(monorepos: `npm --prefix server run build`, not the root script). Examples, only when
the repo names them:

| Stack | build / types | lint | tests (one-shot) |
|---|---|---|---|
| Node/TS | `npm run build`, `npx tsc --noEmit` | `npm run lint` | `npm test` (vitest: `vitest run`, never bare `vitest`) |
| Python | `pyright` / `mypy` if configured | `ruff check .` | `python3 -m pytest -q` |
| Go | `go build ./...` | `go vet ./...` / `golangci-lint run` | `go test ./... -race` |

Never start dev servers, watchers or the app to "check"; the user runs those.

## 2. Run, smallest scope first, then the suite

1. The test you wrote or the one that covers the change; watch it pass (and, for new
   behaviour, watch it fail first).
2. Types and lint for the touched package.
3. The package's full test command. A failure you did not cause is still reported, by
   name.
4. Build, when the change can break it (config, imports, types, routing).

## 3. Security and hygiene on the diff

- Auth, session, middleware, input handling or API files changed →
  `mcp__semgrep__semgrep_scan` on those files (fallback: the `semgrep` CLI). Secrets are
  found by semgrep and the repo's secret scanner, not by ad hoc greps.
- `git diff --stat` and read each hunk: unintended edits, debug output left in, new files
  you forgot, files over the repo's size limit.
- Coverage: only report it when the repo defines a threshold; do not invent one.

## 4. Report

```
VERIFY
  tests:   <command> -> <final line, e.g. "42 passed, 1 skipped">
  types:   <command> -> <errors or "clean">
  lint:    <command> -> <errors/warnings or "clean">
  build:   <command> -> <ok / error> (or "not run: <reason>")
  semgrep: <files> -> <findings or "0"> (or "n/a: no security-sensitive files")
  diff:    <N files>, unintended changes: <none / list>
  NOT VERIFIED: <what needs a running app, device or real database>
```

"Ready" only when every run line is clean and the NOT VERIFIED list is stated.
