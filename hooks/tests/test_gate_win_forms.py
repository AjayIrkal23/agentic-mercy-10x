"""A4v2-01: the destructive-command gate also judges the way a model really spells a Windows delete.

Backtick line continuation, `git.exe` (bare, `&`-called, quoted full path), `Get-ChildItem | Remove-Item`
pipelines, .NET directory deletes and Git Bash's `cmd //c rd //s //q`. Every case runs the real gate script
on a payload, so a spelling that slips past `main()` fails here whatever regex it dodged.
"""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import uuid
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]
PS, BASH = "PowerShell", "Bash"
GIT_EXE = r'"D:\Program Files\Git\cmd\git.exe"'


@pytest.fixture()
def gate(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(f"win_{uuid.uuid4().hex}", HOOKS / "dangerous-bash-gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "STATE_DIR", tmp_path)

    def run(cmd: str, tool: str = PS) -> str:
        payload = {"tool_name": tool, "tool_input": {"command": cmd}, "session_id": f"w-{uuid.uuid4().hex}"}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        out = io.StringIO()
        monkeypatch.setattr(sys, "stdout", out)
        mod.main()
        return (json.loads(out.getvalue() or "{}").get("hookSpecificOutput") or {}).get("permissionDecision", "allow")
    return run


# (command, tools that must deny it). The Bash tool keeps its old verdicts, so only forms that Bash
# itself runs (or that name a Windows-only command) are listed for it.
DENY = [
    ("Remove-Item `\n  -Recurse `\n  -Force D:\\Projects\\x", [PS]),
    ("Remove-Item `\r\n  -Recurse D:\\x", [PS]),
    ("git `\n  reset --hard", [PS]),
    ("git.exe reset --hard", [PS, BASH]),
    ("git.exe -C repo reset --hard HEAD~3", [PS, BASH]),
    ("git.exe push --force origin main", [PS, BASH]),
    ("git.exe clean -fd", [PS, BASH]),
    ("& git.exe reset --hard", [PS]),
    (f"& {GIT_EXE} reset --hard", [PS]),
    (f"& {GIT_EXE} push -f origin main", [PS]),
    (f"{GIT_EXE} reset --hard", [BASH]),
    ("'C:/Program Files/Git/cmd/git.exe' reset --hard", [PS, BASH]),
    ("Get-ChildItem D:\\x -Recurse | Remove-Item -Force", [PS, BASH]),
    ("Get-ChildItem D:\\x -Recurse | Remove-Item -Recurse -Force", [PS, BASH]),
    ("gci D:\\x -r | ri -Force", [PS, BASH]),
    ("gci D:\\x -r | rm -fo", [PS]),
    ("ls D:\\x | del", [PS, BASH]),
    ("dir D:\\x | erase", [PS, BASH]),
    ("ls D:\\x | rmdir", [PS]),
    ("Get-ChildItem D:\\x | Where-Object { $_.Length -gt 0 } | Remove-Item -Force", [PS, BASH]),
    ("Get-ChildItem D:\\x -Recurse |\n  Remove-Item -Force", [PS]),
    ("Get-ChildItem $env:TEMP\\ok -Recurse | Remove-Item; Get-ChildItem D:\\work | Remove-Item", [PS]),
    ("[IO.Directory]::Delete('D:\\x', $true)", [PS, BASH]),
    ("[System.IO.Directory]::Delete($p, $true)", [PS, BASH]),
    ('[io.directory]::delete("D:\\x",1)', [PS, BASH]),
    ("[IO.Directory]::Delete('D:\\x', $true); [IO.Directory]::Delete($env:TEMP + '\\y', $true)", [PS]),
    ("(Get-Item D:\\x).Delete($true)", [PS, BASH]),
    ("Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory('D:\\x', 'DeleteAllContents')", [PS, BASH]),
    ('powershell -Command "[IO.Directory]::Delete(\'D:\\x\', $true)"', [BASH]),
    ("cmd //c rd //s //q D:\\\\x", [BASH]),
    ('cmd //c "rd /s /q D:\\Projects\\x"', [BASH]),
    ("cmd.exe //c rmdir //s //q D:\\x", [BASH]),
    ("cmd //c del //s //q D:\\x", [BASH]),
    ("cmd //c del //q D:\\*", [BASH]),
    ('"/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe" -c "Remove-Item -Recurse -Force D:\\x"', [BASH]),
]


@pytest.mark.parametrize("cmd,tools", DENY, ids=[c[0][:48] for c in DENY])
def test_natural_spellings_of_a_destructive_command_are_denied(gate, cmd, tools):
    for tool in tools:
        assert gate(cmd, tool) == "deny", (tool, cmd)


ALLOW = [
    "git.exe status",
    "git.exe -C repo log --oneline -n 5",
    f"& {GIT_EXE} status",
    "git.exe commit -m 'fix: x'",
    "git `\n  status",
    "Remove-Item `\n  -Force D:\\x\\f.txt",
    "Get-ChildItem D:\\x | Select-Object -First 3",
    "Get-ChildItem D:\\x |\n  Sort-Object Length",
    "gci | Where-Object Length | Format-Table",
    "Get-Content list.txt | ForEach-Object { Write-Host $_ }",
    "Get-ChildItem $env:TEMP\\x -Recurse | Remove-Item -Force",
    "gci $env:TEMP\\x | Where-Object Length | Remove-Item -Force",
    r"Get-ChildItem D:\Users\me\AppData\Local\Temp\x | del",
    "[IO.Directory]::Delete(\"$env:TEMP\\x\", $true)",
    "[IO.Directory]::Exists('D:\\x')",
    "[IO.File]::Delete('D:\\x\\f.txt')",
    "[IO.Directory]::GetFiles('D:\\x')",
    'echo "git.exe reset --hard is blocked"',
    'git commit -m "mention | Remove-Item and [IO.Directory]::Delete"',
    "Write-Host 'gci x | Remove-Item -Force'",
    "cmd //c dir",
    "cmd //c rd x",
    "cmd //c del x.txt",
    "ls | sort",
]


@pytest.mark.parametrize("cmd", ALLOW, ids=[c[:48] for c in ALLOW])
def test_look_alike_commands_and_temp_targets_still_pass(gate, cmd):
    assert gate(cmd, PS) == "allow", cmd


def test_the_bash_tool_keeps_its_verdicts_for_pipelines_it_never_runs(gate):
    """`rm` / `rd` / `rmdir` after a pipe are PowerShell aliases; in Bash they stay ungated (as on main)."""
    for cmd in ("cat files | xargs rm", "ls x | rm", "echo y | rd"):
        assert gate(cmd, BASH) == "allow", cmd
    assert gate("git status `\nrm -rf x", BASH) == "deny"  # the rm -rf line is still its own command


def test_a_backtick_is_only_a_continuation_in_the_powershell_tool(gate):
    """Bash reads a trailing backtick as command substitution, so `-Recurse` on the next line is not joined."""
    cmd = "Remove-Item `\n -Recurse D:\\x"
    assert gate(cmd, PS) == "deny"
    assert gate("echo `\n -Recurse", BASH) == "allow"
