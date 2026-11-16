"""OpenMontage checkout (2026-11-16): scripts/openmontage_engine.py and the doctor's video-skills row."""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "hooks", ROOT / "installer"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

_spec = importlib.util.spec_from_file_location("openmontage_engine_script", ROOT / "scripts" / "openmontage_engine.py")
om = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(om)  # type: ignore[union-attr]

import doctor_checks  # noqa: E402


def _cp(rc: int, out: str = "", err: str = ""):
    return types.SimpleNamespace(returncode=rc, stdout=out, stderr=err)


def _never(*a, **k):
    raise AssertionError(f"ran {a}")


def _home(tmp_path, monkeypatch) -> Path:
    h = tmp_path / "om"
    monkeypatch.setenv("OPENMONTAGE_HOME", str(h))
    monkeypatch.setattr(om.shutil, "which", lambda t: f"/usr/bin/{t}")
    return h


def test_ready_needs_the_stamp_and_the_pinned_head(tmp_path, monkeypatch):
    h = _home(tmp_path, monkeypatch)
    h.mkdir()
    monkeypatch.setattr(om, "head", lambda p: om.PIN)
    assert not om.ready(h)
    (h / om.STAMP).write_text(om.PIN + "\n", encoding="utf-8")
    assert om.ready(h)
    monkeypatch.setattr(om, "head", lambda p: "b" * 40)  # moved off the pin
    assert not om.ready(h)


def test_ready_checkout_runs_nothing(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    monkeypatch.setattr(om, "ready", lambda p=None: True)
    monkeypatch.setattr(om.plat, "run", _never)
    assert om.ensure() == (0, f"OK({om.PIN[:12]})")


def test_dry_run_plans_without_fetching(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    monkeypatch.setattr(om.plat, "run", _never)
    rc, line = om.ensure(dry=True)
    assert rc == 0 and line.startswith("WOULD-INSTALL")


def test_missing_tools_skip(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    monkeypatch.setattr(om.shutil, "which", lambda t: None if t == "make" else "/x")
    monkeypatch.setattr(om.plat, "run", _never)
    rc, line = om.ensure()
    assert rc == 3 and "make" in line and line.startswith("SKIP")


def test_dirty_checkout_is_left_alone(tmp_path, monkeypatch):
    h = _home(tmp_path, monkeypatch)
    (h / ".git").mkdir(parents=True)
    calls = []

    def run(cmd, **k):
        calls.append(cmd)
        if cmd[:2] == ["git", "rev-parse"]:
            return _cp(0, "b" * 40)
        if cmd[:2] == ["git", "status"]:
            return _cp(0, " M AGENT_GUIDE.md\n")
        raise AssertionError(f"ran {cmd}")

    monkeypatch.setattr(om.plat, "run", run)
    rc, line = om.ensure()
    assert rc == 3 and "local edits" in line
    assert not any(c[:2] == ["git", "checkout"] or c[0] == "make" for c in calls)


def test_setup_runs_make_in_its_own_venv_and_stamps(tmp_path, monkeypatch):
    h = _home(tmp_path, monkeypatch)
    (h / ".git").mkdir(parents=True)
    monkeypatch.setenv("VIRTUAL_ENV", "/some/other/venv")
    monkeypatch.setattr(om, "_checkout", lambda p: None)
    seen = {"setup": False, "restored": None}

    def run(cmd, **k):
        if cmd[:2] == ["git", "rev-parse"]:
            return _cp(0, om.PIN)
        if cmd[:2] == ["git", "diff"]:  # before setup: the user's own edit; after: npm rewrote the lock too
            return _cp(0, "AGENT_GUIDE.md\n" + ("remotion-composer/package-lock.json\n" if seen["setup"] else ""))
        if cmd[:2] == ["git", "checkout"]:
            seen["restored"] = cmd[4:]
            return _cp(0)
        assert cmd == ["make", "setup"] and k["cwd"] == h
        seen["env"], seen["setup"] = k["env"], True
        return _cp(0, "Done!")

    monkeypatch.setattr(om.plat, "run", run)
    assert om.ensure() == (0, f"INSTALLED({om.PIN[:12]})")
    assert "VIRTUAL_ENV" not in seen["env"]
    assert seen["restored"] == ["remotion-composer/package-lock.json"]  # the user's edit stays
    assert (h / om.STAMP).read_text(encoding="utf-8").strip() == om.PIN
    assert om.ready(h)


def test_failed_setup_skips_without_a_stamp(tmp_path, monkeypatch):
    h = _home(tmp_path, monkeypatch)
    h.mkdir()
    monkeypatch.setattr(om, "_checkout", lambda p: None)
    monkeypatch.setattr(om.plat, "run", lambda cmd, **k: _cp(2, "", "npm ERR! network"))
    rc, line = om.ensure()
    assert rc == 3 and "npm ERR! network" in line
    assert not (h / om.STAMP).exists()


def test_not_a_checkout_is_never_touched(tmp_path, monkeypatch):
    h = _home(tmp_path, monkeypatch)
    h.mkdir()
    (h / "mine.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(om.plat, "run", _never)
    rc, line = om.ensure()
    assert rc == 3 and "not a git checkout" in line
    assert (h / "mine.txt").exists()


def test_doctor_row_fails_without_the_vendored_skills(tmp_path):
    status, detail = doctor_checks.video_skills_status(tmp_path, ci=True)
    assert status == "FAIL" and "ffmpeg-skill" in detail


def test_doctor_row_passes_ci_with_the_skills(tmp_path):
    for s in doctor_checks.VIDEO_SKILLS:
        (tmp_path / "skills" / s).mkdir(parents=True)
        (tmp_path / "skills" / s / "SKILL.md").write_text("x", encoding="utf-8")
    assert doctor_checks.video_skills_status(tmp_path, ci=True)[0] == "PASS"
