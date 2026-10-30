# Integration report — ECC merge (package `integrate`, 2026-10-30)

Worktree `~/CODE_FILES/dotclaude-merge`, branch `ecc-merge`, base `6b55a26`. Nothing is committed:
`scripts/golive.py` owns git after review (go-live list in section 7).

## 1. Summary

- Packages integrated: 12 (oom-sentinel, oom-restore-index, gates, session-stop, dispatcher-router,
  library, agents-skills, doctrine-tokens, hooks-hygiene-mod, workflows, model-routing, learning).
- Changed paths: 1,179, every one owned by exactly one package (`scripts/check_ownership.py`).
- Suite (`python3 -m pytest hooks/tests tests -q -p no:cacheprovider`, `CLAUDE_HOOK_DOCTOR` unset):
  baseline 7 failed / 3,041 passed / 26 skipped -> now 0 failed / 3,082 passed / 25 skipped (65 s).
- Dispatch: 15 chains, 13 registered events, 59 enabled links (`link-doctor.py`: 59/59 OK).
- Doctrine (CLAUDE.md + imported machines part + rules without `paths:`): 38,476 -> 18,409 chars;
  `CLAUDE.md` 6,256 -> 4,000 chars (byte-identical to `docs/merge/CLAUDE.md.draft`).

## 2. Ownership check

Before step 1 (after writing the script): `OK 1118 changed paths, all owned` (integrate 3).
Final (after FIX-1): `OK 1179 changed paths, all owned; per package: {agents-skills 177, dispatcher-router 36,
doctrine-tokens 30, gates 23, hooks-hygiene-mod 75, integrate 63, learning 16, library 567,
model-routing 29, oom-restore-index 14, oom-sentinel 94, session-stop 22, workflows 33}`.

### Edits outside owned_paths

All are inside another package's owned paths (so the ownership check stays green); each is minimal.

| File | Lines | Why | Owner |
|---|---|---|---|
| `hooks/tests/test_gates.py` | docstring bullet, two `test_dox_cleanup_*` tests deleted | they import `scripts/dox_cleanup.py`, deleted by hooks-hygiene-mod (plan 0.9) | gates |
| `hooks/tests/test_tdd_guard_bare.py` | 110 (G5 encoding), 145/147 (G3: `_WIN = "C:" + "\\"`) | grep gates G3/G5 | hooks-hygiene-mod |
| `hooks/tests/test_gate_state.py` | 28, 35 (G5) | grep gate G5 | hooks-hygiene-mod |
| `hooks/tests/test_stop_gates_wp4.py` | 170 (G5) | grep gate G5 | hooks-hygiene-mod |
| `hooks/tests/test_state_cleanup_wp8.py` | 125, 155 (G5) | grep gate G5 | hooks-hygiene-mod |
| `hooks/tests/test_code_files_skip.py` | 23 (G3, `_WIN`) | grep gate G3 | hooks-hygiene-mod |
| `installer/basetools.py` | `before_deps`: no row when gitleaks SKIPs | `tests/test_wintools_wiring.py:49` expects no gitleaks row on Windows | library |
| `installer/basetools.py` | `ensure_gitleaks(which=None)`, looked up at call time | the default `which=shutil.which` was bound at import, so `test_before_deps_emits_gitleaks_row` failed on any machine with gitleaks on PATH (it appeared on this one at 02:37 during the run; after go-live it always is) | library |
| `hooks/tests/test_autonomy_wpc_text.py` | 237: `"higgsfield__authenticate" in txt` | the doctrine draft of `rules/frontend.md` names the connector tool `mcp__claude_ai_higgsfield__authenticate`; the assertion still requires the login tool and "pending" | dispatcher-router |

## 3. INTEGRATE snippets applied

