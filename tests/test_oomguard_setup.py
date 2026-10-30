"""test_oomguard_setup.py — installer/oomguard_setup.ensure() and installer/doctor_oomguard.rows(), all seams faked.
attach_live() cases live in tests/test_oomguard_integration.py (unit section)."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "installer"), str(ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import doctor_oomguard as doc  # noqa: E402
import oomguard_setup as og  # noqa: E402
from lib import platform as plat  # noqa: E402

LEAN = "# >>> lean-ctx agent aliases >>>\nalias claude='LEAN_CTX_AGENT=1 claude'\n# <<< lean-ctx agent aliases <<<\nexport PATH=\"$HOME/.local/bin:$PATH\"\n"
MUTATING = ("daemon-reload", "enable", "disable", "start", "try-restart", "busctl")


class FakeRun:
    """Records every command; answers systemctl verbs from ``answers`` ({verb or 'show:<unit>': stdout})."""

    def __init__(self, **answers):
        self.calls, self.answers, self.rc = [], answers, answers.pop("rc", 0)

    def __call__(self, cmd, timeout=None, **_):
        self.calls.append(list(cmd))
        if cmd[:2] == ["systemctl", "--user"] and cmd[2] in ("is-enabled", "is-active"):
            out = self.answers.get(f"{cmd[2]}:{cmd[3]}", "disabled" if cmd[2] == "is-enabled" else "inactive")
        elif cmd[:3] == ["systemctl", "--user", "show"]:
            key = "default" if cmd[3] == "-p" else f"show:{cmd[3]}"
            out = self.answers.get(key, "stop")
            out = f"{cmd[-1]}={out}"
        else:
            out = self.answers.get(cmd[0], "")
        return subprocess.CompletedProcess(cmd, self.rc if cmd[0] == "busctl" else 0, out + "\n", "")

    def mutating(self):
        return [c for c in self.calls if any(m in c for m in MUTATING)]


@pytest.fixture
def box(tmp_path):
    root = tmp_path / "root"
    shutil.copytree(ROOT / "hooks" / "tools" / "oomguard", root / "hooks" / "tools" / "oomguard")
    (root / "scripts").mkdir()
    (root / "scripts" / "restore_sessions.py").write_text("", encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()
    (home / ".zshrc").write_text("# mine\n" + LEAN, encoding="utf-8")
    (home / ".bashrc").write_text(LEAN.rstrip("\n"), encoding="utf-8")  # no trailing newline
    (tmp_path / "proc").mkdir()
    return root, home, tmp_path / "proc"


def _ensure(box, dry=False, run=None, **kw):
    root, home, proc = box
    run = run or FakeRun()
    return og.ensure(dry, home=home, run=run, which=lambda n: "/usr/bin/" + n, bus=Path("/bus"), root=root,
                     proc_root=proc, **kw), run


def _snapshot(home):
    return {p: p.read_bytes() for p in sorted(home.rglob("*")) if p.is_file()}


def test_fresh_home_creates_everything(box):
    root, home, _ = box
    rows, run = _ensure(box)
    for want in ("drop-in 10-oom.conf: CREATED", "unit claude-memwatch.service: CREATED",
                 "unit claude-restore.service: CREATED", "systemctl daemon-reload: OK", "claude-memwatch: ENABLED",
                 "claude-restore: ENABLED", ".zshrc: APPENDED PATH block", ".bashrc: APPENDED PATH block"):
        assert want in rows, (want, rows)
    unit = (home / ".config" / "systemd" / "user" / "claude-memwatch.service").read_text(encoding="utf-8")
    assert f"ExecStart={plat.python_exe()} {root / 'hooks'}/tools/memwatch.py" in unit and "{" not in unit
    restore = (home / ".config" / "systemd" / "user" / "claude-restore.service").read_text(encoding="utf-8")
    assert "\nKillMode=process\n" in restore  # the tmux server restore starts must outlive the oneshot
    for rc in (".zshrc", ".bashrc"):
        text = (home / rc).read_text(encoding="utf-8")
        assert text.endswith(og.path_block()) and text.index(og.BEGIN) > text.index("# <<< lean-ctx agent aliases <<<")
    assert "\n\n" + og.BEGIN in (home / ".bashrc").read_text(encoding="utf-8")
    assert ["systemctl", "--user", "enable", "--now", "claude-memwatch"] in run.calls


def test_second_run_is_idempotent(box):
    _, home, _ = box
    _ensure(box)
    before = _snapshot(home)
    rows, run = _ensure(box, run=FakeRun(**{"is-enabled:claude-memwatch": "enabled", "is-active:claude-memwatch": "active",
                                           "is-enabled:claude-restore": "enabled"}))
    assert all(r.split(": ", 1)[1].startswith(("PRESENT", "OK")) for r in rows), rows
    assert _snapshot(home) == before and not run.mutating()


def test_user_files_are_kept(box):
    _, home, _ = box
    drop = home / ".config" / "systemd" / "user.conf.d" / "10-oom.conf"
    unit = home / ".config" / "systemd" / "user" / "claude-memwatch.service"
    for p, body in ((drop, "[Manager]\nDefaultOOMPolicy=kill\n"), (unit, "[Service]\nExecStart=/bin/true\n")):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    rows, _ = _ensure(box)
    assert "drop-in 10-oom.conf: KEPT (user file differs; wanted DefaultOOMPolicy=continue)" in rows
    assert "unit claude-memwatch.service: KEPT (user unit)" in rows
    assert drop.read_text(encoding="utf-8").endswith("kill\n") and "true" in unit.read_text(encoding="utf-8")


def test_our_stale_unit_is_updated(box):
    _, home, _ = box
    unit = home / ".config" / "systemd" / "user" / "claude-memwatch.service"
    unit.parent.mkdir(parents=True)
    unit.write_text("# agentic-mercy oomguard old\n", encoding="utf-8")
    assert "unit claude-memwatch.service: UPDATED" in _ensure(box)[0]


_LIVE_UNITS = {"is-enabled:claude-memwatch": "enabled", "is-active:claude-memwatch": "active",
               "is-enabled:claude-restore": "enabled"}


def test_updated_unit_restarts_an_active_memwatch(box):
    _, home, _ = box
    unit = home / ".config" / "systemd" / "user" / "claude-memwatch.service"
    unit.parent.mkdir(parents=True)
    unit.write_text("# agentic-mercy oomguard old\n", encoding="utf-8")
    rows, run = _ensure(box, dry=True, run=FakeRun(**_LIVE_UNITS))
    assert "unit claude-memwatch.service: WOULD-UPDATE" in rows and "claude-memwatch: WOULD-RESTART" in rows
    assert not run.mutating()
    rows, run = _ensure(box, run=FakeRun(**_LIVE_UNITS))
    assert "unit claude-memwatch.service: UPDATED" in rows and "claude-memwatch: RESTARTED" in rows
    reload_i = run.calls.index(["systemctl", "--user", "daemon-reload"])
    assert run.calls.index(["systemctl", "--user", "try-restart", "claude-memwatch"]) > reload_i
    rows, run = _ensure(box, run=FakeRun(**_LIVE_UNITS))           # unchanged -> no restart
    assert "claude-memwatch: OK" in rows and not run.mutating()


def test_created_unit_under_a_running_service_restarts_it(box):
    rows, run = _ensure(box, run=FakeRun(**_LIVE_UNITS))
    assert "unit claude-memwatch.service: CREATED" in rows and "claude-memwatch: RESTARTED" in rows


def test_restore_disabled_by_flag(box):
    _, home, _ = box
    (home / ".claude").mkdir()
    (home / ".claude" / "oomguard.local.json").write_text(json.dumps({"restore_enabled": False}), encoding="utf-8")
    rows, run = _ensure(box, run=FakeRun(**{"is-enabled:claude-restore": "enabled"}))
    assert "claude-restore: DISABLED" in rows and ["systemctl", "--user", "disable", "--now", "claude-restore"] in run.calls


def test_restore_script_absent(box):
    root, _, _ = box
    (root / "scripts" / "restore_sessions.py").unlink()
    assert "claude-restore: SKIP(restore_sessions.py absent)" in _ensure(box)[0]


def test_dry_run_changes_nothing(box):
    _, home, _ = box
    before = _snapshot(home)
    rows, run = _ensure(box, dry=True)
    assert all(r.split(": ", 1)[1].startswith("WOULD-") for r in rows), rows
    assert _snapshot(home) == before and not run.mutating()


def test_no_manager_or_windows_touches_nothing(box, monkeypatch):
    root, home, proc = box
    before = _snapshot(home)
    assert og.ensure(False, home=home, run=FakeRun(), bus=None, root=root, proc_root=proc) == [og.NO_MANAGER]
    monkeypatch.setattr(og.plat, "IS_WINDOWS", True)
    assert _ensure(box)[0] == [og.NO_MANAGER] and _snapshot(home) == before


def test_missing_rc_is_never_created(box):
    _, home, _ = box
    (home / ".zshrc").unlink()
    assert ".zshrc: SKIP(absent)" in _ensure(box)[0] and not (home / ".zshrc").exists()


def test_rendered_units_verify(box, tmp_path):
    if not shutil.which("systemd-analyze") or plat.systemd_user_bus() is None:
        pytest.skip("systemd-analyze or a user manager missing")
    _, home, _ = box
    _ensure(box)
    units = sorted(str(p) for p in (home / ".config" / "systemd" / "user").glob("*.service"))
    p = subprocess.run(["systemd-analyze", "--user", "verify", *units], capture_output=True, text=True, timeout=60)
    errors = [ln for ln in p.stderr.splitlines() if "claude-" in ln and "Documentation" not in ln]
    assert p.returncode == 0 or not errors, p.stderr


# ---- doctor_oomguard -------------------------------------------------------------------------------
def _rows(box, run, **kw):
    root, home, proc = box
    which = kw.pop("which", lambda n: "/usr/bin/" + n)
    return {n: (s, d) for n, s, d in doc.rows(root, run=run, which=which, home=home, bus=Path("/bus"),
                                                proc_root=proc, **kw)}


def test_doctor_before_install(box):
    r = _rows(box, FakeRun(zsh="/h/.local/bin/claude", bash="/h/.claude/bin/claude"))
    assert r["oom-policy"] == ("FAIL", "DefaultOOMPolicy=stop (run installer/oomguard_setup.py --apply)")
    assert r["memwatch-unit"][0] == "FAIL" and "unit missing" in r["memwatch-unit"][1]
    assert r["restore-unit"][0] == "WARN" and r["launch-caps"][0] == "WARN"
    assert r["claude-launcher"][0] == "WARN" and "zsh resolves claude to /h/.local/bin/claude" in r["claude-launcher"][1]
    assert r["attach-live"][0] == "PASS"


def test_doctor_after_install(box, monkeypatch, tmp_path):
    _ensure(box)
    monkeypatch.setattr(doc.plat, "cgroup_of", lambda pid, root="/proc": "app-x.scope")
    caps = plat.state_dir() / "launch-caps"
    caps.mkdir(parents=True, exist_ok=True)
    (caps / "1.json").write_text(json.dumps({"workflow_agents": 4, "subagents": 5, "size_guideline": "medium"}),
                                 encoding="utf-8")
    ok = {"default": "continue", "show:app-x.scope": "continue", "is-active:claude-memwatch": "active",
          "is-enabled:claude-memwatch": "enabled", "is-enabled:claude-restore": "enabled",
          "zsh": "/h/.claude/bin/claude", "bash": "/h/.claude/bin/claude"}
    r = _rows(box, FakeRun(**ok))
    assert {n: s for n, (s, _) in r.items()} == dict.fromkeys(doc.NAMES, "PASS"), r
    assert r["launch-caps"][1].startswith("wf4 sub5 medium")
    r = _rows(box, FakeRun(**{**ok, "show:app-x.scope": "stop"}))
    assert r["oom-policy"][0] == "WARN" and "predates the reload" in r["oom-policy"][1]
    assert _rows(box, FakeRun(**ok), which=lambda n: None if n in ("zsh", "bash") else "/x")["claude-launcher"][0] == "SKIP"
    assert r["memwatch-unit"][0] == "PASS"
    _, home, _ = box
    unit = home / ".config" / "systemd" / "user" / "claude-memwatch.service"
    unit.write_text("\n".join("ExecStart=/usr/bin/python3 /elsewhere/hooks/tools/memwatch.py"
                              if ln.startswith("ExecStart=") else ln
                              for ln in unit.read_text(encoding="utf-8").splitlines()) + "\n", encoding="utf-8")
    r = _rows(box, FakeRun(**ok))
    assert r["memwatch-unit"][0] == "WARN" and "not " in r["memwatch-unit"][1]


def test_doctor_ci_and_no_manager(box):
    root, home, proc = box
    assert {s for _, s, _ in doc.rows(root, ci=True)} == {"SKIP"}
    assert {s for _, s, _ in doc.rows(root, run=FakeRun(), home=home, bus=None, proc_root=proc)} == {"SKIP"}


def _cp(rc, out=""):
    return lambda cmd, timeout=None: subprocess.CompletedProcess(cmd, rc, out, "")


@pytest.mark.parametrize("run,which,bus,expect", [
    (_cp(0, "active\n"), lambda n: "/bin/systemctl", Path("/run/bus"), "active"),
    (_cp(3, "inactive\n"), lambda n: "/bin/systemctl", Path("/run/bus"), "inactive"),
    (_cp(3, "failed\n"), lambda n: "/bin/systemctl", Path("/run/bus"), "inactive"),
    (_cp(124, ""), lambda n: "/bin/systemctl", Path("/run/bus"), "unknown"),
    (_cp(127, ""), lambda n: "/bin/systemctl", Path("/run/bus"), "unknown"),
    (_cp(0, "active\n"), lambda n: None, Path("/run/bus"), "unknown"),
    (_cp(0, "active\n"), lambda n: "/bin/systemctl", None, "unknown"),
])
def test_unit_state(run, which, bus, expect, monkeypatch):
    monkeypatch.setattr(og.plat, "IS_WINDOWS", False)
    assert og.unit_state(run=run, which=which, bus=bus) == expect


def test_unit_state_windows_and_start_unit(monkeypatch, tmp_path):
    monkeypatch.setattr(og.plat, "IS_WINDOWS", True)
    assert og.unit_state(run=_cp(0, "active\n"), which=lambda n: "x", bus=Path("/b")) == "unknown"
    monkeypatch.setattr(og.plat, "IS_WINDOWS", False)
    seen = []
    assert og.start_unit(run=lambda cmd, timeout=None: (seen.append(cmd), subprocess.CompletedProcess(cmd, 0, "", ""))[1]) == 0
    assert seen == [["systemctl", "--user", "start", "claude-memwatch"]]
    assert og.unit_file(tmp_path) == tmp_path / ".config" / "systemd" / "user" / "claude-memwatch.service"
