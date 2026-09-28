# HOOKS-LAYER AUDIT — restored ~/.claude (2026-07-18)

Method: parsed `settings.json` + `dispatch.config.json`; existence/exec check on every
registered command; `py_compile` on all 76 hook .py files; `node --check` on all 16 .js
hooks; JSON-validated 22 config files; importlib check on every python import; smoke-ran
`prompt_router/router.py` with a fake payload; ran `hooks/tools/link-doctor.py`
(synthetic fire through every enabled dispatch link); traced wiring for 32 key guard
hooks; checked external binaries, state flags, and README/CLAUDE.md claims.

Headline: **the hooks layer is functionally healthy — 59/59 dispatch links PASS the
link-doctor, zero syntax/import/JSON failures, router live and working.** The real
problems are: duplicate legacy GSD/lean-ctx registrations in settings.json (double
execution), `~/.claude` not being a git repo (all documented git-recovery paths dead),
two missing tdd-guard reporters, a missing `plans/` directory, and stale docs.

---

## WORKING (verified)

### settings.json (item 1)
- All 8 `python3 ~/.claude/hooks/dispatch.py <event>` registrations: dispatch.py exists,
  compiles, and its config parses.
- Every absolute path in every registered hook command exists and is executable:
  `/home/mercy/.local/bin/lean-ctx`, `/home/mercy/.nvm/versions/node/v24.18.0/bin/node`,
  `~/.claude/skills/gstack/hosts/claude/hooks/question-log-hook` and
  `question-preference-hook`, all `gsd-*.js/.sh` hook files, `prompt_router/router.py`.
- Bare `lean-ctx hook observe` (UserPromptSubmit): `lean-ctx` is on PATH at
  `~/.local/bin/lean-ctx`. OK.
- **statusLine**: `${HOME}/.local/bin/node` is a VALID symlink →
  `/home/mercy/.nvm/versions/node/v24.18.0/bin/node` (target exists). The suspected
  broken symlink is NOT broken. `gsd-statusline.js` exists, passes `node --check`.
- Permissions block, env, mcpServers parse fine (all mcpServers commands resolvable:
  uv, uvx, npx, jcodemunch-mcp, jdocmunch-mcp, semgrep, graphify_launcher.py, lean-ctx).

### dispatch.config.json (item 2)
- 8 chains, **59 links, all `enabled:true`**, every `{PY}/{HOOKS}/{NODE}` target file
  exists. `user-prompt-submit` chain is intentionally empty (router live since
  2026-07-12; `_router_mode: "router"` note confirms).
- **link-doctor result: 59/59 OK, 0 FAIL** (synthetic payload through every link:
  session-start 10, pre-tool-use 20, post-tool-use 14, stop 9, subagent-stop 2,
  pre-compact 2, session-end 2).
- **76/76 .py hooks compile clean** (py_compile, incl. lib/, prompt_router/, tools/,
  tests/). **16/16 .js hooks pass `node --check`.**
- Node hooks require only core modules (`child_process`, `fs`, `os`, `path`) — no npm
  deps needed.

### Config files (item 3) — all present, all valid JSON
model-policy.json (IMPLEMENT→opus pin intact, `invoke_categories.IMPLEMENT:"opus"`),
trigger-floor.json (393 KB, built), commands-compat.json, dispatch.config.json,
fullstack-skills-reminder.config.json, graphify-enforce.config.json,
dox-tree-guard.config.json, dox-write-gate.config.json, doc-enforcement.config.json,
autonomous-skill-router.config.json (legacy, kept), skills-index.json (123 KB, built),
skills-index-overrides.json, skill_router.config.json, skill-aliases.json,
skills-lock.json, skills-provenance.json, jcodemunch-enforce.config.json,
jdocmunch-enforce.config.json, index-lifecycle.config.json,
ui-ux-stack-orchestrator.config.json, historic-invoke-commands.json,
prompt_router/router.config.json. No rebuild of trigger-floor/skills-index needed —
both exist and parse.

Grep of all hook sources for further .json refs: everything else they open is either
runtime-generated state (`.state/taste-dials.json`, `.state/retro-tracker.json`,
`state/<sid>.router-manifest.json`, session-breadcrumb, journals), per-project files
(`config.json`, `.autoinit.json`, `.doxinit.json`, `package.json`, `tsconfig*.json`),
or test fixtures. Two dead constants (see ORPHANED).

### prompt_router (item 4)
- `router.py` compiles; all data files present (trigger-floor.json, skills-index.json,
  prompt_router/router.config.json, modules/model_advice.py, budget/classify/select/
  manifest).
