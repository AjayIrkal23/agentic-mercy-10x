"""A4v2-04: the per-repo index state is a locked read-modify-write.

Two sessions on one repo (or parallel subagents) used to lose journal entries (last writer wins), and a
reader `PermissionError` returned the blank default which the next save then persisted, wiping `surfaces`
and the journal. The 4-process test is A4's experiment, on any OS.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from test_index_lifecycle import _mkrepo, _silent, il

HOOKS = Path(__file__).resolve().parents[1]
MARKER = {"state": "FRESH", "failures": 0, "built_at": 123}

CHILD = r"""
import contextlib, importlib.util, io, os, sys
hooks, repo, tag, n = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
spec = importlib.util.spec_from_file_location("il", os.path.join(hooks, "index-lifecycle.py"))
il = importlib.util.module_from_spec(spec)
spec.loader.exec_module(il)
cfg = il._load_config()
cfg["debounce"] = {"writes_threshold": 10 ** 6, "seconds_threshold": 10 ** 6}  # never flush: count the journal
for i in range(n):
    payload = {"tool_name": "Write", "cwd": repo,
               "tool_input": {"file_path": os.path.join(repo, "f_%s_%d.py" % (tag, i))}}
    with contextlib.redirect_stdout(io.StringIO()):
        il.mode_post_write(payload, cfg)
"""


def _state_file(dot: Path, ctx) -> Path:
    return dot / "index" / f"{ctx.key}.json"


def _seed(path: Path, ctx, entries=()) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "repo_root": ctx.root, "repo_key": ctx.key, "surfaces": {"marker": MARKER},
        "journal": {"first_write_at": time.time(), "entries": list(entries)}}), encoding="utf-8")


def test_four_processes_keep_every_journal_entry_and_the_surfaces(tmp_path):
    procs, cycles = 4, 60
    repo = _mkrepo(tmp_path / "repo")
    ctx = il._active_ctx({"cwd": str(repo)})
    dot = tmp_path / "dot"
    _seed(_state_file(dot, ctx), ctx)
    env = {**os.environ, "CLAUDE_HOOK_DOTSTATE_DIR": str(dot), "CLAUDE_HOOK_STATE_DIR": str(tmp_path / "st"),
           "CLAUDE_HOOK_TELEMETRY_DIR": str(tmp_path / "tel"), "PYTHONUTF8": "1"}
    script = tmp_path / "child.py"
    script.write_text(CHILD, encoding="utf-8")
    running = [subprocess.Popen([sys.executable, str(script), str(HOOKS), str(repo), f"p{k}", str(cycles)],
                                env=env, stderr=subprocess.PIPE) for k in range(procs)]
    errs = [p.communicate(timeout=240)[1].decode("utf-8", "replace") for p in running]
    assert [p.returncode for p in running] == [0] * procs, errs
    final = json.loads(_state_file(dot, ctx).read_text(encoding="utf-8"))
    paths = {e["path"] for e in final["journal"]["entries"]}
    assert len(final["journal"]["entries"]) == procs * cycles == len(paths)
    assert final["surfaces"]["marker"] == MARKER


@pytest.fixture
def one(tmp_path, monkeypatch):
    state = tmp_path / "state" / "index"
    state.mkdir(parents=True)
    monkeypatch.setattr(il, "STATE_DIR", state)
    monkeypatch.setattr(il, "_sleep", lambda s: None)
    repo = _mkrepo(tmp_path / "repo")
    ctx = il._active_ctx({"cwd": str(repo)})
    _seed(il._state_path(ctx.key), ctx, [{"path": str(repo / f"old{i}.py"), "tool": "Write", "ts": 1.0}
                                          for i in range(3)])
    return {"repo": repo, "ctx": ctx, "cfg": il._load_config(), "file": il._state_path(ctx.key)}


def _denied_reads(monkeypatch, target: Path, times: int):
    """`Path.read_text` of `target` raises PermissionError the first `times` calls (a writer's replace in flight)."""
    real, calls = Path.read_text, [0]

    def read_text(self, *a, **k):
        if self.name == target.name:
            calls[0] += 1
            if calls[0] <= times:
                raise PermissionError(13, "Access is denied")
        return real(self, *a, **k)
    monkeypatch.setattr(Path, "read_text", read_text)
    return calls


def test_a_reader_permission_error_is_retried_not_turned_into_a_blank_state(one, monkeypatch):
    calls = _denied_reads(monkeypatch, one["file"], 2)
    state = il._load_state(one["ctx"])
    assert state["surfaces"]["marker"] == MARKER and len(state["journal"]["entries"]) == 3
    assert calls[0] == 3 and not state.get("_unreadable")


def test_an_unreadable_state_is_never_overwritten_by_a_post_write(one, monkeypatch):
    before = one["file"].read_text(encoding="utf-8")
    _denied_reads(monkeypatch, one["file"], 10 ** 6)
    payload = {"tool_name": "Write", "cwd": str(one["repo"]),
               "tool_input": {"file_path": str(one["repo"] / "new.py")}}
    assert _silent(il.mode_post_write, payload, one["cfg"]).strip() == "{}"
    monkeypatch.undo()
    assert json.loads(one["file"].read_text(encoding="utf-8")) == json.loads(before)


def test_persisting_probe_results_keeps_the_journal_of_a_concurrent_writer(one):
    """A session-start / build worker saves only the surfaces it computed; the journal it loaded earlier
    (and entries written since) are not its to replace."""
    ctx = one["ctx"]
    stale = il._load_state(ctx)  # what a slow probe holds
    stale["surfaces"]["graphify"] = {"state": "FRESH", "failures": 0}
    payload = {"tool_name": "Write", "cwd": str(one["repo"]),
               "tool_input": {"file_path": str(one["repo"] / "later.py")}}
    _silent(il.mode_post_write, payload, one["cfg"])  # lands after the probe loaded its copy
    il._save_surfaces(ctx, stale, ["graphify"])
    final = il._load_state(ctx)
    assert final["surfaces"]["graphify"]["state"] == "FRESH" and final["surfaces"]["marker"] == MARKER
    assert [Path(e["path"]).name for e in final["journal"]["entries"]] == ["old0.py", "old1.py", "old2.py", "later.py"]


def test_a_flush_drops_only_what_it_flushed_inside_the_lock(one, monkeypatch):
    spawned: list = []
    monkeypatch.setattr(il, "_spawn_build", lambda ctx, s, incremental=False, journal_file=None:
                        spawned.append(sorted(s)))
    for i in range(3):
        (one["repo"] / f"old{i}.py").write_text("x", encoding="utf-8")
    cfg = {**one["cfg"], "debounce": {"writes_threshold": 3, "seconds_threshold": 10 ** 6}}
    payload = {"tool_name": "Write", "cwd": str(one["repo"]),
               "tool_input": {"file_path": str(one["repo"] / "old0.py")}}
    _silent(il.mode_post_write, payload, cfg)  # 4 entries >= 3: flush
    assert len(spawned) == 1
    assert il._load_state(one["ctx"])["journal"]["entries"] == []
    assert il._load_state(one["ctx"])["surfaces"]["marker"] == MARKER
    with contextlib.redirect_stdout(io.StringIO()):
        il.mode_flush({"cwd": str(one["repo"])}, cfg)  # nothing left: no second worker
    assert len(spawned) == 1
