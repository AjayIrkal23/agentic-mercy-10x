"""test_memwatch.py — hooks/tools/memwatch.py: tiers, journal, kill ladder, notify, restore, loop."""
from __future__ import annotations

import importlib.util
import json
import os
import shlex
import sys
import time
from pathlib import Path

import pytest

from test_platform_mem import fake_proc

HOOKS = Path(__file__).resolve().parents[1]
FIX = HOOKS / "tests" / "fixtures"
_spec = importlib.util.spec_from_file_location("memwatch", HOOKS / "tools" / "memwatch.py")
mw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mw)
CFG = mw.load_config(total_mb=30669, local_path=Path("/nonexistent/oomguard.local.json"))
NOW = 1_800_000_000.0


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
    # fixture /proc trees work on any OS; the Windows "unsupported" path is test_unsupported_tree_and_windows
    monkeypatch.setattr(mw.plat, "IS_WINDOWS", False)
    return tmp_path


def _run(tmp, tree, *extra, **seams):
    st, ev = tmp / "s.json", tmp / "e.jsonl"
    rc = mw.main(["--once", "--proc-root", str(tree), "--state", str(st), "--events", str(ev), *extra], **seams)
    events = [json.loads(x) for x in ev.read_text(encoding="utf-8").splitlines()] if ev.exists() else []
    return rc, json.loads(st.read_text(encoding="utf-8")), events


def _ctx(tmp, tree=FIX / "proc-ok", *extra, **seams):
    a = mw._parser().parse_args(["--once", "--proc-root", str(tree), "--state", str(tmp / "s.json"),
                                 "--events", str(tmp / "e.jsonl"), *extra])
    return mw.Ctx(a, CFG, **seams)


def _events(tmp):
    p = tmp / "e.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


# ---- step 5: probe, tiers, --once ------------------------------------------------------------
def test_sample_top_is_grouped_and_sorted():
    top = mw.sample(FIX / "proc-crit")["top"]
    assert [t["name"] for t in top[:2]] == ["python3", "node"] and set(top[0]) == {"name", "pid", "rss_mb", "unit"}


@pytest.mark.parametrize("tree,want", [("proc-ok", "ok"), ("proc-warn", "warn"), ("proc-crit", "crit"),
                                       ("proc-kill", "crit")])
def test_level_per_fixture(tree, want):
    assert mw.decide_level(mw.sample(FIX / tree), "ok", 0, CFG, NOW) == want


def test_level_hysteresis():
    assert mw.decide_level({"mem_available_mb": 3400, "psi_some_avg10": 10}, "crit", 0, CFG, NOW) == "crit"
    ok = mw.sample(FIX / "proc-ok")
    assert mw.decide_level(ok, "warn", NOW - 30, CFG, NOW) == "warn"
    assert mw.decide_level(ok, "warn", NOW - 61, CFG, NOW) == "ok"


def test_once_writes_state_and_one_tier_event(env):
    rc, st, ev = _run(env, FIX / "proc-crit", "--dry-run")
    assert rc == 0 and st["level"] == "crit" and st["kill_policy"]["stage"] >= 1 and st["schema"] == 1
    assert [(e["from"], e["to"]) for e in ev if e["kind"] == "tier"] == [("ok", "crit")]
    _, _, ev2 = _run(env, FIX / "proc-crit", "--dry-run")
    assert len([e for e in ev2 if e["kind"] == "tier"]) == 1 and len(ev2) == len(ev)


def test_unsupported_tree_and_windows(env, monkeypatch, capsys):
    (env / "empty").mkdir()
    assert mw.main(["--once", "--proc-root", str(env / "empty"), "--state", str(env / "s.json")]) == 0
    assert json.loads((env / "s.json").read_text(encoding="utf-8"))["unsupported"] is True
    monkeypatch.setattr(mw.plat, "IS_WINDOWS", True)
    assert mw.main(["--once"]) == 0 and "unsupported" in capsys.readouterr().out
    assert mw.mws.read(stale_s=60).unsupported is True


def test_config_override(env):
    (env / "c.json").write_text(json.dumps({"tiers": {"warn": {"mem_available_mb": 25000}}}), encoding="utf-8")
    assert _run(env, FIX / "proc-ok", "--config", str(env / "c.json"))[1]["level"] == "warn"


# ---- step 6: journal ---------------------------------------------------------------------------
def _jl(name):
    return [json.loads(x) for x in (FIX / "journal" / name).read_text(encoding="utf-8").splitlines()]


