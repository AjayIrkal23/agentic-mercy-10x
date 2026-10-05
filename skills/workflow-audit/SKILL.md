---
name: workflow-audit
description: 'End-to-end audit and improvement of the whole ~/.claude workbench (settings, every hook link, the prompt router, skills, agents, rules, MCP servers, plugins, the mercy mod, installer, state) as it behaves in the current project, which stays read-only while every fix lands in ~/.claude, test-first and verified.'
when_to_use: Use only when the user runs /workflow-audit or asks to audit and improve their Claude Code workflow (hooks, router, skills, mods, MCPs, rules) from inside a project folder.
disable-model-invocation: true
metadata:
  schema: 1
  category: general
  surfaces:
  - general
  platforms:
  - linux
  token-cost: 3862
  triggers:
    keywords:
    - workflow-audit
    - audit workflow
    - audit hooks
    - audit router
    - audit mods
---

# /workflow-audit — the whole workbench, end to end, line by line (Ubuntu)

You are a principal engineer auditing and improving the user's Claude Code workbench:
`~/.claude` (public repo agentic-mercy-10x) plus the mercy mod, the MCP servers and the
plugins it registers. The session started in some project folder. That project is only
context: it shows how the workbench behaves on a real codebase (its stack, how the router
classifies it, what jcodemunch knows about it), and a disposable copy of it hosts the
live runs. Understand every workbench component line by line, verify it works on this
Ubuntu machine, measure it, exercise it live, then implement the improvements in
`~/.claude` so the system becomes more robust, more precise, faster and more autonomous
for full-stack development: quality (correct, verified, reviewed), quantity (throughput,
no wasted turns or blocking) and finish (docs, tests, clean diffs).

Ubuntu only. Ignore the Windows replica and Windows-only code paths (`install.ps1`,
`IS_WINDOWS` branches, `py -3` handling). Never propose Windows work; flag a finding only
when an Ubuntu change would break a cross-platform contract.

## 0. Hard rules for the whole audit

1. Two zones, never mixed:
   - **The project (`PROJECT`) is read-only context.** Read it, index it with
     jcodemunch and jdocmunch (their indexes live in `~/.code-index` and
     `~/.doc-index`, outside the project), query an existing graphify graph, and run
     the router's stack detection on it. Never write, format, install, build, generate,
     commit, or create files in it. Never run `graphify update` on it (that writes
     `graphify-out/` into the project); with no graph, build one in the disposable
     copy (section 4) or skip graphify. Live runs happen only in that disposable copy
     in the scratchpad.
   - **`~/.claude` is the work zone.** Every fix and improvement lands here (section
     6), test-first, verified and documented. The audit folder `$AUDIT` and the
     scratchpad hold notes, raw outputs and experiments.
2. Never: start dev servers, watchers or app instances; `git commit` / `git push` (ask at
   the end); write files through the shell (`sed -i`, heredoc, `tee`, `>` into files):
   use Edit and Write, and the repo's own generators (`installer/render.py`,
   `scripts/build_skills_index.py`, `hooks/gen-*.py`); hand-edit `settings.json`
   (edit `settings.template.json`, then run `installer/render.py`); edit `~/.claude.json`,
   cached feature flags or MCP registrations; run the installer; delete or rotate
   state, telemetry or indexes; stop or restart ollama, docker or any service; run
   destructive commands; use `git checkout`, `git restore`, `git stash` or `git reset`
   in `~/.claude` (they would destroy the user's other uncommitted work).
3. Removals need the user. Deleting files, retiring a link, skill, agent or rule, or
   weakening a gate (CLAUDE.md §3) is never done on your own: collect those items and
   ask once in section 8. Bug fixes, additions, tuning and doc corrections go ahead.
4. Secrets: never print, copy or quote values from `~/.claude/.env*`, `~/.claude.json`
   (tokens, MCP env values), `CLAUDE.machines.local.md`, project `.env*`, or any key the
   scan finds. Report the path, line and kind only. `~/.claude` is a public repo: never
   write a secret, a machine IP or a home-path literal into a tracked file.
5. Evidence or nothing. Every finding cites `path:line`, a command with its output, or
   a telemetry query with its numbers. Mark each finding CONFIRMED (reproduced or read
   in code) or PLAUSIBLE (reasoned, not reproduced). Counts are computed with the
   command shown, never copied from docs.
6. Tools follow the doctrine: `mcp__sequential-thinking__sequentialthinking` before any
   analysis or design step; jcodemunch (and an existing graphify graph) for the
   PROJECT's code; workbench files are read with Read, Grep and Glob (jcodemunch never
   indexes `~/.claude`, and the gates exempt it); jdocmunch for doc sets; context7 for
   library and CLI APIs; semgrep on security-sensitive files;
   `mcp__memory__search_nodes` at the start.
