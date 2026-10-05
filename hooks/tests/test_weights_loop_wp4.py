"""WP4 (audit 2026-10-05 B2-08 / J-04): the weights loop stops churning without input.

- skill-router-weight-updater never rewrites the TRACKED weights file when the
  computed weights did not change (only `generated_at` would have moved).
- weekly-retro-trigger runs only when the effectiveness file is newer than its last
  run, and only the updater (the report's output was captured and dropped).
- state-cleanup rotation never rewrites a file it would not shorten.
Plus state-cleanup retention in a temp dir (B2-15).
"""
from __future__ import annotations

import importlib.util
import io
import json
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


def test_updater_leaves_unchanged_weights_file_alone(tmp_path, monkeypatch):
    upd = _load("upd_wp4", "skill-router-weight-updater.py")
    eff = tmp_path / "skill-effectiveness.jsonl"
    eff.write_text("".join(json.dumps({"reminded": ["a"], "invoked": ["a"]}) + "\n" for _ in range(6)))
    out = tmp_path / "skill_router_weights.json"
    monkeypatch.setattr(upd, "EFFECTIVENESS_FILE", eff)
    monkeypatch.setattr(upd, "WEIGHTS_OUTPUT", out)
    monkeypatch.setattr(sys, "argv", ["upd"])
    assert upd.main() == 0
    first = out.read_text(encoding="utf-8")
    _age(out, 1)
    before = out.stat().st_mtime
    assert upd.main() == 0
    assert out.read_text(encoding="utf-8") == first and out.stat().st_mtime == before
    # new input that changes a weight is written
    with eff.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"reminded": ["b"], "invoked": []}) + "\n")
    assert upd.main() == 0
    assert "\"b\"" in out.read_text(encoding="utf-8")


def _trigger(tmp_path, monkeypatch):
    wrt = _load("wrt_wp4", "weekly-retro-trigger.py")
    monkeypatch.setattr(wrt, "_SIDECAR", tmp_path / ".weights-last-run")
    monkeypatch.setattr(wrt, "_EFFECTIVENESS", tmp_path / "skill-effectiveness.jsonl")
    calls = []
    monkeypatch.setattr(wrt.subprocess, "run", lambda cmd, **k: calls.append(Path(cmd[-1]).name))
    monkeypatch.delenv("CLAUDE_HOOK_DOCTOR", raising=False)
    return wrt, calls


def test_trigger_is_a_noop_without_new_input(tmp_path, monkeypatch):
    wrt, calls = _trigger(tmp_path, monkeypatch)
    side, eff = tmp_path / ".weights-last-run", tmp_path / "skill-effectiveness.jsonl"
    eff.write_text("{}\n")
    side.write_text("0")
    _age(eff, 20)
    _age(side, 10)            # stale run, but no input since it
    wrt._run_weight_loop_if_stale()
    assert calls == [] and abs(side.stat().st_mtime - (time.time() - 10 * 86400)) < 5
    eff.unlink()              # no input file at all
    wrt._run_weight_loop_if_stale()
    assert calls == []


def test_trigger_runs_only_the_updater_on_new_input(tmp_path, monkeypatch):
    wrt, calls = _trigger(tmp_path, monkeypatch)
    side, eff = tmp_path / ".weights-last-run", tmp_path / "skill-effectiveness.jsonl"
    side.write_text("0")
    _age(side, 10)
    eff.write_text("{}\n")    # newer than the last run
    wrt._run_weight_loop_if_stale()
    assert calls == ["skill-router-weight-updater.py"]


def _cleanup():
    return _load("sc_wp4", "tools/state-cleanup.py")


def test_rotate_never_rewrites_a_file_it_would_not_shorten(tmp_path, monkeypatch):
    sc = _cleanup()
    monkeypatch.setattr(sc, "_ROTATE_BYTES", 100)
    monkeypatch.setattr(sc, "_ROTATE_KEEP_LINES", 5)
    f = tmp_path / "eff.jsonl"
    f.write_text("x" * 60 + "\n" + "y" * 60 + "\n")   # over the byte cap, under the line cap
    _age(f, 3)
    before = f.stat().st_mtime
    assert sc._rotate(f) is False and f.stat().st_mtime == before
    f.write_text("".join(f"{i}\n" * 1 + "z" * 30 + "\n" for i in range(10)))
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
        f.write_text("{}")
    _age(old_state, 8)
    _age(old_tel, 15)
    _age(mode, 400)
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    sc.run(base)
    assert not old_state.exists() and new_state.exists()
    assert not old_tel.exists() and not residue.exists()
    assert mode.exists()
