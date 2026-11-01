"""test_oomguard_integration.py — the OOM guard against the real user manager and journal (skipped without a
systemd user bus: Windows replica, CI), plus the hermetic attach_live() unit cases and the brake smoke."""
from __future__ import annotations

import functools
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "installer"), str(ROOT / "hooks"), str(ROOT / "hooks" / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import doctor_oomguard as doc  # noqa: E402
import oomguard_setup as og  # noqa: E402
from lib import memwatch_state as mws  # noqa: E402
from lib import platform as plat  # noqa: E402
from test_oomguard_setup import FakeRun  # noqa: E402
from test_platform_mem import fake_proc  # noqa: E402

MEMWATCH = ROOT / "hooks" / "tools" / "memwatch.py"
SCOPE_PROPS = ["-p", "OOMPolicy=continue", "-p", "ManagedOOMPreference=avoid", "-p", "MemoryHigh=12G"]


@functools.lru_cache(maxsize=1)
def _bus_ok() -> bool:
    if plat.systemd_user_bus() is None or not __import__("shutil").which("systemd-run"):
        return False
    try:
        return subprocess.run(["systemd-run", "--user", "--scope", "--quiet", "--", "true"], capture_output=True,
                              timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


live = pytest.mark.skipif(not _bus_ok(), reason="no systemd user bus")
live_oom = pytest.mark.skipif(os.environ.get("CLAUDE_TEST_LIVE_OOM") != "1",
                              reason="opt-in CLAUDE_TEST_LIVE_OOM=1: kills a real 200M scope; the live sentinel logs and announces it")


def _memwatch(tmp, journal_cmd):
    return subprocess.run([sys.executable, str(MEMWATCH), "--once", "--journal-cmd", journal_cmd, "--events",
                           str(tmp / "e.jsonl"), "--proc-root", str(ROOT / "hooks" / "tests" / "fixtures" / "proc-ok"),
                           "--state", str(tmp / "s.json")], capture_output=True, text=True, timeout=30)


def _events(tmp):
    p = tmp / "e.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


@live
@live_oom
def test_capped_scope_dies_alone_and_the_kernel_line_parses(tmp_path):
    probe = plat.mem_probe()
    if not probe or probe["mem_available_mb"] < 1024:
        pytest.skip("less than 1 GiB available")
    p = subprocess.run(["systemd-run", "--user", "--scope", "--quiet", "--unit", f"claude-test-oom-{os.getpid()}",
                        "-p", "MemoryMax=200M", "-p", "MemorySwapMax=0",
                        "-p", "OOMPolicy=continue", "--", sys.executable, "-c", "bytearray(1 << 30)"],
                       capture_output=True, timeout=60)
    assert p.returncode != 0  # killed inside its scope; this process is still here to assert it
    if subprocess.run(["journalctl", "-k", "-n", "1", "--no-pager"], capture_output=True, timeout=10).returncode != 0:
        pytest.skip("kernel log not readable by this user")
    for _ in range(10):
        r = _memwatch(tmp_path, "journalctl -k -n 20 -o json --no-pager")
        assert r.returncode == 0
        if any(e.get("source") == "kernel" and str(e.get("victim", "")).startswith("python") for e in _events(tmp_path)):
            return
        time.sleep(0.5)
    pytest.fail(f"no kernel kill event for the python victim: {_events(tmp_path)}")


@live
def test_real_user_journal_parses(tmp_path):
    r = _memwatch(tmp_path, "journalctl --user -n 50 -o json --no-pager")
    assert r.returncode == 0
    assert all(e["kind"] == "kill" for e in _events(tmp_path))


@live
def test_doctor_oom_policy_matches_the_manager():
    default = subprocess.run(["systemctl", "--user", "show", "-p", "DefaultOOMPolicy"], capture_output=True, text=True,
                             timeout=10).stdout.strip().partition("=")[2]
    status = {n: s for n, s, _ in doc.rows(ROOT)}["oom-policy"]
    assert status == "FAIL" if default == "stop" else status in ("PASS", "WARN")


@live
def test_launcher_scope_properties_are_accepted():
    p = subprocess.run(["systemd-run", "--user", "--scope", "--quiet", *SCOPE_PROPS, "--", "true"], capture_output=True,
                       text=True, timeout=20)
    assert p.returncode == 0, p.stderr


def test_brake_smoke_asks_at_crit(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("CLAUDE_WORKBENCH_UNATTENDED", raising=False)
    mws.write_atomic(mws.State(level="crit", mem_available_mb=2000, swap_free_pct=1.0, ts=time.time()))
    env = dict(os.environ)
    p = subprocess.run([sys.executable, str(ROOT / "hooks" / "memwatch-brake.py")], capture_output=True, text=True,
                       input=json.dumps({"tool_name": "Agent", "tool_input": {}, "session_id": "smoke"}), env=env, timeout=10)
    assert p.returncode == 0
    assert json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"] == "ask"


# ---- attach_live (hermetic: fake /proc, fake systemctl / busctl) ---------------------------------
def _tree(tmp_path):
    return fake_proc(tmp_path / "proc", procs=[
        {"pid": 100, "name": "claude", "rss_kb": 1, "unit": "ptyxis-spawn-aaaa.scope"},
        {"pid": 101, "name": "node", "ppid": 100, "rss_kb": 1, "unit": "ptyxis-spawn-aaaa.scope"},
        {"pid": 102, "name": "claude", "ppid": 101, "rss_kb": 1, "unit": "ptyxis-spawn-aaaa.scope"},
        {"pid": 200, "name": "claude", "rss_kb": 1, "unit": "claude-200.scope"},
        {"pid": 300, "name": "claude", "rss_kb": 1, "uid": 0, "unit": "ptyxis-spawn-bbbb.scope"}])


def _attach(tmp_path, dry=False, **answers):
    run = FakeRun(**{"show:ptyxis-spawn-aaaa.scope": "stop", "show:claude-200.scope": "continue", **answers})
    return og.attach_live(dry, run=run, proc_root=_tree(tmp_path), bus=Path("/bus"), uid=1000), run


@pytest.fixture
def linux(monkeypatch):
    """attach_live's fake /proc + fake systemctl/busctl run on any OS; only its Windows SKIP is OS-bound."""
    monkeypatch.setattr(plat, "IS_WINDOWS", False)


@pytest.mark.usefixtures("linux")
def test_attach_moves_a_stop_scope_session(tmp_path):
    rows, run = _attach(tmp_path)
    assert rows == ["attach pid 100: MOVED (3 pids)", "attach pid 200: SKIP(already continue)"]
    busctl = [c for c in run.calls if c[0] == "busctl"]
    assert busctl == [["busctl", "--user", "call", "org.freedesktop.systemd1", "/org/freedesktop/systemd1",
                       "org.freedesktop.systemd1.Manager", "StartTransientUnit", "ssa(sv)a(sa(sv))", "claude-safe-100.scope",
                       "fail", "3", "PIDs", "au", "3", "100", "101", "102", "OOMPolicy", "s", "continue",
                       "ManagedOOMPreference", "s", "avoid", "0"]]


@pytest.mark.usefixtures("linux")
def test_attach_rechecks_after_reload_and_reports_failures(tmp_path):
    assert _attach(tmp_path, **{"show:ptyxis-spawn-aaaa.scope": "continue"})[0][0] == "attach pid 100: SKIP(already continue)"
    assert _attach(tmp_path, rc=1)[0][0] == "attach pid 100: WARN(rc=1)"
    rows, run = _attach(tmp_path, dry=True)
    assert rows[0] == "attach pid 100: WOULD-ATTACH (3 pids)" and not [c for c in run.calls if c[0] == "busctl"]
    assert og.attach_live(False, run=run, proc_root=tmp_path / "proc", bus=None) == [og.NO_MANAGER]
