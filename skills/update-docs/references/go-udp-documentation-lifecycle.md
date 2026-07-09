# GO_UDP — documentation lifecycle (skill reference)

This file summarizes the checklist used in the GO_UDP workspace. **Authoritative checked-in source:** repo file `.claude/documentation-lifecycle.md` (relative to repo root). If this summary drifts, follow the repo file.

## Plan gate — Cursor Plan mode (required)

For non-trivial or multi-file work: **must** start in Cursor **Plan mode**, then **Agent mode** to execute — see repo file for full criteria (`AGENTS.md` + Phase A still mandatory).

## Phase A — Read before implementing

1. Repo root **`AGENTS.md`** (mandatory first).
2. Full-stack touches: **`PROJECT_LINKAGES.md`**.
3. Backend: **`UDP_PLATFORM/server/server_docs/README.md`**, **`UDP_PLATFORM/server/server_docs/07-agent-playbook/agent-reading-order.md`**, then domain/routing docs (e.g. `server_docs/05-domains/*`).
4. Frontend: **`UDP_PLATFORM/client/frontend_docs/README.md`**, **`UDP_PLATFORM/client/frontend_docs/08-agent-playbook/agent-reading-order.md`**, then scope-specific layering/routing docs.

Pointers: **`UDP_PLATFORM/server/server_docs/01-overview/http-request-lifecycle.md`**, **`UDP_PLATFORM/client/frontend_docs/04-api/layering-and-backend-linkage.md`**.

## Phase B — Update after code changes

- **`UDP_PLATFORM/server/server_docs/`** when server contracts/routes/domain behavior drift.
- **`UDP_PLATFORM/client/frontend_docs/`** when client routing/state/API layering drifts.
- **`PROJECT_LINKAGES.md`** when cross-layer paths or domains change.
- **`UDP_PLATFORM/server/internal/types/audit/actions.go`** when audited routes change (taxonomy in `server_docs/05-domains/audit.md`).
- **`AGENTS.md`** only if verification commands or repo-wide rules change materially.
- **`dead-code-and-change-audit`** on touched surfaces; **`fix-lint-format`** where applicable.

Follow **`update-docs`** + repo **`AGENTS.md`** verification for touched stacks.

### Handoff (before claiming done)

- Superpowers **`verification-before-completion`** (evidence required).
- Skim **`code-review-and-quality`** on the diff; fix regressions or use **`systematic-debugging`** / **`diagnose`** as needed.
- **`using-agent-skills`** sweep of `~/.claude/skills/` for any remaining gates. Session summary: docs done/none; dead-code cleanup none/summary; bugs/regressions none vs listed.

Cursor repo hooks (**`.claude/hooks.json`**) reinforce **documentation-first + Plan gate** at session start and **Phase B + hygiene + review reminders** on agent stop (`go-udp-documentation-lifecycle.py`).