| Package | Item | Where | Status |
|---|---|---|---|
| oom-sentinel | 1 memwatch-ensure, memwatch-brake (+ shell) links | `dispatch.config.json` | applied |
| oom-sentinel | 2 `oomguard` post-step, `doctor_probes.oomguard` | manifest | applied |
| oom-sentinel | 3 doctor rows | `doctor.py` | applied, guarded: SKIP under `--ci`, doctor mode, pytest |
| oom-sentinel | 4 daily `oomguard` step + `_CHANGED` | `selfheal-daily.py` | applied |
| oom-sentinel | 5 `_repair` oomguard branch | `selfheal.py` | applied, SKIP under pytest |
| oom-sentinel | 6 `.gitignore` state lines | `.gitignore` | `/oomguard.local.json` added; `state/` covers the rest |
| oom-sentinel | 7 template env caps | template | applied |
| oom-sentinel | 8 DIRECTIVES row 31 | `docs/DIRECTIVES.md` | already present |
| oom-sentinel | 9 dox rows | hooks, lib, tools, installer, scripts, tests dox | applied |
| oom-sentinel | 10 MEMORY.md pointers | main session after go-live | handed back |
| oom-restore-index | 12.1 ledger links, failure-hint `mcp__.*` | `dispatch.config.json` | applied |
| oom-restore-index | 12.2 `sessionTitle` forwarding in `dispatch.py` | not integrate's file | handed back (inert: `grep -c sessionTitle hooks/dispatch.py` = 0) |
| oom-restore-index | 12.3 `.gitignore` | — | not applicable (`state/`) |
| oom-restore-index | 12.4 retention rows | `state-cleanup.py` | live-sessions row present; resume-lock / mcp-unhealthy / restore.* handed back to hooks-hygiene-mod |
| oom-restore-index | 12.5 dox rows | hooks, scripts, tests dox | applied |
| oom-restore-index | 12.6 OOM-GUARD runbook pointer | `docs/OOM-GUARD.md` | handed back (oom-sentinel's file) |
| gates | 1 links, connector tools | `dispatch.config.json` | applied |
| gates | 2 PreToolUse matcher `mcp__github__.*` | template | applied |
| gates | 3 hookify sentence | `rules/01` (via draft) | applied |
| gates | 4 DIRECTIVES row 31 | — | already present |
| gates | 5 dox rows | hooks, lib, hooks/tests dox | applied |
| gates | 6 retention rows | `state-cleanup.py` | handed back (hooks-hygiene-mod) |
| gates | 7 skills index | regenerated | applied |
| gates | 8 `.gitignore` | — | not applicable |
| session-stop | 1 links, chains, budgets | `dispatch.config.json` | applied |
| session-stop | 2 Stop 40, StopFailure, InstructionsLoaded | template | applied |
| session-stop | 3 delete `ponytail-caveman-guard.py`, smoke test, fixtures | step 2, step 5 | applied |
| session-stop | 4 delete `suggest-compact.sh` | — | already deleted |
| session-stop | 5 `test_new_lines_fit` | `test_session_start_budget.py` | applied |
| session-stop | 6 retention rows | `state-cleanup.py` | handed back (hooks-hygiene-mod) |
| session-stop | 7 dox rows | hooks, lib, tools, hooks/tests dox | applied |
| session-stop | 8 DIRECTIVES rows | — | already present (rows 31/32) |
| session-stop | 9 `--observed` reader | doctrine-tokens | already present |
| session-stop | 10 caveman `mode` | — | not needed (`test_core_skill_set_has_no_full_entry` passes) |
| dispatcher-router | 1 template registrations | template | applied (shell strings, deviation 1) |
| dispatcher-router | 2 budgets, chains, `crit_exempt` | `dispatch.config.json` | applied (instructions-loaded 800 ms, deviation 4) |
| dispatcher-router | 3 deletions, dox rows | step 2, step 13 | applied |
| dispatcher-router | 4 MODEL_ROUTING keywords move | optional | not applied |
| dispatcher-router | 5 `state/*.router-reset` retention | `state-cleanup.py` | handed back (hooks-hygiene-mod) |
| dispatcher-router | 6 cost-meter rows | `measure_context_cost.py` | handed back (doctrine-tokens) |
| dispatcher-router | 7 `rules-tool-intelligence.md` mirror | not owned | handed back |
| library | 1 G7 | `grep_gates.py` | applied, scope library + agents (deviation 7) |
| library | 2 CI steps | `ci.yml` | applied (validate_imports over library + agents) |
| library | 3 daily `library` step | `selfheal-daily.py` | applied (`_ROOT` paths) |
| library | 4 gitleaks, `library-check` | manifest | applied |
| library | 5 scripts dox rows | `scripts/CLAUDE.md` | applied |
| library | 6 `library_routes.py` row | `prompt_router/modules/CLAUDE.md` | handed back (not owned) |
| library | 7 `check_ownership.py` env form | `scripts/check_ownership.py` | applied |
| library | 8 installer dox | `installer/CLAUDE.md` | applied |
| library | 9 `.gitignore` | — | not applicable |
| library | 10 CHANGELOG bullet | `docs/CHANGELOG.md` | applied (358 entries) |
| agents-skills | 1 regenerate index + floor | step 14 | applied |
| agents-skills | 2 mcp-inventory | step 14 | applied (home paths as `~`, project rows dropped) |
| agents-skills | 3 `PENDING_AGENTS_SKILLS = {}` | model-routing's test | handed back |
| agents-skills | 4 two 1,200 caps | doctrine-tokens / agents-skills tests | handed back |
| agents-skills | 5 `.gitignore` | — | not applicable |
| agents-skills | 6 TOKEN-BUDGET agent row | generated | applied (regenerated) |
| agents-skills | 7 README counts | `README.md` | applied |
| agents-skills | 8 `context-monitor` link | `dispatch.config.json` | applied |
| doctrine-tokens | 1 drafts + README | root, `rules/`, README | applied byte-for-byte |
| doctrine-tokens | 2 `.gitignore` | `.gitignore` | applied |
| doctrine-tokens | 3 outputStyle, skillOverrides, env | template | applied (27 entries, deviation 6) |
| doctrine-tokens | 4 daily `machines-split` | `selfheal-daily.py` | applied (`MOVED` rows) |
| doctrine-tokens | 5 post-step + render | manifest, `render.py` | applied |
| doctrine-tokens | 6 deletions | step 2 | applied |
| doctrine-tokens | 7 docs, dox, CHANGELOG, dox trims | step 13 | applied; infra-root dox fix handed back |
| doctrine-tokens | 8 skills index | step 14 | applied (132) |
| doctrine-tokens | 9 TOKEN-BUDGET write | step 14 | applied; `--record` at go-live |
| hooks-hygiene-mod | 1 `test_gates.py` | step 2 | applied |
| hooks-hygiene-mod | 2 `WRITE_TOOLS` + mcp-post-hints | not owned | handed back |
| hooks-hygiene-mod | 3 `validate_skills.py:191` | agents-skills | handed back |
| hooks-hygiene-mod | 4 `skills_lib.py:9` | unowned | handed back |
| hooks-hygiene-mod | 5 dox rows | scripts, lib, tools, mods dox | applied |
| hooks-hygiene-mod | 6, 7, 8, 12 | session-stop / unowned files | handed back |
| hooks-hygiene-mod | 9 manifest `links` | manifest | applied (deleted) |
| hooks-hygiene-mod | 10 daily `mcp-inventory` | `selfheal-daily.py` | applied (atomic write, preamble kept, public paths) |
| hooks-hygiene-mod | 11 `.gitignore` | — | not applicable |
| workflows | 1 `build-workflows` post-step | manifest | applied |
| workflows | 2 daily `workflows` step | `selfheal-daily.py` | applied |
| workflows | 3 render runs the builder | `render.py` | applied as post-step `workflows` |
| workflows | 4 CLAUDE.md §1 | via draft | applied |
| workflows | 5 `.gitignore` | — | not applicable |
| workflows | 6 dox rows + index | scripts, tests, docs | applied; `workflows/src` row handed back |
| workflows | 7 re-check after agents-skills | step 15 | `build_workflows.py --check` OK |
| workflows | 8 Gate 4 reads SANTA-REVIEW.json | gates | handed back |
| model-routing | plan-tier-detect link | `dispatch.config.json` | applied |
| model-routing | `render_overrides` in `render()` | `render.py` | applied (`_tier_overrides`, fail-open) |
| model-routing | `.gitignore` lines | — | not applicable (`state/`) |
| model-routing | rules/04 replacement | via draft | applied |
| model-routing | directive 32, INDEX link | — | already present / applied |
| learning | 13a `observe-log` link | `dispatch.config.json` | applied |
| learning | 13b daily `learning-evolve` | `selfheal-daily.py` | applied (last step) |
| learning | 13c `.gitignore` | — | not applicable |
| learning | 13d INDEX, CHANGELOG | docs | applied |
| learning | 13e dox rows | hooks, lib, tools, hooks/tests, docs dox | applied |
| learning | 13f skills index | step 14 | applied |
| learning | retention | `state-cleanup.py` | already present |

## 4. Deviations and open items

Deviations (spec section 0 plus what the run found):

1. Hook registrations stay shell strings; exec-form `args` / `if` groups not adopted
   (`doctor_hook.py` and the render tests pin the string form).
2. No `fallbackModel` / `model` in the template; `render.py` adds them per tier; `maxEffortLevel` added.
3. `higgsfield` leaves the manifest; the live registration goes at go-live (`mcp-remove`).
4. `budgets.instructions-loaded.ms` = 800.
5. `.gitignore`: three lines; `state/` covers every state path R3.7 named.
6. `skillOverrides` omits `lean-ctx: name-only`: the template and the render must hold no
   `lean-ctx` string (`test_template_contract`, `render.py` refuses it).
7. G7 (and the CI step) scans `library/` and `agents/` only. Over the five dirs
   `validate_imports.py` exits 1 (M=24 P=1 S=3 U=1 V=193: upstream-locked skills' `@latest`, OOM
   fixtures naming `ptyxis-spawn`, scrubber test strings). The plan measured exit 0; it is not.
8. Render post-steps run only when `--out` is the live `settings.json` (CI's temp render and any
   sandboxed render stay side-effect free), never under pytest or doctor mode
   (`RENDER_POST_STEPS_ALLOW_TEST=1` for tests that stub them); the tier is detected before the
   render on a real write so the first render is tier-correct.
9. The daily `mcp-inventory` step writes home paths as `~` and drops project-scope rows (G6).
10. `tests/test_dox_tree.py` ignores tracked paths deleted in the worktree (a deletion not yet
    committed is gone).
11. Both conftests drop `plan-tier.json` from the shared test state dir before each test: the
    session-start chain's `plan-tier-detect` link wrote it and leaked a tier into statusline tests.

Open items (handed back; not integrate's files):

1. (closed, FIX-1) settings_seed.seed_overlay compared a user model against the tier-derived render
   and dropped an equal pin; model/fallbackModel are now always seeded (ownership of
   installer/settings_seed.py + tests/test_installer_preserve.py moved to integrate).
2. `validate_imports.py library skills agents hooks docs` (acceptance) exits 1, and `golive.py`'s
   import-hygiene step runs the same command: needs an allowlist (library) before go-live.
3. `dispatch.py` `sessionTitle` forwarding (oom-restore-index 12.2): the ledger's title is dropped.
4. Retention rows (`hookify-cache`, `*.toolring.json`, `*.typecheck.json`, `*.stop-failure.json`,
   `typecheck/*.tsbuildinfo`, `*.router-reset`, resume locks, `*.mcp-unhealthy.json`) in
   `state-cleanup.py` (hooks-hygiene-mod).
5. Dox gaps outside integrate: `mods/mercy/hooks/features`, `mods/mercy/hooks/lib`,
   `mods/mercy/tests`, `workflows/src` local `CLAUDE.md` files do not name every file.
6. dox re-appends `## dox index (children)` to the root `CLAUDE.md` in this worktree on writes;
   it was 0 at the end of this run. golive must check before commit.

## 5. Dispositions fulfilled

Template optimized (env caps, effort cap, output style, overrides, registrations); dispatch config
merged (ECC hooks.json idea = stable ids + schema test); SubagentStop/PostCompact registrations
dropped (chains stay disabled); `ponytail-caveman-guard.py` merged into the aggregator; the weights
quartet merged into `scripts/skill_health.py`; integrate-owned tests kept with cases added;
fixtures +2; manifest, deps, doctor, selfheal, render, selfheal-daily, grep gates, CI, `.gitignore`
optimized; root doctrine, rules (with the `rules/web` grafts), README, PREREQUISITES optimized; dox
files optimized and trimmed; `hooks/README.md` refreshed; generated indexes regenerated;
mcp-inventory regenerated. `assets/CLAUDE.md` and `templates/CLAUDE.md`: no new files, nothing to
add. `installer/render.py.bak-20260718` and `CLAUDE.md.bak`: gitignored stale copies, deleted at
go-live by the main session.

## 6. Token table

`python3 scripts/measure_context_cost.py`: doctrine total 18,409 chars (~4,602 tokens); fixed floor
61,397 chars (~15,349 tokens).

| Row | Before | After | Δ |
|---|---|---|---|
| CLAUDE.md | 5,703 | 3,980 | -1,723 |
| machines file (imported part) | 22,512 | 5,752 | -16,760 |
| rules/0*.md | 10,261 | 8,677 | -1,584 |
| skill listing | 45,200 | 24,902 | -20,298 |
| agent descriptions | 16,000 | 12,837 | -3,163 |
| session-start aggregator sample | 5,500 | 2,569 | -2,931 |

The eager-MCP figure (`/context`) is recorded at go-live: `measure_context_cost.py --mcp-eager --record <n>`.

## 7. Go-live command list

For the main session; no git commands except golive's own (A8b-d run inside it):

```
# review this report, then:
cd ~/CODE_FILES/dotclaude-merge
# hook-events smoke (isolated state dirs: a bare loop leaves a stop breadcrumb with the worktree path in hooks/.state)
S=$(mktemp -d); for f in tests/fixtures/hook-events/*.json; do ev=$(basename "$f" .json); \
  CLAUDE_HOOK_DOTSTATE_DIR=$S/dotstate CLAUDE_HOOK_STATE_DIR=$S/state CLAUDE_HOOK_TELEMETRY_DIR=$S/telemetry \
  python3 hooks/dispatch.py "$ev" < "$f" > /dev/null || { echo "FAIL $ev"; break; }; done; rm -rf "$S"
python3 scripts/golive.py --plan          # the 15 steps: ownership, pytest, validators, render-check, secrets x2, commit, merge, render-live, guard-checks, zram, mcp-remove, push, replica, memory
CLAUDE_ECC_PACKAGES=~/CODE_FILES/claude-ecc-merge/plan/PACKAGES.json python3 scripts/golive.py --yes-automatic
# golive stops on the first failing step; nothing is retried destructively.
# open item 2 above stops its validators step until it is fixed.
# after it: python3 ~/.claude/installer/doctor.py   (oom rows PASS; claude-launcher WARN only if a shell has no rc file)
#           /context in the live session -> python3 ~/.claude/scripts/measure_context_cost.py --mcp-eager --record <n>
#           memory: decision:: lines (golive writes them to state/golive for the main session)
```

## 8. Rollback

Nothing is committed: `git -C ~/CODE_FILES/dotclaude-merge checkout -- <path>` restores any
integrate-owned tracked file to `6b55a26`; remove the new ones (`scripts/check_ownership.py`,
`INTEGRATION-REPORT.md`, `tests/fixtures/hook-events/stop-failure.json`,
`tests/fixtures/hook-events/instructions-loaded.json`, `docs/TOKEN-BUDGET.md` regenerates). The four
deleted hooks and `hooks/skill_router_weights.json` come back with `git checkout -- hooks/<name>`.
Regenerated indexes are rebuilt by the step-14 commands. Nothing on the machine changed: no render
wrote `settings.json` (dry-run only), no unit was installed (every session-start run carried
`CLAUDE_HOOK_DOCTOR=1`), `state/` is gitignored. The cross-package edits are listed in section 2
and revert the same way.