def test_parse_journal_lines():
    k = mw.parse_journal_line(_jl("kernel.json")[0])
    assert k == {"kind": "kill", "source": "kernel", "pid": 67860, "victim": "MainThread", "rss_mb": 3838, "unit": None}
    msg = _jl("kernel.json")[0]["MESSAGE"].replace("MainThread", "node (vitest 4)").replace("Out of", "Memory cgroup out of")
    assert mw.parse_journal_line(dict(_jl("kernel.json")[0], MESSAGE=msg))["victim"] == "node (vitest 4)"  # memcg kill
    o = mw.parse_journal_line(_jl("oomd.json")[0])
    assert (o["source"], o["unit"], o["victim"], o["rss_mb"]) == ("oomd", "snap.firefox.firefox-1111.scope", None, None)
    um, stopped = (mw.parse_journal_line(x) for x in _jl("user-manager.json"))
    assert (um["source"], um["unit"]) == ("user-manager", "ptyxis-spawn-aaaa.scope")
    assert stopped == {"kind": "stopped", "unit": "ptyxis-spawn-aaaa.scope"}
    assert mw.parse_journal_line({"SYSLOG_IDENTIFIER": "systemd", "MESSAGE": "Started foo.service"}) is None
    assert mw.parse_journal_text("not json\n") == []


def test_ingest_stopped_marker_and_dedupe(env):
    c = _ctx(env)
    c.ingest([{"kind": "stopped", "unit": "x.scope"}], NOW, [])
    assert _events(env) == []
    k = mw.parse_journal_line(_jl("kernel.json")[0])
    c.last_unit = {k["pid"]: "ptyxis-spawn-aaaa.scope"}  # the victim's scope, from the sample before it died
    c.ingest([k, dict(k)], NOW, [])
    c.ingest([dict(k)], NOW + 3, [])
    c.ingest([{"kind": "stopped", "unit": "ptyxis-spawn-aaaa.scope"}], NOW + 4, [])
    ev = _events(env)
    assert len(ev) == 2 and ev[1]["note"] == "scope stopped after kill" and ev[1]["source"] == "user-manager"
    assert ev[1]["unit"] == "ptyxis-spawn-aaaa.scope" and ev[1]["victim"] == "MainThread"


def test_ingest_drops_test_scopes(env):
    c = _ctx(env)
    c.ingest([{"kind": "kill", "source": "user-manager", "unit": "claude-test-oom-1.scope", "victim": None, "pid": None, "rss_mb": None},
              {"kind": "stopped", "unit": "claude-test-oom-1.scope"}], NOW, [])
    assert _events(env) == []


def _py(code, *args):
    """A --journal-cmd running this interpreter: no cat/false/sleep on Windows, and shlex.join keeps
    backslash paths intact through memwatch's posix shlex.split."""
    return shlex.join([sys.executable, "-c", code, *map(str, args)])


def test_journal_cmd_end_to_end(env, monkeypatch, capsys):
    cat = _py("import sys; sys.stdout.write(open(sys.argv[1], encoding='utf-8').read())", FIX / "journal" / "oomd.json")
    _, _, ev = _run(env, FIX / "proc-ok", "--journal-cmd", cat)
    assert [e["source"] for e in ev] == ["oomd"]
    (env / "e.jsonl").unlink()
    assert _run(env, FIX / "proc-ok", "--journal-cmd", _py("raise SystemExit(1)"))[2] == []
    assert "journal-cmd rc=1" in capsys.readouterr().err
    monkeypatch.setattr(mw, "JOURNAL_CMD_TIMEOUT", 1.0)
    t0 = time.monotonic()
    assert _run(env, FIX / "proc-ok", "--journal-cmd", _py("import time; time.sleep(30)"))[0] == 0
    assert time.monotonic() - t0 < 5


# ---- step 7: kill ladder -----------------------------------------------------------------------
def _rec():
    calls = []
    return calls, (lambda cmd, timeout=None, **_: calls.append(list(cmd)) or mw.subprocess.CompletedProcess(cmd, 0))


def _local(env, **kv):
    (env / "cfg").mkdir(exist_ok=True)
    (env / "cfg" / "oomguard.local.json").write_text(json.dumps(kv), encoding="utf-8")


