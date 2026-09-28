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
- Run: `python3 -m pytest hooks/tests -q` (not the files directly).

## Key files

| File | Role |
|------|------|
| `test_lib_foundation.py` | `platform`, `repo_context` ($HOME ceiling), `hook_telemetry` |
| `test_dispatch_mutator.py` | dispatcher threads mutator `updatedInput` (the dropped-mutation regression) |
| `test_prompt_router.py`, `test_router_surface.py`, `test_surface_classification.py` | router classify/rank/output shape, stack/cwd surface, FE/BE detection |
| `test_mcp_post_hints.py` | PostToolUse MCP hints + memory search directive |
| `test_gates.py` | Stop/Pre gates incl. invoke-suite-gate 1-nag cap |
| `test_opus_guard.py`, `test_workflow_model_guard.py`, `test_model_mode.py`, `test_model_advice.py` | model routing |
| `test_gen_invoke_skills.py` | `/invoke` skill generator determinism |
| `test_index_lifecycle.py` | index-lifecycle state machine |

## Gotchas / fragile spots

- `$HOME` tests prove the ceiling only on a machine with a stray `~/.git`; elsewhere they
  pass vacuously.
- Router tests build tmp repos and run the hook as a subprocess — keep them fast.

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children: none
