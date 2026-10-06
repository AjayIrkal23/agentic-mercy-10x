"""SEC1-03 / SANTA1-06: through cmd.exe (the `.cmd` shim fallback or an explicit `.cmd` / `.bat`
target) an arg with `%`, `"`, `!`, CR or LF cannot be delivered literally, so `plat.run` refuses it:
a 127 CompletedProcess with a clear stderr, and cmd.exe never starts. Windows is simulated with
``plat.IS_WINDOWS`` and a stub ``subprocess.run``, so this runs on Ubuntu too."""
from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

_HOOKS = pathlib.Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

from lib import platform as plat  # noqa: E402

BAD = ["a%PATH%b", 'k"v', "x!y", "x\ny", "x\ry", "100%", 'x"&echo y&z']  # %, !, line break, an odd number of "
JSON = '{"type":"stdio","args":["-y","@x/a@1.0.0"],"env":{"K":"v"}}'  # what `claude mcp add-json` gets
JSON_SH = '{"command":"sh","args":["-c","T=$(gh auth token) exec npx"]}'  # metacharacters inside the strings


@pytest.fixture
def seen(monkeypatch):
    """Records every subprocess.run; a bare name raises like CreateProcess on a `.cmd` shim."""
    calls: list = []

    def fake(cmd, **kw):
        calls.append((cmd, kw.get("shell")))
        if not kw.get("shell") and not str(cmd[0]).lower().endswith((".cmd", ".bat", ".exe")):
            raise OSError(193, "not a valid Win32 application")
        return subprocess.CompletedProcess(cmd, 0, "ran", "")
    monkeypatch.setattr(subprocess, "run", fake)
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    return calls


@pytest.mark.parametrize("bad", BAD)
def test_the_shell_fallback_refuses_an_arg_cmd_cannot_deliver_literally(seen, bad):
    cp = plat.run(["npx", "-y", bad])
    assert cp.returncode == 127 and "refus" in cp.stderr and cp.stdout == ""
    assert not any(shell for _, shell in seen)  # cmd.exe never started


@pytest.mark.parametrize("target", ["E:\\p\\npm.cmd", "E:\\p\\X.BAT", "tool.cmd"])
@pytest.mark.parametrize("bad", BAD)
def test_an_explicit_cmd_or_bat_target_is_refused_before_it_starts(seen, target, bad):
    cp = plat.run([target, bad])
    assert cp.returncode == 127 and "refus" in cp.stderr
    assert seen == []  # not even the direct CreateProcess attempt (it runs cmd.exe /c implicitly)


@pytest.mark.parametrize("bad", BAD)
def test_an_exe_target_still_gets_any_arg(seen, bad):
    assert plat.run(["E:\\p\\tool.exe", bad]).returncode == 0
    assert seen == [(["E:\\p\\tool.exe", bad], None)]


@pytest.mark.parametrize("bad", BAD)
def test_posix_is_untouched(monkeypatch, bad):
    calls: list = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0, "", ""))
    monkeypatch.setattr(plat, "IS_WINDOWS", False)
    assert plat.run(["tool.cmd", bad]).returncode == 0 and calls == [["tool.cmd", bad]]


@pytest.mark.parametrize("payload,line", [
    (JSON, 'claude mcp add-json n "{""type"":""stdio"",""args"":[""-y"",""@x/a@1.0.0""],""env"":{""K"":""v""}}"'),
    (JSON_SH, 'claude mcp add-json n "{""command"":""sh"",""args"":[""-c"",""T=$(gh auth token) exec npx""]}"'),
])
def test_balanced_json_still_goes_through_a_cmd_shim(seen, payload, line):
    """`claude mcp add-json <name> <json>` (installer/mcp_restore.py) must keep working when `claude` is
    an npm `.cmd` shim: a `"` is written `""`, which keeps `( ) & |` inside the strings inside cmd's quotes."""
    assert plat.run(["claude", "mcp", "add-json", "n", payload]).returncode == 0
    assert seen[-1] == (line, True)


def test_metacharacter_args_and_ordinary_cmd_shim_calls_are_allowed(seen):
    cp = plat.run(["npx", "-y", "x|y", "a&b", "(p)", "https://h/?a=1&b=2"])
    assert cp.returncode == 0
    assert seen[-1] == ('npx -y "x|y" "a&b" "(p)" "https://h/?a=1&b=2"', True)
    # an explicit .cmd runs implicitly under cmd.exe too: it gets the same quoted line, never a bare list
    assert plat.run(["E:\\p\\npm.cmd", "install", "a&b"]).returncode == 0
    assert seen[-1] == ('E:\\p\\npm.cmd install "a&b"', True)
