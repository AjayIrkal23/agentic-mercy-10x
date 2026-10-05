---
paths:
  - "**/*.go"
  - "**/go.mod"
  - "**/*.sql"
  - "**/migrations/**"
  - "**/server/**/*.{ts,js,mjs,cjs,py}"
  - "**/{routes,handlers,controllers,middleware}/**/*.{ts,js,py}"
  - "**/{api,app,services}/**/*.py"
---
# Backend (loads on BE files)

**Baseline skills:** `backend-standards-always-follow`, `backend-api-standards`,
`service-layer-standards`; contracts via `api-contract-standards` — success
`{success, data, message, meta}`, error `{success:false, error:{code, message, details}}`,
list endpoints paginate server-side (page/limit capped, whitelisted sort keys). These are
defaults: the project contract wins (its `CLAUDE.md`, `CODEX.md`, API docs).
Controllers thin (validate → service → respond); services own logic, DB, filtering,
transactions; domain errors mapped centrally (`backend-error-handling`).

**Go:** `golang-patterns` — accept interfaces, return structs; `fmt.Errorf("…: %w", err)`;
`context.Context` first; no panics for control flow. Tests: `golang-testing` —
table-driven, `t.Run`, `httptest`, always `-race`.

**TDD loop (generic):** failing test first → `go test ./... -race` · `make tdd` when the
Makefile has it · `vitest` · `pytest` → green → refactor → `make lint` / the project
linter. Never refactor while RED. `tdd-guard` is advisory (`⚠️ TDD GUARD`): treat it as
a directive — stop, write the failing test, then implement. Ops: skill `tdd-auto-init`.

**Node stack:** Fastify routes, schemas, hooks, error handler → `fastify-patterns`;
Mongoose models, queries, indexes, aggregations → `mongoose-patterns`.

**Data:** `postgres-patterns` for SQL schemas, indexes, migrations, RLS (not for Mongo).

**Security:** `mcp__semgrep__semgrep_scan` on any change to auth, input handling, or the
API surface; `owasp-security` for review. Never log secrets; redact at the handler
boundary.

**Python services:** typed, stdlib first, `python3 -m pytest` where a suite exists.
(`~/.claude` hooks and scripts follow `rules/claude-infra.md`, not this file.)
