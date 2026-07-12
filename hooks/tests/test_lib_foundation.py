"""Unit tests for hooks/lib foundation (P1-T1).

Pure stdlib + pytest-style asserts. Runnable via `pytest hooks/tests/` or
directly: `python3 hooks/tests/test_lib_foundation.py`.
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import time

_HOOKS = pathlib.Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

from lib import hook_telemetry as tel  # noqa: E402
from lib import platform as plat  # noqa: E402
from lib import repo_context as rc  # noqa: E402


# --------------------------------------------------------------------------- #
# platform
# --------------------------------------------------------------------------- #
def test_is_windows_is_bool():
    assert isinstance(plat.IS_WINDOWS, bool)


def test_claude_dir_ends_with_dotclaude():
    assert plat.claude_dir().name == ".claude"


def test_python_exe_nonempty():
    assert plat.python_exe()


def test_state_and_telemetry_dirs_created():
    assert plat.state_dir().is_dir()
    assert plat.telemetry_dir().is_dir()


def test_slugify_deterministic_and_safe():
    a = plat.slugify_path("/a/b/My Repo/")
    b = plat.slugify_path("/a/b/My Repo")
    assert a == b  # trailing slash ignored
    assert a.startswith("My-Repo-")
    assert "/" not in a and " " not in a


def test_materialize_substitutes_and_leaves_unknown():
    out = plat.materialize(["{PY}", "{HOOKS}/x.py", "{UNKNOWN}"], {"PY": "py", "HOOKS": "/h"})
    assert out == ["py", "/h/x.py", "{UNKNOWN}"]


def test_atomic_write_roundtrip():
    tmp = pathlib.Path(tempfile.mkdtemp()) / "deep" / "f.txt"
    assert plat.atomic_write(tmp, "payload")
    assert tmp.read_text() == "payload"
    assert plat.atomic_write(tmp, "second")  # overwrite atomically
    assert tmp.read_text() == "second"


def test_run_never_raises_on_bad_command():
    cp = plat.run(["___definitely_not_a_binary___"])
    assert cp.returncode != 0  # synthetic 127, no exception


def test_pid_alive_self_true_bogus_false():
    assert plat.pid_alive(os.getpid()) is True
    assert plat.pid_alive(2_147_480_000) is False


# --------------------------------------------------------------------------- #
# repo_context
# --------------------------------------------------------------------------- #
def test_active_repo_inside_claude():
    ctx = rc.active_repo(cwd=str(_HOOKS))
    assert ctx is not None
    assert ctx.name == ".claude"
    assert ctx.key.startswith(".claude-")
    assert len(ctx.key.rsplit("-", 1)[1]) == 8


def test_active_repo_outside_git_is_none():
    # walk-up from filesystem root can never find .git above /
    assert rc.active_repo(cwd=os.path.abspath(os.sep)) is None


def test_active_repo_resolution_order_payload_workspace_roots():
    ctx = rc.active_repo({"workspace_roots": [str(_HOOKS)], "cwd": os.sep})
    assert ctx is not None and ctx.name == ".claude"


def test_is_inside_containment():
    ctx = rc.active_repo(cwd=str(_HOOKS))
    assert rc.is_inside(ctx, str(_HOOKS / "lib" / "platform.py"))
    assert not rc.is_inside(ctx, os.sep + "etc")
    assert not rc.is_inside(None, str(_HOOKS))


# --------------------------------------------------------------------------- #
# hook_telemetry
# --------------------------------------------------------------------------- #
def test_record_appends_jsonl():
    tel.record("UserPromptSubmit", "unit_test_link", session="t", ms=0.5, exit=0)
    day = time.strftime("%Y%m%d")
    f = plat.telemetry_dir() / f"hook-fires-{day}.jsonl"
    assert f.exists()
    assert "unit_test_link" in f.read_text(encoding="utf-8")


def test_timer_records_ms_and_swallows_exception():
    # exception inside Timer is swallowed (reraise=False default) and recorded
    with tel.Timer("PreToolUse", "unit_timer_link", session="t") as tm:
        tm.set(decision="x")
        raise ValueError("boom")  # must be swallowed
    day = time.strftime("%Y%m%d")
    f = plat.telemetry_dir() / f"hook-fires-{day}.jsonl"
    body = f.read_text(encoding="utf-8")
    assert "unit_timer_link" in body and "boom" in body


def test_popen_new_group_roundtrip_and_kill():
    # POSIX/live path: launch a short-lived child in its own group, prove the
    # handle is live and poll-able, then kill_tree it.
    proc = plat.popen_new_group(
        [plat.python_exe(), "-c", "import time; time.sleep(30)"],
        stdout=None,
        stderr=None,
    )
    try:
        assert proc.poll() is None  # still running
        assert plat.pid_alive(proc.pid)
    finally:
        plat.kill_tree(proc.pid)
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
            proc.wait()
    assert proc.poll() is not None  # reaped


def test_popen_new_group_windows_flags(monkeypatch):
    # Windows branch: assert CREATE_NEW_PROCESS_GROUP is passed and
    # start_new_session is NOT (that kwarg is POSIX-only) — without spawning.
    captured = {}

    class _FakePopen:
        def __init__(self, cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            self.pid = 4321

    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    monkeypatch.setattr(plat.subprocess, "Popen", _FakePopen)
    plat.popen_new_group("echo hi", shell=True)
    assert captured["kwargs"].get("creationflags") == 0x00000200
    assert "start_new_session" not in captured["kwargs"]
    assert captured["kwargs"].get("shell") is True


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
    print(f"test_lib_foundation: {len(fns)} tests PASSED")


if __name__ == "__main__":
    _run_all()
