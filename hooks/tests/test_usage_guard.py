"""lib/usage_guard.py: the 5-hour-window step-down (MERGE-PLAN R3.3). Newest fresh bridge file wins,
80/70 hysteresis, resets_at clears, state file written only on a flip, the per-tier step-down table,
fable paused, fail-open on bad input, saved workflows regenerated on a flip."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]
ROOT = HOOKS.parent
sys.path.insert(0, str(HOOKS))
sys.path.insert(0, str(ROOT / "tests" / "fixtures" / "plan-tier"))
from lib import usage_guard as UG  # noqa: E402
import tier_fixture as TF  # noqa: E402

NOW = 1_800_000_000.0


@pytest.fixture(autouse=True)
def _clean():
    TF.set_tier("max20")
    TF.set_usage(None)
    yield
    TF.clear()


def test_inactive_without_bridge():
    assert UG.state(NOW) == {"active": False, "pct": None, "resets_at": None, "flipped": False}


def test_newest_bridge_file_wins_and_old_ones_are_ignored():
    TF.set_usage(85.0, NOW + 3600, sid="old", age_s=30)
    TF.set_usage(40.0, NOW + 3600, sid="new", age_s=1)
    assert UG.state(NOW)["pct"] == 40.0
    TF.set_usage(None)
    TF.set_usage(90.0, NOW + 3600, sid="stale", age_s=1200)  # > max_age_s (600) -> ignored
    assert UG.state(NOW)["pct"] is None and UG.state(NOW)["active"] is False


def test_hysteresis_80_on_70_off():
    TF.set_usage(79.9, NOW + 3600)
    assert UG.state(NOW)["active"] is False
    TF.set_usage(80.0, NOW + 3600)
    s = UG.state(NOW)
    assert s["active"] and s["flipped"]
    TF.set_usage(75.0, NOW + 3600)
    s = UG.state(NOW)
    assert s["active"] and not s["flipped"]  # between 70 and 80: stays
    TF.set_usage(69.9, NOW + 3600)
    s = UG.state(NOW)
    assert not s["active"] and s["flipped"]


def test_resets_at_clears_even_while_pct_is_high():
    TF.set_usage(95.0, NOW - 1)
    assert UG.state(NOW)["active"] is False
    TF.set_usage(95.0, NOW + 1)
    assert UG.state(NOW)["active"] is True


@pytest.mark.parametrize("stamp", [NOW + 60, (NOW + 60) * 1000, "2027-01-15T10:00:00Z", "2027-01-15T10:00:00+00:00"])
def test_resets_at_accepts_seconds_ms_and_iso(stamp):
    TF.set_usage(90.0, stamp)
    assert UG.state(NOW)["active"] is True and UG.state(NOW)["resets_at"] > NOW


def test_state_file_written_only_on_flip():
    TF.set_usage(90.0, NOW + 3600)
    UG.state(NOW)
    p = TF.state_dir() / "usage-guard.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["active"] is True and d["five_hour_pct"] == 90.0 and d["since"] == NOW
    assert d["tier"] == "max20" and d["schema"] == 1
    m = p.stat().st_mtime_ns
    UG.state(NOW + 10)
    assert p.stat().st_mtime_ns == m  # no rewrite without a flip
    TF.set_usage(10.0, NOW + 3600)
    UG.state(NOW + 20)
    assert json.loads(p.read_text(encoding="utf-8"))["active"] is False


def test_no_fresh_bridge_keeps_active_until_resets_at():
    TF.set_usage(None)
    (TF.state_dir() / "usage-guard.json").write_text(json.dumps(
        {"schema": 1, "active": True, "five_hour_pct": 90.0, "resets_at": NOW + 3600, "since": NOW, "tier": "max20"}),
        encoding="utf-8")
    assert UG.state(NOW + 100)["active"] is True  # stored state carries while the window has not reset
    assert UG.state(NOW + 4000)["active"] is False  # past resets_at -> cleared


@pytest.mark.parametrize("tier,model,role,want", [
    ("max20", "opus", "impl", "sonnet"), ("max20", "sonnet", "impl", "haiku"), ("max20", "haiku", "docs", "haiku"),
    ("max20", "opus", "judge", "sonnet"), ("max20", "fable", "judge", "sonnet"), ("max20", "fable", "impl", "sonnet"),
    ("max5", "sonnet", "impl", "haiku"), ("max5", "sonnet", "judge", "sonnet"), ("max5", "opus", "judge", "sonnet"),
    ("pro", "sonnet", "impl", "haiku"), ("pro", "sonnet", "judge", "haiku"), ("pro", "haiku", "explore", "haiku"),
    ("api", "sonnet", "test", "haiku"), ("max20", "gpt", "impl", "gpt"),
    # the guard never raises a judge's model (a haiku per-project pin stays haiku)
    ("max20", "haiku", "judge", "haiku"), ("max5", "haiku", "judge", "haiku")])
def test_step_down_table(tier, model, role, want):
    assert UG.step_down(model, role, tier) == want


def test_step_down_fail_open_without_policy():
    assert UG.step_down("opus", "impl", "max20", {}) == "sonnet"
    assert UG.step_down("sonnet", "judge", "pro", {}) == "haiku"


def test_fail_open_on_bad_bridge_json():
    b = TF.state_dir() / "session-bridge"
    b.mkdir(exist_ok=True)
    (b / "x.json").write_text("{ nope", encoding="utf-8")
    assert UG.state(NOW)["active"] is False


def test_bridge_without_pct_never_activates():  # API-key users: statusline gets no rate_limits
    b = TF.state_dir() / "session-bridge"
    b.mkdir(exist_ok=True)
    (b / "x.json").write_text(json.dumps({"sid": "x"}), encoding="utf-8")
    assert UG.state(NOW) == {"active": False, "pct": None, "resets_at": None, "flipped": False}


def test_regenerate_called_on_flip_when_builder_exists(monkeypatch, tmp_path):
    builder = tmp_path / "build_workflows.py"
    builder.write_text("# fake\n", encoding="utf-8")
    calls = []
    monkeypatch.setattr(UG, "_builder_path", lambda: builder)
    monkeypatch.setattr(UG, "_spawn", lambda cmd: calls.append(cmd))
    TF.set_usage(90.0, NOW + 3600)
    UG.state(NOW)
    assert len(calls) == 1 and calls[0][-1] == str(builder)
    UG.state(NOW + 5)
    assert len(calls) == 1  # same state -> no call
    TF.set_usage(10.0, NOW + 3600)
    UG.state(NOW + 10)
    assert len(calls) == 2
    monkeypatch.setattr(UG, "_builder_path", lambda: tmp_path / "absent.py")
    TF.set_usage(95.0, NOW + 3600)
    UG.state(NOW + 20)
    assert len(calls) == 2  # no builder -> no spawn
