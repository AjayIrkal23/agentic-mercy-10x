"""Tests for hooks/tool-failure-hint.py (PostToolUseFailure advisory).

Legacy hints (Edit before Read, lean-ctx PathJail) plus the OOM additions: a recent
kill in state/oomguard.events names the victim, a SIGKILL with a tool memory cap set
records a `toolcap` kill, and repeated MCP failures name the server once it fails twice.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import types
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parents[1]
_ROOT = _HOOKS.parent
sys.path.insert(0, str(_HOOKS))
from lib import platform as plat  # noqa: E402


def _load():
    spec = importlib.util.spec_from_file_location("tool_failure_hint_under_test", _HOOKS / "tool-failure-hint.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tfh = _load()
NOW = 1_800_000_000
KILL = {"session_id": "s", "tool_name": "Bash", "tool_input": {"command": "npx vitest run"},
        "error": "Exit code 137\nKilled", "is_interrupt": False}


@pytest.fixture(autouse=True)
def state(tmp_path, monkeypatch):
    d = tmp_path / "state"
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(d))
    monkeypatch.setattr(tfh, "_now", lambda: NOW)
    monkeypatch.delenv("CLAUDE_CODE_TOOL_MEMORY_LIMIT", raising=False)
    monkeypatch.delenv("TOOL_MEMORY_LIMIT", raising=False)
    import lib
    monkeypatch.setitem(sys.modules, "lib.memwatch_state", None)  # inline writer unless a test injects one
    monkeypatch.delattr(lib, "memwatch_state", raising=False)
    return d


def run(payload) -> dict:
    old = sys.stdin
    sys.stdin = io.StringIO(payload if isinstance(payload, str) else json.dumps(payload))
    try:
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            assert tfh.main() == 0
    finally:
        sys.stdin = old
    return json.loads(buf.getvalue())


def ctx(out: dict) -> str:
    return out["hookSpecificOutput"]["additionalContext"]


def events(state, *rows):
    state.mkdir(parents=True, exist_ok=True)
    with open(state / "oomguard.events", "a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def read_events(state) -> list:
    p = state / "oomguard.events"
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def test_existing_hints_unchanged():
    fixture = json.loads((_ROOT / "tests" / "fixtures" / "hook-events" / "post-tool-use-failure.json")
                         .read_text(encoding="utf-8"))
    assert "Read the exact file" in ctx(run(fixture))
    out = run({"tool_name": "Bash", "error": "Error: path escapes project root", "session_id": "s"})
    assert "lean-ctx PathJail" in ctx(out)


def test_normal_failure_is_silent(state):
    assert run(dict(KILL, error="Exit code 1\nnpm ERR!")) == {}
    assert run(dict(KILL, is_interrupt=True)) == {}
    assert read_events(state) == []


@pytest.mark.parametrize(("source", "text"), [("kernel", "kernel OOM kill"), ("oomd", "oomd"),
                                              ("user-manager", "user-manager"), ("memwatch", "memwatch stage 2")])
def test_recent_kernel_kill_names_the_victim(state, source, text):
    events(state, {"ts": NOW - 20, "kind": "kill", "victim": "node", "rss_mb": 3900,
                   "unit": "ptyxis-x.scope", "source": source, "stage": 2})
    hint = ctx(run(KILL))
    assert text in hint and "node" in hint and "3900" in hint and "20 s ago" in hint
    assert len(read_events(state)) == 1


def test_old_kill_is_ignored(state):
    events(state, {"ts": NOW - 91, "kind": "kill", "victim": "node", "rss_mb": 1, "unit": "u", "source": "kernel"})
    assert run(KILL) == {}


@pytest.mark.parametrize("var", ["CLAUDE_CODE_TOOL_MEMORY_LIMIT", "TOOL_MEMORY_LIMIT"])
def test_toolcap_inference_writes_the_event_and_hints(state, monkeypatch, var):
    monkeypatch.setenv(var, "6G")
    assert "tool memory cap (6G)" in ctx(run(KILL))
    (row,) = read_events(state)
    assert row["kind"] == "kill" and row["source"] == "toolcap" and row["tool"] == "Bash"
    assert row["limit"] == "6G" and row["cmd"] == "npx vitest run" and row["sid"] == "s" and row["ts"] == NOW


def test_toolcap_needs_the_env_and_the_sigkill_shape(state, monkeypatch):
    assert run(KILL) == {}
    assert not (state / "oomguard.events").exists()
    monkeypatch.setenv("CLAUDE_CODE_TOOL_MEMORY_LIMIT", "6G")
    assert run(dict(KILL, error="Exit code 1")) == {}
    for err in ("Exit code 137", "Exit code -9\nboom", "Killed", "npm run x\nKilled\n"):
        assert "tool memory cap" in ctx(run(dict(KILL, error=err)))


def test_sigkill_shape_is_the_exit_status_not_free_text(state, monkeypatch):
    """settings always set CLAUDE_CODE_TOOL_MEMORY_LIMIT, so a free-text match used to turn an
    exit-1 test failure into a tool-cap kill."""
    monkeypatch.setenv("CLAUDE_CODE_TOOL_MEMORY_LIMIT", "6G")
    for err in ("Exit code 1\nFAILED t.py::test_x - AssertionError: expected SIGKILL row",
                "Exit code 1\nchild terminated by signal 9", "Exit code 2\nKilled 3 zombies",
                "log line\nExit code 137"):
        assert tfh.memory_hint(dict(KILL, error=err), err) == ""
    assert not (state / "oomguard.events").exists()
    err = "Exit code 137\nnpx vitest run"
    assert "tool memory cap" in tfh.memory_hint(dict(KILL, error=err), err)
    assert read_events(state)[0]["source"] == "toolcap"


def test_toolcap_rows_never_count_as_a_recent_kill(state, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_TOOL_MEMORY_LIMIT", "6G")
    run(KILL)
    assert "tool memory cap" in ctx(run(KILL))  # not "toolcap hit ..."


def test_tier_line_is_added_when_the_state_says_warn(state):
    events(state, {"ts": NOW - 5, "kind": "kill", "victim": "node", "rss_mb": 1, "unit": "u", "source": "kernel"})
    (state / "mem-pressure.json").write_text(json.dumps({"schema": 1, "ts": NOW - 2, "level": "warn"}),
                                             encoding="utf-8")
    assert ctx(run(KILL)).endswith("memory tier warn: wait for ok before heavy commands")


def test_mcp_failure_cache_and_normalised_reason(state):
    p = {"session_id": "s", "tool_name": "mcp__github__search_code", "error": "Error 429: rate limit exceeded"}
    assert run(p) == {}
    cache = state / "s.mcp-unhealthy.json"
    assert json.loads(cache.read_text(encoding="utf-8")) == {"github": {"count": 1, "last_code": "429", "last_ts": NOW}}
    assert "MCP server github failed 2x this session (429)" in ctx(run(p))
    assert json.loads(cache.read_text(encoding="utf-8"))["github"]["count"] == 2
    run(dict(p, tool_name="mcp__jdoc__x", error="connect ECONNREFUSED 127.0.0.1"))
    run(dict(p, tool_name="mcp__other__x", error="weird"))
    d = json.loads(cache.read_text(encoding="utf-8"))
    assert d["jdoc"]["last_code"] == "transport" and "other" not in d


def test_mcp_ordinary_tool_errors_are_not_server_failures(state):
    """A bad argument or a missing symbol is not an unhealthy server (MCP-first rule)."""
    p = {"session_id": "s", "tool_name": "mcp__jcodemunch__get_symbol_source",
         "error": "Symbol not found: foo.bar"}
    assert run(p) == {} and run(p) == {}
    assert not (state / "s.mcp-unhealthy.json").exists()
    p = dict(p, error="HTTP 429 Too Many Requests")
    assert run(p) == {}
    assert "MCP server jcodemunch failed 2x this session (429)" in ctx(run(p))


@pytest.mark.parametrize(("text", "code"), [("401 Unauthorized", "401"), ("forbidden", "403"),
                                            ("too many requests", "429"), ("service unavailable", "503"),
                                            ("socket hang up", "transport"), ("timed out", "transport"),
                                            ("boom", "other")])
def test_normalize_reason_table(text, code):
    assert tfh.normalize_reason(text) == code


def test_events_tail_read_survives_garbage_and_large_files(state):
    state.mkdir(parents=True, exist_ok=True)
    junk = ("x" * 99 + "\n") * 21000
    (state / "oomguard.events").write_text(junk, encoding="utf-8")
    assert run(KILL) == {}
    events(state, {"ts": NOW - 3, "kind": "kill", "victim": "java", "rss_mb": 5, "unit": "u", "source": "kernel"})
    assert "java" in ctx(run(KILL))


def test_append_prefers_memwatch_state_when_importable(state, monkeypatch):
    import lib
    got: list = []
    fake = types.ModuleType("lib.memwatch_state")
    fake.append_event = got.append
    monkeypatch.setitem(sys.modules, "lib.memwatch_state", fake)
    monkeypatch.setattr(lib, "memwatch_state", fake, raising=False)
    monkeypatch.setenv("CLAUDE_CODE_TOOL_MEMORY_LIMIT", "6G")
    assert "tool memory cap" in ctx(run(KILL))
    assert len(got) == 1 and got[0]["source"] == "toolcap"
    assert not (state / "oomguard.events").exists()


def test_windows_flag_still_hints_and_writes_the_event(state, monkeypatch):
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    monkeypatch.setenv("CLAUDE_CODE_TOOL_MEMORY_LIMIT", "6G")
    assert "tool memory cap (6G)" in ctx(run(KILL))
    assert read_events(state)[0]["source"] == "toolcap"


def test_garbage_stdin_prints_empty_json():
    assert run("not json") == {}


def test_hint_is_capped_at_220_chars(state):
    events(state, {"ts": NOW - 1, "kind": "kill", "victim": "v" * 300, "rss_mb": 1, "unit": "u", "source": "kernel"})
    assert len(ctx(run(KILL))) <= 220
