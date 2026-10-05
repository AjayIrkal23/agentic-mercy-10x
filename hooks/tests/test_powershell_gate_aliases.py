"""SANTA1-04: in the PowerShell tool `rm` / `rd` / `rmdir` are `Remove-Item` aliases and `-r` is
`-Recurse`, so they are judged like `Remove-Item -Recurse`. In Bash `rm -r` stays ungated
(`rm -rf` is the Bash rule). The gate fixture comes from test_powershell_gates.py."""
from __future__ import annotations

import pytest

from test_powershell_gates import gate  # noqa: F401 (fixture)


@pytest.mark.parametrize("cmd", [
    r"rm -r D:\Projects\app",
    r"rd -r D:\Projects\app",
    r"rmdir -r D:\Projects\app",
    r"rm -rec -fo D:\x",
    r"Get-ChildItem D:\x | rm -r",
    r"if ($x) { rm -r D:\x }",
    r"rm -r $env:TEMP\ok,D:\x",
    r'powershell -NoProfile -Command "rm -r D:\x"',
])
def test_powershell_tool_gates_abbreviated_recurse_aliases(gate, cmd):
    assert gate(cmd, tool="PowerShell") == "deny", cmd


@pytest.mark.parametrize("cmd", ["rm -r ./build", r"rm -r D:\Projects\app", "rd -r build"])
def test_bash_tool_rm_r_is_unchanged(gate, cmd):
    assert gate(cmd, tool="Bash") == "allow", cmd


@pytest.mark.parametrize("cmd", [
    r"rm -r $env:TEMP\scratch",
    "git rm -r --cached build",
    "rm build.log",
    "rm -rx foo",
    "echo rm -r D:\\x",
])
def test_powershell_tool_alias_rule_spares_temp_git_rm_and_plain_rm(gate, cmd):
    assert gate(cmd, tool="PowerShell") == "allow", cmd
