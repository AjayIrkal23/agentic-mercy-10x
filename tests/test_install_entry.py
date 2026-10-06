"""One-click entry (A5-01, A5-04, A5-13): install.cmd -> install.ps1 -> install.py.

Text contracts for the two launchers (they can only be run for real on Windows), the manifest
pin install.ps1 reads, a static PowerShell parse where a PowerShell exists, and ``pick_python``:
the Python choice that never accepts a Microsoft Store stub or a too-old interpreter.
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
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks"), str(_ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import winutil  # noqa: E402
from winfakes import Runs  # noqa: E402

CMD = (_ROOT / "install.cmd").read_text(encoding="utf-8") if (_ROOT / "install.cmd").exists() else ""
PS1 = (_ROOT / "install.ps1").read_text(encoding="utf-8")
M = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))


def test_install_cmd_runs_the_ps1_with_bypass_and_forwards_every_argument():
    ps = r'"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"'  # absolute: never the cwd's
    assert f'{ps} -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*' in CMD
    assert CMD.splitlines()[0] == "@echo off" and "setlocal" in CMD
    assert 'set "NoDefaultCurrentDirectoryInExePath=1"' in CMD  # reaches python.exe / shutil.which too


def test_install_cmd_keeps_the_exit_code_and_pauses_only_when_double_clicked_and_failed():
    lines = CMD.splitlines()
    assert "set RC=%ERRORLEVEL%" in lines and lines[-1] == "exit /b %RC%"
    pause = [ln for ln in lines if "pause" in ln]
    assert len(pause) == 1 and 'if "%~1"=="" if not "%RC%"=="0"' in pause[0]  # a double-click passes no argument (A5v2-05)
    assert 'echo "%cmdcmdline:"=%"' in pause[0]  # quotes stripped, then re-quoted: a path with & | ^ stays text
    assert r'"%SystemRoot%\System32\find.exe"' in pause[0] and " find " not in pause[0]
    assert '/i "%~nx0 """' in pause[0]  # Explorer's `/c ""path" "` ends `install.cmd "` once the quotes are gone


def test_install_cmd_has_no_labels_or_multiline_blocks_so_lf_line_endings_are_safe():
    """cmd.exe mis-reads GOTO labels and multi-line ( ) blocks in an LF-only file (`* -text` keeps LF)."""
    for ln in CMD.splitlines():
        assert not ln.startswith(":") and ln.strip() not in ("(", ")") and not ln.rstrip().endswith("("), ln


def test_ps1_has_the_switches_forwards_them_and_exits_with_the_pythons_code():
    assert "param([switch]$Headless, [switch]$Ci, [Parameter(ValueFromRemainingArguments" in PS1
    assert "'--headless'" in PS1 and "'--ci'" in PS1 and "install.py" in PS1
    assert PS1.rstrip().splitlines()[-1] == "exit $LASTEXITCODE"


def test_ps1_installs_python_only_from_the_manifest_pin_verified_twice():
    assert r"installer\manifest.json" in PS1 and "user_space.windows.python" in PS1
    for field in ("url", "version", "arch.x64", "sha256.x64", "signer"):
        assert f"$Pin.{field}" in PS1, field
    py = M["user_space"]["windows"]["python"]
    assert py["url"] and py["version"] and py["arch"]["x64"] and py["sha256"]["x64"] and py["signer"]
    assert "Get-FileHash" in PS1 and "Get-AuthenticodeSignature" in PS1 and "'Valid'" in PS1
    assert "GetNameInfo('SimpleName', $false) -ne $Pin.signer" in PS1  # exact certificate name, not a substring


def test_ps1_runs_the_per_user_installer_without_start_process_wait():
    for opt in ("/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_launcher=1", "InstallLauncherAllUsers=0",
                "Include_test=0", "Include_doc=0", "Shortcuts=0", r'TargetDir=`"$Tools\python`"'):
        assert opt in PS1, opt
    start = next(ln for ln in PS1.splitlines() if "Start-Process" in ln)
    assert "-PassThru" in start and "-Wait" not in start and ".WaitForExit()" in PS1


def test_ps1_unblocks_warns_about_long_paths_and_never_mentions_winget_or_remote_scripts():
    assert "Unblock-File" in PS1 and "-gt 120" in PS1
    low = PS1.lower()
    for bad in ("winget", "iex", "invoke-expression", "irm "):
        assert bad not in low, bad
    assert "WindowsApps" in PS1  # the Store python stub is never accepted


def test_ps1_builds_the_py_launcher_prefix_as_a_real_array():
    """`$pre = if (...) { @('-3') } else { @() }` unrolls to the STRING '-3' and `@pre` then mangles
    the call (python started its REPL instead of running the probe): wrap it in @( ... )."""
    assert "$pre = @(if ($n -eq 'py') { '-3' })" in PS1


def test_ps1_never_runs_the_python_installer_inside_a_sandbox_rehearsal():
    """The python.org installer writes the real HKCU PATH (PrependPath=1): a sandboxed proof run
    (AGENTIC_MERCY_SANDBOX=1) must stop before it, not leak into the user's profile."""
    body = PS1[PS1.index("function Install-Python"):]
    guard = body.index("AGENTIC_MERCY_SANDBOX")
    assert guard < body.index("Start-Process") and "Stop-Install" in body[guard:guard + 400]


def test_ps1_never_installs_python_in_ci_mode():
    """SANTA1B-02: `-Ci` only plans. With no usable Python it stops with an error BEFORE the download."""
    guard = PS1.index("-not $Py -and $IsCi")
    assert guard < PS1.index("Install-Python;") and "Stop-Install" in PS1[guard:guard + 300]
    assert "never installs" in PS1[guard:guard + 300]
    assert "$IsCi = $Ci -or (@($Rest) -contains '--ci')" in PS1  # `install.cmd --ci` is the same mode