def test_stage1_sheds_own_index_scopes_only(env):
    _, st, ev = _run(env, FIX / "proc-crit", "--dry-run")
    assert [(e["unit"], e["dry_run"]) for e in ev if e["kind"] == "shed"] == [("claude-index-graphify-ab12cd34.scope", True)]
    assert not [e for e in ev if e["kind"] == "kill"] and st["kill_policy"]["stage"] == 1 and st["kill_policy"]["crit_since"]
    (env / "s.json").unlink()
    calls, run = _rec()
    _run(env, FIX / "proc-crit", run=run)
    stops = [c for c in calls if c[:3] == ["systemctl", "--user", "stop"]]
    assert stops == [["systemctl", "--user", "stop", "claude-index-graphify-ab12cd34.scope"]]
    (env / "s.json").unlink()
    (env / "e.jsonl").unlink()
    _local(env, shed_mode="none")
    assert not [e for e in _run(env, FIX / "proc-crit", "--dry-run")[2] if e["kind"] == "shed"]


def test_stage2_emergency_kills_biggest_renderer_never_parent_or_claude(env):
    _, st, ev = _run(env, FIX / "proc-kill", "--dry-run")
    kills = [e for e in ev if e["kind"] == "kill"]
    assert [(k["stage"], k["pid"], k["victim"], k["dry_run"]) for k in kills] == [(2, 301, "Isolated Web Co", True)]
    assert kills[0]["cmd"].startswith("/snap/firefox") and "firefox-parent" not in json.dumps(ev)
    assert not {100, 101} & {e.get("pid") for e in ev} and st["kill_policy"]["stage"] == 2


@pytest.mark.parametrize("age,stage", [(25, 2), (5, 1)])
def test_stage2_after_holdoff(env, age, stage):
    t = time.time()
    (env / "s.json").write_text(json.dumps({"ts": t, "level": "crit", "kill_policy": {"stage": 1, "crit_since": t - age}}),
                                encoding="utf-8")
    assert _run(env, FIX / "proc-crit", "--dry-run")[1]["kill_policy"]["stage"] == stage


MATRIX = [(11, "tmux", "tmux", 1, "protected"), (12, "gnome-shell", "gnome-shell", 1, "protected"),
          (13, "sshd", "sshd", 1, "protected"), (14, "systemd", "/lib/systemd/systemd --user", 1, "protected"),
          (15, "ptyxis", "ptyxis", 1, "protected"), (16, "claude", "claude", 15, "protected"),
          (17, "node", "node /x/vitest.mjs run", 16, "protected"), (18, "firefox", "/usr/lib/firefox/firefox", 1, "protected"),
          (19, "chrome", "/opt/chrome/chrome", 1, "protected"), (20, "Isolated Web Co", "firefox -contentproc", 18, "victim"),
          (21, "chrome", "/opt/chrome/chrome --type=renderer", 19, "victim"), (22, "WebKitWebProcess", "x", 1, "victim"),
          (23, "node", "node /x/tsserver.js", 1, "victim"), (24, "node", "node /x/vitest.mjs run", 1, "victim"),
          (25, "cargo", "cargo build", 1, "victim"), (26, "gradle", "gradle build", 1, "victim"),
          (27, "mongod", "mongod", 1, "other")]


@pytest.mark.parametrize("extra,mongod", [({}, "other"), ({"protected_extra": ["mongod"]}, "protected"),
                                          ({"victims_extra": ["mongod"]}, "victim"),
                                          ({"protected_extra": ["mongod"], "victims_extra": ["mongod"]}, "protected")])
def test_classify_matrix(env, extra, mongod):
    root = fake_proc(env / "p", procs=[{"pid": p, "name": n, "cmdline": c, "ppid": pp, "rss_kb": 1024}
                                       for p, n, c, pp, _ in MATRIX])
    _local(env, **extra)
    lad = mw.Ladder(CFG, str(root))
    procs = mw.read_procs(str(root))
    by = {p["pid"]: p for p in procs}
    got = {p: lad.classify(by[p], by) for p, *_ in MATRIX}
    assert got == {p: (mongod if n == "mongod" else w) for p, n, _, _, w in MATRIX}


def test_one_victim_per_ten_seconds():
    lad, s = mw.Ladder(CFG, str(FIX / "proc-kill")), mw.sample(FIX / "proc-kill")
    kills = []
    kp = {}
    for t in (NOW, NOW + 3, NOW + 11):
        kp, acts = lad.step(t, "crit", s, s["procs"], [], kp)
        kills += [a[1]["pid"] for a in acts if a[0] == "kill"]
    assert kills == [301, 400]


