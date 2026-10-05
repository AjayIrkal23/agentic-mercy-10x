"""PowerShell is a shell tool everywhere Bash is (audit A1-02 / A4-01 / A7-02, plan W6a).

Claude Code on Windows exposes a `PowerShell` tool beside `Bash`. Before this slice no matcher,
`dispatch.config.json` link or gate script knew it, so `git reset --hard` was denied as Bash and
ran untouched as PowerShell. Everything here is payload-driven and runs on any OS.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import sys
import uuid
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]
ROOT = HOOKS.parent
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

import tool_compat  # noqa: E402

CFG = json.loads((HOOKS / "dispatch.config.json").read_text(encoding="utf-8"))
SETTINGS_HOOKS = json.loads((ROOT / "settings.template.json").read_text(encoding="utf-8"))["hooks"]


def _load(file: str):
    spec = importlib.util.spec_from_file_location(f"ps_{uuid.uuid4().hex}", HOOKS / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _decision(out: dict) -> str:
    return (out.get("hookSpecificOutput") or {}).get("permissionDecision") or "allow"


def _reason(out: dict) -> str:
    return (out.get("hookSpecificOutput") or {}).get("permissionDecisionReason", "")


@pytest.fixture(scope="module")
def dispatcher():
    return _load("dispatch.py")


def _gates_only() -> dict:
    """The real pre-tool-use gate links (not the advisories): what must deny or ask."""
    gates = [ln for ln in CFG["chains"]["pre-tool-use"] if ln["type"] == "gate"]
    return {"chains": {"pre-tool-use": gates}, "budgets": CFG["budgets"]}


def _dispatch(dispatcher, tool: str, cmd: str, sid: str = "", cwd: str = "") -> dict:
    payload = {"session_id": sid or f"ps-{uuid.uuid4().hex}", "tool_name": tool,
               "tool_input": {"command": cmd}}
    if cwd:
        payload["cwd"] = cwd
    return dispatcher.dispatch("pre-tool-use", payload, _gates_only())


# ---- tool_compat ---------------------------------------------------------- #
def test_powershell_is_a_shell_tool():
    assert tool_compat.is_shell_tool("PowerShell")
    assert tool_compat.is_shell_tool("Bash") and tool_compat.is_shell_tool("Shell")
    assert not tool_compat.is_shell_tool("Write") and not tool_compat.is_shell_tool("powershellx")


# ---- matchers and dispatch.config tools agree ------------------------------ #
@pytest.mark.parametrize("event", ["PreToolUse", "PostToolUse", "PostToolUseFailure"])
def test_every_settings_matcher_that_matches_bash_matches_powershell(event):
    for group in SETTINGS_HOOKS[event]:
        m = group["matcher"]
        assert re.fullmatch(m, "Bash"), (event, m)
        assert re.fullmatch(m, "PowerShell"), (event, m)


def test_every_dispatch_link_that_matches_bash_matches_powershell():
    seen = set()
    for event, chain in CFG["chains"].items():
        for ln in chain:
            tools = ln.get("tools")
            if tools and re.fullmatch(f"(?:{tools})", "Bash"):
                seen.add(ln["id"])
                assert re.fullmatch(f"(?:{tools})", "PowerShell"), (event, ln["id"], tools)
    assert {"dangerous-bash-gate", "bash-write-gate", "blocking-doc-enforcer", "graphify-enforce",
            "security-semgrep-tracker", "tool-failure-hint"} <= seen


# ---- the dispatcher denies PowerShell like Bash ---------------------------- #
DENY = [
    "git reset --hard HEAD~5",
    "git push --force origin main",
    r"Remove-Item -Recurse -Force D:\x",
    "rd /s /q x",
    "del /s /q x",
    "Format-Volume -DriveLetter D",
]


@pytest.mark.parametrize("cmd", DENY)
@pytest.mark.parametrize("tool", ["Bash", "PowerShell"])
def test_dispatch_denies_destructive_commands_for_either_shell(dispatcher, tool, cmd):
    out = _dispatch(dispatcher, tool, cmd)
    assert _decision(out) == "deny", (tool, cmd, out)
    assert "DANGEROUS COMMAND BLOCKED" in _reason(out)


def test_dispatch_doc_enforcer_sees_a_powershell_git_commit():
    spec = importlib.util.spec_from_file_location("dispatch_ps_doc", HOOKS / "dispatch.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sid = f"ps-doc-{uuid.uuid4().hex}"
    state = {"be_touched": True, "fe_touched": False, "code_files": ["/work/GO_UDP/server/a.go"],
             "be_docs_written": False, "linkages_written": False}
    state_dir = Path(os.environ["CLAUDE_HOOK_DOTSTATE_DIR"])
    (state_dir / f"{sid}.doc-enforcer.json").write_text(json.dumps(state), encoding="utf-8")
    for tool in ("Bash", "PowerShell"):
        out = _dispatch(mod, tool, "git commit -m x", sid=sid, cwd="/work/GO_UDP")
        assert _decision(out) == "deny", (tool, out)
        assert "server_docs/" in _reason(out)


# ---- dangerous-bash-gate: PowerShell-native patterns ----------------------- #
@pytest.fixture()
def gate(tmp_path, monkeypatch):
    m = _load("dangerous-bash-gate.py")
    monkeypatch.setattr(m, "STATE_DIR", tmp_path)

    def run(cmd: str, tool: str = "PowerShell") -> str:
        payload = {"tool_name": tool, "tool_input": {"command": cmd}, "session_id": f"g-{uuid.uuid4().hex}"}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        out = io.StringIO()
        monkeypatch.setattr(sys, "stdout", out)
        m.main()
        return _decision(json.loads(out.getvalue() or "{}"))
    return run


@pytest.mark.parametrize("cmd", [
    r"Remove-Item -Recurse -Force D:\x",
    r"Remove-Item D:\x -Recurse",
    r'Remove-Item -Path "D:\Program Files\x" -Recurse -Force',
    r"remove-item -r -fo D:\work",
    r"ri -Recurse D:\x",
    r"del -Recurse D:\x",
    r"rm -Recurse D:\x",
    r"Get-ChildItem D:\x | Remove-Item -Recurse -Force",
    r"Remove-Item -Recurse -Force $env:USERPROFILE\src",
    r"Remove-Item -Recurse -Force $env:TEMP\ok; Remove-Item -Recurse -Force D:\work",
    "rd /s /q x",
    "RMDIR /S D:\\x",
    "rmdir x /s /q",
    "del /s /q *.tmp",
    r"del /q D:\*",
    r"del /q *",
    r"erase /q D:\\",
    "Format-Volume -DriveLetter D",
    "Clear-Disk -Number 1 -RemoveData",
    "format D: /q",
    "git clean -fd",
    "git clean -fdx",
    'cmd /c "rd /s /q D:\\x"',
    'powershell -NoProfile -Command "Remove-Item -Recurse -Force D:\\x"',
    "pwsh -c 'Remove-Item -Recurse -Force C:/x'",
    "iex 'Remove-Item -Recurse -Force D:\\x'",
    # SANTA1-01: another command's -n / -rn / -NonInteractive must not pass as git clean's dry run
    "git clean -fdx && git log -n 5",
    "git clean -fdx && grep -rn TODO src",
    'powershell -NonInteractive -Command "git clean -fdx"',
    "git log -n 5 && git clean -fd",
    "git clean -n -fd && git clean -fd",
    "git clean -fd -- -n",
    # SANTA1-03 / SEC1-02: a PowerShell array is several targets, one of them not temp
    r"Remove-Item -Recurse -Force $env:TEMP\build,D:\Users\X\proj",
    r'Remove-Item -Recurse -Force "$env:TEMP\build","D:\Projects\app"',
    r"Remove-Item $env:TEMP\x,D:\Users\X\Documents -Recurse",
    r"Remove-Item -Recurse -Path $env:TEMP\x,D:\Users\X\Documents",
])
def test_powershell_native_destructive_commands_are_denied(gate, cmd):
    assert gate(cmd) == "deny", cmd
    assert gate(cmd, tool="Bash") == "deny", cmd


@pytest.mark.parametrize("cmd", [
    r"Remove-Item D:\x\file.txt",
    r"Remove-Item -Force D:\x\file.txt",
    r"Remove-Item -Recurse -Force $env:TEMP\scratch",
    r'Remove-Item -Recurse -Force "$env:TEMP\scratch"',
    r"Remove-Item -Recurse -Force $env:TMP\a $env:TEMP\b",
    r"Remove-Item -Recurse -Force D:\Users\me\AppData\Local\Temp\x",
    "Remove-Item -Recurse -Force /tmp/x",
    r"Get-ChildItem -Recurse D:\x",
    "rd x",
    "rmdir x",
    "del x.txt",
    "del /q x.txt",
    r"del /q build\out.log",
    "git clean -nfd",
    "git clean -n -fd",
    "git clean --dry-run -fd",
    "git clean -fd --dry-run",
    "git -C repo clean -n -fd",
    r"Remove-Item -Recurse -Force $env:TEMP\a,$env:TEMP\b",
    r'Remove-Item -Recurse -Force "$env:TEMP\a","$env:TMP\b"',
    "grep -ri foo -r .",
    "ls -ri",
    'git commit -m "document Remove-Item -Recurse and rd /s and Format-Volume"',
    "Write-Host 'Remove-Item -Recurse -Force D:\\x is blocked'",
    "echo 'del /s /q x'",
])
def test_powershell_safe_commands_pass(gate, cmd):
    assert gate(cmd) == "allow", cmd


# SANTA1-04 (rm -r aliases in the PowerShell tool): test_powershell_gate_aliases.py
# bash-write-gate, tool-failure-hint and turn commands: test_powershell_writes.py