7. Your own tool calls fire the hooks and the mod. That is evidence too: log anything
   a hook does to you during the audit (a gate blocking a legitimate step, router
   noise, a late advisory, a slow call) as a finding with the moment it happened.
8. `~/.claude` is the live configuration of this very session: a hook script you edit
   runs on your next tool call. Change one thing at a time, run its tests before
   relying on it, and if your own tool calls start misbehaving after a change, revert
   that change at once with Edit. Settings changes apply after `installer/render.py`
   and a restart; mod changes apply in the next session.
9. Experiments with hook scripts (adversarial inputs, timeouts, crashes) run only from
   the sandbox copy (section 2.4), never against the real `~/.claude` state.
10. Parallel subagents do the area audits (section 3): read-only, the template in
    section 3.0, one report file each in `$AUDIT`. Implementation (section 6) stays
    in the main session, or goes one item at a time to an implementor agent with its
    exact files; two agents never edit the same file, and none of them commits.
11. Checkpoint after every phase and every implemented item in `$AUDIT/PROGRESS.md`
    (phase table, done, next, finding count, subagent ids, items applied with their
    files and tests). After a usage limit, a compaction or a restart, continue from
    that file: never restart finished phases, resume unfinished subagents with
    SendMessage. Note the reset time of any usage limit in PROGRESS.md.
12. Context economy: run independent tool calls in parallel, never paste whole large
    files into the conversation, keep raw outputs in `$AUDIT/raw/` and quote only the
    lines that matter.

## 1. Setup

1. Variables (state them in PROGRESS.md):
   - `PROJECT` = git root of the start folder (`git rev-parse --show-toplevel`), else
     the start folder itself.
   - `SLUG` = basename of `PROJECT`; `DATE` = `date +%F`.
   - `AUDIT` = `~/.claude/plans/audit-$DATE-$SLUG` (`plans/` is gitignored). Create it
     and `$AUDIT/raw`, `$AUDIT/e2e`, `$AUDIT/router` with `mkdir -p`.
   - `SCRATCH` = the session scratchpad from the system prompt, else `mktemp -d`.
2. If `PROJECT` is `$HOME` or `~/.claude` itself, run the workbench audit only and mark
   every project-specific step N/A with that reason.
3. Start snapshots, so the end can prove the project is untouched and tell your edits
   apart from the user's own uncommitted work:
   - `git -C ~/.claude status --short > $AUDIT/raw/claude-status-start.txt` and
     `git -C ~/.claude diff > $AUDIT/raw/claude-start.patch`;
   - for `PROJECT`: `git -C "$PROJECT" status --short > $AUDIT/raw/project-status-start.txt`
     and `git -C "$PROJECT" rev-parse HEAD`; for a folder outside git, a listing with
     sizes and mtimes (`find "$PROJECT" -type f -printf '%s %T@ %p\n' | sort -k3`).
4. Write `$AUDIT/PROGRESS.md` with the phase table from section 9
   (`references/phase-table.md`) before starting.

## 2. Phase 0 — orient and baseline (facts before reasoning)

### 2.1–2.2 Environment facts and memory

Run the environment list and the memory reads in `references/phase0.md` (2.1, 2.2);
save to `$AUDIT/raw/env.txt`.

### 2.3 Doctrine, read every line

