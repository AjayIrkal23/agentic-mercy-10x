"""dispatch.py plumbing: mutations survive (Agent), Bash control-char drop,
new events (SubagentStart / TeammateIdle / PostToolUseFailure), async execs."""
from __future__ import annotations

import importlib.util
import json
import os
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
    # The exec waits on a gate file (up to 30 s) that the test releases afterwards: dispatch must
    # come back long before that, however slow this box is (A7-07). No tight clock bound.
    release = tmp_path / "release"
    slow = tmp_path / "slow.py"
    slow.write_text("import os, time\n"
                    f"for _ in range(300):\n    if os.path.exists({str(release)!r}): break\n    time.sleep(0.1)\n",
                    encoding="utf-8")
    cfg = {"chains": {"stop": [
        {"id": "slow", "type": "exec", "async": True, "cmd": [sys.executable, str(slow)]}]}}
    t0 = time.perf_counter()
    try:
        assert mod.dispatch("stop", {}, cfg) == {}
        assert time.perf_counter() - t0 < 15
    finally:
        release.write_text("go", encoding="utf-8")


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


def test_the_prompt_delivers_queued_stop_gate_notes(tmp_path):
    """CLAUDE.md §11: Stop gates queue model-only notes; the next prompt delivers them before
    any tool runs (they used to wait for the next tool call)."""
    mod = _load()
    sid = f"t-q-{os.getpid()}"
    assert mod._sup.enqueue(sid, "invoke-suite-gate", "Pushed skills not loaded last turn (advisory): update-docs.")
    out = mod.dispatch("user-prompt-submit", {"session_id": sid, "prompt": "next"}, {"chains": {"user-prompt-submit": []}})
    ctx = json.dumps(out)
    assert "update-docs" in ctx
    assert mod._sup.drain(sid) == []  # delivered once


def test_stop_passes_system_message(tmp_path):
    mod = _load()
    gate = tmp_path / "gate.py"
    gate.write_text("print('{\"systemMessage\": \"heads up\"}')\n", encoding="utf-8")
    cfg = {"chains": {"stop": [{"id": "g", "type": "gate", "cmd": [sys.executable, str(gate)]}]}}
    assert mod.dispatch("stop", {}, cfg) == {"systemMessage": "heads up"}


def _echo_links(tmp_path) -> dict:
    """Two advisory links that each print their own id as context."""
    links = []
    for lid in ("a", "b"):
        script = tmp_path / f"{lid}.py"
        script.write_text(f"print('{{\"additionalContext\": \"from-{lid}\"}}')\n", encoding="utf-8")
        links.append({"id": lid, "type": "advisory", "tools": "Edit", "cmd": [sys.executable, str(script)]})
    return {"chains": {"post-tool-use": links}}


def _contexts(out: dict) -> str:
    return (out.get("hookSpecificOutput") or {}).get("additionalContext", "")


def _own(monkeypatch, ids: str, session: str = "s1", age_s: float = 0.0):
    monkeypatch.setenv("MERCY_MOD_OWNED", ids)
    monkeypatch.setenv("MERCY_MOD_SESSION", session)
    monkeypatch.setenv("MERCY_MOD_BEAT", str(int((time.time() - age_s) * 1000)))


def test_mod_owned_links_skipped_only_for_the_owning_session(tmp_path, monkeypatch):
    """mods/mercy bridge: owned links are the mod's to run, for its own session only."""
    mod = _load()
    cfg = _echo_links(tmp_path)
    _own(monkeypatch, "a")
    mine = _contexts(mod.dispatch("post-tool-use", {"session_id": "s1", "tool_name": "Edit"}, cfg))
    assert "from-b" in mine and "from-a" not in mine
    other = _contexts(mod.dispatch("post-tool-use", {"session_id": "s2", "tool_name": "Edit"}, cfg))
    assert "from-a" in other and "from-b" in other
    monkeypatch.delenv("MERCY_MOD_SESSION")
    unowned = _contexts(mod.dispatch("post-tool-use", {"session_id": "s1", "tool_name": "Edit"}, cfg))
    assert "from-a" in unowned


