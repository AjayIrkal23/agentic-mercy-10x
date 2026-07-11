"""Guard-rail tests for hooks/index-lifecycle.py (P3-T7).

Encodes the structural guarantees of the active-repo, zero-daemon index
lifecycle so they are regression-proof (Spec B §3, Charter §7):

  * active repo ONLY — a write outside the active repo is never journaled;
    a non-git cwd is a total no-op.
  * debounced flush — at N writes or T seconds, exactly ONE detached worker.
  * locks — PID-liveness + TTL; a crashed worker's lock is broken after TTL;
    two sessions never double-spawn.
  * build worker — refuses a mismatched repo key; ≤3 failures → FAILED backoff
    with no retry until the fingerprint changes.
  * probes — a timeout/exception fails OPEN (assume FRESH, never brick).
  * SessionStart parity (P3-T5) — for every surface × {FRESH, STALE, MISSING}
    the session-start blob still VISIBLY reports the state (equivalent-or-richer
    than the retired guards; the build is auto-spawned instead of demanded).
  * CI grep-gate — no live hook .py contains glob("/DATA…), a /DATA/CODE_FILES
    root list, or systemctl/systemd-escape (zero daemons, no cross-repo sweeps).

Pure stdlib + pytest. Builders and detached spawns are stubbed so no real
indexer runs. Runnable via `pytest hooks/tests/` or directly:
`python3 hooks/tests/test_index_lifecycle.py`.
"""
from __future__ import annotations

import importlib.util
import io
import json
import contextlib
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "index_lifecycle_under_test", _HOOKS / "index-lifecycle.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


il = _load()


def _mkrepo(where: Path) -> Path:
    where.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(where)], check=True)
    subprocess.run(["git", "-C", str(where), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(where), "config", "user.name", "t"], check=True)
    (where / "a.txt").write_text("hi")
    subprocess.run(["git", "-C", str(where), "add", "."], check=True)
    subprocess.run(["git", "-C", str(where), "commit", "-qm", "init"], check=True)
    return where