Read in order: `~/.claude/CLAUDE.md`, `rules/00-tool-precedence.md`,
`rules/01-no-shell-writes.md`, `rules/02-lifecycle.md`, `rules/03-thinking.md`,
`rules/04-model-routing.md`, `rules/frontend.md`, `rules/backend.md`,
`rules/claude-infra.md`; check that `CLAUDE.machines.local.md` exists (do not print it);
then the project's `CLAUDE.md`, every nested `CLAUDE.md`, `AGENTS.md` and `CODEX.md`.

Build the **enforcement matrix** in `$AUDIT/enforcement.md`: one row per MUST / NEVER /
ALWAYS rule → the mechanism that enforces it (hook link id, mod feature, gate, skill,
or "none: model memory only") → verified working? (fill in later phases) → gap.

### 2.4 Sandbox for running hook scripts

1. `SANDBOX=$SCRATCH/sandbox`; `mkdir -p $SANDBOX/home`; `cp -a ~/.claude/hooks
   $SANDBOX/hooks`; symlink `skills plugins scripts agents rules installer mods tests`
   from `~/.claude` into `$SANDBOX`; copy `settings.json`, `settings.template.json`
   and `CLAUDE.md` into `$SANDBOX`.
2. Every hook script you run directly runs as `CLAUDE_CONFIG_DIR=$SANDBOX
   HOME=$SANDBOX/home CLAUDE_HOOK_DOCTOR=1 GIT_OPTIONAL_LOCKS=0 python3
   $SANDBOX/hooks/<script>` with a payload on stdin (start from
   `~/.claude/tests/fixtures/hook-events/*.json`).
3. `touch $SANDBOX/.marker` now; at the end list
   `find ~/.claude/hooks/.state ~/.claude/hooks/.telemetry ~/.claude/state -newer
   $SANDBOX/.marker -type f` and explain every file: only this session's own rows and
   the e2e sessions' rows are expected there (your intended edits go to tracked files,
   never to state).

### 2.5–2.6 Baseline checks and computed inventory

Run every baseline check in `references/phase0.md` 2.5 (doctor, both test suites,
validators, generators `--check`, render, vendored, mod types and contract, link
matrix, MCP, plugins, the rollout switch) and build `$AUDIT/inventory.md` per 2.6
(computed counts against `README.md` / `docs/`; drift is a LOW finding).

Checkpoint PROGRESS.md.

## 3. Phase 1 — static audit, area by area (parallel subagents)

### 3.0 Subagent template (fill in AREA, FILES, CHECKS, REPORT)

> You are the read-only auditor for AREA of the user's `~/.claude` workbench. Never
> edit files, commit, start servers or print secret values. Read every line of FILES
> (list each with its line count; any file you skip, list with the reason). Answer
> every item in CHECKS with evidence (`path:line`, command output, or telemetry
> numbers); mark findings CONFIRMED or PLAUSIBLE. Hook scripts run only from the
> sandbox at `$SANDBOX` with `CLAUDE_HOOK_DOCTOR=1` (see the env line). Write REPORT
> with: scope (files read, line counts); how it works end to end (flow, in your own
> words); inventory table; findings table (id, severity HIGH/MED/LOW, finding,
> evidence, impact, minimal fix, owner layer, effort S/M/L, test that proves the fix);
> measurements; automation and mod opportunities; open questions. Stop exploring after
> about 30 tool calls and write the report with what you have.

Launch A–J in parallel (B may split into B1 tool events and B2 lifecycle and Stop).
Severity: HIGH = a stated guarantee is broken; MED = wrong behaviour or measurable
waste; LOW = drift or small cost.

The ten area briefs (A settings, B dispatcher and hook links, C router, D skills, E
agents, F rules and memory, G MCP and plugins, H the mercy mod, I installer and CI,
J state and hygiene: FILES, CHECKS and report path each) live in
`references/areas.md` (A–G) and `references/areas-h-j.md` (H–J). Read both now and
paste each area's brief into its subagent.

Collect all ten reports, merge them into the enforcement matrix, checkpoint
PROGRESS.md.

## 4–5. Phase 2 (live e2e runs) and Phase 3 (analysis)

