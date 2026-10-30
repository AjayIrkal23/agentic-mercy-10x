"""state-cleanup retention families added by the 2026-10-05 audit (J-03).

Seeds aged and fresh files in a temp base and runs `run()`; nothing touches the
real ~/.claude. Runnable: `python3 -m pytest hooks/tests/test_state_cleanup_wp8.py -q`.
"""
from __future__ import annotations

import importlib.util
import json
import os
import time
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "state_cleanup_wp8", Path(__file__).resolve().parents[1] / "tools" / "state-cleanup.py")
sc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sc)

DAY = 86400.0


def _put(path: Path, age_days: float, body: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    t = time.time() - age_days * DAY
    os.utime(path, (t, t))
    return path


def test_new_families_age_out_and_live_state_survives(tmp_path):
    base = tmp_path
    live_root = tmp_path / "repo"
    live_root.mkdir()
    old = [
        _put(base / "hooks/.telemetry/s1.suite-gate.json", 20),
        _put(base / "state/abc.stack.json", 20),
        _put(base / "state/persist-dedup/s1.json", 20),
        _put(base / "state/.tmp-x1.swap", 2),
        _put(base / "hooks/.state/index/repo-1.flush-9-9.txt", 2),
        _put(base / "hooks/.state/taste-dials/dial.json", 10),
        _put(base / "hooks/.state/index/gone-1.json", 2,
             json.dumps({"repo_root": str(tmp_path / "deleted-repo")})),
    ]
    keep = [
        _put(base / "hooks/.telemetry/s2.suite-gate.json", 3),
        _put(base / "state/def.stack.json", 3),
        _put(base / "state/persist-dedup/s2.json", 3),
        _put(base / "state/.tmp-x2.swap", 0.1),
        _put(base / "hooks/.state/index/live-1.json", 40,
             json.dumps({"repo_root": str(live_root)})),
        _put(base / "hooks/.state/index/legacy-1.json", 40, json.dumps({"surfaces": {}})),
        _put(base / "hooks/.state/index/fresh-dead-1.json", 0.1,
             json.dumps({"repo_root": str(tmp_path / "just-removed")})),
        _put(base / "state/model-modes/repo", 400),
        _put(base / "state/ponytail-active", 400),
    ]
    sc.run(base)
    assert [p.name for p in old if p.exists()] == []
    assert [p.name for p in keep if not p.exists()] == []


def test_real_session_uuid_containing_e2e_survives(tmp_path):
    """Santa H1: `*e2e-*` matched real UUIDs (…-8e2e-…) and wiped their gate evidence at age 0."""
    sid = "6dcc99ed-a957-4897-8e2e-5446b56602d4"
    keep = [_put(tmp_path / f"hooks/.state/{sid}.desloppify.json", 0),
            _put(tmp_path / f"hooks/.telemetry/{sid}.skill-invocations.jsonl", 0)]
    residue = [_put(tmp_path / "hooks/.state/x-e2e-1.json", 0),
               _put(tmp_path / "state/e2e-repo.stack.json", 0),
               _put(tmp_path / "telemetry/t.e2e-run.jsonl", 0)]
    sc.run(tmp_path)
    assert all(p.exists() for p in keep)
    assert not any(p.exists() for p in residue)


def test_orphan_lock_sidecars_go_live_and_daily_locks_stay(tmp_path):
    """`append_line` / `locked_update` leave `<file>.lock` beside data files; once the data
    file is purged the sidecar is litter. A lock whose data file still exists, a fresh
    orphan and the daily self-heal's own lock are kept."""
    live = _put(tmp_path / "telemetry/hook-fires-20261006.jsonl", 1)
    orphans = [_put(tmp_path / "telemetry/hook-fires-20260901.jsonl.lock", 2, ""),
               _put(tmp_path / "state/advisory-queue/s1.jsonl.lock", 2, ""),
               _put(tmp_path / "state/s1.desloppify.json.lock", 2, ""),
               _put(tmp_path / "hooks/.telemetry/s1.x.jsonl.lock", 2, "")]
    keep = [_put(tmp_path / "telemetry/hook-fires-20261006.jsonl.lock", 2, ""),
            _put(tmp_path / "state/advisory-queue/s2.jsonl.lock", 0.1, ""),
            _put(tmp_path / "state/selfheal-daily.lock", 30, ""),
            live]
    sc.run(tmp_path)
    assert [p.name for p in orphans if p.exists()] == []
    assert [p.name for p in keep if not p.exists()] == []


def test_unreadable_index_state_is_left_alone(tmp_path):
    bad = _put(tmp_path / "hooks/.state/index/bad-1.json", 40, "{not json")
    sc.run(tmp_path)
    assert bad.exists()


# --------------------------------------------------------------------------- #
# PKG hooks-hygiene-mod step 15: one retention table, new families
# --------------------------------------------------------------------------- #
def test_oom_state_families(tmp_path):
    alive, dead = os.getpid(), 999_999_983           # dead pid: pid_alive False
    old = [_put(tmp_path / "state/live-sessions/d1.json", 8, json.dumps({"sid": "d1", "pid": dead})),
           _put(tmp_path / "state/live-sessions/d2.json", 8, json.dumps({"sid": "d2", "pid": alive, "ended": 1})),
           _put(tmp_path / "state/session-bridge/s1.json", 2), _put(tmp_path / "state/resume-lock/s1", 2, "{}"),
           _put(tmp_path / "state/mercy-mod.active.d/x.json", 2, json.dumps({"sid": "x", "ts": 1})),
           _put(tmp_path / "state/mercy-mod.active", 2, json.dumps({"sid": "x", "ts": 1})),  # legacy single flag
           _put(tmp_path / "state/launch-caps/123.json", 2), _put(tmp_path / "state/launch-settings-123.json", 2),
           _put(tmp_path / "state/advisory-queue/old.jsonl", 8)]
    keep = [_put(tmp_path / "state/live-sessions/l1.json", 40, json.dumps({"sid": "l1", "pid": alive})),
            _put(tmp_path / "state/live-sessions/y1.json", 2, json.dumps({"sid": "y1", "pid": dead})),
            _put(tmp_path / "state/live-sessions/bad.json", 40, "{nope"),
            _put(tmp_path / "state/session-bridge/s2.json", 0.2), _put(tmp_path / "state/resume-lock/s2", 0.2, "{}"),
            _put(tmp_path / "state/mem-pressure.json", 40, "{}"),            # never touched
            _put(tmp_path / "state/mercy-mod.active.d/y.json", 0.2, json.dumps({"sid": "y", "ts": 1})),
            _put(tmp_path / "state/advisory-queue/new.jsonl", 2)]
    counts = sc.run(tmp_path)
    assert [p.name for p in old if p.exists()] == [] and [p.name for p in keep if not p.exists()] == []
    assert counts["live-sessions"] == 2 and counts["session-bridge"] == 1
    assert counts["resume-lock"] == 1 and counts["mod-flag"] == 1 and counts["mod-flag-legacy"] == 1


def test_oomguard_events_rotate_at_2mb(tmp_path):
    ev = _put(tmp_path / "state/oomguard.events", 0, ('{"kind":"tier"}\n' * 200_000))   # ~3.2 MB
    sc.run(tmp_path)
    assert ev.stat().st_size < 2 * 1024 * 1024 and len(ev.read_text(encoding="utf-8").splitlines()) == 5000


def test_teams_dirs_age_out_unless_the_lead_session_is_live(tmp_path):
    old = tmp_path / "teams/session-aaaaaaaa"
    _put(old / "config.json", 20, json.dumps({"leadSessionId": "gone"}))
    os.utime(old, (time.time() - 20 * DAY,) * 2)
    live = tmp_path / "teams/session-bbbbbbbb"
    _put(live / "config.json", 20, json.dumps({"leadSessionId": "L"}))
    os.utime(live, (time.time() - 20 * DAY,) * 2)
    _put(tmp_path / "state/live-sessions/L.json", 20, json.dumps({"sid": "L", "pid": os.getpid()}))
    young = tmp_path / "teams/session-cccccccc"
    _put(young / "config.json", 1, "{}")
    sc.run(tmp_path)
    assert not old.exists() and live.exists() and young.exists()


def test_ponytail_legacy_keys_and_launch_files(tmp_path):
    legacy = _put(tmp_path / "ponytail-modes/6dcc99ed-a957-4897-8e2e-5446b56602d4", 8, "full")
    current = _put(tmp_path / ("ponytail-modes/" + "a" * 64), 400, "full")
    sc.run(tmp_path)
    assert not legacy.exists() and current.exists()


def test_learning_rows_older_than_30_days_are_trimmed(tmp_path):
    now = time.time()
    rows = [{"ts": now - 40 * DAY, "tool": "a"}, {"ts": now - 1 * DAY, "tool": "b"}, {"tool": "no-ts"}]
    f = _put(tmp_path / "state/learning/repo-1/observations.jsonl", 0,
             "\n".join(json.dumps(r) for r in rows) + "\n")
    counts = sc.run(tmp_path, now=now)
    kept = [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines()]
    assert [r["tool"] for r in kept] == ["b", "no-ts"] and counts["learning"] == 1


def test_table_flag_matches_docstring():
    import subprocess
    import sys
    cp = subprocess.run([sys.executable, str(Path(sc.__file__)), "--table"], capture_output=True,
                        text=True, timeout=30)
    assert cp.returncode == 0 and cp.stdout.strip() and cp.stdout.strip() in sc.__doc__
    assert all(row[0] in cp.stdout for row in sc.RETENTION)
