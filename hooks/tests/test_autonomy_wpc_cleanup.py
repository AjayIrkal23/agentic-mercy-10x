"""WP-C (autonomy 2026-10-05) item 5: state-cleanup purges test-named residue and says so.

Residue measured read-only on the live dirs (2026-10-05): router manifests and
pushed-skills files of test sessions (audit-a3-*, ma-heavy-live-*, t11-*, t-iso-*,
dryrun-*, isg-*, t-<32hex>) and stack caches of fixture repos named go / vite / wt.
Seeds a temp base only; nothing here touches the real ~/.claude.
"""
from __future__ import annotations

import importlib.util
import json
import os
import time
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "state_cleanup_wpc", Path(__file__).resolve().parents[1] / "tools" / "state-cleanup.py")
sc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sc)

DAY = 86400.0
UUID = "6dcc99ed-a957-4897-8e2e-5446b56602d4"


def _put(path: Path, age_days: float, body: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    t = time.time() - age_days * DAY
    os.utime(path, (t, t))
    return path


TEST_SESSIONS = ["audit-a3-BE1-migration", "ma-heavy-live-1252405-1790764295475",
                 "ma-light-live-805006-1790569129850", "ma-heavy-shadow-426057-1790565582580",
                 "t11-shape-2915384-1791177806933", "t-iso-3-1790000000000",
                 "dryrun-rls-1790000000", "isg-fe1-1790000000", "t-0112d6ecbc5b4e70a93bba6c5cb929a8"]


def _old_test_files(base: Path) -> list[Path]:
    out = []
    for s in TEST_SESSIONS:
        out += [_put(base / f"state/{s}.router-manifest.json", 2),
                _put(base / f"hooks/.telemetry/{s}.pushed-skills.jsonl", 2),
                _put(base / f"hooks/.telemetry/{s}.suite-gate.json", 2)]
    return out


def test_old_test_named_session_files_are_purged(tmp_path):
    old = _old_test_files(tmp_path)
    sc.run(tmp_path)
    assert [p.name for p in old if p.exists()] == []


def test_fresh_test_named_files_survive_a_running_test(tmp_path):
    fresh = [_put(tmp_path / f"state/{s}.router-manifest.json", 0.2) for s in TEST_SESSIONS]
    sc.run(tmp_path)
    assert all(p.exists() for p in fresh)


def test_real_session_uuids_and_lookalikes_survive_at_any_age(tmp_path):
    keep = []
    for sid in (UUID, "0112d6ec-bc5b-4e70-a93b-ba6c5cb929a8", "a0df35e4-1111-2222-3333-444455556666"):
        keep += [_put(tmp_path / f"state/{sid}.router-manifest.json", 0.5),
                 _put(tmp_path / f"hooks/.telemetry/{sid}.agent-dispatches.jsonl", 3),
                 _put(tmp_path / f"hooks/.telemetry/{sid}.suite-gate.json", 3)]
    # names that merely start like a family but are not test sessions
    keep += [_put(tmp_path / "state/audit.router-manifest.json", 0.5),
             _put(tmp_path / "state/tool-use-1.router-manifest.json", 0.5),
             _put(tmp_path / "state/model-modes/audit-repo", 400),
             _put(tmp_path / "hooks/.telemetry/skill-effectiveness.jsonl", 3),
             _put(tmp_path / "state/ponytail-active", 400)]
    sc.run(tmp_path)
    assert [p.name for p in keep if not p.exists()] == []


@pytest.mark.parametrize("name", ["go-08a94529", "vite-fdccba1d", "wt-e1cfca00"])
def test_fixture_stack_caches_age_out_after_a_day_not_two_weeks(tmp_path, name):
    old = _put(tmp_path / f"state/{name}.stack.json", 2)
    new = _put(tmp_path / f"state/{name[:-1]}7.stack.json", 0.2)
    real = _put(tmp_path / "state/site-sync-vista-78b1653c.stack.json", 3)
    sc.run(tmp_path)
    assert not old.exists() and new.exists() and real.exists()


def test_purge_counts_per_family_are_logged(tmp_path):
    _old_test_files(tmp_path)
    _put(tmp_path / "state/go-08a94529.stack.json", 2)
    _put(tmp_path / "state/old.classification.json", 2)
    sc.run(tmp_path)
    log = tmp_path / "state" / "state-cleanup.log"
    rows = [json.loads(ln) for ln in log.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1 and rows[0]["ts"]
    purged = rows[0]["purged"]
    assert purged["test-session:audit"] == 3
    assert purged["test-session:ma"] == 9 and purged["test-session:t11"] == 3
    assert purged["test-session:t-hex"] == 3 and purged["stack:go"] == 1
    assert purged["classification"] == 1
    assert sum(purged.values()) == rows[0]["total"]


def test_nothing_purged_logs_nothing_and_the_log_survives_later_runs(tmp_path):
    sc.run(tmp_path)
    assert not (tmp_path / "state" / "state-cleanup.log").exists()
    _put(tmp_path / "state/audit-a3-x.router-manifest.json", 2)
    sc.run(tmp_path)
    _put(tmp_path / "state/audit-a3-y.router-manifest.json", 2)
    sc.run(tmp_path)
    log = tmp_path / "state" / "state-cleanup.log"
    assert len(log.read_text(encoding="utf-8").splitlines()) == 2
    assert log.exists() and (time.time() - log.stat().st_mtime) < DAY  # the cleanup never ages its own log