def _silent(fn, *a):
    with contextlib.redirect_stdout(io.StringIO()) as buf:
        fn(*a)
    return buf.getvalue()


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolated STATE_DIR + stubbed builders/spawns + a committed temp repo."""
    state = tmp_path / "state" / "index"
    state.mkdir(parents=True)
    monkeypatch.setattr(il, "STATE_DIR", state)
    spawns: list = []
    monkeypatch.setattr(
        il, "_spawn_build",
        lambda ctx, surfaces, incremental=False, journal_file=None:
        spawns.append((sorted(surfaces), incremental)))
    for k in list(il._BUILD):
        monkeypatch.setitem(il._BUILD, k, lambda *a, **k: True)
    repo = _mkrepo(tmp_path / "repo")
    payload = {"workspace_roots": [str(repo)], "cwd": str(repo)}
    ctx = il._active_ctx(payload)
    cfg = il._load_config()
    return {"repo": repo, "payload": payload, "ctx": ctx, "cfg": cfg,
            "spawns": spawns, "tmp": tmp_path}


def _reset(env):
    ctx = env["ctx"]
    for s in il.SURFACES:
        il._release_lock(ctx.key, s)
    st = il._load_state(ctx)
    st["surfaces"] = {}
    st["journal"] = {"first_write_at": None, "entries": []}
    il._save_state(ctx, st)
    env["spawns"].clear()


# --------------------------------------------------------------------------- #
# active-repo containment
# --------------------------------------------------------------------------- #
def test_non_git_cwd_is_total_noop(env, tmp_path, monkeypatch):
    nongit = tmp_path / "nogit"
    nongit.mkdir()
    monkeypatch.chdir(nongit)
    out = _silent(il.mode_session_start, {}, env["cfg"])
    assert not env["spawns"]  # nothing spawned
    # post-write / flush / tick / session-end all no-op too
    for mode in (il.mode_post_write, il.mode_flush, il.mode_tick, il.mode_session_end):
        assert _silent(mode, {}, env["cfg"]).strip() == "{}"


def test_cross_repo_write_is_ignored(env, tmp_path):
    _reset(env)
    other = _mkrepo(tmp_path / "other")
    pw = {"tool_name": "Write", "cwd": str(env["repo"]),
          "tool_input": {"file_path": str(other / "x.py")}}
    _silent(il.mode_post_write, pw, env["cfg"])
    st = il._load_state(env["ctx"])
    assert st["journal"]["entries"] == []


# --------------------------------------------------------------------------- #
# debounced flush
# --------------------------------------------------------------------------- #
def test_flush_at_n_writes(env):
    _reset(env)
    repo, cfg = env["repo"], env["cfg"]
    for i in range(5):
        (repo / f"f{i}.py").write_text("x")
        _silent(il.mode_post_write,
                {"tool_name": "Write", "cwd": str(repo),
                 "tool_input": {"file_path": str(repo / f"f{i}.py")}}, cfg)
    assert len(env["spawns"]) == 1
    surfaces, incremental = env["spawns"][0]
    assert incremental is True
    assert il._load_state(env["ctx"])["journal"]["entries"] == []  # truncated


def test_flush_at_t_seconds(env):
    _reset(env)
    repo, cfg, ctx = env["repo"], env["cfg"], env["ctx"]
    (repo / "z.py").write_text("x")
    st = il._load_state(ctx)
    st["journal"] = {"first_write_at": time.time() - 100,
                     "entries": [{"path": str(repo / "z.py"), "tool": "Edit", "ts": 0}]}
    il._save_state(ctx, st)
    _silent(il.mode_post_write,
            {"tool_name": "Edit", "cwd": str(repo),
             "tool_input": {"file_path": str(repo / "z.py")}}, cfg)
    assert len(env["spawns"]) == 1


def test_tick_flushes_at_t(env):
    _reset(env)
    repo, cfg, ctx = env["repo"], env["cfg"], env["ctx"]
    st = il._load_state(ctx)
    st["journal"] = {"first_write_at": time.time() - 100,
                     "entries": [{"path": str(repo / "a.txt"), "tool": "Edit", "ts": 0}]}
    il._save_state(ctx, st)
    _silent(il.mode_tick, {"cwd": str(repo)}, cfg)
    assert len(env["spawns"]) == 1


def test_session_end_drains(env):
    _reset(env)
    repo, cfg, ctx = env["repo"], env["cfg"], env["ctx"]
    st = il._load_state(ctx)
    st["journal"] = {"first_write_at": time.time(),
                     "entries": [{"path": str(repo / "a.txt"), "tool": "Edit", "ts": 0}]}
    il._save_state(ctx, st)
    _silent(il.mode_session_end, {"cwd": str(repo)}, cfg)
    assert len(env["spawns"]) == 1


# --------------------------------------------------------------------------- #
# locks
# --------------------------------------------------------------------------- #
def test_lock_live_for_own_pid(env):
    ctx = env["ctx"]
    il._rewrite_lock(ctx.key, "graphify", "t")
    assert il._lock_is_live(ctx.key, "graphify", 30) is True
    il._release_lock(ctx.key, "graphify")


def test_lock_ttl_break_on_dead_old_pid(env):
    ctx = env["ctx"]
    lp = il._lock_path(ctx.key, "graphify")
    lp.parent.mkdir(parents=True, exist_ok=True)
    lp.write_text(json.dumps({"pid": 2_147_480_000, "started_at": time.time() - 3600,
                              "cmd": "x"}))
    assert il._lock_is_live(ctx.key, "graphify", 30) is False
    assert not lp.exists()  # broken


def test_dead_pid_within_ttl_kept(env):
    # a freshly-spawned worker's lock (dead placeholder pid, recent) is NOT broken
    ctx = env["ctx"]
    lp = il._lock_path(ctx.key, "graphify")
    lp.parent.mkdir(parents=True, exist_ok=True)
    lp.write_text(json.dumps({"pid": 2_147_480_000, "started_at": time.time(),
                              "cmd": "x"}))
    assert il._lock_is_live(ctx.key, "graphify", 30) is True
    il._release_lock(ctx.key, "graphify")


def test_two_sessions_no_double_spawn(env):
    _reset(env)
    _silent(il.mode_session_start, env["payload"], env["cfg"])
    first = len(env["spawns"])
    env["spawns"].clear()
    _silent(il.mode_session_start, env["payload"], env["cfg"])
    second = len(env["spawns"])
    assert first == 1 and second == 0


# --------------------------------------------------------------------------- #
# build worker
# --------------------------------------------------------------------------- #
def test_build_refuses_mismatched_key(env):
    class A:
        pass
    a = A()
    a.root, a.key = str(env["repo"]), "WRONG-deadbeef"
    a.surfaces, a.incremental, a.journal = "graphify", False, ""
    assert il.mode_build(a, env["cfg"]) == 0
    # no state written under the wrong key
    assert not il._state_path("WRONG-deadbeef").exists()


def test_build_success_marks_fresh(env):
    _reset(env)
    ctx = env["ctx"]

    class A:
        pass
    a = A()
    a.root, a.key = str(env["repo"]), ctx.key
    a.surfaces, a.incremental, a.journal = "graphify", False, ""
    il.mode_build(a, env["cfg"])
    assert il._load_state(ctx)["surfaces"]["graphify"]["state"] == il.FRESH


def test_build_failure_backoff(env, monkeypatch):
    _reset(env)
    ctx = env["ctx"]
    monkeypatch.setitem(il._BUILD, "graphify", lambda *a, **k: False)

    class A:
        pass
    a = A()
    a.root, a.key = str(env["repo"]), ctx.key
    a.surfaces, a.incremental, a.journal = "graphify", False, ""
    st = il._load_state(ctx)
    st["surfaces"]["graphify"] = {"state": "STALE", "failures": 0, "fingerprint": {}}
    il._save_state(ctx, st)
    for _ in range(3):
        il._release_lock(ctx.key, "graphify")
        il.mode_build(a, env["cfg"])
    g = il._load_state(ctx)["surfaces"]["graphify"]
    assert g["state"] == il.FAILED and g["failures"] >= 3


def test_failed_backoff_no_rebuild_until_fingerprint_change(env, monkeypatch):
    """A FAILED surface with an unchanged fingerprint is NOT rebuilt at start."""
    _reset(env)
    ctx = env["ctx"]
    # Force the probe to a fixed STALE fingerprint that matches the FAILED state.
    fp = {"git_head": "abc", "dirty_sha": "def"}
    monkeypatch.setitem(il._PROBE, "graphify",
                        lambda root, prior, cfg: (il.STALE, fp, "stale"))
    for s in ("jcodemunch", "jdocmunch", "dox"):
        monkeypatch.setitem(il._PROBE, s, lambda root, prior, cfg: (il.FRESH, {}, ""))
    st = il._load_state(ctx)
    st["surfaces"]["graphify"] = {"state": il.FAILED, "failures": 3, "fingerprint": fp}
    il._save_state(ctx, st)
    _silent(il.mode_session_start, env["payload"], env["cfg"])
    # graphify stays FAILED, no build spawned for it (backoff honoured)
    assert il._load_state(ctx)["surfaces"]["graphify"]["state"] == il.FAILED
    assert env["spawns"] == []  # nothing to build (others FRESH, graphify backed off)


# --------------------------------------------------------------------------- #
# probes fail open
# --------------------------------------------------------------------------- #
def test_probe_exception_fails_open_fresh(env, monkeypatch):
    def boom(root, prior, cfg):
        raise RuntimeError("probe blew up")
    monkeypatch.setitem(il._PROBE, "graphify", boom)
    res = il._probe_all(env["ctx"], il._load_state(env["ctx"]), env["cfg"])
    assert res["graphify"][0] == il.FRESH  # fail-open


# --------------------------------------------------------------------------- #
# SessionStart guard-parity matrix (P3-T5): surface × {FRESH, STALE, MISSING}
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("surface", list(il.SURFACES))
@pytest.mark.parametrize("state", [il.FRESH, il.STALE, il.MISSING])
def test_session_start_parity_reports_state(env, monkeypatch, surface, state):
    _reset(env)
    # all surfaces FRESH except the one under test at the target state
    for s in il.SURFACES:
        monkeypatch.setitem(il._PROBE, s, lambda root, prior, cfg: (il.FRESH, {}, ""))
    monkeypatch.setitem(il._PROBE, surface,
                        lambda root, prior, cfg: (state, {}, "detail"))
    out = _silent(il.mode_session_start, env["payload"], env["cfg"])
    blob = json.loads(out or "{}").get("additionalContext", "")
    # the surface is named and its state is VISIBLY reported
    assert surface in blob
    if state == il.FRESH:
        assert "FRESH" in blob
    else:
        assert state in blob  # MISSING / STALE surfaced (build auto-spawned)


# --------------------------------------------------------------------------- #
# CI grep-gate — zero daemons, no cross-repo sweeps in live hook .py
# --------------------------------------------------------------------------- #
def _live_hook_py() -> list[Path]:
    files = list(_HOOKS.glob("*.py")) + list((_HOOKS / "lib").glob("*.py"))
    return [p for p in files if "__pycache__" not in p.parts]


def test_grep_gate_no_daemon_or_datapath_patterns():
    forbidden = ['systemctl', 'systemd-escape', 'glob("/DATA', '/DATA/CODE_FILES']
    offenders = []
    for p in _live_hook_py():
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pat in forbidden:
            if pat in text:
                offenders.append(f"{p.name}: {pat}")
    assert not offenders, f"forbidden daemon/cross-repo patterns present: {offenders}"


def test_index_lifecycle_has_no_path_list_iteration():
    text = (_HOOKS / "index-lifecycle.py").read_text(encoding="utf-8")
    assert "project_roots" not in text
    # config carries no path field
    cfg_text = (_HOOKS / "index-lifecycle.config.json").read_text(encoding="utf-8")
    cfg = json.loads(cfg_text)

    def _no_paths(obj):
        if isinstance(obj, str):
            assert "/DATA" not in obj and "project_roots" not in obj
        elif isinstance(obj, dict):
            for k, v in obj.items():
                assert "root" not in k.lower() or k == "_note"
                _no_paths(v)
        elif isinstance(obj, list):
            for v in obj:
                _no_paths(v)
    _no_paths(cfg)


def _run_all() -> None:
    """Direct-run harness (no pytest): exercises the non-parametrized checks."""
    import tempfile as _tf

    class _MP:
        def __init__(self):
            self._undo = []

        def setattr(self, obj, name, val):
            old = getattr(obj, name)
            self._undo.append(lambda: setattr(obj, name, old))
            setattr(obj, name, val)

        def setitem(self, obj, key, val):
            old = obj[key]
            self._undo.append(lambda: obj.__setitem__(key, old))
            obj[key] = val

        def chdir(self, d):
            cwd = os.getcwd()
            self._undo.append(lambda: os.chdir(cwd))
            os.chdir(d)

        def undo(self):
            for fn in reversed(self._undo):
                fn()

    passed = 0
    for name, fn in sorted(globals().items()):
        if not (name.startswith("test_") and callable(fn)):
            continue
        # skip pytest-parametrized tests in the direct harness
        if getattr(fn, "pytestmark", None):
            continue
        tmp = Path(_tf.mkdtemp())
        mp = _MP()
        state = tmp / "state" / "index"
        state.mkdir(parents=True)
        mp.setattr(il, "STATE_DIR", state)
        spawns: list = []
        mp.setattr(il, "_spawn_build",
                   lambda ctx, surfaces, incremental=False, journal_file=None:
                   spawns.append((sorted(surfaces), incremental)))
        for k in list(il._BUILD):
            mp.setitem(il._BUILD, k, lambda *a, **k: True)
        repo = _mkrepo(tmp / "repo")
        payload = {"workspace_roots": [str(repo)], "cwd": str(repo)}
        e = {"repo": repo, "payload": payload, "ctx": il._active_ctx(payload),
             "cfg": il._load_config(), "spawns": spawns, "tmp": tmp}
        try:
            import inspect
            params = inspect.signature(fn).parameters
            args = []
            for pn in params:
                if pn == "env":
                    args.append(e)
                elif pn == "tmp_path":
                    args.append(tmp)
                elif pn == "monkeypatch":
                    args.append(mp)
            fn(*args)
            passed += 1
        finally:
            mp.undo()
    print(f"test_index_lifecycle: {passed} non-parametrized tests PASSED")


if __name__ == "__main__":
    _run_all()
