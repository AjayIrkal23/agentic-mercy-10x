"""One install at a time per tools dir (A5v2-04): a second installer or the daily self-heal reports
"another install is running" and changes nothing, instead of deleting a live peer's extraction or
interleaving PATH writes. The lock is a non-blocking file lock (``daily_lock.try_lock``), so it works across
processes and dies with its holder.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks"), str(_ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import winlock  # noqa: E402
from lib import platform as plat  # noqa: E402
from winfakes import ENV, World, short_limit  # noqa: E402, F401  (autouse: long basetemp)

M = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))


def test_a_second_holder_of_the_same_tools_dir_is_refused_until_the_first_releases(tmp_path):
    first, second = winlock.InstallLock(tmp_path / "tools"), winlock.InstallLock(tmp_path / "tools")
    assert first.take() and (tmp_path / "tools" / winlock.LOCK_NAME).is_file()
    assert not second.take() and second.busy
    first.release()
    third = winlock.InstallLock(tmp_path / "tools")
    assert third.take()
    third.release()


def test_taking_the_lock_lazily_never_creates_the_tools_dir_when_nothing_is_written(tmp_path):
    lock = winlock.InstallLock(tmp_path / "tools")
    assert lock.take(create=False) and not (tmp_path / "tools").exists()  # PRESENT-only run: nothing to protect
    lock.release()


def test_the_lock_is_held_across_processes_and_dies_with_its_holder(tmp_path):
    code = ("import sys; sys.path[:0]=[sys.argv[1], sys.argv[2]]; import winlock; l=winlock.InstallLock(sys.argv[3]); "
            "print(l.take(), flush=True); sys.stdin.readline()")
    child = subprocess.Popen([sys.executable, "-c", code, str(_ROOT / "installer"), str(_ROOT / "hooks"),
                              str(tmp_path / "tools")], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline().strip() == "True"
        mine = winlock.InstallLock(tmp_path / "tools")
        assert not mine.take()
    finally:
        child.stdin.write("\n")
        child.stdin.flush()
        child.wait(timeout=30)
    again = winlock.InstallLock(tmp_path / "tools")
    assert again.take()
    again.release()


@pytest.fixture
def w(tmp_path, monkeypatch):
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    return World(tmp_path, M)


def test_a_busy_tools_dir_installs_nothing_and_says_another_install_is_running(w):
    peer = winlock.InstallLock(w.tools)
    assert peer.take()
    rows = dict(w.ensure())
    peer.release()
    assert all("another install is running" in s for s in rows.values()), rows
    assert w.urls == [] and w.registry.sets() == [] and not (w.tools / "node").exists()


def test_a_live_peers_extraction_dir_survives_a_busy_run_and_the_next_run_installs(w):
    tmp = w.tools / "node.tmp-424242"
    (tmp / "partial").mkdir(parents=True)
    peer = winlock.InstallLock(w.tools)
    assert peer.take()
    w.ensure()
    peer.release()
    assert tmp.is_dir()  # the busy run never touched it
    assert all(s.startswith(("INSTALLED", "PRESENT")) for s in dict(w.ensure()).values())


def test_a_free_lock_does_not_change_a_normal_install(w):
    assert all(s.startswith("INSTALLED") for _, s in w.ensure())
    assert (w.tools / winlock.LOCK_NAME).is_file()
    assert w.registry.values[(ENV, "Path")][0]
    assert winlock.InstallLock(w.tools).take()  # released at the end of the run


def test_a_present_only_run_neither_locks_nor_creates_the_tools_dir(w):
    w.found = {"git": str(_fake_git(w)), "node": "/n/node.exe", "npm": "/n/npm.cmd", "claude": "/c/claude.exe",
               "uv": "/u/uv.exe", "gh": "/g/gh.exe"}
    w.runs(out={"node": "v22.9.0", "claude": "2.1.289 (Claude Code)"})
    assert set(dict(w.ensure()).values()) == {"PRESENT"} and not w.tools.exists()


def _fake_git(w) -> Path:
    g = w.home / "Git"
    for rel in ("cmd/git.exe", "bin/bash.exe"):
        (g / rel).parent.mkdir(parents=True, exist_ok=True)
        (g / rel).write_bytes(b"x")
    return g / "cmd" / "git.exe"
