"""hooks/tools/worktree_audit.py: read-only one-line worktree audit for SessionStart.

A temp repo with three linked worktrees: one stale (last commit 30 days back), one dirty,
one whose branch conflicts with main (merge-tree prediction). The audit must change
nothing in any checkout. Loaded both by path and through session_notices._optional_tool
(the exec path the aggregator uses).
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parents[1]
TOOL = _HOOKS / "tools" / "worktree_audit.py"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))
from lib import platform as plat  # noqa: E402

pytestmark =pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _env(tmp_path, date: str | None = None) -> dict:
    cfg = tmp_path / "gitconfig"
    cfg.touch()
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=str(cfg), GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="t",
               GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")
    if date:
        env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    return env


def _g(tmp_path, cwd, *args, date=None) -> str:
    cp = subprocess.run(["git", *args], cwd=str(cwd), env=_env(tmp_path, date), capture_output=True,
                        text=True, check=True, timeout=30)
    return cp.stdout


def _commit(tmp_path, cwd, name, text, msg, date=None):
    (Path(cwd) / name).write_text(text, encoding="utf-8")
    _g(tmp_path, cwd, "add", name)
    _g(tmp_path, cwd, "commit", "-q", "-m", msg, date=date)


def _base_repo(tmp_path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _g(tmp_path, repo, "init", "-q", "-b", "main")
    _commit(tmp_path, repo, "a.txt", "line1\nline2\n", "init")
    return repo


@pytest.fixture
def repo(tmp_path) -> Path:
    r = _base_repo(tmp_path)
    old = f"@{int(time.time()) - 30 * 86400} +0000"
    _g(tmp_path, r, "worktree", "add", "-q", "../wt-clean", "-b", "feat-clean")
    _commit(tmp_path, tmp_path / "wt-clean", "b.txt", "b\n", "clean", date=old)
    _g(tmp_path, r, "worktree", "add", "-q", "../wt-dirty", "-b", "feat-dirty")
    (tmp_path / "wt-dirty" / "a.txt").write_text("dirty\nline2\n", encoding="utf-8")
    _g(tmp_path, r, "worktree", "add", "-q", "../wt-conflict", "-b", "feat-conflict")
    _commit(tmp_path, tmp_path / "wt-conflict", "a.txt", "theirs\nline2\n", "theirs")
    _commit(tmp_path, r, "a.txt", "ours\nline2\n", "ours")
    (r / "sub").mkdir()
    return r


@pytest.fixture
def wa(monkeypatch):
    spec = importlib.util.spec_from_file_location("wa_t", TOOL)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setattr(m, "GIT_T", 5.0)  # a loaded test box must not turn into a partial audit
    return m


def _snapshot(tmp_path, repo) -> list:
    dirs = [repo, tmp_path / "wt-clean", tmp_path / "wt-dirty", tmp_path / "wt-conflict"]
    return [_g(tmp_path, d, "status", "--porcelain") for d in dirs if d.exists()] + \
        [_g(tmp_path, repo, "worktree", "list", "--porcelain")]


def test_one_line_names_dirty_stale_and_conflict(wa, repo, tmp_path, monkeypatch):
    monkeypatch.setattr(wa.plat, "IS_WINDOWS", False)  # one_line is "" on Windows by design; audit the logic
    before = _snapshot(tmp_path, repo)
    line = wa.one_line(str(repo), budget_ms=20000)
    assert "\n" not in line and len(line) <= 200
    for key in ("worktrees: 4", "1 dirty", "1 stale", "1 predicted conflict", "feat-conflict"):
        assert key in line, (key, line)
    assert _snapshot(tmp_path, repo) == before


def test_silent_when_the_only_worktree_is_the_main_one_or_everything_is_clean(wa, tmp_path):
    r = _base_repo(tmp_path)
    assert wa.one_line(str(r), budget_ms=20000) == ""
    _g(tmp_path, r, "worktree", "add", "-q", "../wt-ok", "-b", "feat-ok")
    _commit(tmp_path, tmp_path / "wt-ok", "c.txt", "c\n", "ok")
    assert wa.one_line(str(r), budget_ms=20000) == ""


def test_runs_from_a_subdirectory_and_from_a_linked_worktree(wa, repo, tmp_path, monkeypatch):
    monkeypatch.setattr(wa.plat, "IS_WINDOWS", False)
    main =wa.one_line(str(repo), budget_ms=20000)
    assert main
    assert wa.one_line(str(repo / "sub"), budget_ms=20000) == main
    assert wa.one_line(str(tmp_path / "wt-clean"), budget_ms=20000) == main


def test_budget_partial(wa, repo, monkeypatch):
    monkeypatch.setattr(wa, "GIT_T", 0.15)
    t0 = time.monotonic()
    line = wa.one_line(str(repo), budget_ms=1)
    assert line == "" or line.endswith("(partial)")
    assert time.monotonic() - t0 < 1.0


def test_not_a_repo_windows_and_old_git_fail_open(wa, repo, tmp_path, monkeypatch):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert wa.one_line(str(plain), budget_ms=20000) == ""
    monkeypatch.setattr(wa.plat, "IS_WINDOWS", True)
    assert wa.one_line(str(repo), budget_ms=20000) == ""
    monkeypatch.setattr(wa.plat, "IS_WINDOWS", False)
    monkeypatch.setattr(wa, "_git_version", lambda: (2, 30))
    line = wa.one_line(str(repo), budget_ms=20000)
    assert "1 dirty" in line and "1 stale" in line
    assert "predicted conflict" not in line and "conflict check needs git 2.38+" in line


def test_optional_tool_path_matches_session_notices_contract(wa, repo, monkeypatch):
    from lib import session_notices
    monkeypatch.setattr(session_notices, "_HOOKS", _HOOKS)
    assert session_notices._optional_tool("worktree_audit") is not None
    full = wa.one_line(str(repo), budget_ms=20000)
    got = session_notices.worktree_line(str(repo))
    assert got == full[:session_notices._MAX_LINE] or got.endswith("(partial)")


@pytest.mark.skipif(plat.IS_WINDOWS, reason="the audit is off on Windows by design; the CLI child cannot be stubbed")
def test_cli_prints_the_line(wa, repo, tmp_path):
    expected = wa.one_line(str(repo), budget_ms=20000)
    cp = subprocess.run([sys.executable, str(TOOL), str(repo)], capture_output=True, text=True, timeout=60,
                        check=False)
    assert cp.returncode == 0
    assert cp.stdout == expected + "\n" or cp.stdout.rstrip("\n").endswith("(partial)")
    plain = tmp_path / "plain2"
    plain.mkdir()
    cp = subprocess.run([sys.executable, str(TOOL), str(plain)], capture_output=True, text=True, timeout=60,
                        check=False)
    assert cp.returncode == 0 and cp.stdout == ""
