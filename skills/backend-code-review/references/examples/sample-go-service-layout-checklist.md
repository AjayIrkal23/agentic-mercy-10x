# Example checklist: layered HTTP service (optional)

Use during **backend-code-review** when the codebase follows a **classic layered** layout (names vary by repo). Treat every line as a **pattern**, not a mandate—infer real directories from `AGENTS.md`, `README`, and existing code.

- **Transport / HTTP:** handlers stay thin; routing and middleware match project conventions.
- **Validation:** request/query/body parsing lives in a dedicated validation layer (schemas, DTOs, or equivalent)—not buried in transport-only shims.
- **Domain logic:** core behavior sits in services/use-cases; avoid leaking persistence details into handlers.
- **Contracts:** API success/error shapes stay consistent with project standards; breaking changes update clients and docs together.
- **Auth / sessions:** authentication and authorization behavior unchanged unless the task explicitly requires it.
- **Migrations / data:** schema changes are safe to apply, reversible where required, and covered by tests when the repo does so.
- **Documentation:** when the repo has `server_docs/`, `docs/api/`, or similar, update the relevant pages when behavior or contracts change; use the **update-docs** skill for workflow.

For authoritative commands and folder layout, read the repository’s **`AGENTS.md`** (if present) and team documentation.
