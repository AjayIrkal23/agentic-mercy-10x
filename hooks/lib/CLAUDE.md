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
| `code_files.py` | the ONE "is this a code file?" classifier + HOME-guarded root, used by every gate |
| `skill_aliases.py` | runtime alias → canonical skill resolution (sole reader of `../skill-aliases.json`) |
| `model_mode.py` | per-project model mode (`state/model-modes/<repo_key>`), read by opus-guard, workflow-model-guard, router; also `global_flags`, `user_phrase` (the user's "use opus/sonnet/fable" override phrase) and `escalation_reason` |
| `invoke_templates.py` | text templates + the one `run.json` schema used by `../gen-invoke-skills.py` |
| `workflow_script.py` | meta/wrapper surgery on workflow scripts, used by `../workflow-model-guard.py` |
| `turns.py` | turn-boundary helpers for once-per-turn Stop gates; only human prompts (and slash-command rows) start a turn — `isMeta` (Stop feedback, skill bodies), `<task-notification>`, peer `<cross-session-message>` and interrupt rows do not; `turn_bash_commands` lists this turn's Bash commands (suite gate counts a `cat`/`sed` of a SKILL.md as loading it) |
| `memory_gate.py` | Stop gate 7 for `hard-completion-gate.py`: `prompt_cue` (the router's memory-route regex from `tool-intelligence.json` + bare "remember" outside a question + `always/never <verb>`; code fences ignored) and `turn_saved_memory` (this turn's tool_use rows: Memory MCP `add_observations`/`create_entities`, mercy `remember`, a `memory-codex` dispatch, or a Write/Edit under `projects/*/memory/` or of a `CODEX.md`); `gate7_memory(transcript, prompt)` fails open |
| `session_notices.py` | SessionStart one-liners for `session-start-aggregator.py`: `mod_off_notice()` (mods enabled in `installer/manifest.json`, no `MERCY_MOD_SESSION`, `~/.claude.json` `cachedGrowthBookFeatures.tengu_plugin_hooks_modules` is false — that one boolean only) and `selfheal_line()` (`state/selfheal-daily.json` with `reported:false` → one line from `changed`/`errors`, then `reported:true` via `locked_update`; a `CLAUDE_HOOK_DOCTOR` dry-fire never consumes it) |
| `persist_common.py` | per-session dedup ledger + CODEX append (used by `codex-capture.py`) |
| `platform.py` | OS detection, interpreter/token resolution, Windows `.cmd` shell fallback in `run`; `telemetry_dir()` / `state_dir()` honour `CLAUDE_HOOK_TELEMETRY_DIR` / `CLAUDE_HOOK_STATE_DIR` (test isolation); `locked_update(path, fn)` = read-modify-write of a shared per-session JSON state file under an exclusive flock on `<path>.lock` with an atomic write (security-scan-gate, security-semgrep-tracker, first-write-skill-gate, fullstack-skills-reminder, desloppify-cleanup use it) |
| `hook_telemetry.py` | per-link telemetry records |

## Gotchas / fragile spots

- `$HOME` is a walk-up ceiling, not a repo (`~/.git` exists on this machine). `active_repo`
  and `git_root` stop at `$HOME`; `git_root` must `.resolve()` its input.
- `git_remote_identity` has a private twin in `../jcodemunch-enforce.py`; change both.
- `repo_context.py` has a parallel copy in `~/.codex/hooks/lib/`; port changes, never copy
  the file wholesale.

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children: none
