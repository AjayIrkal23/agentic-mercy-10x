"""install.cmd / install.ps1 run for real (Windows only): Windows PowerShell 5.1 and cmd.exe on a scratch copy.

Every run is sandboxed twice over (A7v2-04): ``AGENTIC_MERCY_SANDBOX=1`` AND a scratch manifest whose
python.org pin points at ``https://127.0.0.1:9/x.exe`` with a zero hash, so a regressed sandbox guard fails a
download instead of installing Python into the user's profile (the P5 incident) while "testing".
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "hooks") not in sys.path:
    sys.path.insert(0, str(_ROOT / "hooks"))
from lib import platform as plat  # noqa: E402

SYS = Path(os.environ.get("SystemRoot", ""))
PS51 = SYS / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
CMD_EXE = SYS / "System32" / "cmd.exe"
needs_ps51 = pytest.mark.skipif(not PS51.is_file(), reason="no Windows PowerShell 5.1 here")
needs_cmd = pytest.mark.skipif(not (CMD_EXE.is_file() and PS51.is_file() and plat.IS_WINDOWS),
                               reason="cmd.exe + PowerShell 5.1 only")
DEAD_URL = "https://127.0.0.1:9/x.exe"
PY_STDERR = "@echo off\r\necho warning: Error processing line 1 of x.pth 1>&2\r\necho 314\r\n"
PY_ENV = '@echo off\r\necho 314\r\n>> "%~dp0env.txt" echo [%PSExecutionPolicyPreference%] %*\r\n'


def _scratch_manifest(dst: Path) -> None:
    m = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))
    py = m["user_space"]["windows"]["python"]
    py["url"], py["sha256"] = DEAD_URL, {a: "0" * 64 for a in py["sha256"]}
    dst.write_text(json.dumps(m), encoding="utf-8")


def _run_ps1(tmp_path, args, fake_python=None, repo_name="repo", manifest=True, setup=None):
    """A scratch copy of install.ps1 (its dir is what it unblocks), a PATH holding only a fake python.cmd,
    a scratch profile, the sandbox flag and a manifest that cannot download the real Python."""
    repo = tmp_path / repo_name
    (repo / "installer").mkdir(parents=True)
    shutil.copy(_ROOT / "install.ps1", repo / "install.ps1")
    if manifest:
        _scratch_manifest(repo / "installer" / "manifest.json")
    (repo / "install.py").write_text("", encoding="utf-8")
    if setup:
        setup(repo)
    fakebin, prof = tmp_path / "fakebin", tmp_path / "profile"
    fakebin.mkdir()
    prof.mkdir()
    if fake_python:
        (fakebin / "python.cmd").write_bytes(fake_python.encode("ascii"))
    env = {k: os.environ[k] for k in ("SystemRoot", "windir", "ComSpec") if k in os.environ}
    env.update(PATH=str(fakebin), PATHEXT=".COM;.EXE;.BAT;.CMD", USERPROFILE=str(prof), HOME=str(prof),
               LOCALAPPDATA=str(prof / "la"), APPDATA=str(prof / "ra"), TEMP=str(tmp_path), TMP=str(tmp_path),
               AGENTIC_MERCY_TOOLS_DIR=str(prof / "tools"), AGENTIC_MERCY_SANDBOX="1",
               CLAUDE_CONFIG_DIR=str(prof / "claude"))
    cp = subprocess.run([str(PS51), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                         str(repo / "install.ps1"), *args], env=env, capture_output=True, encoding="utf-8",
                        errors="replace", timeout=180)
    return cp.returncode, cp.stdout + cp.stderr


def test_the_scratch_manifest_cannot_fetch_the_real_python(tmp_path):
    """A7v2-04: the second, independent guard of every run below: a regressed sandbox check would hit a dead
    URL with a zero hash, not python.org."""
    _scratch_manifest(tmp_path / "m.json")
    py = json.loads((tmp_path / "m.json").read_text(encoding="utf-8"))["user_space"]["windows"]["python"]
    assert py["url"] == DEAD_URL and set(py["sha256"].values()) == {"0" * 64}


@needs_ps51
@pytest.mark.parametrize("flag", ["-Ci", "--ci"])
def test_ci_without_python_stops_with_the_ci_message_not_the_sandbox_one(tmp_path, flag):
    rc, out = _run_ps1(tmp_path, [flag])
    assert rc == 1 and "never installs" in out and "python.org installer is not run" not in out, out


@needs_ps51
@pytest.mark.parametrize("flag", ["/ci", "--dry-run"])
def test_an_unknown_flag_stops_before_any_python_lookup_or_install(tmp_path, flag):
    """SANTA2B-02: with no Python, `/ci` reached the python.org installer before install.py could refuse it."""
    rc, out = _run_ps1(tmp_path, [flag])
    assert rc == 1 and "unknown argument" in out and "python.org installer is not run" not in out, out


@needs_ps51
def test_without_ci_the_sandbox_still_refuses_the_python_installer(tmp_path):
    rc, out = _run_ps1(tmp_path, [])
    assert rc == 1 and "python.org installer is not run" in out, out


@needs_ps51
def test_ps51_accepts_a_working_python_that_writes_to_stderr(tmp_path):
    rc, out = _run_ps1(tmp_path, ["-Ci"], fake_python=PY_STDERR)
    assert rc == 0 and " xx " not in out, out


@needs_ps51
@pytest.mark.parametrize("name", ["claude [work]", "x]y", "a [1] b", "100%done"])
def test_a_clone_path_with_brackets_works(tmp_path, name):
    """A5v2-01: `Get-Content -Raw <path>` wildcard-expanded `[`/`]` and died with `A parameter cannot be
    found that matches parameter name 'Raw'`; `install.cmd` then said only `Install failed, code 1`."""
    rc, out = _run_ps1(tmp_path, ["-Ci"], fake_python=PY_STDERR, repo_name=name)
    assert rc == 0 and "parameter" not in out.lower() and " xx " not in out, out


@needs_ps51
def test_the_child_python_does_not_inherit_the_bypass_policy_preference(tmp_path):
    """A5v2-08: `-ExecutionPolicy Bypass` makes PowerShell export PSExecutionPolicyPreference=Bypass to every child;
    each powershell.exe the installer spawns later (signature checks ...) would run with Bypass."""
    rc, out = _run_ps1(tmp_path, ["-Ci"], fake_python=PY_ENV)
    seen = (tmp_path / "fakebin" / "env.txt").read_text(encoding="utf-8", errors="replace").splitlines()
    final = next(ln for ln in seen if "install.py" in ln)
    assert rc == 0 and final.startswith("[]"), seen


@needs_ps51
def test_nothing_is_unblocked_when_this_is_not_the_workbench_folder(tmp_path):
    """A5v2-08: the Unblock-File pass ran over install.ps1's whole folder before anything checked it is the
    repository (an install.cmd copied into Downloads would unblock every file there)."""
    stray = tmp_path / "repo" / "stray.txt"

    def mark(repo):
        (repo / "stray.txt").write_text("x", encoding="utf-8")
        with open(str(repo / "stray.txt") + ":Zone.Identifier", "w", encoding="utf-8") as fh:
            fh.write("[ZoneTransfer]\nZoneId=3\n")
    rc, out = _run_ps1(tmp_path, ["-Ci"], fake_python=PY_STDERR, manifest=False, setup=mark)
    assert rc == 1 and "manifest.json" in out and os.path.exists(str(stray) + ":Zone.Identifier"), out


@needs_ps51
def test_the_workbench_folder_is_still_unblocked(tmp_path):
    """The other half: a browser-downloaded zip carries Mark-of-the-Web on every file; the real repo is cleaned."""
    def mark(repo):
        with open(str(repo / "install.py") + ":Zone.Identifier", "w", encoding="utf-8") as fh:
            fh.write("[ZoneTransfer]\nZoneId=3\n")
    rc, out = _run_ps1(tmp_path, ["-Ci"], fake_python=PY_STDERR, setup=mark)
    assert rc == 0 and not os.path.exists(str(tmp_path / "repo" / "install.py") + ":Zone.Identifier"), out


# --- install.cmd: pause only on a real Explorer double-click ------------------------------------- #
def _cmd_run(tmp_path, tail_of_cmdline, args=""):
    d = tmp_path / "repo"
    d.mkdir()
    shutil.copy(_ROOT / "install.cmd", d / "install.cmd")
    (d / "install.ps1").write_text("exit 3\n", encoding="ascii")  # a stub: nothing is installed
    script = d / "install.cmd"
    line = tail_of_cmdline.format(cmd=str(CMD_EXE), script=str(script))
    env = {k: os.environ[k] for k in ("SystemRoot", "windir", "ComSpec") if k in os.environ}
    cp = subprocess.run(line, env=env, stdin=subprocess.DEVNULL, capture_output=True, encoding="utf-8",
                        errors="replace", timeout=120)
    return cp.returncode, cp.stdout + cp.stderr


@needs_cmd
@pytest.mark.parametrize("shape,line", [
    ("explorer double-click", '"{cmd}" /c ""{script}" "'),
])
def test_a_real_double_click_failure_waits_for_a_key(tmp_path, shape, line):
    rc, out = _cmd_run(tmp_path, line)
    assert rc == 3 and "Install failed, code 3" in out and "Press any key" in out, out


@needs_cmd
@pytest.mark.parametrize("shape,line", [
    ("an argument (a script / agent)", '"{cmd}" /c ""{script}" --bogus"'),
    ("PowerShell call operator", '"{cmd}" /c ""{script}""'),
    ("plain cmd /c", '"{cmd}" /c "{script}"'),
    ("an argument after a double-click-shaped line", '"{cmd}" /c ""{script}" -Ci "'),
])
def test_a_scripted_failure_returns_without_waiting_for_a_key(tmp_path, shape, line):
    """A5v2-05: `cmd /c install.cmd` from PowerShell, an SSH session or an agent matched the old `install.cmd in
    cmdcmdline` test and sat on `pause`; only Explorer's `/c ""path" "` (no arguments) is a double-click."""
    rc, out = _cmd_run(tmp_path, line)
    assert rc == 3 and "Press any key" not in out, out
