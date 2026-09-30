# `templates/` — local rules

Files copied into *other* repos, never loaded by `~/.claude` itself.

| File | Role |
|------|------|
| `mcp/db-readonly.mcp.json` | read-only Supabase / MongoDB MCP servers, project scope; installed by `scripts/add-db-mcp.py` |
| `CODEX.md.template` | starting point for a project's CODEX.md; `hooks/codex-capture.py` points at it |

- Pinned package versions; bump deliberately.
- Secrets only as `${VAR}` placeholders — never literal tokens or connection strings.
- Parent: [`../CLAUDE.md`](../CLAUDE.md)
