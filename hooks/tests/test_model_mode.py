"""lib/model_mode.py — per-project subagent model mode (D4)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import model_mode as mm  # noqa: E402


@pytest.fixture
def repo(monkeypatch, tmp_path):
    monkeypatch.setattr(mm, "modes_dir", lambda: tmp_path / "model-modes")
    r = tmp_path / "repo"
    (r / "sub").mkdir(parents=True)
    return r


def test_repo_key_stable_and_none_for_empty(repo):
    assert mm.repo_key(None) is None
    assert mm.repo_key(str(repo)) == mm.repo_key(str(repo))
    assert mm.repo_key(str(repo)).startswith("repo-")


def test_set_get_clear(repo):
    assert mm.forced_mode(str(repo)) is None
    assert mm.set_mode(str(repo), "OPUS")
    assert mm.forced_mode(str(repo)) == "opus"
    assert not mm.set_mode(str(repo), "gpt")
    assert mm.set_mode(str(repo), None)
    assert mm.forced_mode(str(repo)) is None


def test_subdir_shares_mode_when_git_repo(repo):
    import subprocess
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    assert mm.set_mode(str(repo / "sub"), "fable")
    assert mm.forced_mode(str(repo)) == "fable"
