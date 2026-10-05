"""WP4 (audit 2026-10-05): teammate-idle-gate (B2-13), the retired fullstack stop
mode (B2-14), and dedicated tests for subagent-context and the permissions self-heal
(B2-15). Everything runs in temp dirs; nothing touches the live settings or state.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, _HOOKS / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _stdout(fn, payload, monkeypatch, *args) -> dict:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    buf = io.StringIO()
    with redirect_stdout(buf):
        fn(*args)
    out = buf.getvalue().strip()
    return json.loads(out.splitlines()[-1]) if out else {}


# --------------------------------------------------------------------------- B2-13
def _run_folder(base: Path, name: str, expected: dict, age_s: float = 0) -> Path:
    run = base / ".claude" / "runs" / name
    run.mkdir(parents=True)
    rj = run / "run.json"
    rj.write_text(json.dumps({"expected_artifacts": expected}))
    t = time.time() - age_s
    os.utime(rj, (t, t))
    return run


def test_teammate_found_in_an_older_run_when_the_newest_does_not_expect_it(tmp_path):
    tig = _load("tig_wp4", "teammate-idle-gate.py")
    _run_folder(tmp_path, "a", {"impl-be": "IMPL-BE.md"}, age_s=600)
    _run_folder(tmp_path, "b", {"impl-fe": "IMPL-FE.md"})          # newest, other teammate
    hit = tig.missing_artifact({"teammate_name": "impl-be", "cwd": str(tmp_path)})
    assert hit and hit[1] == "IMPL-BE.md" and "/a/" in hit[2].replace("\\", "/")  # native path


def test_newest_run_that_expects_the_teammate_wins(tmp_path):
    tig = _load("tig_wp4", "teammate-idle-gate.py")
    _run_folder(tmp_path, "old", {"impl-be": "OLD.md"}, age_s=600)  # stale, never written
    new = _run_folder(tmp_path, "new", {"impl-be": "NEW.md"})
    (new / "NEW.md").write_text("x")
    assert tig.missing_artifact({"teammate_name": "impl-be", "cwd": str(tmp_path)}) is None


# --------------------------------------------------------------------------- B2-14
def test_fullstack_reminder_stop_mode_is_gone(tmp_path, monkeypatch):
    fsr = _load("fsr_wp4", "fullstack-skills-reminder.py")
    for dead in ("_stop", "_write_effectiveness_record", "_stop_skill_reminder_lines",
                 "_remember_stop_skills", "QUALITY_SKILLS", "SHIPPING_SKILLS"):
        assert not hasattr(fsr, dead), dead
    monkeypatch.setenv("CLAUDE_HOOK_TELEMETRY_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["fsr", "stop"])
    assert _stdout(fsr.main, {"session_id": "s"}, monkeypatch) == {}
    assert not (tmp_path / "skill-effectiveness.jsonl").exists()


# --------------------------------------------------------------------------- B2-15
def test_subagent_context_carries_the_protocol_within_budget(monkeypatch):
    sc = _load("sac_wp4", "subagent-context.py")
    out = _stdout(sc.main, {"agent_type": "x", "cwd": "/nonexistent"}, monkeypatch)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "SubagentStart"
    assert "FILE ACCESS PROTOCOL" in ctx and "git commit" in ctx and "MCP PROTOCOL" in ctx
    assert len(ctx) <= 1800


def test_subagent_context_fails_open_on_garbage(monkeypatch):
    sc = _load("sac_wp4", "subagent-context.py")
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
    buf = io.StringIO()
    with redirect_stdout(buf):
        assert sc.main() == 0
    assert buf.getvalue().strip() == "{}"


def _selfheal(tmp_path, monkeypatch, live_deny, tmpl_deny):
    sh = _load("sph_wp4", "settings-permissions-selfheal.py")
    live, tmpl = tmp_path / "settings.json", tmp_path / "settings.template.json"
    live.write_text(json.dumps({"env": {"K": "v"}, "permissions": {"deny": live_deny}}))
    tmpl.write_text(json.dumps({"permissions": {"deny": tmpl_deny}}))
    monkeypatch.setattr(sh, "LIVE", live)
    monkeypatch.setattr(sh, "TEMPLATE", tmpl)
    monkeypatch.delenv("CLAUDE_HOOK_DOCTOR", raising=False)
    return sh, live


def test_selfheal_repairs_only_a_drifted_deny_list(tmp_path, monkeypatch):
    sh, live = _selfheal(tmp_path, monkeypatch, ["Read"], [])
    out = _stdout(sh.main, {}, monkeypatch, ["session-start"])
    assert json.loads(live.read_text(encoding="utf-8")) == {"env": {"K": "v"}, "permissions": {"deny": []}}
    assert "Read" in out["hookSpecificOutput"]["additionalContext"]
    before = live.stat().st_mtime_ns
    assert _stdout(sh.main, {}, monkeypatch, ["session-start"]) == {}   # in sync: silent
    assert live.stat().st_mtime_ns == before


def test_selfheal_config_change_heals_and_blocks(tmp_path, monkeypatch):
    sh, live = _selfheal(tmp_path, monkeypatch, ["Grep"], [])
    out = _stdout(sh.main, {}, monkeypatch, ["config-change"])
    assert out["decision"] == "block"
    assert json.loads(live.read_text(encoding="utf-8"))["permissions"]["deny"] == []


def test_selfheal_doctor_mode_writes_nothing(tmp_path, monkeypatch):
    sh, live = _selfheal(tmp_path, monkeypatch, ["Read"], [])
    monkeypatch.setenv("CLAUDE_HOOK_DOCTOR", "1")
    assert _stdout(sh.main, {}, monkeypatch, ["session-start"]) == {}
    assert json.loads(live.read_text(encoding="utf-8"))["permissions"]["deny"] == ["Read"]