Follow `references/phases-2-3.md`: scenarios S1–S9 run only in a disposable copy
(`git clone --local --no-hardlinks`), never in `PROJECT`; per-run timelines and
lifecycle scoring; failure modes from the sandbox only; then the enforcement matrix,
area scores, the autonomy scorecard, santa-reviewer refutation of the top 15, and
`$AUDIT/PLAN.md` (removals and gate loosening in a "needs the user" list).
Checkpoint PROGRESS.md after each phase.

## 6. Phase 4 — implement in `~/.claude`

Work through PLAN.md one item at a time. For each item:

1. Read every file you will touch (and its local `CLAUDE.md`) before editing.
2. Write the failing test first, in the suite that owns the code: `hooks/tests/` for
   hooks and the router, `tests/` for installer, render and catalog contracts,
   `mods/mercy/tests/` for the mod. Run it and see it fail for the right reason.
3. Make the smallest change that passes. Edit with Edit and Write only. Settings go
   through `settings.template.json` + `python3 installer/render.py`; skills through
   their `SKILL.md` + `python3 scripts/build_skills_index.py`; agent preloads through
   `python3 hooks/gen-agent-skill-blocks.py`; model policy through
   `hooks/model-policy.json` + `python3 hooks/gen-invoke-skills.py`. Never hand-edit a
   generated file (`skills-index.json`, `trigger-floor.json`, `skills-provenance.json`,
   `skills/invoke*/`, agent `skills:` lines).
4. Run the item's own tests, then the checks for the layer you touched: hooks →
   `python3 -m pytest hooks/tests -q`; installer and catalog → `python3 -m pytest
   tests -q`; skills → `python3 scripts/validate_skills.py` and
   `python3 hooks/build-trigger-floor.py --check`; mod → `tsc -p mods/mercy`,
   `claude plugin validate --strict mods/mercy`, `claude plugin test mods/mercy`;
   settings → `python3 installer/render.py --check`; portability →
   `python3 scripts/grep_gates.py`.
5. A hook script you changed runs on your next tool call: fire it once through the
   sandbox with a fixture payload first. If anything regresses, revert your own change
   with Edit (never `git checkout`, `restore`, `stash` or `reset`) and record why.
6. Update the docs in the same item: the local `CLAUDE.md` of every directory you
   changed (each must still name every tracked file beside it), `README.md` when
   behaviour or counts change, and one dated section in `docs/CHANGELOG.md` for this
   audit run. `rules/**` changes stay minimal and only when a rule was wrong.
7. Record the item in PROGRESS.md: id, files, tests added, checks run, result.

After the last item:

8. Dead-code audit of your own diff (jcodemunch cannot index `~/.claude`): `tsc -p
   mods/mercy` with its noUnused checks, a caller scan for every export and function
   you added, an unused-import scan of the Python files you touched. Remove only what
   your diff orphaned; report older dead code without touching it.
9. Security: `mcp__semgrep__semgrep_scan` on every changed hook, installer and mod
   file (small batches; the CLI `semgrep scan --config auto` when the MCP fails).
10. Review: the `santa-reviewer` agent on the full diff since the start snapshot (3+
    files); fix every CONFIRMED finding, then re-run the checks of step 4.

Checkpoint PROGRESS.md.

## 7–8. Phase 5 (verify after) and Phase 6 (report and hand-off)

Follow `references/phases-5-6.md`: re-run the 2.5 baseline (0 doctor FAIL), re-run the
affected scenarios (at least S1, S3, S7) in a fresh copy, the before/after table, prove
`PROJECT` untouched against the start snapshot, list your `~/.claude` changes against
`claude-status-start.txt`, the `find -newer` check; then `$AUDIT/AUDIT-REPORT.md` (12
sections), `$AUDIT/findings.json`, the page or path, and the closing chat summary with
the "needs the user" question. Commit only when the user says so.
Checkpoint PROGRESS.md after each phase.

## 9. Phase table for PROGRESS.md and the definition of done

The table (phases 0–6, each with its "done when" condition) is in
`references/phase-table.md`; copy it into PROGRESS.md.

The run is done only when every row is done, the project's `git status` and `HEAD` (or
file listing) equal the start snapshot, every change sits in `~/.claude` and is
covered by a test or a check, the doctor shows 0 FAIL, nothing is committed without
the user's word, and no output contains a secret value.
