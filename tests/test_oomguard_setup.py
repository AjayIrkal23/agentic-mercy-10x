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

pytestmark = pytest.mark.skipif(plat.IS_WINDOWS, reason="systemd user units: Linux only")

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
        else:  # "bash -lc" answers before "bash" (the doctor's login-shell probe)
            out = self.answers.get(" ".join(cmd[:2]), self.answers.get(cmd[0], ""))
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
    (home / ".profile").write_text('. "$HOME/.bashrc"\nPATH="$HOME/.local/bin:$PATH"\n', encoding="utf-8")
    (tmp_path / "proc").mkdir()
    return root, home, tmp_path / "proc"


def _ensure(box, dry=False, run=None, **kw):
    root, home, proc = box
    run = run or FakeRun()
    if "linger_dir" not in kw:  # lingering already on: the host's /var/lib/systemd/linger never decides a test
        kw["linger_dir"] = proc.parent / "linger"
        kw["linger_dir"].mkdir(exist_ok=True)
        (kw["linger_dir"] / og._user()).write_text("", encoding="utf-8")
    return og.ensure(dry, home=home, run=run, which=lambda n: "/usr/bin/" + n, bus=Path("/bus"), root=root,
                     proc_root=proc, **kw), run


def _snapshot(home):
    return {p: p.read_bytes() for p in sorted(home.rglob("*")) if p.is_file()}


def test_fresh_home_creates_everything(box):
    root, home, _ = box
    rows, run = _ensure(box)
    for want in ("drop-in 10-oom.conf: CREATED", "unit claude-memwatch.service: CREATED",
                 "unit claude-restore.service: CREATED", "systemctl daemon-reload: OK", "claude-memwatch: ENABLED",
                 "claude-restore: ENABLED", ".zshrc: APPENDED PATH block", ".bashrc: APPENDED PATH block",
                 ".profile: APPENDED PATH block"):
        assert want in rows, (want, rows)
    unit = (home / ".config" / "systemd" / "user" / "claude-memwatch.service").read_text(encoding="utf-8")
    assert f"ExecStart={plat.python_exe()} {root / 'hooks'}/tools/memwatch.py" in unit and "{" not in unit
    restore = (home / ".config" / "systemd" / "user" / "claude-restore.service").read_text(encoding="utf-8")
    assert "\nKillMode=process\n" in restore  # the tmux server restore starts must outlive the oneshot
    for rc in (".zshrc", ".bashrc"):
        text = (home / rc).read_text(encoding="utf-8")
        assert text.endswith(og.path_block()) and text.index(og.BEGIN) > text.index("# <<< lean-ctx agent aliases <<<")
    profile = (home / ".profile").read_text(encoding="utf-8")  # after the ~/.local/bin prepend: bash -l wins too
    assert profile.endswith(og.path_block()) and profile.index(og.BEGIN) > profile.index(".local/bin")
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


# ---- O7: a daemon older than its code restarts itself ---------------------------------------------
_RESTART = ["systemctl", "--user", "restart", "claude-memwatch"]


def _daemon(box, started_ago: float, code_ago: float = 60, pid: int = 4242):
    """Fake /proc for a running memwatch that started `started_ago` s ago; memwatch.py written `code_ago` s ago."""
    import os
    import time
    root, _, proc = box
    now = time.time()
    clk = os.sysconf("SC_CLK_TCK")
    btime = int(now - 100000)
    (proc / "stat").write_text(f"cpu  1 2 3\nbtime {btime}\n", encoding="utf-8")
    ticks = int((now - started_ago - btime) * clk)
    (proc / str(pid)).mkdir(exist_ok=True)
    (proc / str(pid) / "stat").write_text(f"{pid} (python3) S " + " ".join(["0"] * 18 + [str(ticks), "0", "0"]) + "\n",
                                          encoding="utf-8")
    code = root / "hooks" / "tools" / "memwatch.py"
    code.write_text("# code\n", encoding="utf-8")
    os.utime(code, (now - code_ago, now - code_ago))
    return FakeRun(**_LIVE_UNITS, **{"show:claude-memwatch": str(pid)})


def test_daemon_older_than_its_code_is_restarted(box):
    _ensure(box)
    run = _daemon(box, started_ago=3600, code_ago=60)
    rows, run = _ensure(box, run=run)
    assert "claude-memwatch: OK" in rows
    assert "memwatch-code: RESTARTED(code newer than daemon)" in rows, rows
    assert _RESTART in run.calls