def _stage3_tree(env, pending=False):
    now = time.time()
    root = fake_proc(env / "p", mem_available_kb=1048576, procs=[
        {"pid": 10, "name": "gnome-shell", "rss_kb": 1024}, {"pid": 20, "name": "tmux: server", "rss_kb": 1024},
        {"pid": 100, "name": "claude", "ppid": 20, "rss_kb": 600000, "unit": "claude-100.scope"},
        {"pid": 101, "name": "node", "ppid": 100, "cmdline": "node mcp-server", "rss_kb": 900000, "unit": "claude-100.scope"},
        {"pid": 200, "name": "claude", "ppid": 20, "rss_kb": 600000, "unit": "claude-200.scope"}])
    led = env / "state" / "live-sessions"
    led.mkdir(parents=True)
    for sid, pid, age in (("s-idle", 100, 900), ("s-active", 200, 5)):
        tr = env / f"{sid}.jsonl"
        line = {"timestamp": now - age, "message": {"content": [{"type": "tool_use", "name": "Bash", "id": "t1"}]}}
        tr.write_text(json.dumps(line) + "\n" if pending else "{}\n", encoding="utf-8")
        os.utime(tr, (now - age, now - age))
        (led / f"{sid}.json").write_text(json.dumps({"sid": sid, "pid": pid, "transcript": str(tr), "scope": f"claude-{pid}.scope",
                                                     "seen": now - age, "ended": None}), encoding="utf-8")
    return root


def test_stage3_stops_the_idle_session(env):
    _, st, ev = _run(env, _stage3_tree(env), "--dry-run")
    kills = [e for e in ev if e["kind"] == "kill"]
    assert [(k["stage"], k["sid"], k["pid"]) for k in kills] == [(3, "s-idle", 100)] and st["kill_policy"]["stage"] == 3


def test_stage3_skips_pending_bash(env, capsys):
    _, st, ev = _run(env, _stage3_tree(env, pending=True), "--dry-run")
    assert not [e for e in ev if e["kind"] == "kill"] and st["kill_policy"]["stage"] == 3
    assert "stage3: no idle session" in capsys.readouterr().err


def test_stage3_activity_is_per_pid_so_a_stale_sibling_never_exposes_a_live_session(env):
    root = _stage3_tree(env)                       # s-idle→100 (900 s), s-active→200 (5 s)
    led = env / "state" / "live-sessions"
    now = time.time()
    old_tr = env / "s-idle.jsonl"                  # readable and 900 s old: a candidate under the sid-keyed code
    for sid in ("fixture-a", "fixture-b"):         # two stale replays bound to the ACTIVE pid 200 (O5)
        (led / f"{sid}.json").write_text(json.dumps({"sid": sid, "pid": 200, "transcript": str(old_tr),
                                                     "scope": "claude-200.scope", "seen": now - 7200, "ended": None}), encoding="utf-8")
    _, st, ev = _run(env, root, "--dry-run")
    kills = [(k["stage"], k["sid"], k["pid"]) for k in ev if k["kind"] == "kill"]
    assert kills == [(3, "s-idle", 100)]           # never pid 200, whatever its siblings say


def test_stage3_never_picks_an_entry_without_a_readable_transcript(env, capsys):
    root = _stage3_tree(env)
    led = env / "state" / "live-sessions"
    (led / "s-idle.json").write_text(json.dumps({"sid": "s-idle", "pid": 100, "transcript": str(env / "gone.jsonl"),
                                                 "scope": "claude-100.scope", "seen": time.time() - 900, "ended": None}), encoding="utf-8")
    _, st, ev = _run(env, root, "--dry-run")
    assert not [e for e in ev if e["kind"] == "kill"] and st["kill_policy"]["stage"] == 3
    assert "stage3: no idle session" in capsys.readouterr().err


def test_policy_disabled_and_dry_run_never_signal(env):
    def boom(*a, **k):
        raise AssertionError("signalled")
    calls, run = _rec()
    _, st, ev = _run(env, FIX / "proc-kill", "--dry-run", run=run, kill=boom)
    assert any(e["kind"] == "kill" for e in ev) and not [c for c in calls if c[0] == "systemctl"]
    (env / "s.json").unlink()
    (env / "e.jsonl").unlink()
    _local(env, kill_policy={"enabled": False})
    _, st, ev = _run(env, FIX / "proc-kill", run=run, kill=boom)
    assert st["kill_policy"]["stage"] == 0 and [e["kind"] for e in ev] == ["tier"]


# ---- REVIEW2 fixes -----------------------------------------------------------------------------
def _p(pid, name, ppid, rss, unit=None, uid=1000):
    return {"pid": pid, "name": name, "ppid": ppid, "rss_mb": rss, "unit": unit, "uid": uid}


def _restore_ctx(env, spawned):
    root = env / "root"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "restore_sessions.py").write_text("", encoding="utf-8")
    c = _ctx(env, spawn=spawned.append, root=root, local_cfg=env / "absent.json")
    c.restore_pending, c.level, c.ok_since = True, "ok", time.time() - 120
    return c