def test_a_stale_mod_heartbeat_hands_every_link_back(tmp_path, monkeypatch):
    """A mod unloaded mid-session leaves its env behind; the aged beat voids ownership."""
    mod = _load()
    cfg = _echo_links(tmp_path)
    _own(monkeypatch, "a", age_s=600)
    out = _contexts(mod.dispatch("post-tool-use", {"session_id": "s1", "tool_name": "Edit"}, cfg))
    assert "from-a" in out and "from-b" in out


def test_only_runs_the_listed_links_and_ignores_ownership(tmp_path, monkeypatch):
    mod = _load()
    cfg = _echo_links(tmp_path)
    _own(monkeypatch, "a,b")
    out = _contexts(mod.dispatch("post-tool-use", {"session_id": "s1", "tool_name": "Edit"}, cfg, frozenset({"a"})))
    assert "from-a" in out and "from-b" not in out


def test_only_flag_and_ownership_through_the_cli():
    """The real config + CLI path the mod uses: `dispatch.py <event> --only <ids>`."""
    import os
    payload = _fixture("post-tool-use-failure.json")
    env = {**os.environ, "CLAUDE_HOOK_DOCTOR": "1", "MERCY_MOD_OWNED": "tool-failure-hint",
           "MERCY_MOD_SESSION": payload["session_id"], "MERCY_MOD_BEAT": str(int(time.time() * 1000))}
    owned = subprocess.run([sys.executable, str(DISPATCH), "post-tool-use-failure"], input=json.dumps(payload),
                           capture_output=True, text=True, timeout=60, env=env)
    assert json.loads(owned.stdout) == {}
    only = subprocess.run([sys.executable, str(DISPATCH), "post-tool-use-failure", "--only", "tool-failure-hint"],
                          input=json.dumps(payload), capture_output=True, text=True, timeout=60, env=env)
    assert "Read the exact file" in json.loads(only.stdout)["hookSpecificOutput"]["additionalContext"]


def _run_cp1252(event: str, payload: dict) -> subprocess.CompletedProcess:
    """A Windows console without PYTHONUTF8: stdio (and child stdin) encode as cp1252."""
    import os
    env = {**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0",
           "CLAUDE_HOOK_DOCTOR": "1"}
    # Claude Code writes raw UTF-8 (not \\u escapes) to the hook's stdin.
    return subprocess.run([sys.executable, str(DISPATCH), event],
                          input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                          capture_output=True, timeout=60, env=env)


def test_non_cp1252_text_survives_a_cp1252_console(tmp_path):
    """A Windows console without PYTHONUTF8. Output: the merged context ("→") must not
    crash the final print (it fell back to {} and lost SessionStart). Input: stdin is
    UTF-8 from Claude Code; decoded as cp1252 it garbled Agent prompts in updatedInput
    ("—" -> "â€”") and a byte like 0x9D (in "”") emptied the payload so no gate ran."""
    ss = json.loads(_run_cp1252("session-start", _fixture("session-start.json")).stdout)
    assert "ALWAYS-ON STYLE" in ss["hookSpecificOutput"]["additionalContext"]
    bash = _fixture("pre-tool-use-bash.json")
    # fresh session: the bash gate lets an identical retry through once per session
    bash["session_id"] = f"cp1252-{time.time_ns()}"
    bash["tool_input"] = {"command": "rm -rf ~/projects  # said ”ok” → done"}
    out = _run_cp1252("pre-tool-use", bash).stdout.decode("utf-8")
    assert "DANGEROUS COMMAND BLOCKED" in out, out
    agent = _fixture("pre-tool-use-agent.json")
    agent["tool_input"] = {"description": "d", "subagent_type": "general-purpose",
                           "prompt": "Review A — then B → report ”done”"}
    hso = json.loads(_run_cp1252("pre-tool-use", agent).stdout)["hookSpecificOutput"]
    assert hso["updatedInput"]["prompt"] == "Review A — then B → report ”done”"