def test_imported_lib_change_marks_the_daemon_stale(box):
    # SANTA-FINAL runtime F3: memwatch.py imports lib/platform + lib/hook_telemetry; a change there is stale code too
    root = box[0]
    run = _daemon(box, started_ago=30, code_ago=3600)
    assert og.code_newer_than_daemon(run, root, proc_root=box[2]) is False
    for name in ("platform.py", "hook_telemetry.py"):
        lib = root / "hooks" / "lib" / name
        lib.parent.mkdir(parents=True, exist_ok=True)
        lib.write_text("# touched\n", encoding="utf-8")
        assert og.code_newer_than_daemon(run, root, proc_root=box[2]) is True, name
        lib.unlink()


def test_current_daemon_is_left_alone(box):
    _ensure(box)
    rows, run = _ensure(box, run=_daemon(box, started_ago=30, code_ago=3600))
    assert "memwatch-code: OK(current)" in rows and _RESTART not in run.calls


def test_stale_daemon_waits_at_crit(box, monkeypatch):
    _ensure(box)
    monkeypatch.setattr(og, "_tier", lambda: "crit")
    rows, run = _ensure(box, run=_daemon(box, started_ago=3600, code_ago=60))
    assert "memwatch-code: SKIP(crit: restart later)" in rows and _RESTART not in run.calls


def test_stale_daemon_dry_run_and_not_running(box):
    _ensure(box)
    rows, run = _ensure(box, dry=True, run=_daemon(box, started_ago=3600, code_ago=60))
    assert not [r for r in rows if r.startswith("memwatch-code")] and _RESTART not in run.calls
    rows, run = _ensure(box, run=FakeRun(**_LIVE_UNITS))          # MainPID unreadable -> no row, no restart
    assert not [r for r in rows if r.startswith("memwatch-code")] and _RESTART not in run.calls


def test_doctor_memwatch_code_row(box):
    _ensure(box)
    run = _daemon(box, started_ago=3600, code_ago=60)
    r = _rows(box, run)
    assert r["memwatch-code"][0] == "WARN" and "older than" in r["memwatch-code"][1]
    assert _RESTART not in run.calls                                 # the doctor only reports
    assert _rows(box, _daemon(box, started_ago=30, code_ago=3600))["memwatch-code"][0] == "PASS"
    assert _rows(box, FakeRun(**_LIVE_UNITS))["memwatch-code"][0] == "SKIP"


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
    _, home, proc = box
    before = _snapshot(home)
    (proc.parent / "no-linger").mkdir()
    rows, run = _ensure(box, dry=True, linger_dir=proc.parent / "no-linger")
    assert all(r.split(": ", 1)[1].startswith("WOULD-") for r in rows), rows
    assert _snapshot(home) == before and not run.mutating()


def test_no_manager_still_writes_the_path_block_and_windows_touches_nothing(box, monkeypatch):
    """FI-6: a container / SSH session without a user bus still gets ~/.claude/bin on PATH."""
    root, home, proc = box
    before = _snapshot(home)
    monkeypatch.setattr(og.plat, "IS_WINDOWS", True)
    assert _ensure(box)[0] == [og.NO_MANAGER] and _snapshot(home) == before
    monkeypatch.setattr(og.plat, "IS_WINDOWS", False)
    rows = og.ensure(False, home=home, run=FakeRun(), bus=None, root=root, proc_root=proc)
    assert rows[-1] == og.NO_MANAGER and ".bashrc: APPENDED PATH block" in rows
    for rc in (".bashrc", ".profile"):
        assert (home / rc).read_text(encoding="utf-8").count(og.BEGIN) == 1
    assert not (home / ".config" / "systemd").exists()


