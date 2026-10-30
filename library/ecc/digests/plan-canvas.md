---
name: ecc-digest-plan-canvas
description: ECC Plan Canvas, a loopback browser page where a human annotates and approves a plan while the agent long-polls for the verdict; the reusable idea is a blocking await that returns structured feedback JSON plus a loopback-only host guard.
---
<!-- ecc-digest:plan-canvas@25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b -->
# Plan Canvas

## What it is
Plan Canvas lets a human review a plan in a browser instead of in chat. `scripts/plan-canvas.js` is the CLI: `open` starts (or reuses) one detached Node server on 127.0.0.1 port 4517 that serves every session and shuts down after 30 idle minutes; it renders a `.plan.md` file with its own Markdown renderer, or an HTML artifact with an injected script so the reviewer can annotate any element. Pages reload live over server-sent events. `await` blocks in a long poll until there is feedback, an Approve or Request-changes verdict, or the session ends, and prints the result as JSON on stdout (progress goes to stderr). `--reply`, `end` and `stop` close the loop. The server code is in `scripts/lib/plan-canvas`; `scripts/lib/loopback-guard.js` and `scripts/lib/platform-launch.js` are shared helpers. Two hooks connect it to the session: `scripts/hooks/plan-canvas-pending.js` (Stop) drains queued feedback and blocks the stop with it as the next input, honouring the stop-hook-active flag, and `plan-canvas-sessions.js` (SessionStart) lists up to five open review sessions. `commands/plan-canvas.md` and `skills/plan-canvas` are the entry points.

## The reusable idea
The await contract is clean: the agent calls one command that blocks until a human decides, and gets back structured JSON (verdict, comments anchored to elements), so the plan approval becomes data instead of a typed sentence. The Stop hook makes sure feedback that arrived late is not lost. The loopback guard is worth copying for any local web tool: accept a request only when both Host and Origin are loopback names, which defeats DNS-rebinding attacks even when the port is reachable; add a request body cap (1 MB here) and an allowlist of request paths.

## Why not adopted
Plans are approved in chat today (`plan-mode-gate`, the planning skills), and the workbench rules say never to open a browser or start a server on the agent's own initiative; Plan Canvas does both and leaves a detached process running after the turn. It would also add the Node runtime for one feature. If visual plan review is wanted later, the await-plus-JSON contract and the loopback guard are the parts to rebuild, ideally on an artifact page the user opens.

## Upstream paths
- `README.md#plan-canvas`
- `commands/plan-canvas.md`
- `scripts/hooks/plan-canvas-pending.js`
- `scripts/hooks/plan-canvas-sessions.js`
- `scripts/lib/loopback-guard.js`
- `scripts/lib/plan-canvas`
- `scripts/lib/platform-launch.js`
- `scripts/plan-canvas.js`
- `skills/plan-canvas`
