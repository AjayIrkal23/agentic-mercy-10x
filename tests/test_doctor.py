"""test_doctor.py — the install-time doctor + its regression-detection.

Runs the doctor READ-ONLY: HOME and CLAUDE_CONFIG_DIR point at a tmp sandbox and
CLAUDE_HOOK_DOCTOR=1, so no dispatch link can touch the real ~/.claude. Asserts
the doctor is green on a faithful checkout and that link-doctor catches a
deliberately broken dispatch link.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

import live_interpreter

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks"), str(_ROOT / "hooks" / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, _ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore
    return mod


@pytest.fixture
def sandbox_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home / ".claude"))
    monkeypatch.setenv("CLAUDE_HOOK_DOCTOR", "1")
    live_interpreter.pin_tier(home, monkeypatch)  # FIX-r2 S3: this machine's tier, not a fallback
    # audit I-17: never depend on the installed claude CLI / tsc (offline, fresh clone)
    real_which = shutil.which
    monkeypatch.setattr(shutil, "which", lambda n, *a, **k: None if n in ("claude", "tsc") else real_which(n, *a, **k))
    return home


def test_doctor_is_green(sandbox_home, monkeypatch):
    live_interpreter.pin(monkeypatch)  # A7v2-03: the render compares the live file's interpreter, not pytest's
    doctor = _load("doctor", "installer/doctor.py")
    rows = doctor.run_doctor()
    fails = [(n, d) for n, s, d in rows if s == "FAIL"]
    assert not fails, f"doctor FAIL rows: {fails}"
    by = {n: s for n, s, _ in rows}
    for name in ("model-routing", "workflow-args", "hook-fixtures", "settings-safety",
                 "plugins-contract", "interpreters"):
        assert by.get(name) == "PASS", (name, by.get(name))
    # nothing machine-specific leaked in: sandbox has no ~/.claude.json / lean-ctx config
    assert by.get("mcp-roster") == "WARN"
    assert by.get("lean-ctx-config") in ("WARN", "PASS")
    assert by.get("statusline") in ("PASS", "SKIP")  # runs the rendered statusLine.command when settings.json exists


def test_workflows_rendered_row(tmp_path):
    """I10: the saved-workflow render is per machine and untracked; a missing or drifted render FAILs so
    self-heal rebuilds it."""
    import subprocess
    checks = _load("doctor_checks", "installer/doctor_checks.py")
    root = tmp_path / "root"
    shutil.copytree(_ROOT / "workflows" / "src", root / "workflows" / "src")
    (root / "scripts").mkdir()
    shutil.copy2(_ROOT / "scripts" / "build_workflows.py", root / "scripts" / "build_workflows.py")
    (root / "hooks").mkdir()
    shutil.copy2(_ROOT / "hooks" / "model-policy.json", root / "hooks" / "model-policy.json")
    st, det = checks.workflows_rendered_status(root, ci=False)
    assert st == "FAIL" and "not rendered" in det
    cp = subprocess.run([sys.executable, str(root / "scripts" / "build_workflows.py"), "--tier", "api", "--usage", "off",
                         "--out", str(root / "workflows"), "--quiet"], capture_output=True, text=True, timeout=120)
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert checks.workflows_rendered_status(root, ci=False)[0] == "PASS"
    with open(root / "workflows" / "review.js", "a", encoding="utf-8") as fh:
        fh.write("//x\n")
    st, det = checks.workflows_rendered_status(root, ci=False)
    assert st == "FAIL" and "DRIFT review.js" in det
    assert checks.workflows_rendered_status(root, ci=True)[0] == "SKIP"


def _routing_status(tmp_path, mutate) -> tuple[str, str]:
    checks = _load("doctor_checks", "installer/doctor_checks.py")
    policy = json.loads((_ROOT / "hooks" / "model-policy.json").read_text(encoding="utf-8"))
    mutate(policy)
    (tmp_path / "model-policy.json").write_text(json.dumps(policy), encoding="utf-8")
    rows: list = []
    checks.check_model_routing(rows, tmp_path, tmp_path, lambda r, n, s, d: r.append((n, s, d)),
                               None, sys.executable, "PASS", "FAIL", "WARN")
    return next((s, d) for n, s, d in rows if n == "model-routing")


def test_model_routing_accepts_judges_on_opus(tmp_path):
    assert _routing_status(tmp_path, lambda p: None)[0] == "PASS"


def test_model_routing_rejects_opus_pinned_implementor(tmp_path):
    def pin_impl(p):
        p["agent_pins"]["opus"].append("implementation-engineer")
    assert _routing_status(tmp_path, pin_impl)[0] == "FAIL"


def test_model_routing_rejects_unpinned_judge(tmp_path):
    def unpin_santa(p):
        p["agent_pins"]["opus"].remove("santa-reviewer")
    assert _routing_status(tmp_path, unpin_santa)[0] == "FAIL"


def test_doctor_ci_skips_machine_rows(sandbox_home):
    doctor = _load("doctor", "installer/doctor.py")
    by = {n: s for n, s, _ in doctor.run_doctor(ci=True)}
    assert by["mcp-roster"] == "SKIP" and by["lean-ctx-config"] == "SKIP"


def test_doctor_ci_and_doctor_mode_skip_the_oomguard_rows(sandbox_home):
    doctor = _load("doctor", "installer/doctor.py")
    for ci in (True, False):                       # sandbox_home sets CLAUDE_HOOK_DOCTOR=1
        by = {n: (s, d) for n, s, d in doctor.run_doctor(ci=ci)}
        for name in ("oom-policy", "memwatch-unit", "memwatch-code", "restore-unit", "claude-launcher",
                     "launcher-model", "launch-caps", "attach-live"):
            assert by[name][0] == "SKIP", (name, by[name])


def test_doctor_help_runs_no_check(monkeypatch, capsys):
    """RT-9: `doctor.py --help` prints usage and exits 0 without running a single probe."""
    doctor = _load("doctor", "installer/doctor.py")
    monkeypatch.setattr(doctor, "run_doctor", lambda **k: pytest.fail("a check ran"))
    with pytest.raises(SystemExit) as e:
        doctor.main(["--help"])
    assert e.value.code == 0 and "--ci" in capsys.readouterr().out


def test_link_doctor_detects_a_broken_link(tmp_path):
    ld = _load("link_doctor", "hooks/tools/link-doctor.py")
    # a minimal dispatch config whose one GATE link emits NON-JSON garbage -> FAIL
    broken = {
        "chains": {
            "pre-tool-use": [
                {"id": "broken-gate", "type": "gate", "tools": "Bash",
                 "cmd": [sys.executable, "-c", "print('garbage-not-json')"], "enabled": True}
            ]
        }
    }
    cfg = tmp_path / "dispatch.config.json"
    cfg.write_text(json.dumps(broken))
    ld._CONFIG = cfg  # point link-doctor at the broken config
    passed, failed, rows = ld.run_doctor()
    assert failed >= 1, f"expected a FAIL row, got {rows}"
    assert any("broken-gate" in r[1] and r[2].startswith("FAIL") for r in rows)
