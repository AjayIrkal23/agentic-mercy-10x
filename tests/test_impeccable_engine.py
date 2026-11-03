"""Install path of the design trio (2026-11-03): scripts/impeccable_engine.py and the doctor's design-trio row."""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "hooks", ROOT / "installer"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from lib import impeccable_engine as eng  # noqa: E402

_spec = importlib.util.spec_from_file_location("impeccable_engine_script", ROOT / "scripts" / "impeccable_engine.py")
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)  # type: ignore[union-attr]

import doctor_checks  # noqa: E402


def _cp(rc: int, out: str = "", err: str = ""):
    return types.SimpleNamespace(returncode=rc, stdout=out, stderr=err)


def test_cached_engine_is_ok_without_running_anything(monkeypatch):
    monkeypatch.setattr(script.eng, "cached_binary", lambda *a: Path("/x/impeccable"))
    monkeypatch.setattr(script.plat, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("ran")))
    assert script.ensure() == (0, f"OK(cached {eng.version()})")


def test_missing_engine_dry_run_plans_the_fetch(monkeypatch):
    monkeypatch.setattr(script.eng, "cached_binary", lambda *a: None)
    rc, line = script.ensure(dry=True)
    assert rc == 0 and line.startswith("WOULD-FETCH")


def test_fetch_runs_the_vendored_launcher_once(monkeypatch):
    state = {"cached": None, "argv": None}
    monkeypatch.setattr(script.eng, "cached_binary", lambda *a: state["cached"])

    def run(argv, **kw):
        state["argv"], state["cached"] = argv, Path("/x/impeccable")
        return _cp(0, "impeccable-engine 0.1.18")

    monkeypatch.setattr(script.plat, "run", run)
    rc, line = script.ensure()
    assert rc == 0 and line.startswith("INSTALLED")
    assert state["argv"][-1] == "engine-probe" and "impeccable" in state["argv"][-2]


def test_failed_fetch_is_a_skip_with_the_reason(monkeypatch):
    monkeypatch.setattr(script.eng, "cached_binary", lambda *a: None)
    monkeypatch.setattr(script.plat, "run", lambda *a, **k: _cp(1, "", "Engine 0.1.18 setup needs network access"))
    rc, line = script.ensure()
    assert rc == 3 and "needs network access" in line and line.startswith("SKIP")


def test_check_mode_never_downloads(monkeypatch, capsys):
    monkeypatch.setattr(script.eng, "cached_binary", lambda *a: None)
    monkeypatch.setattr(script.plat, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("ran")))
    assert script.main(["--check"]) == 1
    assert "MISSING" in capsys.readouterr().out


def test_launcher_argv_matches_the_os(monkeypatch, tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "impeccable").write_text("#!/bin/sh\n", encoding="utf-8")
    (tmp_path / "scripts" / "impeccable.cmd").write_text("@echo off\n", encoding="utf-8")
    monkeypatch.setattr(eng.os, "name", "posix")
    assert eng.launcher_argv(tmp_path) == ["sh", str(tmp_path / "scripts" / "impeccable")]
    monkeypatch.setattr(eng.os, "name", "nt")
    assert eng.launcher_argv(tmp_path) == [str(tmp_path / "scripts" / "impeccable.cmd")]


def test_doctor_row_fails_on_a_missing_skill_and_warns_on_a_missing_engine(tmp_path, monkeypatch):
    assert doctor_checks.design_trio_status(tmp_path)[0] == "FAIL"
    for s in doctor_checks.DESIGN_TRIO:
        (tmp_path / "skills" / s).mkdir(parents=True)
        (tmp_path / "skills" / s / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
    assert doctor_checks.design_trio_status(tmp_path, ci=True)[0] == "PASS"
    monkeypatch.setattr(eng, "cached_binary", lambda *a: None)
    status, detail = doctor_checks.design_trio_status(tmp_path)
    assert status == "WARN" and "not cached" in detail
    monkeypatch.setattr(eng, "cached_binary", lambda *a: Path("/x/impeccable"))
    monkeypatch.setattr("lib.platform.node_exe", lambda: "/usr/bin/node")
    assert doctor_checks.design_trio_status(tmp_path)[0] == "PASS"
