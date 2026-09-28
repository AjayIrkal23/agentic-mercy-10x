---
paths:
  - "**/*.go"
  - "**/go.mod"
  - "**/*.sql"
  - "**/migrations/**"
  - "**/server/**"
  - "**/internal/**"
  - "**/api/**"
  - "**/routes/**"
  - "**/handlers/**"
  - "**/*.py"
---
# Backend (loads on BE files)

**Baseline skills:** `backend-standards-always-follow`, `backend-api-standards`,
`service-layer-standards`; contracts via `api-contract-standards` — success
`{success, data, message, meta}`, error `{success:false, error:{code, message, details}}`,
list endpoints paginate server-side (page/limit capped, whitelisted sort keys).
Controllers thin (validate → service → respond); services own logic, DB, filtering,
transactions; domain errors mapped centrally (`backend-error-handling`).

**Go:** `golang-patterns` — accept interfaces, return structs; `fmt.Errorf("…: %w", err)`;
`context.Context` first; no panics for control flow. Tests: `golang-testing` —
table-driven, `t.Run`, `httptest`, always `-race`.

**TDD loop (generic):** failing test first → `go test ./... -race` · `make tdd` when the
Makefile has it · `vitest` · `pytest` → green → refactor → `make lint` / the project
linter. Never refactor while RED. `tdd-guard` is advisory (`⚠️ TDD GUARD`): treat it as
a directive — stop, write the failing test, then implement. Ops: skill `tdd-auto-init`.

**Data:** `postgres-patterns` for schemas, indexes, migrations, RLS;
`clickhouse:clickhouse-best-practices` when ClickHouse files appear.

**Security:** `mcp__semgrep__semgrep_scan` on any change to auth, input handling, or the
API surface; `owasp-security` for review. Never log secrets; redact at the handler
boundary.

**Python (hooks, scripts, services):** typed, stdlib first, `python3 -m pytest` where a
suite exists; hook scripts print nothing on success and exit non-zero only on a real
failure.
