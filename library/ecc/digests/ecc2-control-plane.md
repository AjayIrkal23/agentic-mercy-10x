---
name: ecc-digest-ecc2-control-plane
description: ECC 2.0, an alpha Rust TUI and SQLite control plane for agent sessions, worktrees, delegation and merge queues; the reusable ideas are heartbeat staleness, pid-based crash recovery and a paired-seed gate before promoting prompt changes.
---
<!-- ecc-digest:ecc2-control-plane@25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b -->
# ECC 2.0 control plane

## What it is
`ecc2` is a Rust workspace of about 2 MB that the upstream README itself calls alpha. It starts, stops and resumes agent sessions, gives each one a git worktree, delegates work between sessions, schedules jobs, accepts remote dispatch over HTTP, runs a merge queue with automatic rebase, scores risk, and runs a harness evaluation. State lives in SQLite; a `daemon` subcommand keeps it running in the background and a ratatui dashboard renders it. On the Node side, `scripts/control-pane.js` and `scripts/lib/control-pane` serve a loopback web view of the same database, `scripts/lib/state-store` is the sql.js store other ECC scripts query, and `scripts/lib/agent-proximity` with `scripts/proximity-tick.js` scores agents for inter-session messages on a loop. The design and planning material is in `docs/architecture` (cross-harness contracts, session snapshots, HUD, observability), `docs/design` (feature designs with TDD logs), `docs/control-plane`, `docs/ROADMAP.md`, `docs/ECC-2.0-GA-ROADMAP.md` (108 KB, a mirror of an external tracker) and `docs/ECC-2.0-REFERENCE-ARCHITECTURE.md`.

## The reusable idea
Four mechanisms stand out in the study note, each small enough to rebuild alone. Heartbeat staleness: every session writes a heartbeat, and one that misses its window is shown as stale rather than running, so a crashed worker never looks alive. Crash recovery by probing the recorded pid with a zero signal: a dead pid with an open session row means the session is resumable, not lost. A merge queue that rebases each finished branch on the current head before it lands, so parallel workers never merge a stale base. And a paired-seed promotion gate: a prompt or config change is evaluated on the same seeds as the current version and promoted only when it wins on those pairs, which removes run-to-run noise from the decision. Quiet-hours rules for desktop and webhook notifications are a fifth, minor idea.

## Why not adopted
The workbench is a single-user Claude Code setup with Python hooks; it already has session state and resume through the mercy mod, worktree and parallel-agent skills, and the OOM watcher (`hooks/tools/memwatch.py`) plus restore tooling for crash recovery. Adopting `ecc2` would add a Rust toolchain, a background daemon and a second session database that nothing else reads, and the roadmaps are ECC's internal planning. The heartbeat, pid probe and paired-seed ideas are noted for the restore and evaluation work; the code is not taken.

## Upstream paths
- `docs/ECC-2.0-GA-ROADMAP.md`
- `docs/ECC-2.0-REFERENCE-ARCHITECTURE.md`
- `docs/ROADMAP.md`
- `docs/architecture`
- `docs/control-plane`
- `docs/design`
- `ecc2`
- `scripts/control-pane.js`
- `scripts/lib/agent-proximity`
- `scripts/lib/control-pane`
- `scripts/lib/state-store`
- `scripts/proximity-tick.js`