@pytest.mark.skipif(os.name == "nt", reason="restore_sessions is POSIX only")
def test_maybe_restore_then_restore_sessions_launches(env, monkeypatch):
    """memwatch's spawn must not pre-empt restore_sessions' own restore.lock."""
    spawned = []
    c = _restore_ctx(env, spawned)
    assert mw.maybe_restore(c, time.time()) is True and len(spawned) == 1
    assert not (env / "state" / "restore.lock").exists() and (env / "state" / "restore.spawned").exists()
    spec = importlib.util.spec_from_file_location("rs_under_mw", HOOKS.parent / "scripts" / "restore_sessions.py")
    rs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rs)
    monkeypatch.setattr(rs, "tmux", lambda args, env: mw.subprocess.CompletedProcess(args, 0, "", ""))
    monkeypatch.setattr(rs.shutil, "which", lambda n: "/usr/bin/" + n)
    monkeypatch.setattr(rs, "_sleep", lambda s: None)
    monkeypatch.setattr(rs._sl, "mark_restored", lambda sid: None)
    dead = {"sid": "5f0c3a3e-1d2b-4c5d-9e8f-0a1b2c3d4e5f", "pid": 4190000, "cwd": str(env),  # a UUID: O6
            "started": time.time() - 100}
    monkeypatch.setattr(rs._sl, "classify", lambda max_age, now=None: {"eligible": [dead], "stale": [], "ended": []})
    out = rs.run(rs.build_parser().parse_args(["--only-if-ok", "--max-age", "7200"]))
    assert out["stopped_reason"] is None and out["launched"] >= 1


def test_restore_pending_held_until_restore_row_or_timeout(env):
    spawned = []
    c = _restore_ctx(env, spawned)
    now = time.time()
    assert mw.maybe_restore(c, now) is True and c.restore_pending is True
    assert mw.maybe_restore(c, now + 30) is False and len(spawned) == 1  # debounced
    mw.settle_restore(c, now + 40)
    assert c.restore_pending is True
    mw.mws.append_event({"kind": "restore", "ok": True, "ts": now + 50}, path=c.events_path)
    mw.settle_restore(c, now + 60)
    assert c.restore_pending is False and c.restore_spawned_ts is None
    c.restore_pending, c.restore_spawned_ts = True, now + 100
    mw.settle_restore(c, now + 100 + 601)
    assert c.restore_pending is False


def test_storm_held_crit_kills_once_never_stops_session(env):
    """One dip below the crit line, then 3.0 GB free: hysteresis keeps 'crit', kills must not."""
    lad = mw.Ladder(CFG, "/nonexistent", env / "absent.json")
    lad.uid = 1000
    lad.cmd = lambda pid: "/usr/lib/firefox/firefox" if pid == 500 else "/usr/lib/firefox/firefox -contentproc"
    procs = [_p(1, "systemd", 0, 10), _p(500, "firefox", 1, 800)] + \
        [_p(600 + i, "Isolated Web Co", 500, 900 - i * 100) for i in range(6)] + \
        [_p(900, "claude", 1, 700, "claude-900.scope"), _p(901, "claude", 1, 700, "claude-901.scope")]
    tr = env / "idle.jsonl"
    tr.write_text("{}\n", encoding="utf-8")
    os.utime(tr, (0, 0))
    ledger = [{"sid": "s-idle", "pid": 900, "transcript": str(tr), "seen": 0, "scope": "claude-900.scope"},
              {"sid": "s-busy", "pid": 901, "transcript": None, "seen": 1e12, "scope": "claude-901.scope"}]
    level, lts, kp, t0, acts_all = "ok", 0.0, {}, 1_000_000.0, []
    for t in range(0, 95, 5):
        s = {"mem_available_mb": 2000 if t <= 20 else 3000, "psi_some_avg10": 2.0, "swap_free_pct": 100.0}
        new = mw.decide_level(s, level, lts, CFG, t0 + t)
        if new != level:
            level, lts = new, t0 + t
        kp, acts = lad.step(t0 + t, level, s, procs, ledger, kp)
        acts_all += acts
        procs = [p for p in procs if not any(a[0] == "kill" and a[1]["pid"] == p["pid"] for a in acts)]
    assert level == "crit"
    assert [a[0] for a in acts_all] == ["kill"] and kp["stage2_since"] is None


class _NowTimer:
    def __init__(self, _delay, fn):
        self.fn = fn

    def start(self):
        self.fn()


