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
| `model_mode.py` | per-project model mode (`state/model-modes/<repo_key>`), read by opus-guard, workflow-model-guard, router |
| `turns.py` | turn-boundary helpers for once-per-turn Stop gates |
| `persist_common.py` | per-session dedup ledger + CODEX append (used by `codex-capture.py`) |
| `platform.py` | OS detection, interpreter/token resolution, Windows `.cmd` shell fallback in `run` |
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
