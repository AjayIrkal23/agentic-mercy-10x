<!-- dox:child v1 -->
# `hooks/lib/` — local rules (dox)

> Local doc for this directory only. Read after the root `CLAUDE.md`. Update it whenever
> you add, remove, or rename files here, or change a local convention.

## What lives here

Shared foundation modules imported by the hooks in `../`. Pure, dependency-light helpers
only — no hook entry points, no import-time I/O. Every helper fails soft.

## Local conventions

- Import as `from lib.<mod> import ...`, guarded by `try/except` so a hook stays fail-open.
- One concern per module; add a module rather than overloading one.
- Do not re-implement these elsewhere (extension lists, `.git` walkers, alias maps).

## Key files

| File | Role |
|------|------|
| `repo_context.py` | the ONE active-repo resolver (`active_repo`, `is_inside`) + git identity (`git_root`, `git_remote_identity`, `sanitize_name`) |
| `code_files.py` | the ONE "is this a code file?" classifier + HOME-guarded root, used by every gate; `is_infra_root` = the never-indexed roots (`$HOME`, `~/.claude`, `~/.codex`, this checkout), mirroring `../index-lifecycle.py` `NEVER_INDEX`, asked by the router, graphify-enforce and the jcodemunch read gate |
| `skill_aliases.py` | runtime alias → canonical skill resolution (sole reader of `../skill-aliases.json`) |
| `model_mode.py` | per-project model mode (`<state_dir>/model-modes/<repo_key>`; `modes_dir()` honours `CLAUDE_HOOK_STATE_DIR` without creating it, RQ-9; on max5/max20 an unauthorised `[fable]` lands on Sonnet and the reason says `fable floor -> sonnet`, never on pro), read by opus-guard, workflow-model-guard, router; also `global_flags`, `user_phrase` (the user's "use opus/sonnet/fable" override phrase) and `escalation_reason` |
| `invoke_templates.py` | text templates + the one `run.json` schema used by `../gen-invoke-skills.py` |
| `workflow_script.py` | meta/wrapper surgery on workflow scripts, used by `../workflow-model-guard.py` |
| `turns.py` | turn-boundary helpers for once-per-turn Stop gates; only human prompts (and slash-command rows) start a turn — `isMeta` (Stop feedback, skill bodies), `<task-notification>`, peer `<cross-session-message>` and interrupt rows do not; `turn_bash_commands` lists this turn's shell (Bash and PowerShell) commands (suite gate counts a `cat`/`sed` of a SKILL.md as loading it); `tail_entries` / `iter_tail` = the one transcript tail reader (`memory_gate` uses it); `prompt_names` = "the last human turn names one of these files or phrases" (settings-protection-gate escape, `PERMISSION_PHRASES`) |
| `memory_gate.py` | Stop gate 7 for `hard-completion-gate.py`: `prompt_cue` (the router's memory-route regex from `tool-intelligence.json` + bare "remember" outside a question + `always/never <verb>`; code fences ignored) and `turn_saved_memory` (this turn's tool_use rows: Memory MCP `add_observations`/`create_entities`, mercy `remember`, a `memory-codex` dispatch, or a Write/Edit under `projects/*/memory/` or of a `CODEX.md`); `gate7_memory(transcript, prompt)` fails open |
| `session_notices.py` | SessionStart one-liners for `session-start-aggregator.py`: `mod_off_notice()` (mods enabled in `installer/manifest.json`, no `MERCY_MOD_SESSION`, `~/.claude.json` `cachedGrowthBookFeatures.tengu_plugin_hooks_modules` is false — that one boolean only) and `selfheal_line()` (`state/selfheal-daily.json` with `reported:false` → one line from `changed`/`errors`, then `reported:true` via `locked_update`; a `CLAUDE_HOOK_DOCTOR` dry-fire never consumes it); + `memwatch_line`, `mod_active` (fresh per-session `state/mercy-mod.active.d/<sid>.json`), `worktree_line`, `instinct_lines` |
| `persist_common.py` | per-session dedup ledger + CODEX append (used by `codex-capture.py`) |
| `platform.py` | OS detection, interpreter/token resolution; `ollama_url()` = the one reader of `OLLAMA_HOST`; `telemetry_dir()` / `state_dir()` honour the test-isolation env; process helpers (`run`, `passes_cmd_exe`, `spawn_worker`, `spawn_detached`, `kill_tree`, `pid_alive`) and file helpers (`atomic_write`, `replace_file`, `append_line`, `locked_update`); OOM guard probes `mem_probe`, `cgroup_of`, `scope_of`, `proc_chain`, `systemd_user_bus`, `notify`, `tmux_pane`. history: `docs/CHANGELOG.md` v4.3.0 § platform.py |
| `blast_radius.py` | the one importer counter + sensitive/secret classifier behind gateguard and bash-write-gate |
| `gate_mode.py` | directive 31: `decide` (ask, or a logged advisory when the session is unattended) and `once_per_file` |
| `gate_state.py` | the ONE per-session JSON state helper for gates (safe_cid, paths, locked RMW through `locked_update`; dotstate dir resolved at call time) |
| `hookify_rules.py` | parse, load and evaluate repo-local `.claude/hookify.*.local.md` rules; untrusted input, hard limits, fail-open |
| `memwatch_state.py` | the OOM guard state, events and cursor files; stale reads as ok |
| `oomguard_config.py` | `~/.claude/oomguard.local.json` readers (`memory_high` "" = RAM-derived; `linger_wanted`; `tiers_override` = absolute int `tiers.warn/crit` numbers) + RAM scaling for a smaller box: `mem_total_mb()`, `ram_factor(total)` = min(1, MemTotal/30000) and `scale_mb(value, floor, factor)` (index-lifecycle only now); `memory_cap_mb(total)` = max(MemTotal − 4096, MemTotal // 2), the one cap rule (scope MemoryHigh, tool memory limit; F7) |
| `session_notices.py` `tier_line()` | `plan tier <tier> · main <model>` from `state/plan-tier.json` ("" without it) |
| `ollama.py` | the ONE ollama client for the learning package: `host()` (= `platform.ollama_url()`), `alive(timeout_s=1.5)`, `chat(model, messages, timeout_s)` -> content or None (one telemetry row per failure, never the prompt), `models()`; stdlib urllib; never the Claude quota |
| `scrub.py` | `scrub(text)` / `scrub_obj(obj)`: credential values -> `[REDACTED]` (key list, token shapes, URL creds, private-key blocks); bounded regexes; `index-lifecycle.py` keeps its private twin |
| `plan_tier.py` | `detect` / `read` / `update_state` (state carries `main` = `main_model(tier)`, read by `bin/claude`), `render_overrides(tier)` for `installer/render.py`, `cap` / `ceiling`; never logs token material |
| `usage_guard.py` | `state()` / `step_down(model, role)`; `state/usage-guard.json` (on at 80 %, off under 70 % of the 5-hour window) |
| `skills_index.py` | the one skills-index reader: `load()` / `skills()` merge the tracked `../skills-index.json` (local skills only) with the gitignored per-machine plugin sidecar `<root>/state/skills-index.plugins.json` |
| `hook_telemetry.py` | per-link telemetry records (appended through `plat.append_line`) |

## Gotchas / fragile spots

- `$HOME` is a walk-up ceiling, not a repo (`~/.git` exists on this machine). `active_repo`
  and `git_root` stop at `$HOME`; `git_root` must `.resolve()` its input.
- `git_remote_identity` has a private twin in `../jcodemunch-enforce.py`; change both.
- `repo_context.py` has a parallel copy in `~/.codex/hooks/lib/`; port changes, never copy
  the file wholesale.

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children: none