@pytest.mark.parametrize("scope,stopped", [("app-kitty-4242.scope", False), ("vscode-x.scope", False),
                                           ("claude-safe-123.scope", True), ("claude-123.scope", True)])
def test_stop_session_only_stops_own_scopes(env, monkeypatch, scope, stopped):
    calls, run = _rec()
    kills = []
    c = _ctx(env, run=run, kill=lambda pid, sig: kills.append(pid))
    c.live, c.once = True, False
    monkeypatch.setattr(mw.threading, "Timer", _NowTimer)
    monkeypatch.setattr(mw.plat, "pid_alive", lambda pid: False)
    c._stop_session(777, scope)
    assert kills == [777]
    assert (["systemctl", "--user", "stop", scope] in calls) is stopped


def test_stage3_event_records_scope_stopped(env):
    c = _ctx(env, FIX / "proc-ok", "--dry-run")
    c.act([("stop-session", "s-idle-kitty", 777, "app-kitty-4242.scope")], NOW)
    assert _events(env)[0]["scope_stopped"] is False


def test_focused_pane_child_session_is_protected(env):
    now = 10_000.0
    by_pid = {p["pid"]: p for p in [_p(150, "tmux: server", 1, 10), _p(200, "zsh", 150, 5), _p(300, "claude", 200, 600),
                                    _p(210, "zsh", 150, 5), _p(400, "claude", 210, 600)]}
    t300, t400 = env / "a.jsonl", env / "b.jsonl"
    for f, age in ((t300, 900), (t400, 5)):
        f.write_text("{}\n", encoding="utf-8")
        os.utime(f, (now - age, now - age))
    ledger = [{"sid": "s-focused", "pid": 300, "transcript": str(t300), "seen": now - 900},
              {"sid": "s-busy", "pid": 400, "transcript": str(t400), "seen": now - 5}]
    assert mw.idle_session(ledger, now, 10, by_pid, fg_pid=200) is None
    assert mw.idle_session(ledger, now, 10, by_pid, fg_pid=None)[0] == "s-focused"


def test_stopped_scope_attribution_consumes_kernel_kill_once(env):
    notes = []
    root = env / "root"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "restore_sessions.py").write_text("", encoding="utf-8")
    c = _ctx(env, notify=lambda *a, **k: notes.append(a) or True, root=root, local_cfg=env / "absent.json")
    c.last_unit = {4242: "claude-abc.scope"}
    ledger = [{"sid": "s-closed", "pid": 4321, "scope": "app-bar.scope"}]
    c.ingest([{"kind": "kill", "source": "kernel", "pid": 4242, "victim": "node", "rss_mb": 900, "unit": None}], NOW, ledger)
    c.ingest([{"kind": "stopped", "unit": "app-foo.scope"}, {"kind": "stopped", "unit": "app-bar.scope"},
              {"kind": "stopped", "unit": "claude-abc.scope"}, {"kind": "stopped", "unit": "claude-abc.scope"}],
             NOW + 20, ledger)
    conv = [e for e in _events(env) if e.get("note") == "scope stopped after kill"]
    assert [e["unit"] for e in conv] == ["claude-abc.scope"] and len(notes) == 2
    assert c.restore_pending is False and "used" not in json.dumps(_events(env))


def test_ptyhost_sheltering_claude_is_never_a_victim(env):
    lad = mw.Ladder(CFG, "/nonexistent", env / "absent.json")
    lad.uid = 1000
    cmds = {500: "/usr/share/code/code", 510: "/usr/share/code/code --type=utility ptyHost", 520: "/usr/bin/zsh",
            530: "claude", 540: "/usr/share/code/code --type=renderer"}
    lad.cmd = lambda pid: cmds.get(pid, "")
    procs = [_p(500, "code", 1, 400), _p(510, "code", 500, 300), _p(520, "zsh", 510, 5), _p(530, "claude", 520, 900),
             _p(540, "code", 500, 200)]
    s = {"mem_available_mb": 1000, "psi_some_avg10": 30.0, "swap_free_pct": 0.0}
    kills = [a[1]["pid"] for a in lad.step(1e6, "crit", s, procs, [], {})[1] if a[0] == "kill"]
    assert kills == [540]


