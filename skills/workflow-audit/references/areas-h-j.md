# /workflow-audit — Phase 1 area briefs (H–J)

Continues `references/areas.md` (A–G).

### H. The mercy mod → `$AUDIT/H-mods.md`

FILES: `mods/CLAUDE.md`, `mods/mercy/.claude-plugin/plugin.json`,
`mods/mercy/hooks/hooks.json`, `hooks/register.ts`, every `hooks/features/*` and
`hooks/lib/*` file, `types/index.d.ts`, `tests/*.test.ts`, `scripts/validate_mods.py`;
the engine API `mods/mercy/.claude-plugin/types/claude-code/index.d.ts` (grep for the
names you need; never read all of it).

CHECKS:
1. One matcher-less hook per event; every classic hook calls `next(e)` except an owned
   gate's deny; `$` only passed to same-file helpers; no hook can exceed the 10 s
   own-time budget (sleep races); every hook catches its own errors.
2. `$.state` writes match the `types/index.d.ts` contract; userConfig defaults in
   `plugin.json` match `lib/runtime.ts` DEFAULTS (DEFAULT_HIDE duplicates focusHide).
3. Bridge parity: for each entry in `lib/bridgeplan.ts` POLICIES, compare the
   predicate with the owned Python link's real trigger. Any case where the mod skips a
   link that would have fired, or runs it with a wrong payload (cwd, session id,
   transcript), is HIGH.
4. Lanes: drain points (before classic tool events, PreCompact, Stop), slow-lane
   coalescing per file, behaviour when the process exits with jobs queued, failure
   accounting and release after three failures, heartbeat refresh.
5. Guard: run 25 sample commands through `analyze()`/`bashDeny` mentally or in a
   scratch test file (servers, watchers, one-shot test runs with `--watch=false`,
   subagent commits, harmless commands that mention "dev"); secret patterns against
   fixtures and real-looking false positives; files git would not track.
6. Verify gate (once per turn, `stop_hook_active`, background tasks, backgrounded runs
   give no evidence), governor rules, focus (repos only), brain (staleness, 1,600-char
   cap, store growth), auto-resume (per-session key, cancel paths, at most 12), pulse
   UI, model tools.
7. Did the mod load in this session and in each e2e run? Record the rollout switch.

### I. Installer, scripts, tests and CI (Ubuntu path) → `$AUDIT/I-installer.md`

FILES: `install.py`, `install.sh`, `installer/*.py`, `installer/manifest.json`,
`scripts/*.py`, `tests/*.py`, `hooks/tests/*.py`, `.github/workflows/ci.yml`,
`PREREQUISITES.md`.

CHECKS: install order (lean-ctx config written before lean-ctx is installed and
registered?); post-steps; each doctor row and whether it can pass while broken
(link-doctor and exit codes, stderr); a coverage map of which links, scripts and mod
features have no test; test hermeticity (residue of test sessions in production
telemetry: `ls ~/.claude/hooks/.telemetry | grep -cE '^(t-|t11-|audit-|fake)'`); the CI
Ubuntu leg; pinned versions against `npx -y` latest; manifest against live drift.

### J. State, telemetry, hygiene and security → `$AUDIT/J-hygiene.md`

PATHS: `~/.claude/hooks/.state/`, `hooks/.telemetry/`, `telemetry/`, `state/`,
`projects/` (sizes only), `plans/`, `settings.json.bak-*`, `~/.code-index`,
`~/.doc-index`.

CHECKS: size and growth (`du -sh`); what cleans what and after how long; files older
than 30 days; JSON state files written by more than one hook without a lock
(read-modify-write races); `git -C ~/.claude status --short --ignored`: any runtime
file that is untracked AND not ignored in this public repo is MED (a `git add -A`
would publish it); secret scan of tracked files with semgrep secrets rules or key-shape
greps (report path, line and kind only); permissions of `.env*` files (expect 600).
