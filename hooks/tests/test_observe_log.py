"""Tests for hooks/lib/scrub.py and hooks/observe-log.py (package learning, docs/LEARNING.md).

Scrub section: credential values become [REDACTED] while keys and ordinary text stay, in
linear time. Hook section: one scrubbed <= 2 KB row per tool call into
state/learning/<repo_key>/observations.jsonl; skip list, infra roots, doctor no-op, fail-open.
Fake credentials are assembled from pieces (EXAMPLE values) so the file holds no literal key.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HOOKS))
from lib import scrub as sc  # noqa: E402

_PK_HEADER = "-----BEGIN RSA " + "PRIVATE KEY-----"
_GHP = "gh" + "p_" + "EXAMPLE" + "ABCDEFGHIJKLMNOPQRSTUVWXYZab"
_AWS = "AK" + "IA" + "IOSFODNN7EXAMPLE"


# --------------------------------------------------------------------------- scrub
def test_key_value_secrets_are_redacted():
    s = sc.scrub('api_' + 'key="abcdef' + '123456789" token: ' + _GHP + ' password=hunter2hunter2')
    assert "abcdef123456789" not in s and _GHP[:12] not in s and "hunter2hunter2" not in s
    assert "api_key" in s and "[REDACTED]" in s


def test_bare_tokens_are_redacted():
    for tok in ("sk-" + "ant-api03-" + "a" * 40, "sk-" + "b" * 32, _AWS, "AI" + "za" + "c" * 35,
                "xo" + "xb-1234567890-abcdefghij", "hf_" + "d" * 24, "eyJhbGciOi.eyJzdWIi.sig123",
                "github" + "_pat_" + "e" * 30):
        assert tok not in sc.scrub("before " + tok + " after"), tok


def test_url_credentials_and_private_key_header():
    assert "user:pa55word" not in sc.scrub("https://user:pa55word@host/x")
    assert "PRIVATE KEY" not in sc.scrub(_PK_HEADER + "\nMIIE...")


def test_ordinary_text_is_untouched():
    for s in ("Edit src/auth/token_store.py (old 12, new 14)", "npm test -- --watch=false", "export PATH=$HOME/bin:$PATH",
              'pytest -k "test_token_refresh"', "python3 hooks/tools/secrets_scan.py --known-values",
              "the password field label", "AUTH_TOKEN_TTL=3600 node app.js", "tokenizer=cl100k_base"):
        assert sc.scrub(s) == s, s


def test_env_style_keys_are_redacted():
    # env-var names glue a prefix onto the key (AWS_SECRET_ACCESS_KEY, PGPASSWORD); values assembled from pieces
    aws_val = "wJalrXUtnFEMI" + "/K7MDENG/bPxRfiCY" + "EXAMPLEKEY"
    gh_val = "abcd" + "efghijkl" + "mnop12"
    cases = {
        "export AWS_SECRET_ACCESS_KEY=" + aws_val + " && deploy": "wJalrXUtnFEMI",
        "PGPASSWORD=" + "hunter22" + "extra psql -h db": "hunter22extra",
        "DB_PASSWORD=" + "supersecret" + "value1 node x": "supersecretvalue1",
        "GITHUB_" + "TOKEN=" + gh_val + " gh auth status": gh_val,
        "OPENAI_API_KEY=" + "plainvalue" + "123456 python run.py": "plainvalue123456",
        'STRIPE_SECRET_KEY: "' + "sk_" + "test_" + "z" * 24 + '"': "z" * 24,
        "MY-API-KEY=" + "hyphenated" + "12345": "hyphenated12345",
    }
    for s, leak in cases.items():
        out = sc.scrub(s)
        assert leak not in out and "[REDACTED]" in out, s
        assert s.split("=")[0].split(":")[0] in out, s  # the key name stays


def test_scrub_dict_redacts_by_key_before_serialising():
    out = sc.scrub_obj({"command": "ls", "env": {"API_KEY": "zzzzzzzzzzzz", "HOME": "/h"}, "Authorization": "Bearer abcdefghijklmnop"})
    assert out["env"]["API_KEY"] == "[REDACTED]" and out["env"]["HOME"] == "/h" and out["Authorization"] == "[REDACTED]"


def test_scrub_is_linear_on_a_flood():
    flood = ("token=" + "x" * 50 + " ") * 1000 + "a" * 50_000
    t0 = time.monotonic()
    sc.scrub("a" * 50_000)
    t1 = time.monotonic()
    sc.scrub(flood)
    t2 = time.monotonic()
    assert (t2 - t1) < 20 * max(t1 - t0, 0.001) + 0.5


# --------------------------------------------------------------------------- hook
def _load():
    spec = importlib.util.spec_from_file_location("observe_log_under_test", _HOOKS / "observe-log.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ol = _load()


@pytest.fixture
def box(tmp_path, monkeypatch):
    state = tmp_path / "state"
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(state))
    monkeypatch.setenv("CLAUDE_HOOK_TELEMETRY_DIR", str(tmp_path / "tel"))
    monkeypatch.delenv("CLAUDE_HOOK_DOCTOR", raising=False)  # CI exports it; writes must happen here
    monkeypatch.setattr(ol, "_CONFIG_PATH", tmp_path / "learning.config.json")
    return {"state": state, "repo": repo, "tmp": tmp_path}


def run(payload) -> str:
    old = sys.stdin
    sys.stdin = io.StringIO(payload if isinstance(payload, str) else json.dumps(payload))
    try:
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            assert ol.main() == 0
    finally:
        sys.stdin = old
    return buf.getvalue()


def payload(tool="Edit", cwd=None, inp=None, resp=None, **extra):
    return {"session_id": "t-sid", "cwd": str(cwd) if cwd is not None else None, "hook_event_name": "PostToolUse",
            "tool_name": tool,
            "tool_input": inp if inp is not None else {"file_path": str(Path(str(cwd)) / "src" / "a.py"),
                                                       "old_string": "a", "new_string": "bb"},
            "tool_response": resp if resp is not None else {"filePath": "x"}, **extra}


def obs_files(box):
    return sorted((box["state"] / "learning").glob("*/observations.jsonl"))


def rows(box, cwd=None):
    from lib.model_mode import repo_key
    f = box["state"] / "learning" / repo_key(str(cwd or box["repo"])) / "observations.jsonl"
    return [json.loads(ln) for ln in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []


def write_cfg(box, **cfg):
    (box["tmp"] / "learning.config.json").write_text(json.dumps(cfg), encoding="utf-8")


def test_row_shape_and_location(box):
    out = run(payload(cwd=box["repo"]))
    assert out == "{}\n"
    (row,) = rows(box)
    assert set(row) == {"ts", "sid", "tool", "summary", "ok", "files"}
    assert isinstance(row["ts"], float) and abs(row["ts"] - time.time()) < 60
    assert row["sid"] == "t-sid" and row["tool"] == "Edit" and row["ok"] is True
    assert row["files"] == ["src/a.py"] and "src/a.py" in row["summary"]


def test_edit_summary_is_metadata_not_content(box):
    inp = {"file_path": str(box["repo"] / "src" / "a.py"), "old_string": "SECRET_BODY_OLD" * 20, "new_string": "NEW" * 50}
    run(payload(cwd=box["repo"], inp=inp))
    s = rows(box)[0]["summary"]
    assert "SECRET_BODY_OLD" not in s and "NEWNEW" not in s
    assert "old 300, new 150" in s


def test_bash_summary_is_the_scrubbed_command_head(box):
    cmd = "curl -H 'Authorization: " + "Bearer " + "abcdefgh" + "ijklmnop' https://x && " + "y" * 500
    run(payload("Bash", cwd=box["repo"], inp={"command": cmd}, resp={"stdout": "", "stderr": ""}))
    row = rows(box)[0]
    assert "abcdefghijklmnop" not in row["summary"] and "[REDACTED]" in row["summary"]
    assert len(row["summary"]) <= 420 and row["files"] == []
    run(payload("Bash", cwd=box["repo"], inp={"command": "export PGPASSWORD=" + "hunter22" + "extra && psql"}))
    pg = rows(box)[1]["summary"]
    assert "hunter22extra" not in pg and "PGPASSWORD=[REDACTED]" in pg


def test_row_never_exceeds_2048_bytes(box):
    long_path = str(box["repo"] / ("d" * 290) / "f.py")
    run(payload("Write", cwd=box["repo"], inp={"file_path": long_path, "content": "z" * 10000}))
    edits = [{"file_path": str(box["repo"] / f"pkg{i}" / ("m" * 60 + ".py")), "old_string": "a", "new_string": "b"}
             for i in range(40)]
    run(payload("MultiEdit", cwd=box["repo"], inp={"file_path": edits[0]["file_path"], "edits": edits}))
    f = obs_files(box)[0]
    lines = f.read_bytes().splitlines()
    assert len(lines) == 2
    for ln in lines:
        assert len(ln) + 1 <= 2048
        json.loads(ln)
    multi = json.loads(lines[1])
    assert len(multi["files"]) <= 9 and "z" * 50 not in lines[0].decode()
    big = {"ts": 1.0, "sid": "s", "tool": "Bash", "summary": "q" * 3000, "ok": True, "files": [f"f{i}" * 30 for i in range(40)]}
    for limit in (2048, 400, 200):
        assert len(ol._cap(big, limit)) <= limit


def test_ok_false_shapes(box):
    for resp in ({"is_error": True, "error": "boom"}, {"stdout": "", "stderr": "x", "interrupted": True}, "Error: ENOENT",
                 {"stdout": "fine"}, [{"type": "text", "text": "ok"}]):
        run(payload("Bash", cwd=box["repo"], inp={"command": "ls"}, resp=resp))
    assert [r["ok"] for r in rows(box)] == [False, False, False, True, True]


def _failure(tool, cwd, inp, **fields):
    """A PostToolUseFailure-style payload: top-level error, no tool_response."""
    p = payload(tool, cwd=cwd, inp=inp)
    p.pop("tool_response")
    p.update(fields)
    return p


def test_failure_payload_is_logged_as_not_ok(box):
    run(_failure("Bash", box["repo"], {"command": "pytest -q"}, hook_event_name="PostToolUseFailure", error="Exit code 1"))
    run(_failure("Edit", box["repo"], {"file_path": "a.py", "old_string": "x", "new_string": "y"},
                 error="String to replace not found"))
    run(payload("Bash", cwd=box["repo"], inp={"command": "ls"}, resp={"stdout": "fine"}))
    got = rows(box)
    assert [r["ok"] for r in got] == [False, False, True]
    assert got[0]["tool"] == "Bash" and got[0]["files"] == [] and got[0]["error"] == "Exit code 1"
    assert got[1]["error"] == "String to replace not found" and "error" not in got[2]


def test_failure_error_is_scrubbed_and_clipped(box):
    err = "auth failed for DB_PASSWORD=" + "supersecret" + "value1 " + "e" * 400
    run(_failure("Bash", box["repo"], {"command": "psql"}, hook_event_name="PostToolUseFailure", error=err))
    (row,) = rows(box)
    assert "supersecretvalue1" not in row["error"] and "[REDACTED]" in row["error"]
    assert len(row["error"]) <= 161 and row["ok"] is False


def test_dispatch_failure_link_mirrors_the_success_link():
    cfg = json.loads((_HOOKS / "dispatch.config.json").read_text(encoding="utf-8"))
    chains = cfg.get("chains", {})
    ok_link = next((ln for ln in chains.get("post-tool-use", []) if ln.get("id") == "observe-log"), None)
    fail_link = next((ln for ln in chains.get("post-tool-use-failure", []) if ln.get("id") == "observe-log-failure"), None)
    if ok_link is None or fail_link is None:
        pytest.skip("integrate wires the links")
    assert fail_link["tools"] == ok_link["tools"] and fail_link["cmd"] == ok_link["cmd"]
    assert fail_link["async"] is True and fail_link["type"] == "exec" and fail_link["timeout_ms"] == 1500


def test_skip_list_from_config(box):
    for tool in ("Read", "Grep", "Glob"):
        run(payload(tool, cwd=box["repo"], inp={"file_path": "x"}))
    assert obs_files(box) == []
    write_cfg(box, skip_tools=["Edit"])
    run(payload(cwd=box["repo"]))
    assert rows(box) == []
    run(payload("Read", cwd=box["repo"], inp={"file_path": str(box["repo"] / "r.py")}))
    assert [r["tool"] for r in rows(box)] == ["Read"]


def test_infra_roots_are_skipped_unless_configured(box, monkeypatch):
    home = box["tmp"] / "home"
    (home / ".claude" / ".git").mkdir(parents=True)
    (home / ".claude" / "hooks").mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    cwd = home / ".claude" / "hooks"
    run(payload(cwd=cwd, inp={"file_path": str(cwd / "x.py"), "old_string": "a", "new_string": "b"}))
    assert obs_files(box) == []
    write_cfg(box, observe_infra=True)
    run(payload(cwd=cwd, inp={"file_path": str(cwd / "x.py"), "old_string": "a", "new_string": "b"}))
    names = [p.parent.name for p in obs_files(box)]
    assert len(names) == 1 and re.fullmatch(r"\.claude-[0-9a-f]{12}", names[0])
    loose = box["tmp"] / "loose"
    loose.mkdir()
    run(payload("Bash", cwd=loose, inp={"command": "ls"}))
    assert any(re.fullmatch(r"loose-[0-9a-f]{12}", p.parent.name) for p in obs_files(box))


def test_doctor_and_disabled_write_nothing(box, monkeypatch):
    monkeypatch.setenv("CLAUDE_HOOK_DOCTOR", "1")
    assert run(payload(cwd=box["repo"])) == "{}\n"
    monkeypatch.delenv("CLAUDE_HOOK_DOCTOR")
    write_cfg(box, enabled=False)
    assert run(payload(cwd=box["repo"])) == "{}\n"
    write_cfg(box, enabled=True)
    p = payload(cwd=box["repo"])
    p["session_id"] = "link-doctor"
    assert run(p) == "{}\n"
    assert obs_files(box) == []


def test_malformed_input_is_fail_open(box):
    no_cwd = payload(cwd=box["repo"])
    no_cwd.pop("cwd")
    for raw in ("not json", "", "[]", '{"tool_name": 5}', json.dumps(no_cwd)):
        assert run(raw) == "{}\n"
    assert obs_files(box) == []


def test_agent_and_mcp_rows_are_compact(box):
    run(payload("Agent", cwd=box["repo"], inp={"subagent_type": "santa-reviewer", "description": "review x", "prompt": "p" * 5000}))
    run(payload("mcp__jcodemunch__search_symbols", cwd=box["repo"], inp={"repo": "r", "query": "foo", "long": "v" * 500}))
    agent, mcp = rows(box)
    assert agent["summary"] == "santa-reviewer: review x"
    assert mcp["summary"].startswith("long=" + "v" * 60) and mcp["summary"].endswith("query=foo repo=r")
    assert len(mcp["summary"]) <= 200


def test_subprocess_run_matches_acceptance(tmp_path):
    raw = ('{"tool_name":"Edit","tool_input":{"file_path":"/tmp/x.py","old_string":"a","new_string":"b"},'
           '"tool_response":{"ok":true},"session_id":"t","cwd":"/tmp"}')
    env = {**os.environ, "CLAUDE_HOOK_STATE_DIR": str(tmp_path)}
    env.pop("CLAUDE_HOOK_DOCTOR", None)
    cp = subprocess.run([sys.executable, str(_HOOKS / "observe-log.py")], input=raw, env=env,
                        capture_output=True, text=True, timeout=30)
    assert cp.returncode == 0 and cp.stdout.strip() == "{}"
    files = list((tmp_path / "learning").glob("*/observations.jsonl"))
    assert len(files) == 1 and re.fullmatch(r"tmp-[0-9a-f]{12}", files[0].parent.name)
    assert len(files[0].read_text(encoding="utf-8").splitlines()) == 1


def test_dispatch_link_mirrors_skip_tools():
    cfg = json.loads((_HOOKS / "dispatch.config.json").read_text(encoding="utf-8"))
    link = next((ln for ln in cfg.get("chains", {}).get("post-tool-use", []) if ln.get("id") == "observe-log"), None)
    if link is None:
        pytest.skip("integrate wires the link")
    skip = json.loads((_HOOKS / "learning.config.json").read_text(encoding="utf-8"))["skip_tools"]
    rx = re.compile(link["tools"])
    for t in skip:
        assert rx.fullmatch(t) is None, t
    for t in ("Edit", "Write", "Bash", "Agent", "Skill", "mcp__semgrep__semgrep_scan"):
        assert rx.fullmatch(t), t
    assert link["async"] is True and link["type"] == "exec" and link["timeout_ms"] == 1500


def test_no_quota_or_posix_only_calls():
    src = (_HOOKS / "observe-log.py").read_text(encoding="utf-8")
    for bad in ("subprocess", "fcntl", "SIGALRM", "/proc", "systemctl", "claude -p", "ANTHROPIC_API_KEY"):
        assert bad not in src, bad
    assert "anthropic" not in src.lower()


def test_telemetry_row_only_on_failure(box, monkeypatch):
    run(payload(cwd=box["repo"]))
    tel = box["tmp"] / "tel"
    assert list(tel.glob("hook-fires-*.jsonl")) == []

    def boom(*a, **k):
        raise OSError("disk")
    monkeypatch.setattr(ol, "_append", boom)
    assert run(payload(cwd=box["repo"])) == "{}\n"
    recs = [json.loads(ln) for f in tel.glob("hook-fires-*.jsonl") for ln in f.read_text(encoding="utf-8").splitlines()]
    assert [(r["link_id"], r["kind"]) for r in recs] == [("observe-log", "write_failed")]