@pytest.mark.parametrize("how", ["foreign-home", "env"])
def test_sandbox_writes_files_but_runs_no_verbs(box, monkeypatch, how):
    root, home, proc = box
    monkeypatch.setattr(og.plat, "IS_WINDOWS", False)
    monkeypatch.setattr(og.plat, "systemd_user_bus", lambda: Path("/fake/bus"))
    run = FakeRun(**_LIVE_UNITS)
    if how == "env":
        monkeypatch.setenv("AGENTIC_MERCY_SANDBOX", "1")
        monkeypatch.setattr(og, "_foreign_home", lambda h: False)  # as if home were the real one
    else:
        monkeypatch.delenv("AGENTIC_MERCY_SANDBOX", raising=False)
    rows = og.ensure(False, home=home, run=run, which=lambda n: "/usr/bin/" + n, root=root, proc_root=proc)
    assert not [c for c in run.calls if c[0] in ("systemctl", "busctl")], run.calls
    assert (home / ".config" / "systemd" / "user" / "claude-memwatch.service").is_file()
    assert {"claude-memwatch: SKIP(sandbox)", "attach: SKIP(sandbox)"} <= set(rows)


def test_missing_rc_is_never_created(box):
    _, home, _ = box
    (home / ".zshrc").unlink()
    (home / ".profile").unlink()
    rows = _ensure(box)[0]
    assert ".zshrc: SKIP(absent)" in rows and not (home / ".zshrc").exists()
    assert ".profile: SKIP(absent)" in rows and not (home / ".profile").exists()


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
    if "linger_dir" not in kw:  # lingering on, like _ensure: the host never decides a row
        kw["linger_dir"] = proc.parent / "linger"
        kw["linger_dir"].mkdir(exist_ok=True)
        (kw["linger_dir"] / og._user()).write_text("", encoding="utf-8")
    return {n: (s, d) for n, s, d in doc.rows(root, run=run, which=which, home=home, bus=Path("/bus"),
                                                proc_root=proc, **kw)}


def test_doctor_linger_row(box, tmp_path):
    root, home, proc = box
    empty = tmp_path / "linger-none"
    empty.mkdir()
    assert _rows(box, FakeRun())["linger"][0] == "PASS"
    assert _rows(box, FakeRun(), linger_dir=empty)["linger"][0] == "WARN"      # guard not installed yet
    _ensure(box)
    r = _rows(box, FakeRun(), linger_dir=empty)["linger"]
    assert r[0] == "FAIL" and "loginctl enable-linger" in r[1]
    (home / ".claude").mkdir(exist_ok=True)
    (home / ".claude" / "oomguard.local.json").write_text('{"linger": false}', encoding="utf-8")
    assert _rows(box, FakeRun(), linger_dir=empty)["linger"] == ("PASS", "opted out (oomguard.local.json)")


def test_doctor_restore_unit_needs_tmux(box):
    run = FakeRun(**{"is-enabled:claude-restore": "enabled"})
    r = _rows(box, run, which=lambda n: None if n == "tmux" else "/usr/bin/" + n)["restore-unit"]
    assert r == ("WARN", "tmux missing: restore cannot run (sudo apt-get install -y tmux)")
    assert _rows(box, run)["restore-unit"] == ("PASS", "enabled")


def test_doctor_launcher_fails_when_the_real_binary_is_missing(box):
    run = FakeRun(zsh="/h/.claude/bin/claude", bash="/h/.claude/bin/claude",
                  **{"bash -ic": "claude: real binary not found (set CLAUDE_REAL_BIN)"})
    r = _rows(box, run)["claude-launcher"]
    assert r[0] == "FAIL" and "real claude missing" in r[1] and "~/.local/bin" in r[1]


def test_doctor_before_install(box):
    r = _rows(box, FakeRun(zsh="/h/.local/bin/claude", bash="/h/.claude/bin/claude"))
    assert r["oom-policy"] == ("FAIL", "DefaultOOMPolicy=stop (run installer/oomguard_setup.py --apply)")
    assert r["memwatch-unit"][0] == "FAIL" and "unit missing" in r["memwatch-unit"][1]
    assert r["restore-unit"][0] == "WARN" and r["launch-caps"][0] == "WARN"
    assert r["claude-launcher"][0] == "WARN" and "zsh resolves claude to /h/.local/bin/claude" in r["claude-launcher"][1]
    assert r["attach-live"][0] == "PASS"


def _launcher_argv(box, *argv) -> dict:
    """FakeRun answer for the launcher-model probe (`bash <root>/bin/claude --version`)."""
    return {f"bash {box[0].resolve() / 'bin' / 'claude'}": "\n".join(("/h/.local/bin/claude", *argv, "--version"))}


