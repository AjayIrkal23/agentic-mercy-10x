"""W6b hook robustness on Windows, part 2: cmd.exe escaping, bounded locks, ``pid_alive``
and the Windows branches of platform.py / daily_lock.py (A4-11, A4-12, A4-15, A7-03).
Windows is simulated with ``plat.IS_WINDOWS`` plus stub ``msvcrt`` / ``ctypes``, so the
file runs on Ubuntu too; the two ``skipif`` tests run the real cmd.exe / msvcrt.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import types

import pytest

_HOOKS = pathlib.Path(__file__).resolve().parents[1]
for _p in (str(_HOOKS), str(_HOOKS / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib import platform as plat  # noqa: E402


def _os(monkeypatch, windows: bool):
    monkeypatch.setattr(plat, "IS_WINDOWS", windows)


def _msvcrt(monkeypatch, locking):
    stub = types.SimpleNamespace(LK_LOCK=1, LK_NBLCK=2, LK_UNLCK=0, locking=locking)
    monkeypatch.setitem(sys.modules, "msvcrt", stub)
    return stub


def _held(fd, mode, n):
    raise OSError(36, "locked")


# --------------------------------------------------------------------------- #
# A4-11 / SANTA1-06 / SEC1-03: cmd.exe quoting for the plat.run shell fallback. A real npm shim
# forwards `%*`, so the line is parsed twice: only double-quoted metacharacters stay literal.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("args,expect", [
    (["npm", "install"], "npm install"),
    (["echo", "x|y"], 'echo "x|y"'),
    (["echo", "a&b", "(c)", "<d>"], 'echo "a&b" "(c)" "<d>"'),
    (["echo", "v^w"], 'echo "v^w"'),
    (["echo", "a b", "c"], 'echo "a b" c'),
    (["echo", "a b&c"], 'echo "a b&c"'),
    (["echo", "https://h/?a=1&b=2"], 'echo "https://h/?a=1&b=2"'),
    (["echo", ""], 'echo ""'),
    (["echo", "E:\\dir with space\\"], 'echo "E:\\dir with space\\\\"'),
    (["echo", "E:\\dir&x\\"], 'echo "E:\\dir&x\\\\"'),
    (["x", '{"a":"b"}'], 'x "{""a"":""b""}"'),
    (["x", '{"k":"v&w"}'], 'x "{""k"":""v&w""}"'),
    (["x", 'a\\"b"'], 'x "a\\\\""b"""'),
])
def test_shell_cmdline_double_quotes_whitespace_and_metacharacters(args, expect):
    assert plat.shell_cmdline(args) == expect


def test_run_falls_back_to_a_quoted_shell_line_for_cmd_shims(monkeypatch):
    _os(monkeypatch, True)
    calls: list = []

    def fake(cmd, **kw):
        calls.append((cmd, kw.get("shell")))
        if not kw.get("shell"):
            raise OSError(193, "not a valid Win32 application")
        return subprocess.CompletedProcess(cmd, 0, "ok", "")
    monkeypatch.setattr(subprocess, "run", fake)
    assert plat.run(["claude", "mcp", "add", "x|y"]).returncode == 0
    assert calls[1] == ('claude mcp add "x|y"', True)


def _npm_style_shim(tmp_path, monkeypatch):
    """What npm writes for every CLI (`npm.cmd`, `npx.cmd`, `tsc.cmd`): the args are forwarded as `%*`."""
    (tmp_path / "echoargs.py").write_text("import sys,json;print(json.dumps(sys.argv[1:]))", encoding="utf-8")
    (tmp_path / "echoargs.cmd").write_text('@"%s" "%%~dp0echoargs.py" %%*\r\n' % sys.executable, encoding="utf-8")
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])