def test_uid_filter_and_eperm_not_announced(env):
    notes = []

    def kill(pid, sig):
        raise PermissionError(1, "Operation not permitted")
    c = _ctx(env, kill=kill, notify=lambda *a, **k: notes.append(a) or True)
    lad = c.ladder
    lad.uid = 1000
    lad.cmd = lambda pid: {700: "node /app/node_modules/.bin/vite build"}.get(pid, "firefox -contentproc")
    s = {"mem_available_mb": 1000, "psi_some_avg10": 30.0, "swap_free_pct": 0.0}
    procs = [_p(700, "node", 1, 3000, "docker-abc.scope", uid=0), _p(701, "Isolated Web Co", 1, 1500)]
    c.kp, acts = lad.step(1e6, "crit", s, procs, [], {})
    assert [a[1]["pid"] for a in acts if a[0] == "kill"] == [701]
    c.act(acts, 1e6)
    ev = [e for e in _events(env) if e["kind"] == "kill"]
    assert [(e["pid"], e["ok"]) for e in ev] == [(701, False)] and notes == []
    assert 701 not in lad.killed and not c.kp["last_kill_ts"]
    assert [a[1]["pid"] for a in lad.step(1e6 + 5, "crit", s, procs, [], c.kp)[1] if a[0] == "kill"] == [701]


# ---- FIX-r2 O1: a native-installer Claude (comm = version string) is recognised by cmdline -----
def _native_tree(lad, parent_name="2.1.312"):
    lad.uid = 1000
    cmds = {600: "/usr/bin/ptyxis", 610: "/opt/u/.local/share/claude/versions/2.1.312 --session-id x",
            620: "node /x/typescript-language-server --stdio", 630: "node /x/tsserver.js",
            700: "/usr/bin/bash", 710: "node /y/tsserver.js"}
    if parent_name != "2.1.312":
        cmds[610] = "/usr/bin/" + parent_name
    lad.cmd = lambda pid: cmds.get(pid, "")
    return [_p(600, "ptyxis", 1, 100), _p(610, parent_name, 600, 700), _p(620, "node", 610, 200),
            _p(630, "node", 620, 900), _p(700, "bash", 1, 5), _p(710, "node", 700, 400)]


def test_native_claude_child_is_protected_and_shelters(env):
    lad = mw.Ladder(CFG, "/nonexistent", env / "absent.json")
    procs = _native_tree(lad)
    by = {p["pid"]: p for p in procs}
    assert lad.classify(by[630], by) == "protected"
    assert lad.classify(by[610], by) == "protected"
    assert lad.classify(by[710], by) == "victim"   # the same tsserver under a plain bash
    s = {"mem_available_mb": 1000, "psi_some_avg10": 30.0, "swap_free_pct": 0.0}
    kills = [a[1]["pid"] for a in lad.step(1e6, "crit", s, procs, [], {})[1] if a[0] == "kill"]
    assert kills == [710]


def test_npm_claude_with_mainthread_comm_shelters_its_children(env):
    # SANTA-FINAL hooks F5: node 24 names its main thread "MainThread", so an npm Claude's comm is that
    lad = mw.Ladder(CFG, "/nonexistent", env / "absent.json")
    procs = _native_tree(lad, parent_name="MainThread")
    lad.cmd = lambda pid: {610: "node /u/lib/node_modules/@anthropic-ai/claude-code/cli.js"}.get(pid, "")
    by = {p["pid"]: p for p in procs}
    assert lad.classify(by[630], by) == "protected"


def test_version_comm_without_claude_cmdline_is_not_claude(env):
    lad = mw.Ladder(CFG, "/nonexistent", env / "absent.json")
    procs = _native_tree(lad, parent_name="bash")
    by = {p["pid"]: p for p in procs}
    assert lad.classify(by[630], by) == "victim"


# ---- FIX-r2 O4: a dry run never pops a desktop kill toast -------------------------------------
def test_dry_run_kill_sends_no_notification(env):
    notes = []
    c = _ctx(env, FIX / "proc-ok", "--dry-run", notify=lambda *a, **k: notes.append(a) or True, kill=lambda *a: None)
    p = {"pid": 4242, "name": "sleep", "rss_mb": 7, "unit": None}
    c.act([("kill", p, 2)], 1e6)
    c.act([("stop-session", "sid-dry-0001", 4242, "claude-4242.scope")], 1e6)
    ev = [e for e in _events(env) if e["kind"] == "kill"]
    assert notes == [] and len(ev) == 2 and all(e["dry_run"] for e in ev)


def test_local_cfg_without_kill_policy_keeps_shipped_enabled_false(env):
    cfg = json.loads(json.dumps(CFG))
    cfg["kill_policy"]["enabled"] = False
    assert mw.Ladder(cfg, "/nonexistent", env / "absent.json").kp["enabled"] is False
    _local(env, kill_policy={"enabled": True})
    assert mw.Ladder(cfg, "/nonexistent", env / "cfg" / "oomguard.local.json").kp["enabled"] is True


