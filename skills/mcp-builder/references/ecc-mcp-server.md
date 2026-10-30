<!-- ecc:skills/mcp-server-patterns @25278e7d -->
# Node/TS MCP server patterns (ECC graft)

- **Schema per tool:** every tool declares a strict input schema (zod / JSON Schema) and
  validates before doing anything; reject unknown fields.
- **Timeouts:** every outbound call (HTTP, DB, subprocess) has a timeout, and the tool
  returns a clear error when it fires.
- **No stdout logging on stdio servers:** stdout is the protocol channel; log to stderr or a
  file.
- Small, single-purpose tools with descriptive names beat one tool with a mode flag.
