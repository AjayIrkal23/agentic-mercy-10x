<!-- dox:child v1 -->
# `hooks/tests/` — local rules (dox)

> Local doc for this directory only. Update it when you add, remove, or rename tests.

## What lives here

Unit tests for the hook layer — pytest-style `assert` functions, `monkeypatch`/`tmp_path`
only. Hook logic lives in `../`; installer/template tests live in `../../tests/`.

## Local conventions

- `test_<subject>.py` / `test_<behaviour>()`. Put the hooks dir on `sys.path` via
  `Path(__file__).resolve().parents[1]`; never rely on cwd.
- Extend the existing file for a covered module (all `lib/` coverage →
  `test_lib_foundation.py`).
- Run: `python3 -m pytest hooks/tests -q` (not the files directly). `conftest.py` sends
  telemetry and `state/` to temp dirs; a helper that seeds or reads gate telemetry must
  use `CLAUDE_HOOK_TELEMETRY_DIR` too (`test_gates._tel_dir`). `conftest.py` also sets
  `CLAUDE_HOOK_DOTSTATE_DIR` (`hooks/.state`); a full run leaves 0 files in the live
  state/telemetry dirs.

## Key files

| File | Role |
|------|------|
| `test_lib_foundation.py` | `platform`, `repo_context` ($HOME ceiling), `hook_telemetry` |
| `test_dispatch_mutator.py` | dispatcher threads mutator `updatedInput` (the dropped-mutation regression); mod bridge: owned links skipped only for the owner session with a fresh `MERCY_MOD_BEAT`, `--only` ignores ownership |
| `test_prompt_router.py`, `test_router_surface.py`, `test_surface_classification.py` | router classify/rank/output shape, stack/cwd surface, FE/BE detection, path-scoped push = Read; `fullstack-post` doc hit decided by path segments, never file content |
| `test_router_scoring.py` | description keywords half weight, stack-only surface half credit, hidden skills never ranked, learned weights never boost, URLs / `*-guard` names are not SECURITY |
| `test_tool_intelligence_routes.py` | context7 route needs an API-question cue plus a library token (never a `name/` path, never bare "go") |
| `test_jdocmunch_enforce.py` | jdoc-doc-steer nudges only whole reads of large indexed docs; small, sliced and `CODEX.md` reads pass silently (`{}`) |
| `test_mcp_post_hints.py` | PostToolUse MCP hints + memory search directive |
| `test_memory_load_on_start.py` | SessionStart memory: 5 entities fit 1,200 chars (whole-line clips), ranked fragile > decision > pattern, newest first; repo-name match normalises `_`/space to `-` (F-10) |
| `test_link_doctor.py` | link-doctor fails a crashing link, a non-zero exit (`FAIL(rc=N)`) and a missing script; stderr alone passes |
| `test_dangerous_bash_gate.py` | destructive forms denied (chained rm after a /tmp rm, `bash -c`/`eval` payloads, quoted SQL to DB clients, Mongo drop, dd/mkfs, curl\|sh); commit messages, heredocs and /tmp cleanups pass |
| `conftest.py`, `test_telemetry_isolation.py` | suite-wide temp telemetry/state dirs; router + dispatch write only to the override |
| `test_workflow_models.py` | every `agentType`/`model` in `workflows/*.js` matches `model-policy.json` pins (unpinned = sonnet) |
| `test_teammate_idle_gate.py` | an expected artifact counts when it exists relative to the repo or to the run folder; a missing one still blocks |
| `test_turns.py` | `lib/turns`: meta / task-notification / interrupt rows never start a turn; slash-command rows do; `turn_bash_commands` |
| `test_gates.py` | Stop/Pre gates incl. invoke-suite-gate 1-nag cap; completion gate skips sessions that only touched `~/.claude` infra (mods, installer, tests included); tdd-guard spawned by resolved path over UTF-8; git global options in the destructive-command gate (no exponential backtracking); semgrep credit only for scans; codex-capture, security-scan-gate and doc-update-enforcer on Windows paths; hooks name only existing `rules/` files |
| `test_gateguard.py` | gateguard-write-gate counts Python importers (5 → `ask`, 4 → `{}`, comment/string mentions ignored); skip patterns match Windows separators |
| `test_blocking_doc_enforcer.py` | `git commit` in GO_UDP/UDP_PLATFORM denied until docs + `PROJECT_LINKAGES.md` are written; other repos, amends, no-state pass |
| `test_opus_guard.py`, `test_workflow_model_guard.py`, `test_model_mode.py`, `test_model_advice.py` | model routing (pins, escalation, routing log) |
| `test_model_policy_consistency.py` | agent frontmatter / template env / escalation agree with `model-policy.json`; `max` effort banned |
| `test_gen_invoke_skills.py` | `/invoke` skill generator determinism |
| `test_index_lifecycle.py` | index-lifecycle state machine, jcodemunch env passthrough, ollama-down DEFER, db chosen by recorded `source_root` (same-named clones) |
| `test_session_start_budget.py` | dispatched SessionStart and every `budgets.chars` stay under the 8,000-char cap |
| `test_agent_path_skills.py` | agent bodies name their `paths:`-scoped preloads to Read (`skills:` skips them) |
| `test_own_checkout_guard.py` | this checkout is never indexed / dox-swept under a sandbox HOME; doctor mode spawns no writers |
| `test_router_wp1.py` | classify fixes: negation window, intent plurals, `write … tests`, noun-only LARGE, mobile surface/tag + expo skill mapping, `mobile` not a UI word, shared weights loader parity (C-04, C-07, C-12, C-16) |
| `test_router_wp1_emit.py` | `prompt_router/policy.py` + router emission: hard/soft enforcement, doctor-run no-record, skill line format, UI line availability, routing cap, chat/question/trivial gating (subprocess: lunch → `{}`), symbol summary length, session-model opus skip (C-05, C-10, C-11, C-12, C-14, C-17, D-05) |
| `test_router_wp1_mcp.py` | MCP availability: reticle only when instrumented (router route + mcp-post-hints), project-disabled servers, no dead plugin route targets (G-03, G-14) |
| `test_dispatch_wp3.py` | dispatcher: deferred advisories, lean-ctx adapters, mod failure/release signal, gate precedence, `via` on `--only` rows, raw stdout only on exit 0, line-boundary cap, ownership parsing, `ms` on every row |
| `test_gates_wp3.py` | first-write-skill-gate is a hint, tdd-guard skips non-code edits, destructive-connector ask gate, tdd-guard link deferred |
| `test_write_gates_wp3.py` | bash-write-gate allow-list, blocking-doc-enforcer in any doc-tree repo, dox-write-gate once per repo, `--force-with-lease` passes |
| `test_gateguard_wp3.py` | TS/JS importer counting needs a quoted specifier; an ask is acknowledged only after the write ran |
| `test_settings_wp3.py` | `settings.template.json` hook matchers agree with `dispatch.config.json`; no literal `lean-ctx` string |
| `test_stop_gates_wp4.py` | suite gate scope (path/one-sided surface match, soft pushes advisory), infra never counts toward gate thresholds, turn key "?" |
| `test_session_lifecycle_wp4.py` | breadcrumb keyed by git root, pre-compact handoff, retired subagent-stop / post-compact |
| `test_session_start_wp4.py` | aggregator core block at a fixed budget, startup/clear only |
| `test_weights_loop_wp4.py` | weights updater never rewrites an unchanged tracked file; weekly-retro-trigger runs only on new input |
| `test_lifecycle_wp4.py` | teammate-idle-gate, retired fullstack stop mode, subagent-context and permissions self-heal |
| `test_agents_wp5.py` | run folders, team path, agent contracts, preload cap 20k (uiux 30k), model-mode show state dir |
| `test_opus_guard_explicit.py` | E-04: an explicit `model` needs the user's override phrase for pinned judges, executors and fable |
| `test_links_smoke_wp7.py` | fires the 18 previously untested dispatch links in a copied hooks tree with temp HOME/state/telemetry |
| `test_lead_wp8.py` | lead items: `ms` on the router live row, `locked_update` concurrency and corrupt-file recovery, hcg consent regex = the mod's, subagent mode line says omit `model`, every writer honours `CLAUDE_HOOK_DOTSTATE_DIR`, link-doctor children never write live state, state writers use `locked_update` |
| `test_autonomy_wpc_text.py`, `test_autonomy_wpc_memory.py`, `test_autonomy_wpc_session.py`, `test_autonomy_wpc_cleanup.py` | autonomy WP-C: router/gate text never tells the user to type (model advice, dispatch, graph, Gate 2-5), Higgsfield login line + conditional templates, Gate 7 memory-save block (once per turn, saves counted from the transcript), mod-off and self-heal session lines, test-session purge with logged counts |
| `test_autonomy_wpb_builders.py`, `test_autonomy_wpb_gates.py`, `test_autonomy_wpb_reprobe.py` | autonomy WP-B: `build_fail` telemetry carries scrubbed builder stderr; the detached builder waits for ollama instead of asking; jcodemunch / graphify gates and the graphify launcher start the build themselves; `index-lifecycle.py reprobe` and the HEAD-moving git trigger spawn one reprobe |
| `test_dox_engine_wp8.py` | `dox_engine plan` lists leaf docs (≤ `LEAF_MAX_FILES` code files) that do not name their code files (F-12); layer roots stay folded |
| `test_state_cleanup_wp8.py` | `state-cleanup` retention families (J-03) on seeded aged/fresh files in a temp base |
| `test_skill_router_wp8.py` | `skill_router` rule hygiene (NEW-07): no generic review pushes, hidden skills dropped, `be_errors` / `be_debug` / `fe_ui_design` leads |
| `test_retention_report_wp8.py` | `retention-report.py` lists reclaimable space on a fake layout and deletes nothing |

## Gotchas / fragile spots

- `$HOME` tests prove the ceiling only on a machine with a stray `~/.git`; elsewhere they
  pass vacuously.
- Router tests build tmp repos and run the hook as a subprocess — keep them fast.
- Tests must pass with a bare `HOME` and a checkout outside `~/.claude` (CI does both).
  Router MCP-directive tests get their `~/.claude.json` from the `fake_home` fixture; check
  with `HOME=<empty dir> python3 -m pytest hooks/tests tests -q`.
- A test that fires a real hook chain sets `CLAUDE_HOOK_DOCTOR=1`, or its writers act on
  real repos.
- CI exports `CLAUDE_HOOK_DOCTOR=1` for the whole pytest step. A test of a path that
  no-ops under doctor (git-trigger re-probe, `_reprobe_graphify`) must
  `monkeypatch.delenv("CLAUDE_HOOK_DOCTOR", raising=False)`, or it passes locally and
  fails in CI.

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children: none
