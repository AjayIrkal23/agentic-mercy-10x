"""WP-B (autonomy 2026-10-05): `index-lifecycle.py reprobe` and the mid-session git trigger.

reprobe probes every surface of ONE root exactly like the session-start probe, claims
locks, spawns the existing detached builders for STALE/MISSING surfaces and reports one
JSON line. The git trigger spawns ONE detached reprobe when a Bash command moved HEAD.
Builders / spawns are stubbed; no real indexer, ollama or graphify runs.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

_HOOKS = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("il_wpb_reprobe", _HOOKS / "index-lifecycle.py")
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


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_HOOK_DOCTOR", raising=False)  # CI sets it; the git trigger no-ops under it
    state = tmp_path / "state" / "index"
    state.mkdir(parents=True)
    monkeypatch.setattr(il, "STATE_DIR", state)
    spawns: list = []
    monkeypatch.setattr(il, "_spawn_build",
                        lambda ctx, surfaces, incremental=False, journal_file=None:
                        spawns.append(sorted(surfaces)))
    monkeypatch.setattr(il, "_summarizer_alive", lambda *a, **k: True)
    monkeypatch.setattr(il, "_spawn_detached", lambda cmd, cwd=None: spawns.append(("detached", list(cmd))) or 1)
    repo = _mkrepo(tmp_path / "repo")

    def probes(**states):
        for s in il.SURFACES:
            st = states.get(s, il.FRESH)
            monkeypatch.setitem(il._PROBE, s, lambda root, prior, cfg, st=st: (st, {"x": 1}, ""))
    probes()
    return {"repo": repo, "spawns": spawns, "probes": probes, "tmp": tmp_path}


# --------------------------------------------------------------------------- #
# reprobe
# --------------------------------------------------------------------------- #
def test_reprobe_non_git_root_is_empty(env, tmp_path):
    nogit = tmp_path / "plain"
    nogit.mkdir()
    assert il.reprobe(str(nogit)) == {"surfaces": {}, "spawned": []}
    assert env["spawns"] == []


def test_reprobe_never_index_root_is_empty(env):
    assert il.reprobe(str(il.HOME / ".claude")) == {"surfaces": {}, "spawned": []}


def test_reprobe_spawns_builders_for_stale_and_missing_only(env):
    env["probes"](jcodemunch=il.STALE, graphify=il.MISSING)
    out = il.reprobe(str(env["repo"]))
    assert out["surfaces"] == {"jcodemunch": "BUILDING", "jdocmunch": "FRESH",
                               "graphify": "BUILDING", "dox": "FRESH"}
    assert sorted(out["spawned"]) == ["graphify", "jcodemunch"]
    assert env["spawns"] == [["graphify", "jcodemunch"]]  # ONE detached worker for both


def test_reprobe_all_fresh_spawns_nothing(env):
    out = il.reprobe(str(env["repo"]))
    assert set(out["surfaces"].values()) == {"FRESH"} and out["spawned"] == []
    assert env["spawns"] == []


def test_reprobe_is_idempotent_while_a_build_runs(env):
    env["probes"](jcodemunch=il.STALE)
    first = il.reprobe(str(env["repo"]))
    second = il.reprobe(str(env["repo"]))
    assert first["spawned"] == ["jcodemunch"]
    assert second["spawned"] == [] and second["surfaces"]["jcodemunch"] == "BUILDING"
    assert env["spawns"] == [["jcodemunch"]]  # no second spawn


def test_reprobe_failed_backoff_is_reported_not_rebuilt(env):
    env["probes"](graphify=il.STALE)
    ctx = il._active_ctx({"cwd": str(env["repo"])})
    st = il._load_state(ctx)
    st["surfaces"]["graphify"] = {"state": il.FAILED, "failures": 3, "fingerprint": {"x": 1}}
    il._save_state(ctx, st)
    out = il.reprobe(str(env["repo"]))
    assert out["surfaces"]["graphify"] == "FAILED" and out["spawned"] == []


def test_reprobe_maps_unavailable_to_failed_and_names_it(env):
    env["probes"](jcodemunch=il.UNAVAILABLE)
    out = il.reprobe(str(env["repo"]))
    assert out["surfaces"]["jcodemunch"] == "FAILED"
    assert out["unavailable"] == ["jcodemunch"]


def test_reprobe_cli_prints_one_json_line(env, capsys):
    env["probes"](dox=il.MISSING)
    assert il.main(["reprobe", "--root", str(env["repo"])]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["spawned"] == ["dox"]


def test_reprobe_cli_without_root_still_prints_json(env, capsys):
    assert il.main(["reprobe"]) == 0
    assert json.loads(capsys.readouterr().out) == {"surfaces": {}, "spawned": []}


def test_reprobe_wall_time_survives_a_hung_probe(env, monkeypatch):
    def hang(root, prior, cfg):
        time.sleep(30)
        return (il.STALE, {}, "")
    monkeypatch.setitem(il._PROBE, "graphify", hang)
    t0 = time.time()
    out = il.reprobe(str(env["repo"]))
    assert time.time() - t0 < 3.0
    assert out["surfaces"]["graphify"] == "FRESH"  # fail-open on timeout


def test_reprobe_subprocess_non_git_exits_fast_with_json(tmp_path):
    t0 = time.time()
    cp = subprocess.run([sys.executable, str(_HOOKS / "index-lifecycle.py"), "reprobe",
                         "--root", str(tmp_path)],
                        capture_output=True, text=True, timeout=10)
    assert cp.returncode == 0 and time.time() - t0 < 3.0
    assert json.loads(cp.stdout) == {"surfaces": {}, "spawned": []}


# --------------------------------------------------------------------------- #
# mid-session git trigger (PostToolUse path)
# --------------------------------------------------------------------------- #
def _bash(env, cmd, tool="Bash"):
    payload = {"tool_name": tool, "tool_input": {"command": cmd},
               "cwd": str(env["repo"]), "workspace_roots": [str(env["repo"])]}
    with contextlib.redirect_stdout(io.StringIO()) as buf:
        il.mode_post_write(payload, il._load_config())
    return buf.getvalue()


def _reprobe_spawns(env):
    return [c for k, c in (s for s in env["spawns"] if isinstance(s, tuple))
            if "reprobe" in c]


@pytest.mark.parametrize("cmd", [
    "git commit -m x", "git pull", "git pull --rebase origin main", "git merge dev",
    "git checkout main", "git switch -c topic", "git rebase main", "git reset --hard HEAD~1",
    "git cherry-pick abc123", "git revert HEAD", "git stash pop", "git am < p.patch",
    "git -C /x commit -m y", "cd /x && git commit -am z", "make && git pull",
])
def test_head_moving_git_command_spawns_one_reprobe(env, cmd):
    assert _bash(env, cmd).strip() == "{}"
    spawned = _reprobe_spawns(env)
    assert len(spawned) == 1
    cmd_line = spawned[0]
    assert cmd_line[cmd_line.index("reprobe") + 1:] == ["--root", str(env["repo"])]


@pytest.mark.parametrize("cmd", [
    "git status", "git log --oneline", "git diff", "git add .", "git push", "git fetch",
    "git branch", "git stash", "git stash list", "ls -la", "npm test", "gitk",
])
def test_other_commands_do_not_reprobe(env, cmd):
    _bash(env, cmd)
    assert _reprobe_spawns(env) == []


def test_non_shell_tool_with_git_text_does_not_reprobe(env):
    _bash(env, "git commit", tool="Write")
    assert _reprobe_spawns(env) == []


def test_git_trigger_is_off_under_doctor(env, monkeypatch):
    monkeypatch.setenv("CLAUDE_HOOK_DOCTOR", "1")
    _bash(env, "git commit -m x")
    assert _reprobe_spawns(env) == []


def test_git_trigger_ignores_never_index_repo(env, monkeypatch):
    monkeypatch.setattr(il, "NEVER_INDEX", (env["repo"],))
    _bash(env, "git commit -m x")
    assert _reprobe_spawns(env) == []
