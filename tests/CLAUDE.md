<!-- dox:child v1 -->
# `tests/` — local rules (dox)

> Local doc for this directory only. Update it when you add, remove, or rename tests.

## What lives here

Repo-level tests for the installer, doctor, settings template/render, skills catalog and
portability. Hook unit tests live in `../hooks/tests/`. `fixtures/hook-events/*.json` are
synthetic event payloads (one per event, incl. subagent-start, teammate-idle,
post-tool-use-failure, post-compact, config-change).

## Local conventions

- Run: `python3 -m pytest tests -q` (CI runs it on Ubuntu + Windows).
- Tests must not touch the live `~/.claude`: sandbox `HOME`/`CLAUDE_CONFIG_DIR` and set
  `CLAUDE_HOOK_DOCTOR=1`. `conftest.py` (here and in `hooks/tests/`) points
  `CLAUDE_HOOK_TELEMETRY_DIR` and `CLAUDE_HOOK_STATE_DIR` at temp dirs for the whole run;
  scripts derive `hooks/.telemetry` from their own path, so HOME alone never isolated them.
- No PyYAML or other non-stdlib imports (the CI interpreter is bare).
- Tests that load installer modules with `_load()` replace `sys.modules[...]`; a test that
  monkeypatches a module `selfheal` imports lazily must pin it with
  `monkeypatch.setitem(sys.modules, …)` (see `test_selfheal_wp7` `box`).
- Doctor/installer sandboxes hide `claude` and `tsc` from `shutil.which` (I-17).

## Key files

| File | Role |
|------|------|
| `test_installer.py`, `test_doctor.py` | installer + doctor smoke, read-only doctor in a sandbox; `model-routing` invariant (judges on Opus, no executor pinned) |
| `test_render_settings.py`, `test_template_contract.py` | render equivalence; template has no MCP block, no home literal, no "lean-ctx"; Windows `CLAUDE_DIR` = the rendered checkout; `{{MOD_DIRS}}` → absolute `CLAUDE_CODE_PLUGIN_DIRS` joined with `os.pathsep` |
| `test_statusline.py` | `scripts/statusline.py` run as a subprocess the way Claude Code runs it (git cache in `CLAUDE_STATUSLINE_CACHE_DIR`): model/effort, context bar, cost, 5-hour/7-day windows, git counts, `NO_COLOR`, `COLUMNS` |
| `test_semgrep_env.py` | template env sets `EIO_BACKEND=posix` (semgrep-core's io_uring dies under the 8 MB memlock limit) |
| `test_envelope_precedence.py` | any skill or `rules/backend.md` that prescribes a nested `error:{…}` envelope also says "the project contract wins" |
| `test_timeout_ladder.py` | each event's worst dispatch path (sequential gates/mutators/sync execs + parallel advisories, priority>0 skipped past `budgets.ms`) stays 1 s under its settings `timeout` |
| `test_mods_contract.py` | `manifest.mods` shape; every enabled mod passes `validate_mods.py` static M1–M6; the M3 scan ignores comments |
| `test_settings_wp8.py` | template contract (A-03): marketplaces `karpathy-skills`, `nateherk`, `ponytail` carry `autoUpdate: false` (hook-running plugins from personal repos update by hand); `superpowers-marketplace` stays true |
| `test_skills_wp2.py` | new skills' frontmatter, curated keywords, router recall for the C-13 prompts, core-skill-set budget, rule and skill `paths:` globs vs representative project and infra paths |
| `test_skills_wp2_refs.py` | no stale plugin/skill/rules names or broken relative links in skills, router cap in docs = `max_skill_pushes`, Higgsfield/kokonutui listing ≤420 chars, workflow-audit lean + user-only, baseline/verification/dead-code text contracts |
| `test_autonomy_wpd.py`, `test_autonomy_wpd_daily.py`, `test_autonomy_wpd_fixtures.py` | autonomy WP-D: `deps.reconcile_mcp_pins` (swap/restore/skip/idempotent/env-never-logged), doctor roster FAIL-when-repairable + `_repair` route, exact manifest pins, the dispatch link; `selfheal-daily.py` (24 h stamp, lock, independent steps, summary contract, probe/doctor no-op, `--dry-run`). The fixtures module puts a fake `claude` on PATH that records argv and edits `$HOME/.claude.json` (plus a `claude.cmd` shim on Windows, which runs no shebangs); no real CLI or network |
| `test_userspace.py`, `test_ostools.py`, `test_ollama_setup.py`, `test_headless_install.py`, `test_pyyaml_dep.py`, `test_npm_pack.py` | one-command fresh-Ubuntu install: node/claude/uv/gh in `~/.local` (SHA check, pinned claude, npm fallback), apt tools via root / `sudo -n` / one batched line, ollama + models, `--headless` vs `--ci`, install order + the end-of-run checklist, PyYAML via uv, `lean-ctx-bin` through a tarball, graphify `mcp` pin. Downloads, subprocesses and HOME are injected (set `USERPROFILE` beside `HOME`: `Path.home()` reads it on Windows; force `os_arch` to linux to test the POSIX install logic there); `conftest.py` sets `AGENTIC_MERCY_SKIP_BASE_TOOLS=1` suite-wide |
| `test_installer_preserve.py`, `test_userspace_safety.py`, `test_ollama_safety.py` | Santa installer review: `*.pre-install` copies on relocation, first-install settings merge, symlink / hardlink containment, Windows-style absolute / climbing tar names skipped on every OS, verified downloads + pinned hashes, partial ollama repair, systemd unit ownership |
| `test_settings_carry.py` | the re-render keeps `/plugin`, marketplace and permission-rule additions (template wins shared keys, lean-ctx injections never carried), `--check` ignores additions, settings-safety on user deny rules, atomic write |
| `test_doctor_wp7.py` | doctor rows added or hardened by WP7 (mods version/runtime, MCP roster pins, installed plugins, secret-file modes, lean-ctx zero injection) on injected inputs: no claude CLI, no network |
| `test_manifest_wp7.py` | manifest invariants: `manifest.version` = the CHANGELOG head, the Windows github launcher and the playwright post-step follow the manifest pins, python tools pinned, ponytail is the mandatory plugin |
| `test_render_wp7.py` | `render.py` / `backups.py` fixes (bounded backups, `--check` with `--out/--user`, Claude-managed seed keys) in tmp dirs |
| `test_selfheal_wp7.py` | `self_heal` / relocate / `install.py --ci` rehearsed in a sandbox with a subprocess recorder |
| `test_ci_wp7.py` | text checks that the CI workflow keeps its steps (matrix, SHA-pinned actions, mods job, sandboxed `install.py --ci`) |
| `test_grep_gates_wp7.py` | gate G6: no machine home literals in tracked Markdown |
| `test_jcodemunch_config.py` | JSONC read, required keys, list union, `config set`-only writes with backup, dry-run |
| `test_mcp_secret_transport.py` | secret-safe MCP registrations |
| `test_validate_skills.py`, `test_vendor_sources.py` | skill validation (incl. R13 WARN on inert lowercase intents); vendored skills match `skills-sources.json` + R10 |
| `test_build_skills_index_plugins.py` | `build_skills_index` leaves out skills of plugins the template disables (`claude-session-driver`); enabled plugins stay indexed (NEW-08) |
| `test_ci_portability.py`, `test_portability_gate.py` | CI-green regressions; portability grep-gates |
| `test_dox_tree.py` | every directory `CLAUDE.md` names each tracked file beside it |

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children: none
