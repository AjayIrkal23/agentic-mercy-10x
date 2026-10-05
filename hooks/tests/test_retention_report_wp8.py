"""retention-report: read-only list of reclaimable space (audit J-07, J-08, J-13,
G-10, G-15). Builds a fake ~/.claude + index layout under tmp_path.
Runnable: `python3 -m pytest hooks/tests/test_retention_report_wp8.py -q`.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import time
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "retention_report", Path(__file__).resolve().parents[1] / "tools" / "retention-report.py")
rr = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rr)

DAY = 86400.0


def _file(p: Path, body: str = "x" * 100, age_days: float = 0) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    t = time.time() - age_days * DAY
    os.utime(p, (t, t))
    return p


def _db(p: Path, source_root: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p))
    con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO meta VALUES ('source_root', ?)", (source_root,))
    con.commit()
    con.close()


def _layout(tmp: Path) -> dict:
    claude, docs, code = tmp / "claude", tmp / "doc-index" / "local", tmp / "code-index"
    live_repo = tmp / "repo"
    live_repo.mkdir()
    live = claude / "plugins/cache/mk/plug/2.0.0"
    _file(live / "plugin.json")
    _file(claude / "plugins/cache/mk/plug/1.0.0/plugin.json")            # orphan version
    _file(claude / "plugins/installed_plugins.json",
          json.dumps({"plugins": {"plug@mk": [{"installPath": str(live)}]}}))
    _file(claude / "graphify-out/graph.json")                              # frozen duplicate
    _file(claude / "projects/-old-proj/a.jsonl", age_days=90)              # stale transcripts
    _file(claude / "projects/-live-proj/b.jsonl", age_days=1)
    _file(claude / "projects/-mem-proj/c.jsonl", age_days=90)              # old, but holds memory
    _file(claude / "projects/-mem-proj/memory/MEMORY.md", age_days=90)
    _file(docs / "gone.json", json.dumps({"x": 1, "source_root": "/tmp/e2e/gone"}))
    _file(docs / "gone.related.json")
    _file(docs / "alive.json", json.dumps({"source_root": str(live_repo)}))
    _db(code / "local-gone.db", "/nonexistent/repo")
    _db(code / "local-alive.db", str(live_repo))
    return {"claude": claude, "docs": docs, "code": code}


def test_lists_only_reclaimable_items(tmp_path):
    lay = _layout(tmp_path)
    rows = rr.report(lay["claude"], lay["docs"], lay["code"], keep_days=30)
    paths = {str(r[1]) for r in rows}
    assert str(lay["claude"] / "plugins/cache/mk/plug/1.0.0") in paths
    assert str(lay["claude"] / "graphify-out") in paths
    assert str(lay["claude"] / "projects/-old-proj") in paths
    assert any(p.endswith("gone.json") for p in paths)
    assert any(p.endswith("local-gone.db") for p in paths)
    assert not any("2.0.0" in p or "-live-proj" in p or "-mem-proj" in p or "alive" in p
                   for p in paths), paths


def test_never_deletes_anything(tmp_path):
    lay = _layout(tmp_path)
    before = sorted(str(p) for p in tmp_path.rglob("*"))
    rr.report(lay["claude"], lay["docs"], lay["code"], keep_days=30)
    rr.main(["--claude-dir", str(lay["claude"]), "--doc-index", str(lay["docs"]),
             "--code-index", str(lay["code"])])
    assert sorted(str(p) for p in tmp_path.rglob("*")) == before