@pytest.mark.skipif(not plat.IS_WINDOWS, reason="needs cmd.exe")
@pytest.mark.parametrize("target", ["echoargs", "echoargs.cmd"])
def test_a_real_npm_style_shim_receives_metacharacter_args_literally(tmp_path, monkeypatch, target):
    _npm_style_shim(tmp_path, monkeypatch)
    args = ["x|y", "a&b", "https://h/?a=1&b=2", "(p)", "a b&c", "p<q>r", "c^d", '{"k":"v","a":[1,"x y"]}',
            '{"k":"v&w"}', 'say "hi" & go', 'x"&echo y&"z', 'T=$(gh auth token) exec', 'a\\"b"', '"&"', '']
    cmd = [target if target == "echoargs" else str(tmp_path / target), *args]
    out = plat.run(cmd)
    assert out.returncode == 0 and json.loads(out.stdout) == args


@pytest.mark.skipif(not plat.IS_WINDOWS, reason="needs cmd.exe")
def test_a_real_shim_never_sees_percent_quote_or_bang_args(tmp_path, monkeypatch):
    _npm_style_shim(tmp_path, monkeypatch)
    for bad in ("a%PATH%b", 'k"v', "x!y", "x\ny", 'x"&echo y&z'):
        out = plat.run(["echoargs", "ok", bad])
        assert out.returncode == 127 and "refus" in out.stderr and out.stdout == "", bad


# --------------------------------------------------------------------------- #
# A4-12 (locked_update with a bounded lock wait): test_win_lock_wait.py
# A4-15: pid_alive through ctypes (no tasklist)
# --------------------------------------------------------------------------- #
def _kernel32(monkeypatch, *, handle, exit_code=None, last_error=0):
    import ctypes
    closed: list = []

    def get_exit(h, ref):
        ref._obj.value = exit_code
        return 1
    k32 = types.SimpleNamespace(
        OpenProcess=lambda access, inherit, pid: handle,
        GetExitCodeProcess=get_exit, CloseHandle=lambda h: closed.append(h) or 1)
    monkeypatch.setattr(ctypes, "WinDLL", lambda name, **kw: k32, raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: last_error, raising=False)
    return closed


@pytest.mark.parametrize("handle,code,err,alive", [
    (77, 259, 0, True),     # STILL_ACTIVE
    (77, 0, 0, False),      # exited, handle still open elsewhere
    (0, None, 87, False),   # ERROR_INVALID_PARAMETER: no such pid
    (0, None, 5, True),     # ERROR_ACCESS_DENIED: exists, not ours
])
def test_pid_alive_on_windows_reads_the_exit_code(monkeypatch, handle, code, err, alive):
    def no_spawn(*a, **k):
        raise AssertionError("pid_alive must not spawn tasklist")
    monkeypatch.setattr(subprocess, "run", no_spawn)
    closed = _kernel32(monkeypatch, handle=handle, exit_code=code, last_error=err)
    _os(monkeypatch, True)
    assert plat.pid_alive(1234) is alive
    assert closed == ([handle] if handle else [])


# --------------------------------------------------------------------------- #
# A7-03: the rest of the Windows-only branches
# --------------------------------------------------------------------------- #
def test_kill_tree_on_windows_runs_taskkill(monkeypatch):
    _os(monkeypatch, True)
    seen: list = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: seen.append(cmd))
    plat.kill_tree(321)
    assert seen == [["taskkill", "/F", "/T", "/PID", "321"]]


def test_daily_lock_polls_with_lk_nblck_and_reports_a_held_lock(monkeypatch, tmp_path):
    import daily_lock
    modes: list = []
    _msvcrt(monkeypatch, lambda fd, mode, n: modes.append(mode))
    monkeypatch.setattr(daily_lock.plat, "IS_WINDOWS", True)
    with daily_lock.try_lock(tmp_path / "d.lock") as got:
        assert got is True
    assert modes == [2]
    _msvcrt(monkeypatch, _held)
    with daily_lock.try_lock(tmp_path / "d.lock") as got:
        assert got is False
