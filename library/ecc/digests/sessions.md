---
name: ecc-digest-sessions
description: ECC session tooling (session manager and aliases, session adapters for several runtimes, a session bridge for per-session metrics, sessions and status CLIs over the state store); the reusable idea is one canonical session snapshot shape fed by per-runtime adapters.
---
<!-- ecc-digest:sessions@25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b -->
# Sessions

## What it is
ECC keeps its own view of agent sessions next to the harness's. `scripts/lib/session-manager.js` (with a `.d.ts` type file) lists, loads and describes saved session files, and `scripts/lib/session-aliases.js` (also typed) gives sessions short human names; the `/sessions` command wraps both in large inline scripts. `scripts/lib/session-adapters` (about 51 KB per the study note) reads sessions from several sources into one canonical shape: tmux and dmux panes, Codex worktrees, Claude's own history files and OpenCode. `scripts/lib/session-bridge.js` keeps a small per-session JSON file in the temp dir with tool counts, modified files, a short ring of recent tool-call hashes and a cost snapshot; the context-monitor hook reads it to warn about low context, cost thresholds and repeated identical calls. `scripts/sessions-cli.js` lists sessions and their workers, skill runs and decisions from the ECC 2.0 SQLite state store, and `scripts/status.js` prints a status summary from the same store (sessions, skill runs, install health, governance, work items) with an exit code for scripts.

## The reusable idea
Two ideas carry over. A canonical session snapshot: whatever runtime produced a session, an adapter maps it to one record (id, cwd, branch or worktree, status, last activity, files touched), so dashboards and resume logic are written once. And the bridge's loop detector: keep a ring of the last five tool calls as hashes of tool name plus input; five identical hashes in a row means the agent is stuck, which is cheap to detect after every call and worth one short warning line in context. The same bridge file shows the pattern for cost and context warnings with a per-tier debounce, so each threshold is announced once rather than on every call.

## Why not adopted
The harness already has native resume and session listing, and the workbench tracks live session state through the mercy mod (its session-state tool) and the stop and restore tooling. `sessions-cli.js` and `status.js` only make sense with ECC's SQLite state store, which nothing here writes. The adapters target runtimes this setup does not use. The loop-detector idea is a candidate for a dispatch link in `hooks/dispatch.py` if repeated-call loops ever show up in telemetry.

## Upstream paths
- `scripts/lib/session-adapters`
- `scripts/lib/session-aliases.d.ts`
- `scripts/lib/session-aliases.js`
- `scripts/lib/session-bridge.js`
- `scripts/lib/session-manager.d.ts`
- `scripts/lib/session-manager.js`
- `scripts/sessions-cli.js`
- `scripts/status.js`
