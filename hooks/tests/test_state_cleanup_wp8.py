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


def test_unreadable_index_state_is_left_alone(tmp_path):
    bad = _put(tmp_path / "hooks/.state/index/bad-1.json", 40, "{not json")
    sc.run(tmp_path)
    assert bad.exists()
