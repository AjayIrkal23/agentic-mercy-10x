---
name: ecc-digest-unified-memory
description: ECC Memory Vault, a Markdown memory store with a CLI and a stdio MCP server for saving, searching and handing off context across harnesses; the reusable idea is create-only writes, a fail-closed gitignore check and a transparent keyword score.
---
<!-- ecc-digest:unified-memory@25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b -->
# Unified memory

## What it is
The Memory Vault stores notes as Markdown files in three scopes: project, team and user. `scripts/memory.js` is the CLI (`init`, `save`, `handoff`, `search`, `read`, `doctor`) with a bounded stdin reader and a sanitizer that strips terminal escape sequences from stored text. `scripts/memory-mcp.mjs` exposes the same operations as four MCP tools over stdio; it validates input against JSON schemas and implements JSON-RPC by hand, and the harness identity is bound through the environment. The library is `scripts/lib/memory-vault.js` (about 800 lines) with the file format in `scripts/lib/memory-vault-format.js`. `examples/unified-memory` shows a handoff between two harnesses, and the README's memory-vault section introduces it. The `unified-memory` skill (vendored in this library) is the usage guide; it expects the global ECC npm package to be installed.

## The reusable idea
The trust model is the part worth keeping. Writes are create-only: a save never rewrites an existing note, so a bad session cannot corrupt history, and corrections are new notes that point at old ones. New notes start unreviewed until a human marks them. Before writing into a project scope, the vault checks that its directory is gitignored and refuses otherwise (fail closed), so private notes never reach a public repo by accident. `doctor` reports format errors and orphaned files. Search is a plain, explainable score: title hits weigh 8, tag hits 6, metadata 3, body hits up to 5, and an exact phrase adds 20 (5 in the body), which is easy to tune and to debug compared with an opaque embedding.

## Why not adopted
The workbench is a single-harness setup and already has a memory stack: the memory MCP knowledge graph, the native auto-memory MEMORY.md files, `memory-codex` with CODEX.md, the memory load at session start and the mercy mod's remember tool. A second store would split facts across two places. The vault also needs the Node runtime and a hand-rolled MCP server to maintain. The create-only and gitignore-check rules are noted for the memory protocol; the store is not adopted.

## Upstream paths
- `README.md#memory-vault`
- `examples/unified-memory`
- `scripts/lib/memory-vault-format.js`
- `scripts/lib/memory-vault.js`
- `scripts/memory-mcp.mjs`
- `scripts/memory.js`
