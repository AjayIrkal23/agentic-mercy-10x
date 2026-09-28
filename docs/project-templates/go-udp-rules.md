# GO_UDP — project rules template

Project-specific content extracted from the global `~/.claude` skills on 2026-09-27
(WP-3). Global skills are now stack-neutral; drop the sections below into the
GO_UDP repo's own `.claude/` (as `CLAUDE.md` text, a `rules/*.md` file with
`paths:`, or a project skill) so they load only inside that repo.

## 1. Active stack (was: backend-standards-always-follow / architect-system-design)

The active backend stack is **Go (GO_UDP, `UDP_PLATFORM/server`, chi router)**; the
frontend is **Vite + React (`UDP_PLATFORM/client`)**. Go-first examples apply; the
Node/Fastify variants in the global skills' `references/node-stack.md` do not.

Suggested `.claude/rules/stack.md`:

```markdown
---
paths: ["UDP_PLATFORM/server/**", "UDP_PLATFORM/client/**"]
---
Backend = Go/chi under UDP_PLATFORM/server (internal/, cmd/). Frontend = Vite/React under
UDP_PLATFORM/client. TDD loop: `cd UDP_PLATFORM/server && make tdd` (go test -json | tdd-guard-go),
then `make lint` (golangci-lint). Vertical slices: skim `code-execution-standard` and
`dead-code-and-change-audit` before each slice.
```

## 2. Surface path segments (was: hooks/fullstack-skills-reminder.config.json)

```json
{
  "frontend_path_segments": ["UDP_PLATFORM/client", "client/"],
  "backend_path_segments": ["UDP_PLATFORM/server", "server/internal/", "server/cmd/", "server/pkg/"],
  "documentation_path_segments": [
    "server_docs/", "frontend_docs/", "PROJECT_LINKAGES.md",
    "UDP_PLATFORM/server/server_docs", "UDP_PLATFORM/client/frontend_docs"
  ]
}
```

Frontend route rule exclusion (was `skill_router.config.json` → `fe_routes.exclude_paths`):
`UDP_PLATFORM/server`, `server/internal`.

## 3. Documentation lifecycle (was: update-docs/references/go-udp-documentation-lifecycle.md)

**Authoritative checked-in source:** repo file `.claude/documentation-lifecycle.md`. If
this summary drifts, follow the repo file.

### Plan gate (required)

For non-trivial or multi-file work start with a plan (`plan-mode-gate`), then execute.
`AGENTS.md` + Phase A remain mandatory.

### Phase A — Read before implementing

1. Repo root **`AGENTS.md`** (mandatory first).
2. Full-stack touches: **`PROJECT_LINKAGES.md`**.
3. Backend: `UDP_PLATFORM/server/server_docs/README.md`,
   `UDP_PLATFORM/server/server_docs/07-agent-playbook/agent-reading-order.md`, then
   domain/routing docs (e.g. `server_docs/05-domains/*`).
4. Frontend: `UDP_PLATFORM/client/frontend_docs/README.md`,
   `UDP_PLATFORM/client/frontend_docs/08-agent-playbook/agent-reading-order.md`, then
   scope-specific layering/routing docs.

Pointers: `UDP_PLATFORM/server/server_docs/01-overview/http-request-lifecycle.md`,
`UDP_PLATFORM/client/frontend_docs/04-api/layering-and-backend-linkage.md`.

### Phase B — Update after code changes

- `UDP_PLATFORM/server/server_docs/` when server contracts/routes/domain behavior drift.
- `UDP_PLATFORM/client/frontend_docs/` when client routing/state/API layering drifts.
- `PROJECT_LINKAGES.md` when cross-layer paths or domains change.
- `UDP_PLATFORM/server/internal/types/audit/actions.go` when audited routes change
  (taxonomy in `server_docs/05-domains/audit.md`).
- `AGENTS.md` only if verification commands or repo-wide rules change materially.
- `dead-code-and-change-audit` on touched surfaces; `fix-lint-format` where applicable.

### Handoff (before claiming done)

- Superpowers `verification-before-completion` (evidence required).
- Skim `code-review-and-quality` on the diff; `debug-investigation` for regressions.
- `using-agent-skills` sweep for remaining gates. Session summary: docs done/none;
  dead-code cleanup none/summary; bugs/regressions none vs listed.

## 4. Numbered handbook layout (was: codebase-intel-first/.../sample-doc-tree.md)

Illustrative `frontend_docs/` / `server_docs/` tree used by GO_UDP.

**Frontend read order:** `frontend_docs/README.md` →
`frontend_docs/08-agent-playbook/agent-reading-order.md` →
`frontend_docs/08-agent-playbook/task-routing-matrix.md`. Then by task:
routing/guards `02-routing/route-map.md`; state/query `03-state/redux-architecture.md`;
API integration `04-api/frontend-api-contracts.md`; domains `05-domains/<domain>.md`;
UI composition `06-components/component-patterns.md`; error/loading/empty
`07-operations/error-loading-empty-states.md`.

**Backend read order:** `server_docs/README.md` →
`server_docs/07-agent-playbook/agent-reading-order.md` →
`server_docs/07-agent-playbook/task-routing-matrix.md`. Then by task:
runtime `01-overview/runtime-entrypoints.md`; routing `02-routing/route-map.md`;
contracts `03-contracts/api-contracts-and-validation.md`; data
`04-data/models-and-relationships.md`; domains `05-domains/*.md`; ops/security
`06-operations/ops-security-observability.md`.

**Cross-layer contracts:** `frontend_docs/04-api/frontend-api-contracts.md` ↔
`server_docs/03-contracts/api-contracts-and-validation.md`.