- Live smoke test (fake debug-and-plan payload, cwd=/home/mercy/Desktop): **exit 0**,
  emits well-formed `additionalContext` with Critical directives, Tool precedence
  (jcodemunch-first), the **sequential-thinking directive** (mandate absorbed — see
  `classify.py:242` "Match legacy sequential-thinking-mandate EXACTLY"), and ranked
  skills. Writes its manifest to `~/.claude/state/`. Telemetry confirms the router and
  dispatcher are firing in real sessions today (`~/.claude/telemetry/hook-fires-20260718.jsonl`).

### Runtime deps (item 5)
- Python: every import across hooks/*, lib/*, prompt_router/*, tools/*, tests/* is
  stdlib or local — **0 import failures** (no third-party python deps at all).
- Node: core modules only — **0 missing npm modules**.

### Key guard hooks (item 6) — all present, all wired (one deliberate deletion)
| Hook | Wiring |
|---|---|
| opus-guard.py | dispatch pre-tool-use mutator (Agent) — PASS |
| workflow-model-guard.py | dispatch pre-tool-use mutator (Workflow) — PASS |
| jcodemunch-enforce.py | dispatch gates jcm-gate-read / jcm-gate-leanctx + post jcm-mcp-used |
| graphify-enforce.py | dispatch pre-tool-use advisory (Task/Agent/Bash) |
| jdocmunch-enforce.py | dispatch advisory jdoc-doc-steer |
| jcodemunch-index-guard.py / graphify-index-guard.py / jdocmunch-index-guard.py | run inside session-start-aggregator.py (fan-out replaced by index-lifecycle; aggregator carries them) |
| tdd-guard-init-guard.py | inside session-start-aggregator + dox-tree-guard |
| tdd_guard_launcher.py | dispatch session-start + pre-tool-use → tdd-guard-gate.py → `tdd-guard` binary (present) |
| dox-tree-guard.py | inside session-start-aggregator (+ dox_engine) |
| dox-write-gate.py | dispatch gates (Write and Bash variants) |
| dox_engine.py / dox-child-scaffold.py | engine + post-write-aggregator chain |
| post-write-aggregator.py | dispatch post-tool-use; internally chains index-lifecycle post-write → dox-child-scaffold → doc-update-enforcer → security-scan-gate → jdocmunch-reindex-hook |
| hard-completion-gate.py + invoke-suite-gate.py | dispatch stop gates |
| security-scan-gate.py | via post-write-aggregator (semgrep present) |
| santa-method-writer.py | dispatch post-tool-use + subagent-stop |
| fullstack-skills-reminder.py | dispatch post-tool-use + stop (imports skill_router) |
| skill_router.py | imported by fullstack-skills-reminder + build-trigger-floor; router uses prompt_router/select.py |
| first-write-skill-gate.py, gateguard-write-gate.py, bash-write-gate.py, dangerous-bash-gate.py, blocking-doc-enforcer.py, desloppify-cleanup.py, ui-ux-stack-orchestrator.py | dispatch pre/post links — all PASS |
| doc-update-enforcer.py | via post-write-aggregator + blocking-doc-enforcer |
| session-plan-gate-hint.py | inside session-start-aggregator |
| gen-invoke-commands.py | manual generator (by design, reads model-policy.json) |
| index-lifecycle.py | dispatch stop (flush) + session-end + inside both aggregators |
| sequential-thinking-mandate.py | **deleted BY DESIGN 2026-07-14** — absorbed into router (classify.py reasoning-shaped path). Not a restore gap. |

### External binaries (item 7)
Present: `tdd-guard` (~/.nvm/.../bin), `graphify`, `lean-ctx`, `semgrep`
(~/.local/bin), `gh`, `git` (/usr/bin), `jcodemunch-mcp`, `jdocmunch-mcp`, `uv`,
`uvx`, `npx`, `node`. Missing: see MISSING.

### State flags (item 8)
- `~/.claude/state/` exists with `ponytail-active`, `caveman-active` (+ router
  manifests). Mechanism verified in code AND live: `ponytail-caveman-guard.py` reads
  `state/ponytail-active|caveman-active`; `opus-guard.py`/`workflow-model-guard.py`
  read `state/sonnet-only-mode|opus-only-mode|fable-only-mode`
  (`_DEFAULT_FLAG_DIR = "state"`, opus-guard.py:59). Proof it works: this very session
  received the PONYTAIL injection from the flag file.

### Docs vs reality (item 9) — what checks out
- `tools/link-doctor.py`, `installer/doctor.py`, `scripts/flip-dispatch.py`,
  `scripts/flip-router.py` all exist. Telemetry pipeline live (14-day retention files
  in `~/.claude/telemetry/`). hooks/CLAUDE.md's router-is-live claim matches reality.

---

## BROKEN (exists but wrong)

### B1. Duplicate legacy GSD + lean-ctx registrations in settings.json (double execution)
README/CLAUDE.md say settings.json holds ONLY the 8 dispatch entries. The restored
settings.json ALSO carries direct registrations that are simultaneously dispatch links,
so these fire **twice per event**:
- PreToolUse: `gsd-prompt-guard.js`, `gsd-workflow-guard.js` (also dispatch links),
  `gsd-validate-commit.sh` (dispatch runs the .js port), `lean-ctx hook rewrite`,
  `lean-ctx hook redirect` (also dispatch mutator links)
- PostToolUse: `gsd-context-monitor.js`, `gsd-read-injection-scanner.js`,
  `gsd-phase-boundary.sh` (dispatch runs the .js port), `lean-ctx hook observe`
- SessionStart: `gsd-check-update.js` (dispatch runs gsd-check-update-launcher.js),
  `gsd-session-state.sh` (dispatch runs the .js port), `lean-ctx hook observe`
- Stop/PreCompact/SessionEnd: `lean-ctx hook observe` (also dispatch exec links)

Everything still WORKS (all hooks are idempotent-ish), but it doubles hook latency and
can duplicate advisories/gate evaluations, and the .sh-vs-.js pairs mean the legacy
bash originals run alongside the P6-T2 ports. Likely cause: GSD updater re-installed
its hook block after the 100x cutover, or the restore merged pre- and post-cutover
settings.json.
**Fix (choose one side per pair):** remove the direct GSD/lean-ctx entries from the
`hooks` block of `~/.claude/settings.json` (keep the 8 dispatch entries + router +
statusLine + the gstack question hooks), **but keep `gsd-read-guard.js`** — it exists
ONLY in settings.json, not in any dispatch chain. Alternatively set `enabled:false` on
the corresponding dispatch links. Verify after with
`python3 ~/.claude/hooks/tools/link-doctor.py`.

### B2. ~/.claude is NOT a git repository
`git rev-parse` fails in `~/.claude`. Every documented recovery path is dead:
`flip-dispatch.py --legacy` / `flip-router.py --legacy` explicitly defer to
`git checkout pre-100x` / `pre-legacy-retirement`, which is now impossible; the
git-backup workflow that saved this laptop is also not re-established.
**Fix:** re-clone or re-init from the backup remote, e.g.
`cd ~/.claude && git init && git remote add origin <backup-remote-url> && git fetch &&
git reset --soft origin/main` (or clone fresh and copy `.git/` in), then confirm tags:
`git tag | grep -E "pre-100x|pre-legacy-retirement"`.

### B3. hooks/README.md is stale (pre-cutover)
Claims still made: (a) user-prompt-submit "currently runs the legacy injector set +
router --shadow" — false, router is live and the dispatch UPS chain is empty; (b) "70
enabled links" — actual: 59; (c) `flip-dispatch.py --legacy` restores the
65-registration block — that flag was retired 2026-07-14 (script prints a retirement
notice). hooks/CLAUDE.md already warns the stale-claim caused a real agent error on
2026-07-14 — README is the remaining offender.
**Fix:** update `~/.claude/hooks/README.md` "Prompt router + trigger floor" and "Flip /
revert" sections to match hooks/CLAUDE.md (router live 2026-07-12; 59 links; --legacy
retired).

### B4. rules docs reference the deleted sequential-thinking-mandate.py
`~/.claude/rules/sequential-thinking-doctrine.md` (in context every session) still
names `sequential-thinking-mandate.py` (UserPromptSubmit) as the forcing function. The
file was deleted 2026-07-14; the router's reasoning-shaped classifier is the successor.
**Fix:** edit that rule's Enforcement section to point at
`prompt_router/classify.py` / router directive instead.

### B5. dispatch.config.json comment vs disk: watch-daemon-session-end.py
The `index-session-end` link's `_swap` note says the old file was "deregistered +
atticked in P4-T7" — it is still sitting in `~/.claude/hooks/` (harmless forwarding
shim, unreferenced by any live chain). Cosmetic.
**Fix:** `mkdir -p ~/.claude/hooks/attic && mv ~/.claude/hooks/watch-daemon-session-end.py ~/.claude/hooks/attic/` (or leave; it does nothing).

---

## MISSING (referenced but absent)

### M1. `tdd-guard-go` reporter binary
Not found on PATH, ~/go/bin, ~/.local/bin, or nvm bin. No HOOK shells to it directly
(hooks call only `tdd-guard`), but the TDD doctrine's red/green pipeline needs it:
`rules/tdd-doctrine.md` — GO_UDP `make tdd` = `go test -json | tdd-guard-go` writes
`test.json`. Without it, tdd-guard advisories in Go projects run with no test state
(permanent "no failing test" warnings).
**Fix:** `go install github.com/nizos/tdd-guard/reporters/go/cmd/tdd-guard-go@latest`
(requires Go toolchain; per `skills/tdd-auto-init/SKILL.md:97`).

### M2. `tdd-guard-vitest` reporter
Missing; needed the moment a Vitest suite appears in a JS project (tdd-autoinit flips
the guard on and the reporter is the red/green source).
**Fix:** `npm install -g tdd-guard-vitest` (or per-project devDependency, per
skills/tdd-auto-init). (`tdd-guard-jest` / `tdd-guard-pytest` likewise absent — same
fix pattern when those stacks appear.)

### M3. `~/.claude/plans/` directory
Referenced by hooks/CLAUDE.md (`../plans/PLAN-2026-07-11-100x.md`), hooks/README.md
(`plans/P1-shadow-parity.md`), and listed in the root CLAUDE.md dox index
(`plans/CLAUDE.md`). Directory does not exist — restore gap (history/parity artifacts
lost).
**Fix:** restore `plans/` from the git backup (see B2); if unrecoverable, remove the
`plans/` row from the root dox index and the two doc references.

### M4. GO_UDP project absent from this machine
`rules/tdd-doctrine.md` says "GO_UDP backend is active"; no UDP_PLATFORM directory
found anywhere under /home/mercy. Not a hooks defect, but the tdd rules point at a
project that is not restored yet.
**Fix:** re-clone the GO_UDP repo, or note in rules that it lives elsewhere.

### M5. (Informational, no action) legacy snapshots
`hooks/legacy-prompt-stack.json` and `hooks/legacy-settings-hooks.json` are referenced
as module constants in flip-router.py / flip-dispatch.py but only by the RETIRED
`--legacy/--snapshot` paths, which exit with a clean "recover via git" message. Safe —
becomes fully moot once B2 (git) is fixed.

### M6. (Informational, no action) `skill_router_weights.json`
Optional learned-weights file read by skill_router.py / prompt_router/select.py /
skill-router-weight-updater.py; absent → weights default to 1.0; regenerated by the
weekly-retro-trigger chain. No fix needed.

### M7. (Informational, no action) dead config constants
`jcodemunch-index-guard.config.json` and `jdocmunch-index-guard.config.json` are
declared as `CONFIG_FILE` constants but never read anywhere in either guard — missing
files are harmless dead references.

---

## ORPHANED (present but unwired)

| File | Verdict |
|---|---|
| `hooks/_watch_refcount.py` | No importer, no reference anywhere. Leftover from retired watch-daemon era. Attic candidate. |
| `hooks/watch-daemon-session-end.py` | Replaced by `index-lifecycle.py session-end` link; only referenced by a comment. Attic candidate (see B5). |
| `hooks/lean-ctx-rewrite.sh` | Pass-through `exit 0` stub; live wiring calls `lean-ctx hook rewrite` directly. Delete/attic. |
| `hooks/lean-ctx-redirect.sh`, `lean-ctx-redirect-native`, `lean-ctx-rewrite-native` | lean-ctx installer artifacts; nothing in settings.json or dispatch invokes them. Delete/attic. |
| `hooks/tdd-guard-launcher.sh` | Deliberate 30-day flip-back copy of the P6-T2 py port (documented). Keep until window closes, then attic. |
| `hooks/gsd-*.sh` (phase-boundary, session-state, validate-commit) | Documented as flip-back copies, but currently LIVE via the duplicate settings.json registrations (B1). After fixing B1 they become true flip-back copies. |
| `hooks/build-skills-index.py`, `build-trigger-floor.py`, `gen-invoke-commands.py` | Manual CLI builders — wired by doctrine/docs, not by events. NOT orphans. (Note: `scripts/build_skills_index.py` also exists — near-duplicate name, worth a look during cleanup.) |
| `~/.claude/state/audit-test.router-manifest.json` + 35 session manifests | Transient; `state-cleanup.py` purges >24h ones. No action. |

---

## Verification commands used (reproducible)
- `python3 /tmp/.../hooks_audit.py` (existence/exec/JSON/import sweep — raw JSON at
  `hooks-audit-raw.json` alongside this report)
- `python3 /tmp/.../compile_check.py` → 76 checked, 0 failures
- `python3 ~/.claude/hooks/tools/link-doctor.py` → **59/59 OK, 0 FAIL**
- `python3 ~/.claude/hooks/prompt_router/router.py < payload.json` → exit 0, valid output