def test_doctor_after_install(box, monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(tmp_path / "state"))
    _ensure(box)
    monkeypatch.setattr(doc.plat, "cgroup_of", lambda pid, root="/proc": "app-x.scope")
    caps = plat.state_dir() / "launch-caps"
    caps.mkdir(parents=True, exist_ok=True)
    (caps / "1.json").write_text(json.dumps({"workflow_agents": 4, "subagents": 5, "size_guideline": "medium"}),
                                 encoding="utf-8")
    (plat.state_dir() / "plan-tier.json").write_text(json.dumps({"schema": 1, "tier": "max20", "main": "opus",
                                                                 "detected_at": 1}), encoding="utf-8")
    ok = {"default": "continue", "show:app-x.scope": "continue", "is-active:claude-memwatch": "active",
          "is-enabled:claude-memwatch": "enabled", "is-enabled:claude-restore": "enabled",
          "zsh": "/h/.claude/bin/claude", "bash": "/h/.claude/bin/claude", "show:claude-memwatch": "4242",
          **_launcher_argv(box, "--model", "opus")}
    _daemon(box, started_ago=30, code_ago=3600)                     # a daemon newer than its code (O7)
    r = _rows(box, FakeRun(**ok))
    assert {n: s for n, (s, _) in r.items()} == dict.fromkeys(doc.NAMES, "PASS"), r
    assert r["launch-caps"][1].startswith("wf4 sub5 medium")
    r = _rows(box, FakeRun(**{**ok, "show:app-x.scope": "stop"}))
    assert r["oom-policy"][0] == "WARN" and "predates the reload" in r["oom-policy"][1]
    assert _rows(box, FakeRun(**ok), which=lambda n: None if n in ("zsh", "bash") else "/x")["claude-launcher"][0] == "SKIP"
    assert r["claude-launcher"] == ("PASS", "zsh, bash and bash -l -> ~/.claude/bin/claude")
    bad = _rows(box, FakeRun(**{**ok, "bash -lc": "/h/.local/bin/claude"}))["claude-launcher"]
    assert bad == ("WARN", "bash -l resolves claude to /h/.local/bin/claude"), bad
    assert r["launcher-model"] == ("PASS", "--model opus (tier main)")
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    nomodel = {**ok, **_launcher_argv(box)}
    assert _rows(box, FakeRun(**nomodel))["launcher-model"][0] == "WARN"
    (box[1] / ".claude").mkdir(exist_ok=True)
    (box[1] / ".claude" / "settings.json").write_text('{"model": "sonnet"}', encoding="utf-8")
    assert _rows(box, FakeRun(**nomodel))["launcher-model"] == ("PASS", "settings.json model=sonnet (your /model choice)")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-x")
    assert _rows(box, FakeRun(**nomodel))["launcher-model"] == ("PASS", "ANTHROPIC_MODEL set")
    monkeypatch.delenv("ANTHROPIC_MODEL")
    (plat.state_dir() / "plan-tier.json").write_text('{"schema": 1, "tier": "max20"}', encoding="utf-8")
    assert "no `main` yet" in _rows(box, FakeRun(**ok))["launcher-model"][1]
    assert r["memwatch-unit"][0] == "PASS"
    _, home, _ = box
    unit = home / ".config" / "systemd" / "user" / "claude-memwatch.service"
    unit.write_text("\n".join("ExecStart=/usr/bin/python3 /elsewhere/hooks/tools/memwatch.py"
                              if ln.startswith("ExecStart=") else ln
                              for ln in unit.read_text(encoding="utf-8").splitlines()) + "\n", encoding="utf-8")
    r = _rows(box, FakeRun(**ok))
    assert r["memwatch-unit"][0] == "WARN" and "not " in r["memwatch-unit"][1]


@pytest.mark.parametrize("how", ["foreign-home", "env"])
def test_doctor_sandbox_skips_every_row(box, monkeypatch, how):
    root, home, proc = box
    monkeypatch.setattr(doc.plat, "IS_WINDOWS", False)
    monkeypatch.setattr(doc.plat, "systemd_user_bus", lambda: Path("/fake/bus"))
    run = FakeRun(**_LIVE_UNITS)
    if how == "env":
        monkeypatch.setenv("AGENTIC_MERCY_SANDBOX", "1")
        monkeypatch.setattr(og, "_foreign_home", lambda h: False)
    else:
        monkeypatch.delenv("AGENTIC_MERCY_SANDBOX", raising=False)
    out = doc.rows(root, run=run, which=lambda n: "/usr/bin/" + n, home=home, proc_root=proc)
    assert [(n, s) for n, s, _ in out] == [(n, "SKIP") for n in doc.NAMES]
    assert all("sandbox" in d for _, _, d in out) and run.calls == []


