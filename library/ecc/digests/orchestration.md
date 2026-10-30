---
name: ecc-digest-orchestration
description: ECC multi-agent orchestration (worktree-per-worker tmux swarms, multi-model command family, GAN generator/evaluator loop, claw REPL); the reusable idea is a plan file that materialises task, handoff and status files per worker with rollback on failure.
---
<!-- ecc-digest:orchestration@25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b -->
# Orchestration

## What it is
ECC has several ways to run more than one agent at once. `scripts/orchestrate-worktrees.js` with `scripts/lib/tmux-worktree-orchestrator.js` reads a plan file (session name, base ref, repo root, a launcher command template, seed paths, and a list of workers with their tasks), creates a branch and a git worktree per worker, writes task, handoff and status Markdown files under `.orchestration/<session>/<worker>/`, and opens a tmux session with one pane per worker. It is a dry run by default and needs an execute flag to act. `scripts/lib/orchestration-session.js` and `scripts/orchestration-status.js` read the result back. The `commands/multi-*.md` family (plan, execute, backend, frontend, workflow) routes phases to other providers' CLIs through an external wrapper. `scripts/gan-harness.sh`, `examples/gan-harness` and the GAN commands run a planner, then rounds of generator and evaluator with `claude -p`, extracting a score by regex and stopping at a threshold or a plateau. `scripts/claw.js` and `skills/nanoclaw-repl` are a REPL that shells to `claude -p` with the whole Markdown history each turn.

## The reusable idea
The worktree orchestrator's contract is the part to keep. The plan expands into files before anything runs, so a human or a test can inspect exactly what each worker will receive. Placeholders in the launcher template are offered raw and shell-quoted, seed paths are checked to stay inside the repo root, and every created resource (branch, worktree, tmux pane) is recorded so a failure rolls all of them back. The worker reply has a fixed four-section shape (summary, files changed, validation, remaining risks), and the launcher, not the agent, writes the status and handoff files, so a worker cannot mark itself done. From the GAN loop: stop when the score has not improved for two rounds after round three, which bounds cost without a fixed iteration count.

## Why not adopted
The workbench runs parallel work through subagents and agent teams, the worktree and parallel-dispatch skills, and the JS workflows under `workflows/`; a tmux swarm launcher would be a third mechanism. The `multi-*` commands need an external wrapper and send code to other providers. The GAN harness starts a dev server, which the workbench rules forbid, and its own docs put a run at tens to hundreds of dollars. `claw.js` re-sends the whole history each turn and has no tool continuity; real sessions with resume already exist. The plan-to-files and rollback ideas are worth reusing in `workflows/` if it ever launches long-lived workers.

## Upstream paths
- `commands/multi-backend.md`
- `commands/multi-execute.md`
- `commands/multi-frontend.md`
- `commands/multi-plan.md`
- `commands/multi-workflow.md`
- `examples/gan-harness`
- `scripts/claw.js`
- `scripts/gan-harness.sh`
- `scripts/lib/orchestration-session.js`
- `scripts/lib/tmux-worktree-orchestrator.js`
- `scripts/orchestrate-worktrees.js`
- `scripts/orchestration-status.js`
- `skills/nanoclaw-repl`
