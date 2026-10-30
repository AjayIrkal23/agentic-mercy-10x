"""WP4 (audit 2026-10-05 B2-08 / J-04) remainder: state-cleanup rotation never rewrites a
file it would not shorten, and retention runs in a temp base (B2-15). The weights loop
(updater, weekly trigger, effectiveness report, weights file) was deleted in the 2026-10
merge; its superset is scripts/skill_health.py (tests: tests/test_skill_health.py)."""
from __future__ import annotations

import importlib.util
import io
import os
import sys
import time
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, _HOOKS / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _age(p: Path, days: float) -> None:
    t = time.time() - days * 86400
    os.utime(p, (t, t))


def _cleanup():
    return _load("sc_wp4", "tools/state-cleanup.py")


def test_rotate_never_rewrites_a_file_it_would_not_shorten(tmp_path, monkeypatch):
    sc = _cleanup()
    monkeypatch.setattr(sc, "_ROTATE_BYTES", 100)
    monkeypatch.setattr(sc, "_ROTATE_KEEP_LINES", 5)
    f = tmp_path / "eff.jsonl"
    f.write_text("x" * 60 + "\n" + "y" * 60 + "\n", encoding="utf-8")   # over the byte cap, under the line cap
    _age(f, 3)
    before = f.stat().st_mtime
    assert sc._rotate(f) is False and f.stat().st_mtime == before
    f.write_text("".join(f"{i}\n" * 1 + "z" * 30 + "\n" for i in range(10)), encoding="utf-8")
    assert sc._rotate(f) is True and len(f.read_text(encoding="utf-8").splitlines()) == 5


def test_state_cleanup_retention_in_a_temp_base(tmp_path, monkeypatch):
    sc = _cleanup()
    base = tmp_path / "claude"
    st, tel = base / "hooks" / ".state", base / "hooks" / ".telemetry"
    for d in (st, tel, base / "state" / "model-modes", base / "telemetry"):
        d.mkdir(parents=True)
    old_state, new_state = st / "a.desloppify.json", st / "b.desloppify.json"
    old_tel, residue = tel / "s.pushed-skills.jsonl", tel / "x-e2e-1.json"
    mode = base / "state" / "model-modes" / "repo"
    for f in (old_state, new_state, old_tel, residue, mode):
        f.write_text("{}", encoding="utf-8")
    _age(old_state, 8)
    _age(old_tel, 15)
    _age(mode, 400)
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    sc.run(base)
    assert not old_state.exists() and new_state.exists()
    assert not old_tel.exists() and not residue.exists()
    assert mode.exists()