def test_doctor_injected_bus_still_probes(box, monkeypatch):
    monkeypatch.delenv("AGENTIC_MERCY_SANDBOX", raising=False)
    r = _rows(box, FakeRun(**_LIVE_UNITS))
    assert r["memwatch-unit"][0] != "SKIP"


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


# ---- FI-2 linger --------------------------------------------------------------------------------------
def _linger(tmp_path, run_rc=0, dry=False, local=None, which=lambda n: "/usr/bin/" + n):
    home, ldir = tmp_path / "h", tmp_path / "linger"
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    ldir.mkdir(exist_ok=True)
    if local is not None:
        (home / ".claude" / "oomguard.local.json").write_text(json.dumps(local), encoding="utf-8")
    calls = []

    def run(cmd, timeout=None, **_):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, run_rc, "", "")
    return og._linger(run, dry, which, home, ldir, user="u1"), calls, ldir


def test_linger_enabled_when_absent(tmp_path):
    row, calls, _ = _linger(tmp_path)
    assert row == "linger: ENABLED" and calls == [["loginctl", "enable-linger", "u1"]]


def test_linger_dry_present_optout_and_failure(tmp_path):
    row, calls, ldir = _linger(tmp_path, dry=True)
    assert row == "linger: WOULD-ENABLE" and calls == []
    (ldir / "u1").write_text("", encoding="utf-8")
    assert _linger(tmp_path)[0] == "linger: OK"
    (ldir / "u1").unlink()
    assert _linger(tmp_path, local={"linger": False})[0] == "linger: SKIP(oomguard.local.json)"
    (tmp_path / "h" / ".claude" / "oomguard.local.json").unlink()
    row, _, _ = _linger(tmp_path, run_rc=1)
    assert row == "linger: WARN(rc=1; run: sudo loginctl enable-linger u1)"
    assert _linger(tmp_path, which=lambda n: None)[0] == "linger: SKIP(no loginctl)"


def test_linger_row_in_ensure_and_sandbox(box, monkeypatch):
    rows, run = _ensure(box)
    assert "linger: OK" in rows
    root, home, proc = box
    ldir = proc.parent / "linger-empty"
    ldir.mkdir()
    rows, run = _ensure(box, linger_dir=ldir)
    assert "linger: ENABLED" in rows and ["loginctl", "enable-linger", og._user()] in run.calls
    monkeypatch.setenv("AGENTIC_MERCY_SANDBOX", "1")
    rows, run = _ensure(box, linger_dir=ldir)
    assert "linger: SKIP(sandbox)" in rows and not [c for c in run.calls if c[0] == "loginctl"]


# ---- FI-11 / FI-6 PATH block and SKIP rc -------------------------------------------------------------
def test_path_line_carries_local_bin_and_old_block_is_updated_in_place(box):
    _, home, _ = box
    assert og.PATH_LINE == 'export PATH="$HOME/.claude/bin:$HOME/.local/bin:$PATH"'
    old = f"\n{og.BEGIN}\nexport PATH=\"$HOME/.claude/bin:$PATH\"\n{og.END}\n"
    (home / ".bashrc").write_text("# mine\n" + old + "alias x=y\n", encoding="utf-8")
    rows = _ensure(box)[0]
    text = (home / ".bashrc").read_text(encoding="utf-8")
    assert ".bashrc: UPDATED PATH block" in rows
    assert text.count(og.BEGIN) == 1 and og.PATH_LINE in text and text.startswith("# mine\n")
    assert text.endswith("alias x=y\n")


def test_main_returns_3_without_a_manager(monkeypatch, capsys):
    monkeypatch.setattr(og, "ensure", lambda dry=False, **k: [".bashrc: PRESENT", og.NO_MANAGER])
    assert og.main(["--apply"]) == 3
    monkeypatch.setattr(og, "ensure", lambda dry=False, **k: ["claude-memwatch: OK"])
    assert og.main(["--apply"]) == 0
