"""WP-B (autonomy 2026-10-05): builder observability + ollama-down self-wait.

  * `build_fail` telemetry carries the last ~400 chars of the builder's stderr, scrubbed.
  * The DETACHED jcodemunch builder waits (backoff, <= 90 s) for the summarizer instead of
    asking anyone to start ollama; still down -> a MISSING index builds without AI
    summaries, an existing index is left alone (deferred, never overwritten).
  * Session start never prints "ACTION NEEDED"; the model gets one neutral line.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("il_wpb_builders", _HOOKS / "index-lifecycle.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


il = _load()
NEUTRAL = "summarizer unavailable; index refresh deferred, retrying automatically"


def _mkrepo(where: Path) -> Path:
    where.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(where)], check=True)
    subprocess.run(["git", "-C", str(where), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(where), "config", "user.name", "t"], check=True)
    (where / "a.txt").write_text("hi")
    subprocess.run(["git", "-C", str(where), "add", "."], check=True)
    subprocess.run(["git", "-C", str(where), "commit", "-qm", "init"], check=True)
    return where


@pytest.fixture
def env(tmp_path, monkeypatch):
    state = tmp_path / "state" / "index"
    state.mkdir(parents=True)
    monkeypatch.setattr(il, "STATE_DIR", state)
    monkeypatch.setattr(il, "_which", lambda name: True)
    monkeypatch.setattr(il, "_sleep", lambda s: sleeps.append(s))
    sleeps: list = []
    rows: list = []
    monkeypatch.setattr(il, "_telem", lambda kind, **f: rows.append((kind, f)))
    repo = _mkrepo(tmp_path / "repo")
    ctx = il._active_ctx({"cwd": str(repo)})
    return {"repo": repo, "ctx": ctx, "cfg": il._load_config(), "sleeps": sleeps,
            "rows": rows, "tmp": tmp_path}


def _runs(monkeypatch, rc=0, stderr="", stdout=""):
    calls: list = []

    def fake(cmd, timeout, env=None):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, rc, stdout, stderr)
    monkeypatch.setattr(il, "_run", fake)
    return calls


# --------------------------------------------------------------------------- #
# build_fail carries the stderr tail
# --------------------------------------------------------------------------- #
class _A:
    incremental = False
    journal = ""


def _fail_build(env, monkeypatch, surface, stderr, rc=1):
    _runs(monkeypatch, rc=rc, stderr=stderr)
    monkeypatch.setattr(il, "_summarizer_alive", lambda *a, **k: True)
    a = _A()
    a.root, a.key, a.surfaces = str(env["repo"]), env["ctx"].key, surface
    il.mode_build(a, env["cfg"])
    return [f for k, f in env["rows"] if k == "build_fail"]


def test_build_fail_row_has_last_400_chars_of_stderr(env, monkeypatch):
    err = "x" * 1000 + "THE-REAL-CAUSE: disk full"
    (row,) = _fail_build(env, monkeypatch, "graphify", err)
    assert row["surface"] == "graphify" and row["failures"] == 1
    assert row["err"].endswith("THE-REAL-CAUSE: disk full") and len(row["err"]) <= 400


@pytest.mark.parametrize("secret", ["sk-abcdef1234567890XYZ", "ghp_abcdef1234567890ABCDEF"])
def test_build_fail_err_never_carries_secrets(env, monkeypatch, secret):
    err = (f"boom\nOPENAI_API_KEY={secret}\nAuthorization: Bearer {secret}\n"
           f"token: {secret}\nlast line")
    (row,) = _fail_build(env, monkeypatch, "graphify", err)
    assert secret not in row["err"] and "last line" in row["err"]


# SANTA-autonomy: shapes that survived the first scrub (fixtures concatenated so they never
# look live in this file)
_SURVIVORS = [
    ('{"api_key": "' + "s3cr3tvalue" + '"}', "s3cr3tvalue"),
    ('"Authorization": "Bearer ' + "eyJhbGciOiJIUzI1NiJ9" + ".eyJzdWIiOiIxIn0.sig" + '"', "eyJzdWIiOiIxIn0"),
    ("clone https://" + "alice:hunter2" + "@git.example.com/r.git", "hunter2"),
    ("key " + "AKIA" + "ABCDEFGHIJKLMNOP" + " used", "AKIA" + "ABCDEFGHIJKLMNOP"),
    ("google " + "AIza" + "SyA1234567890abcdefghijklmnopqrstu", "AIza" + "SyA1234567890abcdefghijklmnopqrstu"),
    ("hf " + "hf_" + "abcdefghijklmnopqrstuvwxyz12", "hf_" + "abcdefghijklmnopqrstuvwxyz12"),
]


@pytest.mark.parametrize(("line", "secret"), _SURVIVORS)
def test_build_fail_err_scrubs_quoted_url_and_vendor_keys(env, monkeypatch, line, secret):
    (row,) = _fail_build(env, monkeypatch, "graphify", f"boom\n{line}\nlast line")
    assert secret not in row["err"] and "last line" in row["err"]


def test_build_fail_err_marks_a_timeout(env, monkeypatch):
    (row,) = _fail_build(env, monkeypatch, "graphify", "", rc=124)
    assert "timeout" in row["err"].lower()


def test_build_fail_err_falls_back_to_stdout_tail(env, monkeypatch):
    _runs(monkeypatch, rc=1, stderr="", stdout='{"success": false, "error": "no index"}')
    monkeypatch.setattr(il, "_summarizer_alive", lambda *a, **k: True)
    a = _A()
    a.root, a.key, a.surfaces = str(env["repo"]), env["ctx"].key, "graphify"
    il.mode_build(a, env["cfg"])
    (row,) = [f for k, f in env["rows"] if k == "build_fail"]
    assert "no index" in row["err"]


def test_stale_error_text_does_not_leak_into_the_next_failure(env, monkeypatch):
    il._LAST_ERR[0] = "old failure"
    monkeypatch.setattr(il, "_build_dox", lambda *a, **k: False)
    monkeypatch.setitem(il._BUILD, "dox", il._build_dox)
    a = _A()
    a.root, a.key, a.surfaces = str(env["repo"]), env["ctx"].key, "dox"
    il.mode_build(a, env["cfg"])
    (row,) = [f for k, f in env["rows"] if k == "build_fail"]
    assert "old failure" not in row.get("err", "")


# --------------------------------------------------------------------------- #
# ollama down: the detached builder waits, then degrades safely
# --------------------------------------------------------------------------- #
def _alive_after(monkeypatch, n):
    seen = {"n": 0}

    def alive(*a, **k):
        seen["n"] += 1
        return seen["n"] > n
    monkeypatch.setattr(il, "_summarizer_alive", alive)


def test_builder_waits_for_the_summarizer_then_builds_with_summaries(env, monkeypatch):
    calls = _runs(monkeypatch)
    _alive_after(monkeypatch, 3)
    assert il._build_jcodemunch(env["repo"], False, [], env["cfg"]) is True
    assert len(env["sleeps"]) == 3 and env["sleeps"] == sorted(env["sleeps"])  # backoff grows
    assert calls and "--no-ai-summaries" not in calls[0]


def test_wait_is_capped_at_ninety_seconds_in_total(env, monkeypatch):
    _runs(monkeypatch)
    monkeypatch.setattr(il, "_summarizer_alive", lambda *a, **k: False)
    monkeypatch.setattr(il, "_index_db_for", lambda root: Path("x.db"))
    il._build_jcodemunch(env["repo"], False, [], env["cfg"])
    assert 60 <= sum(env["sleeps"]) <= 90


def test_still_down_and_index_missing_builds_without_ai_summaries(env, monkeypatch):
    calls = _runs(monkeypatch)
    monkeypatch.setattr(il, "_summarizer_alive", lambda *a, **k: False)
    monkeypatch.setattr(il, "_index_db_for", lambda root: None)
    assert il._build_jcodemunch(env["repo"], False, [], env["cfg"]) is True
    assert calls[0][:3] == ["jcodemunch-mcp", "index", "--no-ai-summaries"]


def test_still_down_and_index_exists_defers_and_runs_nothing(env, monkeypatch):
    calls = _runs(monkeypatch)
    monkeypatch.setattr(il, "_summarizer_alive", lambda *a, **k: False)
    monkeypatch.setattr(il, "_index_db_for", lambda root: Path("x.db"))
    assert il._build_jcodemunch(env["repo"], False, [], env["cfg"]) == "DEFERRED"
    assert calls == []


def test_incremental_flush_never_builds_without_summaries(env, monkeypatch):
    calls = _runs(monkeypatch)
    monkeypatch.setattr(il, "_summarizer_alive", lambda *a, **k: False)
    monkeypatch.setattr(il, "_index_db_for", lambda root: None)
    assert il._build_jcodemunch(env["repo"], True, [str(env["repo"] / "a.py")],
                                env["cfg"]) == "DEFERRED"
    assert calls == []


def test_deferred_build_forces_the_next_probe_stale(env, monkeypatch):
    """A deferral must not let the dirty-tree fingerprint count as indexed."""
    ctx = env["ctx"]
    st = il._load_state(ctx)
    st["surfaces"]["jcodemunch"] = {"state": il.STALE, "failures": 0,
                                    "fingerprint": {"git_head": "H", "dirty_sha": "D0"}}
    il._save_state(ctx, st)
    monkeypatch.setitem(il._BUILD, "jcodemunch", lambda *a, **k: "DEFERRED")
    a = _A()
    a.root, a.key, a.surfaces = str(env["repo"]), ctx.key, "jcodemunch"
    il.mode_build(a, env["cfg"])
    prior = il._load_state(ctx)["surfaces"]["jcodemunch"]
    monkeypatch.setattr(il, "_index_db_for", lambda root: Path("x.db"))
    monkeypatch.setattr(il, "_db_meta", lambda db, key: il._git(env["repo"], ["rev-parse", "HEAD"])
                        .stdout.strip())
    monkeypatch.setattr(il, "_dirty_sha", lambda root: "D0")
    assert il._probe_jcodemunch(env["repo"], prior)[0] == il.STALE


def test_session_start_never_asks_for_ollama_and_spawns_the_builder(env, monkeypatch, capsys):
    spawns: list = []
    monkeypatch.setattr(il, "_spawn_build",
                        lambda ctx, surfaces, incremental=False, journal_file=None:
                        spawns.append(sorted(surfaces)))
    monkeypatch.setattr(il, "_summarizer_alive", lambda *a, **k: False)
    for s in il.SURFACES:
        monkeypatch.setitem(il._PROBE, s, lambda root, prior, cfg: (il.FRESH, {}, ""))
    monkeypatch.setitem(il._PROBE, "jcodemunch", lambda root, prior, cfg: (il.STALE, {}, "d"))
    payload = {"cwd": str(env["repo"]), "workspace_roots": [str(env["repo"])]}
    il.mode_session_start(payload, env["cfg"])
    blob = json.loads(capsys.readouterr().out)["additionalContext"]
    assert "ACTION NEEDED" not in blob and "Start ollama" not in blob
    assert blob.count(NEUTRAL) == 1
    assert spawns == [["jcodemunch"]]  # the detached builder does the waiting


# --------------------------------------------------------------------------- #
# config invariants
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("cfg_src", ["file", "default"])
def test_graphify_cap_is_300_and_lock_ttl_outlives_every_build(cfg_src):
    cfg = il._load_config() if cfg_src == "file" else il._DEFAULT_CONFIG
    caps = cfg["build_timeouts_s"]
    assert caps["graphify"] == 300
    wait = (cfg.get("summarizer_healthcheck") or {}).get("wait_s", 90)
    assert cfg["lock_ttl_minutes"] * 60 > max(caps.values()) + wait
