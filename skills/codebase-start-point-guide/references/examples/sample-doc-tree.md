# Example: one possible `frontend_docs/` / `server_docs/` tree

**Illustrative only.** Many repositories use different names (`docs/`, `apps/web/docs/`, etc.). See [`../SKILL.md`](../SKILL.md) for how to adapt.

This snapshot shows a **numbered handbook** style used by some full-stack codebases:

## Frontend (example paths)

Read order when these files exist:

1. `frontend_docs/README.md`
2. `frontend_docs/08-agent-playbook/agent-reading-order.md`
3. `frontend_docs/08-agent-playbook/task-routing-matrix.md`

Then by task:

- Routing / guards → `frontend_docs/02-routing/route-map.md`
- State / query → `frontend_docs/03-state/redux-architecture.md`
- API integration → `frontend_docs/04-api/frontend-api-contracts.md`
- Domain-specific areas → `frontend_docs/05-domains/<your-domain>.md` (when present)
- UI composition → `frontend_docs/06-components/component-patterns.md`
- Error / loading / empty → `frontend_docs/07-operations/error-loading-empty-states.md`

## Backend (example paths)

1. `server_docs/README.md`
2. `server_docs/07-agent-playbook/agent-reading-order.md`
3. `server_docs/07-agent-playbook/task-routing-matrix.md`

Then by task:

- Runtime / startup → `server_docs/01-overview/runtime-entrypoints.md`
- Routing → `server_docs/02-routing/route-map.md`
- API contracts → `server_docs/03-contracts/api-contracts-and-validation.md`
- Data models → `server_docs/04-data/models-and-relationships.md`
- Domains → `server_docs/05-domains/*.md`
- Ops / security → `server_docs/06-operations/ops-security-observability.md`

## Cross-layer contracts (example)

- `frontend_docs/04-api/frontend-api-contracts.md`
- `server_docs/03-contracts/api-contracts-and-validation.md`

Replace filenames with your repository’s canonical contract docs.