def test_stale_state_kill_timers_ignored(env):
    t = time.time()
    (env / "s.json").write_text(json.dumps({"ts": t - 86400, "level": "crit", "shed": ["claude-index-x.scope"],
                                            "kill_policy": {"stage": 2, "crit_since": t - 86400,
                                                            "stage2_since": t - 86400}}), encoding="utf-8")
    _, st, ev = _run(env, FIX / "proc-crit", "--dry-run")
    assert st["kill_policy"]["stage"] == 1 and not [e for e in ev if e["kind"] == "kill"]


# --------------------------------------------------------------------------- #
# F7: tiers are percent of MemTotal
def test_tiers_are_percent_of_memtotal(env):
    absent = env / "absent.json"

    def lines(c):
        t = c["tiers"]
        return (t["warn"]["mem_available_mb"], t["warn"]["swap_mem_available_mb"], t["crit"]["mem_available_mb"],
                c["kill_policy"]["emergency_mb"])
    assert lines(mw.load_config(total_mb=15650, local_path=absent)) == (2347, 3521, 1252, 626)
    assert lines(mw.load_config(total_mb=30669, local_path=absent)) == (4600, 6900, 2453, 1226)
    assert lines(mw.load_config(total_mb=0, local_path=absent)) == (8192, 12288, 3072, 1500)  # MemTotal unknown


def test_shipped_config_holds_the_percents_only():
    raw = json.loads((HOOKS / "memwatch.config.json").read_text(encoding="utf-8"))
    assert (raw["tiers"]["warn"]["mem_available_pct"], raw["tiers"]["warn"]["swap_mem_available_pct"],
            raw["tiers"]["crit"]["mem_available_pct"], raw["kill_policy"]["emergency_pct"]) == (15, 22.5, 8, 4)
    # an MB line in the file pins it (absolute), so the shipped file must not carry one
    assert "mem_available_mb" not in raw["tiers"]["warn"] and "mem_available_mb" not in raw["tiers"]["crit"]
    assert "emergency_mb" not in raw["kill_policy"] and "scale" not in raw


def test_local_tiers_override_beats_the_percent(env):
    loc = env / "oomguard.local.json"
    loc.write_text(json.dumps({"tiers": {"warn": {"mem_available_mb": 3900}}}), encoding="utf-8")
    cfg = mw.load_config(total_mb=15650, local_path=loc)
    assert cfg["tiers"]["warn"]["mem_available_mb"] == 3900 and cfg["tiers"]["crit"]["mem_available_mb"] == 1252


def test_a_16gb_box_is_ok_at_idle(env):
    """The laptop idles at 5.7 GB free: v4.3.0 sat at warn there for good (F4); 15 % is 2347 MB."""
    cfg = mw.load_config(total_mb=15650, local_path=env / "absent.json")
    calm = {"psi_some_avg10": 0.0, "swap_free_pct": 100.0}
    assert mw._enter_level({"mem_available_mb": 5700, **calm}, cfg) == "ok"
    assert mw._enter_level({"mem_available_mb": 2300, **calm}, cfg) == "warn"
    assert mw._enter_level({"mem_available_mb": 1200, **calm}, cfg) == "crit"
    assert mw._enter_level({"mem_available_mb": 3400, "psi_some_avg10": 0.0, "swap_free_pct": 2.0}, cfg) == "warn"


def test_hysteresis_keeps_its_1024_mb_margin_on_a_small_box(env):
    cfg = mw.load_config(total_mb=15650, local_path=env / "absent.json")

    def s(mb):
        return {"mem_available_mb": mb, "psi_some_avg10": 0.0, "swap_free_pct": 100.0}
    assert mw.decide_level(s(1252 + 1023), "crit", 0, cfg, NOW) == "crit"
    assert mw.decide_level(s(1252 + 1024), "crit", 0, cfg, NOW) == "warn"


# FI-5: stage 3 promises a restore only when one can run
def test_stage3_suffix_names_the_restore_path(env):
    loc = env / "oomguard.local.json"
    assert mw._stage3_suffix(env / "absent.json", which=lambda b: "/usr/bin/tmux") == "(restored later)"
    assert mw._stage3_suffix(env / "absent.json", which=lambda b: None) == "(not restorable: tmux missing)"
    loc.write_text(json.dumps({"restore_enabled": False}), encoding="utf-8")
    assert mw._stage3_suffix(loc, which=lambda b: "/usr/bin/tmux") == "(restore off)"
