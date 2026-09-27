<!-- dox:child v1 -->
# `hooks/tests/` — local rules (dox)

> Local doc for this directory only. Read after the root `CLAUDE.md`. Update this
> file whenever you add, remove, or rename files here, or change a local convention.

## What lives here

Unit tests for the hook layer — pure-stdlib, pytest-style `assert` functions, no
fixtures beyond `monkeypatch`. Tests only; hook logic lives in `../`.

## Local conventions

- Name files `test_<subject>.py` and functions `test_<behaviour>()`.
- Put the hooks dir on `sys.path` via `_HOOKS = Path(__file__).resolve().parents[1]`,
  then import `from lib import ...` — do not rely on the caller's cwd.
- Prefer extending the existing file for a module already covered over adding a
  new one (e.g. all `lib/` coverage lives in `test_lib_foundation.py`).

## Key files

| File | Role |
|------|------|
| `test_lib_foundation.py` | `lib/` foundation: `platform`, `repo_context` (incl. the `$HOME`-is-never-a-repo ceiling), `hook_telemetry` |
| `test_index_lifecycle.py` | index-lifecycle state machine |
| `test_prompt_router.py` | prompt router classify/rank/budget |
| `test_opus_guard.py`, `test_opus_guard_name.py`, `test_workflow_model_guard.py`, `test_model_advice.py` | model-routing guards |
| `test_surface_classification.py` | FE/BE surface detection |

## Gotchas / fragile spots

- **Run with `pytest`, not directly.** `python3 hooks/tests/test_lib_foundation.py`
  invokes the module's `_run_all()`, which calls every `test_*` with no args and
  dies on `test_popen_new_group_windows_flags(monkeypatch)` — a pre-existing
  fixture-only test. `python3 -m pytest hooks/tests/ -q` is the working command.
- Tests asserting on `$HOME` behaviour depend on this machine having a stray
  `~/.git`. Without it `test_home_is_never_a_repo_root` still passes, but
  vacuously — it stops proving the ceiling guard works.

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children: <links to deeper `*/CLAUDE.md`, or "none">
- Related repo docs: <link to the numbered doc / CODEX.md section — link, don't restate>
