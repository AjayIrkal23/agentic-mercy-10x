"""test_platform_mem.py — hooks/lib/platform.py memory and cgroup probes (OOM guard).

``fake_proc`` builds a minimal /proc tree; test_memwatch.py imports it from here.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import platform as plat  # noqa: E402

APP = "/user.slice/user-1000.slice/user@1000.service/app.slice/"


def fake_proc(root: Path, *, mem_available_kb: int | None = 11479040, mem_total_kb: int = 31405920,
              swap_total_kb: int = 1000000, swap_free_kb: int = 12000, psi_some_avg10: float | None = 3.4,
              procs: list | None = None) -> Path:
    """Write meminfo, pressure/memory and <pid>/{comm,cmdline,status,cgroup}. ``mem_available_kb=None``
    leaves meminfo out; ``psi_some_avg10=None`` leaves pressure/ out. Each proc is a dict with
    pid, name, ppid (1), rss_kb (0 = kernel thread: no VmRSS), cmdline (str or list), unit, uid (1000)."""
    root.mkdir(parents=True, exist_ok=True)
    if mem_available_kb is not None:
        (root / "meminfo").write_text(
            f"MemTotal:       {mem_total_kb} kB\nMemFree:          100000 kB\n"
            f"MemAvailable:   {mem_available_kb} kB\nSwapTotal:      {swap_total_kb} kB\n"
            f"SwapFree:       {swap_free_kb} kB\n", encoding="ascii")
    if psi_some_avg10 is not None:
        (root / "pressure").mkdir(exist_ok=True)
        (root / "pressure" / "memory").write_text(
            f"some avg10={psi_some_avg10:.2f} avg60=0.00 avg300=0.00 total=4663624\n"
            "full avg10=0.00 avg60=0.00 avg300=0.00 total=1000\n", encoding="ascii")
    for p in procs or []:
        d = root / str(p["pid"])
        d.mkdir(exist_ok=True)
        (d / "comm").write_text(p["name"] + "\n", encoding="utf-8")
        cmd = p.get("cmdline", p["name"])
        argv = cmd if isinstance(cmd, list) else cmd.split(" ")
        (d / "cmdline").write_bytes(b"".join(a.encode() + b"\0" for a in argv))
        uid = p.get("uid", 1000)
        status = f"Name:\t{p['name']}\nPPid:\t{p.get('ppid', 1)}\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n"
        if p.get("rss_kb", 0):
            status += f"VmRSS:\t{p['rss_kb']} kB\n"
        (d / "status").write_text(status, encoding="utf-8")
        (d / "cgroup").write_text(f"0::{APP}{p.get('unit', 'app.slice-x.scope')}\n", encoding="utf-8")
    return root


def test_mem_probe_reads_meminfo_and_psi(tmp_path):
    root = fake_proc(tmp_path / "p")
    got = plat.mem_probe(root)
    assert got == {"mem_available_mb": 11210, "mem_total_mb": 31405920 // 1024, "swap_total_mb": 976,
                   "swap_free_mb": 11, "swap_free_pct": 1.2, "psi_some_avg10": 3.4}


def test_missing_psi_is_none_rest_filled(tmp_path):
    got = plat.mem_probe(fake_proc(tmp_path / "p", psi_some_avg10=None))
    assert got["psi_some_avg10"] is None and got["mem_available_mb"] == 11210


def test_missing_meminfo_is_none(tmp_path):
    assert plat.mem_probe(fake_proc(tmp_path / "p", mem_available_kb=None)) is None


def test_no_swap_is_not_swap_full(tmp_path):
    got = plat.mem_probe(fake_proc(tmp_path / "p", swap_total_kb=0, swap_free_kb=0))
    assert got["swap_free_pct"] == 100.0


def test_windows_probes_are_none(tmp_path, monkeypatch):
    root = fake_proc(tmp_path / "p", procs=[{"pid": 5, "name": "x", "rss_kb": 10}])
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    monkeypatch.setenv("TMUX_PANE", "%1")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    (tmp_path / "bus").write_text("", encoding="utf-8")
    assert plat.mem_probe(root) is None
    assert plat.cgroup_of(5, root) is None and plat.scope_of(5, root) is None
    assert plat.proc_chain(5, root) is None
    assert plat.systemd_user_bus() is None and plat.tmux_pane() is None


def test_cgroup_of_last_segment(tmp_path):
    root = fake_proc(tmp_path / "p", procs=[{"pid": 7, "name": "claude", "rss_kb": 1, "unit": "ptyxis-spawn-abc.scope"}])
    assert plat.cgroup_of(7, root) == "ptyxis-spawn-abc.scope"
    assert plat.scope_of(7, root) == "ptyxis-spawn-abc.scope"
    assert plat.cgroup_of(99, root) is None


def test_proc_chain_walks_ppid_and_stops_on_cycle(tmp_path):
    root = fake_proc(tmp_path / "p", procs=[
        {"pid": 30, "name": "a", "ppid": 20, "rss_kb": 1}, {"pid": 20, "name": "b", "ppid": 10, "rss_kb": 1},
        {"pid": 10, "name": "c", "ppid": 1, "rss_kb": 1},
        {"pid": 40, "name": "d", "ppid": 41, "rss_kb": 1}, {"pid": 41, "name": "e", "ppid": 40, "rss_kb": 1}])
    assert plat.proc_chain(30, root) == [30, 20, 10]
    assert plat.proc_chain(40, root) == [40, 41]
    assert plat.proc_chain(77, root) == [77]


def test_systemd_user_bus(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    assert plat.systemd_user_bus() is None
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert plat.systemd_user_bus() is None
    (tmp_path / "bus").write_text("", encoding="utf-8")
    assert plat.systemd_user_bus() == tmp_path / "bus"


def test_notify_calls_notify_send(monkeypatch):
    calls = []

    def fake_run(cmd, timeout=None, **_):
        calls.append((cmd, timeout))
        return type("CP", (), {"returncode": 0})()

    assert plat.notify("t", "b", "critical", run=fake_run, which=lambda n: "notify-send") is True
    assert calls == [(["notify-send", "-u", "critical", "-a", "claude-memwatch", "t", "b"], 3)]
    calls.clear()
    assert plat.notify("t", "b", run=fake_run, which=lambda n: None) is False and not calls
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    assert plat.notify("t", "b", run=fake_run, which=lambda n: "notify-send") is False and not calls


def test_tmux_pane(monkeypatch):
    monkeypatch.delenv("TMUX_PANE", raising=False)
    assert plat.tmux_pane() is None
    monkeypatch.setenv("TMUX_PANE", "%3")
    assert plat.tmux_pane() == "%3"
