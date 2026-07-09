# Example: split client/server documentation map (illustrative only)

**Not authoritative.** Replace every path with your repository’s real layout and doc index. Use this only as a pattern when you maintain separate client and server packages under one repo.

Assume repo root `<repo>/`:

| Entry | Example path (placeholder) |
| --- | --- |
| Agents / agent guide | `<repo>/AGENTS.md` or `<repo>/docs/AGENTS.md` |
| Cross-surface linkage index | `<repo>/PROJECT_LINKAGES.md` or `<repo>/docs/linkage.md` (if your team uses one) |
| Backend docs root | `<repo>/server/server_docs/` or `<repo>/backend/docs/` |
| Frontend docs root | `<repo>/client/frontend_docs/` or `<repo>/apps/web/docs/` |
| Deep-dive examples | `<repo>/<backendPkg>/server_docs/01-overview/...`, `<repo>/<clientPkg>/frontend_docs/04-api/...` |

**Rule of thumb:** when APIs, routes, or contracts change, update the **canonical** docs for each surface and any shared linkage doc your project maintains.
