"""dispatch.py audit fixes (2026-10-05 WP3): deferred advisories (B1-02), lean-ctx
adapters (B1-04), mod failure/release signal (B1-06), gate precedence (B1-07),
`via` on --only rows (B1-14), raw stdout on non-zero exit (B1-15), line-boundary cap
(B1-16), ownership parsing (B1-18), `ms` on every _dispatch row (A-10)."""
from __future__ import annotations

import glob
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent
DISPATCH = HOOKS / "dispatch.py"


def _load():
    spec = importlib.util.spec_from_file_location("dispatch_wp3", DISPATCH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _script(tmp_path: Path, name: str, body: str) -> list:
    p = tmp_path / f"{name}.py"
    p.write_text("import json, sys, time\n" + body, encoding="utf-8")
    return [sys.executable, str(p)]


def _ctx(out: dict) -> str:
    return (out.get("hookSpecificOutput") or {}).get("additionalContext", "")


def _rows(link_id: str) -> list:
    rows = []
    for f in glob.glob(os.path.join(os.environ["CLAUDE_HOOK_TELEMETRY_DIR"], "hook-fires-*.jsonl")):
        for line in Path(f).read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r.get("link_id") == link_id:
                rows.append(r)
    return rows


# ---- B1-02: deferred advisory --------------------------------------------- #
def test_deferred_advisory_does_not_block_and_arrives_on_the_next_call(tmp_path):
    mod = _load()
    # The advisory blocks on a gate file the test releases, so "dispatch did not wait for it" does
    # not depend on how fast this box is (A7-07). A synchronous run would sit until `timeout_ms`
    # (20 s); the bound is half of that.
    release = tmp_path / "release"
    slow = _script(tmp_path, "slow",
                   "import os\n"
                   "json.load(sys.stdin)\n"
                   f"for _ in range(300):\n    if os.path.exists({str(release)!r}): break\n    time.sleep(0.1)\n"
                   "print(json.dumps({'hookSpecificOutput': {'additionalContext': 'TDD-NOTE'}}))\n")
    cfg = {"chains": {"pre-tool-use": [
        {"id": "slow-tdd", "type": "advisory", "defer": True, "tools": "Edit", "cmd": slow, "timeout_ms": 20000}]}}
    sid = f"defer-{time.time_ns()}"
    t0 = time.perf_counter()
    first = mod.dispatch("pre-tool-use", {"session_id": sid, "tool_name": "Edit"}, cfg)
    assert time.perf_counter() - t0 < 10.0
    assert "TDD-NOTE" not in _ctx(first)
    release.write_text("go", encoding="utf-8")
    seen = ""
    for _ in range(60):
        time.sleep(0.2)
        seen = _ctx(mod.dispatch("post-tool-use", {"session_id": sid, "tool_name": "Read"}, {"chains": {}}))
        if seen:
            break
    assert "TDD-NOTE" in seen
    # drained once: not repeated
    assert "TDD-NOTE" not in _ctx(mod.dispatch("post-tool-use", {"session_id": sid, "tool_name": "Read"}, {"chains": {}}))


def test_only_run_keeps_a_deferred_link_synchronous(tmp_path):
    """The mod's async lane runs `--only tdd-guard-launcher-pre` and needs the answer."""
    mod = _load()
    fast = _script(tmp_path, "fast", "json.load(sys.stdin); print(json.dumps({'additionalContext': 'NOW'}))\n")
    cfg = {"chains": {"pre-tool-use": [
        {"id": "t", "type": "advisory", "defer": True, "tools": "Edit", "cmd": fast}]}}
    out = mod.dispatch("pre-tool-use", {"session_id": "s", "tool_name": "Edit"}, cfg, frozenset({"t"}))
    assert "NOW" in _ctx(out)


# ---- B1-04: lean-ctx write/shell tools reach the gates -------------------- #
def _echo_gate(tmp_path):
    return _script(tmp_path, "echo", "p = json.load(sys.stdin)\n"
                   "print(json.dumps({'hookSpecificOutput': {'permissionDecision': 'deny',"
                   " 'permissionDecisionReason': p['tool_name'] + ':' + json.dumps(p['tool_input'], sort_keys=True)}}))\n")


def test_ctx_shell_is_gated_as_bash(tmp_path):
    mod = _load()
    cfg = {"chains": {"pre-tool-use": [{"id": "g", "type": "gate", "tools": "Bash", "cmd": _echo_gate(tmp_path)}]}}
    for tool in ("mcp__lean-ctx__ctx_shell", "mcp__lean-ctx__shell"):
        out = mod.dispatch("pre-tool-use", {"tool_name": tool, "tool_input": {"command": "rm -rf ~/x"}}, cfg)
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        assert reason.startswith("Bash:") and "rm -rf ~/x" in reason


def test_ctx_patch_is_gated_as_a_write(tmp_path):
    mod = _load()
    cfg = {"chains": {"pre-tool-use": [{"id": "g", "type": "gate", "tools": "Edit|Write", "cmd": _echo_gate(tmp_path)}]}}
    out = mod.dispatch("pre-tool-use", {"tool_name": "mcp__lean-ctx__ctx_patch", "tool_input": {
        "op": "replace_unique", "path": "/r/a.ts", "old_text": "x", "new_text": "y"}}, cfg)
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert reason.startswith("Edit:") and '"file_path": "/r/a.ts"' in reason and '"new_string": "y"' in reason
    out = mod.dispatch("pre-tool-use", {"tool_name": "mcp__lean-ctx__ctx_patch", "tool_input": {
        "op": "create", "path": "/r/b.ts", "new_text": "z"}}, cfg)
    assert out["hookSpecificOutput"]["permissionDecisionReason"].startswith("Write:")


def test_ctx_patch_batch_checks_every_path(tmp_path):
    mod = _load()
    deny_b = _script(tmp_path, "denyb", "p = json.load(sys.stdin)\n"
                     "if p['tool_input']['file_path'].endswith('b.ts'):\n"
                     "    print(json.dumps({'hookSpecificOutput': {'permissionDecision': 'deny', 'permissionDecisionReason': 'B'}}))\n")
    cfg = {"chains": {"pre-tool-use": [{"id": "g", "type": "gate", "tools": "Edit", "cmd": deny_b}]}}
    out = mod.dispatch("pre-tool-use", {"tool_name": "mcp__lean-ctx__ctx_patch", "tool_input": {"ops": [
        {"op": "replace_unique", "path": "/r/a.ts", "old_text": "1", "new_text": "2"},
        {"op": "replace_unique", "path": "/r/b.ts", "old_text": "1", "new_text": "2"}]}}, cfg)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_adapted_calls_ignore_mod_ownership(tmp_path, monkeypatch):
    """The mod plans by the real tool name, so it never runs an owned Bash gate for ctx_shell."""
    mod = _load()
    monkeypatch.setenv("MERCY_MOD_OWNED", "g")
    monkeypatch.setenv("MERCY_MOD_SESSION", "s1")
    monkeypatch.setenv("MERCY_MOD_BEAT", str(int(time.time() * 1000)))
    cfg = {"chains": {"pre-tool-use": [{"id": "g", "type": "gate", "tools": "Bash", "cmd": _echo_gate(tmp_path)}]}}
    out = mod.dispatch("pre-tool-use", {"session_id": "s1", "tool_name": "mcp__lean-ctx__ctx_shell",
                                        "tool_input": {"command": "ls"}}, cfg)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_ctx_read_is_not_adapted(tmp_path):
    mod = _load()
    cfg = {"chains": {"pre-tool-use": [{"id": "g", "type": "gate", "tools": "Bash|Edit|Write", "cmd": _echo_gate(tmp_path)}]}}
    assert mod.dispatch("pre-tool-use", {"tool_name": "mcp__lean-ctx__ctx_read", "tool_input": {"path": "/a"}}, cfg) == {}


# ---- B1-06: the mod's failure / release signal ---------------------------- #
def _own(monkeypatch, ids="a,b"):
    monkeypatch.setenv("MERCY_MOD_OWNED", ids)
    monkeypatch.setenv("MERCY_MOD_SESSION", "s1")
    monkeypatch.setenv("MERCY_MOD_BEAT", str(int(time.time() * 1000)))


def test_a_failed_mod_run_hands_that_call_back(monkeypatch):
    mod = _load()
    _own(monkeypatch)
    monkeypatch.setenv("MERCY_MOD_FAILED", "tu-9:b")
    assert mod._mod_owned({"session_id": "s1", "tool_use_id": "tu-9"}) == frozenset({"a"})
    assert mod._mod_owned({"session_id": "s1", "tool_use_id": "tu-10"}) == frozenset({"a", "b"})


# ---- B1-07: precedence ---------------------------------------------------- #
def _gate(tmp_path, name, out):
    return {"id": name, "type": "gate", "tools": "Bash",
            "cmd": _script(tmp_path, name, f"json.load(sys.stdin); print(json.dumps({out!r}))\n")}


def test_ask_then_deny_returns_deny_and_keeps_earlier_context(tmp_path):
    mod = _load()
    cfg = {"chains": {"pre-tool-use": [
        _gate(tmp_path, "c", {"additionalContext": "EARLY-CTX"}),
        _gate(tmp_path, "a", {"hookSpecificOutput": {"permissionDecision": "ask", "permissionDecisionReason": "ASK-R"}}),
        _gate(tmp_path, "d", {"hookSpecificOutput": {"permissionDecision": "deny", "permissionDecisionReason": "DENY-R"}})]}}
    hso = mod.dispatch("pre-tool-use", {"tool_name": "Bash", "tool_input": {"command": "x"}}, cfg)["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    assert "DENY-R" in hso["permissionDecisionReason"]
    assert "EARLY-CTX" in hso["permissionDecisionReason"] and "ASK-R" in hso["permissionDecisionReason"]


def test_ask_alone_keeps_gate_context(tmp_path):
    mod = _load()
    cfg = {"chains": {"pre-tool-use": [
        _gate(tmp_path, "c", {"additionalContext": "EARLY-CTX"}),
        _gate(tmp_path, "a", {"hookSpecificOutput": {"permissionDecision": "ask", "permissionDecisionReason": "ASK-R"}})]}}
    hso = mod.dispatch("pre-tool-use", {"tool_name": "Bash", "tool_input": {"command": "x"}}, cfg)["hookSpecificOutput"]
    assert hso["permissionDecision"] == "ask" and hso["permissionDecisionReason"] == "ASK-R"
    assert "EARLY-CTX" in hso.get("additionalContext", "")


# ---- B1-14 / A-10: telemetry --------------------------------------------- #
def test_only_rows_carry_via_and_dispatch_rows_carry_ms(tmp_path):
    mod = _load()
    lid = f"via-{time.time_ns()}"
    cfg = {"chains": {"pre-tool-use": [{"id": lid, "type": "gate", "tools": "Bash", "cmd": _script(
        tmp_path, "d", "json.load(sys.stdin); print(json.dumps({'permissionDecision': 'deny'}))\n")}]}}
    sid = f"tel-{time.time_ns()}"
    mod.dispatch("pre-tool-use", {"session_id": sid, "tool_name": "Bash"}, cfg, frozenset({lid}))
    assert [r.get("via") for r in _rows(lid)] == ["mod"]
    d = [r for r in _rows("_dispatch") if r.get("session") == sid]
    assert d and all(isinstance(r.get("ms"), (int, float)) for r in d)


# ---- B1-15: raw stdout only on success ------------------------------------ #
def test_raw_stdout_of_a_failed_advisory_is_dropped(tmp_path):
    mod = _load()
    cfg = {"chains": {"post-tool-use": [
        {"id": "bad", "type": "advisory", "tools": "Edit", "cmd": _script(tmp_path, "bad", "print('Traceback garbage'); sys.exit(3)\n")},
        {"id": "ok", "type": "advisory", "tools": "Edit", "cmd": _script(tmp_path, "ok", "print('plain text ok')\n")}]}}
    out = _ctx(mod.dispatch("post-tool-use", {"tool_name": "Edit"}, cfg))
    assert "plain text ok" in out and "garbage" not in out


# ---- B1-16: cap on a line boundary, gate context first ------------------- #
def test_char_cap_cuts_on_a_line_and_keeps_gate_context(tmp_path):
    mod = _load()
    big = "\n".join(f"L{i:03d} " + "x" * 60 for i in range(200))
    cfg = {"budgets": {"pre-tool-use": {"ms": 99999, "chars": 2000}}, "chains": {"pre-tool-use": [
        _gate(tmp_path, "g", {"additionalContext": "GATE-NOTE"}),
        {"id": "adv", "type": "advisory", "tools": "Bash", "priority": 0,
         "cmd": _script(tmp_path, "adv", f"print(json.dumps({{'additionalContext': {big!r}}}))\n")}]}}
    out = _ctx(mod.dispatch("pre-tool-use", {"tool_name": "Bash"}, cfg))
    assert len(out) <= 2000 and out.startswith("GATE-NOTE")
    assert out.rstrip().endswith("[truncated]")
    body = out.rstrip()[: -len("[truncated]")].rstrip().splitlines()
    assert body[-1].endswith("x" * 60)


# ---- B1-18: ownership parsing -------------------------------------------- #
def test_owned_ids_are_stripped(monkeypatch):
    mod = _load()
    _own(monkeypatch, " a , ,b")
    assert mod._mod_owned({"session_id": "s1"}) == frozenset({"a", "b"})


def test_bare_only_runs_nothing():
    payload = {"session_id": "x", "tool_name": "Bash", "tool_input": {"command": "rm -rf ~/projects"}}
    for argv in (["--only"], ["--only", ""], ["--only", " , "]):
        proc = subprocess.run([sys.executable, str(DISPATCH), "pre-tool-use", *argv], input=json.dumps(payload),
                              capture_output=True, text=True, timeout=60)
        assert json.loads(proc.stdout) == {}, argv
