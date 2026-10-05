"""PowerShell file writes are shell writes (audit A1-02 / A4-01, plan W6a): bash-write-gate sees
Set-Content / Add-Content / Out-File / [IO.File] writers and `>`; tool-failure-hint and the turn
command list treat the PowerShell tool like Bash. Split from test_powershell_gates.py (250-line cap).
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
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))


def _load(file: str):
    spec = importlib.util.spec_from_file_location(f"psw_{uuid.uuid4().hex}", HOOKS / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _decision(out: dict) -> str:
    return (out.get("hookSpecificOutput") or {}).get("permissionDecision") or "allow"


def _reason(out: dict) -> str:
    return (out.get("hookSpecificOutput") or {}).get("permissionDecisionReason", "")


@pytest.fixture()
def bwg(tmp_path, monkeypatch):
    mod = _load("bash-write-gate.py")
    monkeypatch.setattr(mod, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(mod, "_count_references", lambda p: 0)  # no grep over the repo
    return mod


def _write_gate(mod, monkeypatch, cmd: str, tool: str = "PowerShell", armed: bool = False) -> dict:
    monkeypatch.setattr(mod, "BYPASS_DENY_ON", armed)
    payload = {"session_id": f"w-{uuid.uuid4().hex}", "tool_name": tool, "tool_input": {"command": cmd}}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    mod.main()
    return json.loads(buf.getvalue() or "{}")


PS_WRITES = [
    r"Set-Content src\app.ts 'x'",
    r"Set-Content -Path src\app.ts -Value 'x'",
    r"Set-Content -Value 'x' -LiteralPath src\app.ts",
    r"Add-Content -Path src/app.ts -Value 'x'",
    r"'x' | Out-File src\app.ts",
    r"Get-Content a.txt | Out-File -FilePath src\app.ts -Append",
    r"Set-Content -Path 'src\app.ts' -Value 'x'",
    r"[IO.File]::WriteAllText('src\app.ts', 'x')",
    r'[System.IO.File]::AppendAllText("src/app.ts", "x")',
    r"Write-Output 'x' > src\app.ts",
    r"Get-Content a.txt >> src\app.ts",
    r"sc src\app.ts 'x'; ls",
]


@pytest.mark.parametrize("cmd", PS_WRITES)
def test_powershell_writes_are_flagged_as_shell_writes(bwg, monkeypatch, cmd):
    advisory = _write_gate(bwg, monkeypatch, cmd)
    assert "BASH-WRITE-GATE" in json.dumps(advisory), (cmd, advisory)
    assert _decision(advisory) == "allow"
    armed = _write_gate(bwg, monkeypatch, cmd, armed=True)
    assert _decision(armed) == "deny" and "BASH-WRITE-GATE" in _reason(armed), (cmd, armed)
    assert _decision(_write_gate(bwg, monkeypatch, cmd, tool="Bash", armed=True)) == "deny"


@pytest.mark.parametrize("cmd", [
    r"Set-Content $env:TEMP\scratch.ts 'x'",
    r"'x' | Out-File ${env:TMP}\scratch.ts",
    r"Set-Content D:\Users\me\AppData\Local\Temp\a.ts 'x'",
    r"Add-Content build.log 'x'",
    r"Set-Content node_modules\pkg\x.js 'x'",
    r"[IO.File]::WriteAllText('dist\bundle.js', 'x')",
    r"Get-Content src\app.ts",
    r"Get-Content src\app.ts | Select-String foo",
    'git commit -m "use Set-Content src\\app.ts instead"',
    "echo 'Out-File src/app.ts is banned'",
])
def test_powershell_scratch_and_reads_are_exempt(bwg, monkeypatch, cmd):
    assert _write_gate(bwg, monkeypatch, cmd) == {}, cmd
    assert _write_gate(bwg, monkeypatch, cmd, armed=True) == {}, cmd


def test_bash_write_gate_ignores_non_shell_tools(bwg, monkeypatch):
    assert _write_gate(bwg, monkeypatch, r"Set-Content src\app.ts 'x'", tool="Write", armed=True) == {}


# ---- the other scripts that hard-coded Bash -------------------------------- #
def test_tool_failure_hint_covers_powershell():
    mod = _load("tool-failure-hint.py")
    for tool in ("Bash", "PowerShell"):
        assert "PathJail" in mod.hint(tool, "error: path escapes project root"), tool
    assert mod.hint("Read", "path escapes project root") == ""


def test_turn_shell_commands_include_powershell(tmp_path):
    from lib import turns
    rows = [{"type": "user", "timestamp": "2026-10-06T10:00:00+00:00",
             "message": {"role": "user", "content": "go"}}]
    for name, cmd in (("Bash", "ls"), ("PowerShell", "Get-Content SKILL.md"), ("Read", "nope")):
        rows.append({"type": "assistant", "timestamp": "2026-10-06T10:00:01+00:00",
                     "message": {"role": "assistant", "content": [
                         {"type": "tool_use", "name": name, "input": {"command": cmd}}]}})
    p = tmp_path / "t.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    assert turns.turn_bash_commands(str(p)) == ["ls", "Get-Content SKILL.md"]
