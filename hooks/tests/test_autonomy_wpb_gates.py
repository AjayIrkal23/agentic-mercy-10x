"""WP-B (autonomy 2026-10-05): gate / advisory / launcher texts never demand a manual step.

  * jcodemunch-enforce Gate 2 (index missing): spawn the lifecycle build, say it is
    building in the background, fail open on the FIRST block.
  * graphify-enforce stale advisory: trigger the rebuild, say it rebuilds in the background.
  * graphify_launcher missing/foreign graph: spawn the lifecycle build, log only.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, _HOOKS / fname)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _mkrepo(where: Path) -> Path:
    where.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(where)], check=True)
    subprocess.run(["git", "-C", str(where), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(where), "config", "user.name", "t"], check=True)
    (where / "a.txt").write_text("hi")
    subprocess.run(["git", "-C", str(where), "add", "."], check=True)
    subprocess.run(["git", "-C", str(where), "commit", "-qm", "init"], check=True)
    return where


# --------------------------------------------------------------------------- #
# jcodemunch-enforce Gate 2
# --------------------------------------------------------------------------- #
class _FakeLifecycle:
    def __init__(self, building=False, jcm_state="BUILDING"):
        self.building, self.jcm_state, self.reprobed = building, jcm_state, []

    def is_building(self, payload=None):
        return self.building

    def reprobe(self, root, cfg=None):
        self.reprobed.append(root)
        return {"surfaces": {"jcodemunch": self.jcm_state}, "spawned": ["jcodemunch"]}


@pytest.fixture
def gate(tmp_path, monkeypatch):
    jcm = _load("jcm_wpb", "jcodemunch-enforce.py")
    repo = _mkrepo(tmp_path / "repo")
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("x = 1\n" * 80)
    monkeypatch.setattr(jcm, "STATE_DIR", tmp_path / "gstate")
    monkeypatch.setattr(jcm, "INDEX_DIR", tmp_path / "no-index")
    monkeypatch.setattr(jcm, "_is_exempt", lambda t, c: False)  # /tmp/ is an exempt path
    fake = _FakeLifecycle()
    monkeypatch.setattr(jcm, "_lifecycle", lambda: fake)

    def fire(sid="s1", fake_override=None):
        if fake_override is not None:
            monkeypatch.setattr(jcm, "_lifecycle", lambda: fake_override)
        payload = {"tool_name": "Read", "session_id": sid, "cwd": str(repo),
                   "workspace_roots": [str(repo)],
                   "tool_input": {"file_path": str(repo / "src" / "app.py")}}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        buf = io.StringIO()
        monkeypatch.setattr(sys, "stdout", buf)
        jcm.pre_tool_use()
        out = buf.getvalue().strip()
        return json.loads(out) if out else {}
    return {"fire": fire, "fake": fake, "repo": repo, "jcm": jcm}


def test_missing_index_spawns_build_and_fails_open_on_the_first_read(gate):
    out = gate["fire"]()
    assert "permissionDecision" not in out  # NOT blocked, first time
    text = out.get("additionalContext", "")
    assert "building in the background" in text and "Read" in text
    assert "index_folder" not in text
    assert gate["fake"].reprobed == [str(gate["repo"].resolve())]


def test_missing_index_with_build_already_running_stays_silent(gate):
    out = gate["fire"](fake_override=_FakeLifecycle(building=True))
    assert out == {}


def test_missing_index_that_cannot_be_spawned_keeps_the_old_budgeted_block(gate):
    out = gate["fire"](fake_override=_FakeLifecycle(jcm_state="FAILED"))
    assert out.get("permissionDecision") == "deny"


def test_lifecycle_sees_a_fresh_index_so_the_read_is_allowed_silently(gate):
    out = gate["fire"](fake_override=_FakeLifecycle(jcm_state="FRESH"))
    assert out == {}  # naming mismatch with the gate's own check: never demand index_folder


def test_foreign_repo_read_is_not_spawned(gate, tmp_path, monkeypatch):
    other = tmp_path / "elsewhere"
    other.mkdir()
    payload = {"tool_name": "Read", "session_id": "s9", "cwd": str(other),
               "workspace_roots": [str(other)],
               "tool_input": {"file_path": str(gate["repo"] / "src" / "app.py")}}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    gate["jcm"].pre_tool_use()
    assert gate["fake"].reprobed == []  # active repo only


# --------------------------------------------------------------------------- #
# graphify-enforce stale advisory
# --------------------------------------------------------------------------- #
@pytest.fixture
def genf(tmp_path, monkeypatch):
    ge = _load("ge_wpb", "graphify-enforce.py")
    monkeypatch.delenv("CLAUDE_HOOK_DOCTOR", raising=False)  # CI sets it; _reprobe_graphify no-ops under it
    monkeypatch.setattr(ge, "STATE_DIR", tmp_path / "gstate")
    repo = _mkrepo(tmp_path / "repo")
    (repo / "graphify-out").mkdir()
    graph = repo / "graphify-out" / "graph.json"
    graph.write_text("{}")
    os.utime(graph, (1, 1))  # older than the last commit
    return ge, repo, graph


def test_stale_graph_triggers_rebuild_and_says_so(genf, monkeypatch):
    ge, repo, graph = genf
    calls: list = []
    monkeypatch.setattr(ge, "_reprobe_graphify", lambda root: calls.append(str(root)) or "BUILDING")
    text = ge._reminder(repo, graph, cid="c1")
    assert "graph rebuilding in the background; answers may lag the last commit" in text
    assert "graphify update" not in text
    assert calls == [str(repo)]


def test_stale_graph_probe_is_rate_limited_per_session(genf, monkeypatch):
    ge, repo, graph = genf
    calls: list = []
    monkeypatch.setattr(ge, "_reprobe_graphify", lambda root: calls.append(1) or "BUILDING")
    ge._reminder(repo, graph, cid="c1")
    ge._reminder(repo, graph, cid="c1", compact=True)
    assert len(calls) == 1


def test_graph_that_the_probe_calls_fresh_gets_no_stale_warning(genf, monkeypatch):
    ge, repo, graph = genf
    monkeypatch.setattr(ge, "_reprobe_graphify", lambda root: "FRESH")
    text = ge._reminder(repo, graph, cid="c2")
    assert "STALE" not in text and "rebuilding" not in text


def test_reprobe_graphify_reads_the_cli_json_and_fails_open(genf, monkeypatch):
    ge, repo, _ = genf
    seen: list = []

    def fake_run(cmd, **kw):
        seen.append(cmd)
        return subprocess.CompletedProcess(
            cmd, 0, json.dumps({"surfaces": {"graphify": "BUILDING"}, "spawned": ["graphify"]}), "")
    monkeypatch.setattr(ge.subprocess, "run", fake_run)
    assert ge._reprobe_graphify(repo) == "BUILDING"
    assert seen[0][-3:] == ["reprobe", "--root", str(repo)]

    def boom(cmd, **kw):
        raise OSError("nope")
    monkeypatch.setattr(ge.subprocess, "run", boom)
    assert ge._reprobe_graphify(repo) == ""


# --------------------------------------------------------------------------- #
# graphify_launcher: missing / foreign graph kicks the lifecycle build
# --------------------------------------------------------------------------- #
@pytest.fixture
def launcher(tmp_path, monkeypatch):
    gl = _load("gl_wpb", "graphify_launcher.py")
    spawned: list = []
    monkeypatch.setattr(gl._plat, "spawn_detached", lambda cmd, **kw: spawned.append(list(cmd)) or 1)
    return gl, spawned


def test_missing_graph_spawns_lifecycle_reprobe_for_the_open_repo(launcher, tmp_path, monkeypatch):
    gl, spawned = launcher
    repo = _mkrepo(tmp_path / "repo")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(repo))
    gl._kick_graph_build()
    assert len(spawned) == 1
    assert spawned[0][-3:] == ["reprobe", "--root", str(repo.resolve())]
    assert spawned[0][1].endswith("index-lifecycle.py")


def test_non_git_cwd_spawns_nothing(launcher, tmp_path, monkeypatch):
    gl, spawned = launcher
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(plain))
    gl._kick_graph_build()
    assert spawned == []


def test_foreign_graph_message_no_longer_tells_anyone_to_run_graphify_update(launcher):
    gl, _ = launcher
    assert "graphify update" not in Path(gl.__file__).read_text(encoding="utf-8")
