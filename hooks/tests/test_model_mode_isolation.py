"""RQ-9: per-project model-mode pins honour CLAUDE_HOOK_STATE_DIR, so a test run (or the
router replay) never writes into the live ``~/.claude/state/model-modes/``."""
from __future__ import annotations

import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HOOKS))
from lib import model_mode as mm  # noqa: E402


def test_set_mode_writes_under_the_isolated_state_dir(tmp_path, monkeypatch):
    live = Path("~/.claude/state/model-modes").expanduser()
    before = live.stat().st_mtime_ns if live.exists() else None
    state = tmp_path / "state"
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(state))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    repo = tmp_path / "repo"
    repo.mkdir()
    assert mm.modes_dir() == state / "model-modes"
    assert mm.set_mode(str(repo), "opus")
    assert (state / "model-modes" / mm.repo_key(str(repo))).is_file()
    assert mm.forced_mode(str(repo), cap=False) == "opus"
    after = live.stat().st_mtime_ns if live.exists() else None
    assert before == after


def test_default_is_unchanged_without_the_override(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_HOOK_STATE_DIR", raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
    assert mm.modes_dir() == tmp_path / "cfg" / "state" / "model-modes"
