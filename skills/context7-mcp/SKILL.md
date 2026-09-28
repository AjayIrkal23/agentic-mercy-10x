---
name: context7-mcp
description: 'Pointer: fetch current library/framework docs through the Context7 MCP (resolve-library-id, then query-docs). The full procedure lives in rules/context7.md.'
when_to_use: Not model-invoked; the always-on rules/context7.md already routes library questions to Context7.
disable-model-invocation: true
---
Library, framework, SDK, or CLI question → `mcp__context7__resolve-library-id` (name + the user's question) → `mcp__context7__query-docs` (one concept per call). Prefer this over web search and over training-data recall.
