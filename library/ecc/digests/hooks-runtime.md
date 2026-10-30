---
name: ecc-digest-hooks-runtime
description: ECC's Node hook runtime (profile flags, per-hook kill switches, Bash pre/post dispatchers, tmux and push reminders, PR and build notices); the reusable idea is one env-driven profile switch plus a per-hook disable list.
---
<!-- ecc-digest:hooks-runtime@25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b -->
# Hooks runtime

## What it is
Every ECC hook is a Node one-liner that boots a plugin resolver, then `run-with-flags.js <id> <script> <profiles>`, then the hook script. `hooks/README.md` documents the events, the PreToolUse table, the env controls and recipes (the study note marks parts of it stale), and `schemas` holds the JSON schemas for hooks and install config. Enablement is by environment: a global on/off, a profile (`minimal`, `standard`, `strict`) and a comma-separated list of disabled hook ids, plus a profile list inside each hooks.json command. Bash calls go through one dispatcher that runs several checks in process. In this digest's scope: `scripts/hooks/auto-tmux-dev.js` rewrites a package-manager dev-server command into a detached tmux session; `pre-bash-tmux-reminder.js` (strict only) suggests tmux for long commands; `pre-bash-git-push-reminder.js` (strict only) prints a review reminder before a push; `post-bash-pr-created.js` and `post-bash-build-complete.js` print a notice after a PR is opened or a build finishes. The guide anchors cover editor shortcuts, the recommended plugin list, running long jobs in tmux, and Mixedbread's mgrep search service.

## The reusable idea
The profile switch is the part worth having. One variable picks a named tier of hooks, a second variable lists hook ids to disable, and each hook declares which tiers it belongs to. That gives a per-machine or per-session kill switch without editing settings, and a bisect path when a hook misbehaves: disable it by id and retry. Two output rules from the runtime also hold up: a hook that only echoes its input back produces no output (it would only bloat the transcript), and gates that must not fail open (config protection, destructive-command checks) block on truncated input, while advisory hooks fail open with a stderr note.

## Why not adopted
`hooks/dispatch.py` already runs every hook link in one Python process with per-link enable flags and tool filters, so a second runtime would double it. `auto-tmux-dev.js` starts dev servers, which the workbench rules forbid. The tmux and push reminders are noise in the strict tier only, and the PR and build notices duplicate what the transcript already shows. mgrep sends code to an external service. The env profile idea can be added to `hooks/dispatch.py` as a small change if per-link switches ever prove too coarse.

## Upstream paths
- `hooks/README.md`
- `schemas`
- `scripts/hooks/auto-tmux-dev.js`
- `scripts/hooks/post-bash-build-complete.js`
- `scripts/hooks/post-bash-pr-created.js`
- `scripts/hooks/pre-bash-git-push-reminder.js`
- `scripts/hooks/pre-bash-tmux-reminder.js`
- `the-longform-guide.md#mgrep`
- `the-shortform-guide.md#editors-and-shortcuts`
- `the-shortform-guide.md#plugin-list`
- `the-shortform-guide.md#tmux-long-running`
