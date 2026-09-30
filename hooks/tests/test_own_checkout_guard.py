"""The workbench checkout is never indexed or dox-swept, even when HOME points elsewhere.

The guards were $HOME-derived only (NEVER_INDEX, dox exemptRepos "~/.claude"). A test
run under a sandbox HOME therefore swept the real ~/.claude: dox wrote an index block
into CLAUDE.md and 32 stub docs under skills/ (2026-09-30). Doctor mode must also never
spawn the index/tdd-init writers."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1]
ROOT = HOOKS.parent


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, HOOKS / rel)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_index_lifecycle_never_indexes_its_own_checkout(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    il = _load("il_own_guard", "index-lifecycle.py")
    assert il._is_never_index(ROOT)


def test_dox_refuses_its_own_checkout_under_a_sandbox_home(tmp_path):
    env = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    cp = subprocess.run([sys.executable, str(HOOKS / "dox_engine.py"), "plan", str(ROOT)],
                        capture_output=True, text=True, env=env, timeout=60)
    assert "refusing" in cp.stdout + cp.stderr


def test_doctor_mode_aggregator_spawns_no_writers(monkeypatch):
    monkeypatch.setenv("CLAUDE_HOOK_DOCTOR", "1")
    agg = _load("ssa_own_guard", "session-start-aggregator.py")

    def boom(*_a, **_k):
        raise AssertionError("doctor mode spawned an index/tdd writer")
    monkeypatch.setattr(agg, "_run_hook_subprocess", boom)
    agg._full_context({"cwd": str(ROOT)}, "{}")
