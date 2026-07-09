---
name: fix-lint-format
description: Use when you have lint errors, formatting issues, CI failures, or before committing code to ensure it passes project checks. Adapts commands to the repo (Go, Node, React upstream examples).
---

# Fix lint and formatting

## Goal

Get the working tree to a state that would pass the project’s automated checks (format, lint, tests where appropriate) **before** commit or PR.

## Portable workflow

1. **Detect the project** from the workspace root and changed paths:
   - `go.mod` + `Makefile` → likely Go; prefer `make lint` and `go test ./...` when documented
   - `package.json` → use `npm run lint`, `pnpm lint`, or `yarn lint` as defined in `scripts`
2. **Format first** when the repo documents a formatter (`gofmt`/`goimports`, Prettier, etc.)
3. **Lint / static analysis second**
4. **Tests** for substantial logic changes when quick to run locally

## Multi-package / monorepo layouts

If the repository has **sibling packages** (e.g. `client/` and `server/`, or `apps/web` and `services/api`), run each package’s documented lint, format, and test commands from **that package’s root**—not from a parent folder unless the docs say so. Follow `AGENTS.md` or `README` when the repo defines a matrix of commands.

## Example — facebook/react monorepo (upstream reference)

From [facebook/react `fix` skill](https://github.com/facebook/react/tree/main/.claude/skills/fix):

1. Run `yarn prettier` to fix formatting (repo-specific)
2. Run `yarn linc` to check for remaining lint issues
3. Report any remaining manual fixes

Use this block **only** when actually working inside the React repository.

## Common mistakes

- Running a **client** lint command against **server** changes (or vice versa)
- Assuming `npm run preflight` exists — prefer reading `package.json` and `Makefile`
- Ignoring errors that will fail CI — fix or explicitly call out blockers

## References

- [command-cheatsheet.md](references/command-cheatsheet.md)
