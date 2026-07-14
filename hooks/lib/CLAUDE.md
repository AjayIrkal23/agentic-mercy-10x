<!-- dox:child v1 -->
# `hooks/lib/` — local rules (dox)

> Local doc for this directory only. Read after the root `CLAUDE.md`. Update this
> file whenever you add, remove, or rename files here, or change a local convention.

## What lives here

Shared foundation modules imported by the hooks in `../`. Pure, dependency-light
helpers only — no hook entry points, no import-time I/O side effects. Every helper
fails soft (returns a safe default) so an importing hook can stay fail-open.

## Local conventions

- Import as `from lib.<mod> import ...` (hooks put their own dir on `sys.path`);
  guard the import in `try/except` so a hook never hard-crashes if a helper moves.
- Keep helpers PURE and side-effect-free; never raise past your own `try/except`.
- One concern per module. Add a new module rather than overloading an existing one.

## Key files

| File | Role |
|------|------|
| `repo_context.py` | The ONE active-repo resolver (`active_repo`, `is_inside`) **plus** git-identity helpers (`git_root`, `git_remote_identity`, `sanitize_name`). Identity keys a repo on its git REMOTE (`{owner}-{repo}`), not the local folder — reused by graphify to validate a served graph belongs to the open repo. |
| `platform.py` | OS detection + interpreter/token/path resolution (`{PY}`/`{HOOKS}`/`{NODE}`). |
| `hook_telemetry.py` | Per-link telemetry emitted by the dispatcher. |

## Gotchas / fragile spots

- `platform.run` has a **Windows-only shell fallback**: when a direct
  `subprocess.run` raises `OSError` (a `.cmd`/`.bat` shim like the npm-installed
  `claude` CLI or `npx` can't be exec'd by CreateProcess — the classic `rc=127`),
  it retries once via `shell=True` + `list2cmdline`. This is what makes the
  installer's `claude mcp add` / `claude plugin` steps actually run on Windows.
  POSIX is untouched.
- `repo_context.py` is the SINGLE source of active-repo truth (Spec B
  active-repo-only mandate) — do not add a second walk-up-`.git` implementation.
- `git_remote_identity` is a behavioural twin of the private copy inside
  `../jcodemunch-enforce.py` (kept private there to avoid touching the hard read
  gate). If you change one, change both — they must stay identical.

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children: none
- Related repo docs: [`../README.md`](../README.md) (dispatch architecture); [`../../rules/codebase-intel-first.md`](../../rules/codebase-intel-first.md).