def test_find_python_judges_by_exit_code_not_by_stderr_text():
    """SANTA1B-03: Windows PowerShell 5.1 turns native stderr into a terminating error under
    `$ErrorActionPreference = 'Stop'`; a working Python that writes a warning was skipped and reinstalled."""
    body = PS1[PS1.index("function Find-Python"):PS1.index("function Install-Python")]
    assert body.index("$ErrorActionPreference = 'Continue'") < body.index("& $exe @pre")
    assert "$LASTEXITCODE -eq 0" in body and "2>$null" in body


def test_ps1_takes_every_path_literally_so_brackets_in_a_folder_name_work():
    """A5v2-01: `-Path` is wildcard-expanded (`[work]` = one of w, o, r, k); an unmatched one made
    `Get-Content -Raw` die with `A parameter cannot be found ... 'Raw'`. Every cmdlet on a path variable
    takes `-LiteralPath`; `Get-Command` only ever sees a bare name."""
    cmdlets = ("Get-Content", "Test-Path", "Get-ChildItem", "Split-Path", "Remove-Item", "Get-FileHash",
               "Get-AuthenticodeSignature")
    for ln in PS1.splitlines():
        for c in cmdlets:
            if c in ln and "function " not in ln:
                assert "-LiteralPath" in ln, ln
    for ln in PS1.splitlines():
        if "Get-Command" in ln:
            assert "Get-Command $n " in ln and "-like '*\\*'" in ln, ln


def test_ps1_checks_it_is_the_workbench_before_unblocking_and_drops_the_policy_preference():
    """A5v2-08: no Unblock-File pass over a folder that is not the repository, and the Bypass that install.cmd
    asked for is not exported to every child process the installer starts."""
    check = PS1.index("Test-Path -LiteralPath (Join-Path $Repo 'installer\\manifest.json')")
    assert check < PS1.index("Unblock-File -") and "Stop-Install" in PS1[check:check + 200]
    assert PS1.index("SetEnvironmentVariable('PSExecutionPolicyPreference', $null, 'Process')") < PS1.index("& $Py.Exe")


def test_ps1_derives_the_tools_dir_from_the_profile_in_a_sandbox_and_warns_outside_it():
    """SANTA1B-04 / SEC1B-02: a sandboxed run never resolves LOCALAPPDATA (the real profile) and a tools
    dir outside the profile is called out."""
    line = next(ln for ln in PS1.splitlines() if ln.startswith("$Tools ="))
    assert "AGENTIC_MERCY_SANDBOX" in line and "$env:USERPROFILE" in line
    assert "AGENTIC_MERCY_TOOLS_DIR is outside" in PS1


def test_ps1_is_ascii_and_short():
    PS1.encode("ascii")  # Windows PowerShell 5.1 reads a BOM-less file as ANSI
    assert "\r" not in PS1 and len(PS1.splitlines()) <= 110


# (the launchers run for real under PowerShell 5.1 / cmd.exe: test_install_entry_run.py)
@pytest.mark.skipif(not (shutil.which("pwsh") or shutil.which("powershell")), reason="no PowerShell here")
def test_ps1_parses_without_errors():
    ps = shutil.which("pwsh") or shutil.which("powershell")
    code = ("$e=$null;$t=$null;[void][System.Management.Automation.Language.Parser]::ParseFile("
            "$env:P5_PS1,[ref]$t,[ref]$e);$e.Count")
    cp = subprocess.run([ps, "-NoProfile", "-Command", code], capture_output=True, encoding="utf-8",
                        env={**os.environ, "P5_PS1": str(_ROOT / "install.ps1")}, timeout=60)
    assert cp.stdout.strip() == "0", cp.stdout + cp.stderr


# --- pick_python: the choice install.ps1 makes in PowerShell, rehearsed here ------------------- #
STUB = "X:\\Users\\a\\AppData\\Local\\Microsoft\\WindowsApps\\python3.exe"


def test_pick_python_rejects_the_store_stub_even_when_it_would_run():
    runs = Runs(out={"python3": "3.14", "python": "3.14"})
    which = {"python": STUB, "python3": STUB}.get
    assert winutil.pick_python(which, runs) is None
    assert runs.calls == []  # the stub is never executed


def test_pick_python_accepts_the_py_launcher_first():
    runs = Runs(out={"py": "3.14"})
    assert winutil.pick_python({"py": "/w/py.exe", "python": "/p/python.exe"}.get, runs) == ["/w/py.exe", "-3"]
    assert runs.calls[0][:2] == ["/w/py.exe", "-3"]


def test_pick_python_rejects_below_3_10_and_falls_through_to_the_next_candidate():
    runs = Runs(out={"py": "3.9", "python": "3.11"})
    got = winutil.pick_python({"py": "/w/py.exe", "python": "/p/python.exe"}.get, runs)
    assert got == ["/p/python.exe"]
    assert winutil.pick_python({"py": "/w/py.exe"}.get, Runs(out={"py": "3.9"})) is None


def test_pick_python_falls_back_to_the_tools_dir_python(tmp_path):
    exe = tmp_path / "python" / "python.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"x")
    assert winutil.pick_python(lambda n: None, Runs(out={"python": "3.14"}), tools=tmp_path) == [str(exe)]
    assert winutil.pick_python(lambda n: None, Runs(rc={"python": 1}), tools=tmp_path) is None
