"""dispatch.py plumbing: mutations survive (Agent), Bash control-char drop,
new events (SubagentStart / TeammateIdle / PostToolUseFailure), async execs."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent
DISPATCH = HOOKS / "dispatch.py"
FIXTURES = HOOKS.parent / "tests" / "fixtures" / "hook-events"


def _load():
    spec = importlib.util.spec_from_file_location("dispatch_under_test", DISPATCH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(event: str, payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(DISPATCH), event], input=json.dumps(payload),
                          capture_output=True, text=True, timeout=60)


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_agent_rewrite_with_multiline_prompt_survives():
    payload = _fixture("pre-tool-use-agent.json")
    payload["tool_input"] = {"description": "do it", "subagent_type": "general-purpose",
                             "prompt": "line one\nline two\r\nline three"}
    proc = _run("pre-tool-use", payload)
    assert proc.returncode == 0
    hso = json.loads(proc.stdout)["hookSpecificOutput"]
    assert hso["updatedInput"]["model"] == "sonnet"
    assert hso["updatedInput"]["prompt"] == "line one\nline two\r\nline three"


def test_bash_control_chars_still_dropped(tmp_path):
    mod = _load()
    fake = tmp_path / "fake_mutator.py"
    fake.write_text(
        "import json,sys\n"
        "json.load(sys.stdin)\n"
        "print(json.dumps({'hookSpecificOutput':{'hookEventName':'PreToolUse',"
        "'updatedInput':{'command':'echo a\\necho b'}}}))\n",
        encoding="utf-8")
    cfg = {"chains": {"pre-tool-use": [
        {"id": "fake", "type": "mutator", "tools": "Bash", "cmd": [sys.executable, str(fake)]}]}}
    out = mod.dispatch("pre-tool-use", {"tool_name": "Bash", "tool_input": {"command": "ls"}}, cfg)
    assert out == {}


def test_tools_regex_is_fullmatch():
    mod = _load()
    assert mod._link_matches({"tools": "Read"}, "Read")
    assert not mod._link_matches({"tools": "Read"}, "mcp__lean-ctx__ctx_read")
    assert mod._link_matches({"tools": "mcp__semgrep__.*"}, "mcp__semgrep__semgrep_scan")


def test_async_exec_not_waited(tmp_path):
    mod = _load()
    slow = tmp_path / "slow.py"
    slow.write_text("import time; time.sleep(3)\n", encoding="utf-8")
    cfg = {"chains": {"stop": [
        {"id": "slow", "type": "exec", "async": True, "cmd": [sys.executable, str(slow)]}]}}
    t0 = time.perf_counter()
    assert mod.dispatch("stop", {}, cfg) == {}
    assert time.perf_counter() - t0 < 2


def test_subagent_start_injects_protocol():
    proc = _run("subagent-start", _fixture("subagent-start.json"))
    hso = json.loads(proc.stdout)["hookSpecificOutput"]
    assert hso["hookEventName"] == "SubagentStart"
    assert "FILE ACCESS PROTOCOL" in hso["additionalContext"]
    assert "git commit" in hso["additionalContext"]
    assert "MCP PROTOCOL" in hso["additionalContext"]
    assert "sequentialthinking" in hso["additionalContext"]


def test_teammate_idle_blocks_with_exit_2(tmp_path):
    run = tmp_path / ".claude" / "runs" / "20260928-x"
    run.mkdir(parents=True)
    (run / "run.json").write_text(json.dumps(
        {"expected_artifacts": {"impl-be": "IMPL-REPORT-BE.md"}}), encoding="utf-8")
    payload = {"hook_event_name": "TeammateIdle", "teammate_name": "impl-be", "cwd": str(tmp_path)}
    proc = _run("teammate-idle", payload)
    assert proc.returncode == 2
    assert "IMPL-REPORT-BE.md" in proc.stderr
    (tmp_path / "IMPL-REPORT-BE.md").write_text("done", encoding="utf-8")
    proc = _run("teammate-idle", payload)
    assert proc.returncode == 0 and json.loads(proc.stdout) == {}


def test_post_tool_use_failure_hint():
    proc = _run("post-tool-use-failure", _fixture("post-tool-use-failure.json"))
    hso = json.loads(proc.stdout)["hookSpecificOutput"]
    assert hso["hookEventName"] == "PostToolUseFailure"
    assert "Read the exact file" in hso["additionalContext"]


def test_mutator_allow_is_not_forwarded(tmp_path):
    """Santa P2: a rewrite must not auto-approve — updatedInput alone is applied by
    the harness (hookUpdatedInput) and the normal permission flow still runs."""
    mod = _load()
    fake = tmp_path / "allow_mutator.py"
    fake.write_text(
        "import json,sys\n"
        "json.load(sys.stdin)\n"
        "print(json.dumps({'hookSpecificOutput':{'hookEventName':'PreToolUse',"
        "'permissionDecision':'allow','updatedInput':{'script':'x'}}}))\n",
        encoding="utf-8")
    cfg = {"chains": {"pre-tool-use": [
        {"id": "fake", "type": "mutator", "tools": "Workflow", "cmd": [sys.executable, str(fake)]}]}}
    out = mod.dispatch("pre-tool-use", {"tool_name": "Workflow", "tool_input": {"script": "y"}}, cfg)
    hso = out["hookSpecificOutput"]
    assert hso["updatedInput"] == {"script": "x"}
    assert "permissionDecision" not in hso


def test_post_compact_emits_no_hook_specific_output(tmp_path):
    """Santa A4: PostCompact is not in the harness hookSpecificOutput union."""
    mod = _load()
    assert "PostCompact" in mod._NO_HSO_EVENTS
    adv = tmp_path / "adv.py"
    adv.write_text("print('{\"additionalContext\": \"x\"}')\n", encoding="utf-8")
    cfg = {"chains": {"post-compact": [{"id": "a", "type": "advisory",
                                        "cmd": [sys.executable, str(adv)]}]}}
    assert mod.dispatch("post-compact", {}, cfg) == {}


def test_session_start_compact_reinjects_handoff(tmp_path, monkeypatch):
    """Santa A4: the pre-compact handoff reaches the model via SessionStart(compact)."""
    import io
    from contextlib import redirect_stdout
    spec = importlib.util.spec_from_file_location("sl_ut", HOOKS / "session-lifecycle.py")
    sl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sl)
    monkeypatch.setattr(sl, "STATE_DIR", tmp_path)
    monkeypatch.setattr(sl, "BREADCRUMB", tmp_path / "none.json")
    (tmp_path / "sess-9.precompact-handoff.json").write_text(json.dumps(
        {"conversation_id": "sess-9", "write_count": 7}), encoding="utf-8")

    def run(source: str) -> str:
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(
            {"session_id": "sess-9", "source": source, "cwd": str(tmp_path)})))
        buf = io.StringIO()
        with redirect_stdout(buf):
            sl.session_start()
        return buf.getvalue()

    out = json.loads(run("compact"))
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "RESUMED FROM PRE-COMPACT SNAPSHOT" in ctx and "write_count: 7" in ctx
    assert "PRE-COMPACT" not in run("startup")


def test_stop_passes_system_message(tmp_path):
    mod = _load()
    gate = tmp_path / "gate.py"
    gate.write_text("print('{\"systemMessage\": \"heads up\"}')\n", encoding="utf-8")
    cfg = {"chains": {"stop": [{"id": "g", "type": "gate", "cmd": [sys.executable, str(gate)]}]}}
    assert mod.dispatch("stop", {}, cfg) == {"systemMessage": "heads up"}


def _run_cp1252(event: str, payload: dict) -> subprocess.CompletedProcess:
    """A Windows console without PYTHONUTF8: stdio (and child stdin) encode as cp1252."""
    import os
    env = {**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0",
           "CLAUDE_HOOK_DOCTOR": "1"}
    return subprocess.run([sys.executable, str(DISPATCH), event],
                          input=json.dumps(payload), capture_output=True, text=True,
                          encoding="utf-8", timeout=60, env=env)


def test_non_cp1252_text_survives_a_cp1252_console(tmp_path):
    """Output: the merged context ("→" etc.) must not crash the final print, which fell
    back to {} and lost the whole SessionStart. Input: a payload with "→" is passed
    to every link's stdin; encoding it as cp1252 errored each link, so no gate ran."""
    ss = json.loads(_run_cp1252("session-start", _fixture("session-start.json")).stdout)
    assert "ALWAYS-ON STYLE" in ss["hookSpecificOutput"]["additionalContext"]
    bash = _fixture("pre-tool-use-bash.json")
    # fresh session: the bash gate lets an identical retry through once per session
    bash["session_id"] = f"cp1252-{time.time_ns()}"
    bash["tool_input"] = {"command": "rm -rf ~/projects  # cleanup → done"}
    out = _run_cp1252("pre-tool-use", bash).stdout
    assert "DANGEROUS COMMAND BLOCKED" in out, out
