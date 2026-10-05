"""Optional OS tools (apt) + the end-of-run human checklist: sudo is tried, never required."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ostools  # noqa: E402

M = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))
ALL_PKGS = sorted({p for t in M["user_space"]["os_tools"] for p in t["apt"]})


def _which(have=()):
    return lambda n: f"/usr/bin/{n}" if n in have else None


def _recorder(rc_for=lambda argv: 0):
    calls = []

    def run(argv, **_kw):
        calls.append([str(a) for a in argv])
        return subprocess.CompletedProcess(argv, rc_for(argv), "", "")
    return calls, run


def test_missing_tools_lists_only_absent_binaries():
    got = ostools.missing_tools(M, _which(have={"ss", "curl", "notify-send"}))
    assert {t["bin"] for t in got} == {"canberra-gtk-play", "pw-play"}


def test_root_installs_directly_without_sudo():
    calls, run = _recorder()
    rows, sudo = ostools.install_os_tools(M, ci=False, dry_run=False, run=run,
                                          which=_which(have={"apt-get"}), euid=0, system="Linux")
    assert sudo is None and rows[0][1].startswith("INSTALLED")
    assert calls[0][:2] == ["apt-get", "update"]
    assert calls[1][:3] == ["apt-get", "install", "-y"] and "iproute2" in calls[1]
    assert not any("sudo" in c for c in calls)


def test_passwordless_sudo_is_used_non_interactively():
    calls, run = _recorder()
    rows, sudo = ostools.install_os_tools(M, ci=False, dry_run=False, run=run, say=lambda s: None,
                                          which=_which(have={"apt-get", "sudo"}), euid=1000, system="Linux")
    assert sudo is None
    assert calls[0] == ["sudo", "-n", "true"]
    # sudo resets the environment, so DEBIAN_FRONTEND rides through `env`
    assert calls[-1] == ["sudo", "-n", "env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "install", "-y",
                         *ALL_PKGS]


def test_the_exact_command_is_printed_once_before_each_apt_call():
    """A cached sudo timestamp (`sudo apt install git` earlier in the same tty) also passes
    `sudo -n true`: the user must see what runs as root before it runs."""
    said: list = []
    order: list = []
    calls, rec = _recorder()

    def run(argv, **kw):
        order.append(("run", [str(a) for a in argv]))
        return rec(argv, **kw)
    ostools.install_os_tools(M, ci=False, dry_run=False, run=run, say=lambda s: order.append(("say", s)) or said.append(s),
                             which=_which(have={"apt-get", "sudo"}), euid=1000, system="Linux")
    line = "sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install -y " + " ".join(ALL_PKGS)
    assert [s for s in said if "install -y" in s] == [f"  running as root: {line}"]
    i_say = next(i for i, e in enumerate(order) if e[0] == "say" and "install -y" in e[1])
    i_run = next(i for i, e in enumerate(order) if e[0] == "run" and "install" in e[1])
    assert i_say < i_run and all("\n" not in s for s in said)


def test_only_the_fixed_manifest_package_list_is_ever_installed():
    calls, run = _recorder()
    ostools.install_os_tools(M, ci=False, dry_run=False, run=run, say=lambda s: None,
                             which=_which(have={"apt-get"}), euid=0, system="Linux")
    install = next(c for c in calls if "install" in c)
    assert install[install.index("-y") + 1:] == ALL_PKGS


def test_no_sudo_collects_one_batched_command_and_does_not_fail():
    calls, run = _recorder(lambda argv: 1 if argv[:2] == ["sudo", "-n"] else 0)
    rows, sudo = ostools.install_os_tools(M, ci=False, dry_run=False, run=run,
                                          which=_which(have={"apt-get", "sudo"}), euid=1000, system="Linux")
    assert sudo == "sudo apt-get install -y " + " ".join(ALL_PKGS)
    assert rows[0][1].startswith("NEEDS-SUDO")
    assert not any(c[:3] == ["sudo", "-n", "env"] for c in calls)


def test_failed_apt_run_degrades_to_the_batched_command():
    calls, run = _recorder(lambda argv: 100 if "install" in argv else 0)
    rows, sudo = ostools.install_os_tools(M, ci=False, dry_run=False, run=run,
                                          which=_which(have={"apt-get"}), euid=0, system="Linux")
    assert sudo and rows[0][1].startswith("NEEDS-SUDO")


def test_nothing_missing_is_present():
    calls, run = _recorder()
    every = {t["bin"] for t in M["user_space"]["os_tools"]} | {"apt-get"}
    rows, sudo = ostools.install_os_tools(M, ci=False, dry_run=False, run=run, which=_which(have=every),
                                          euid=1000, system="Linux")
    assert rows == [("os-tools", "PRESENT")] and sudo is None and calls == []


def test_plan_modes_run_nothing():
    calls, run = _recorder()
    rows, sudo = ostools.install_os_tools(M, ci=True, dry_run=True, run=run, which=_which(have={"apt-get"}),
                                          euid=1000, system="Linux")
    assert calls == [] and rows[0][1].startswith("WOULD-") and sudo is None


def test_non_linux_and_non_apt_hosts_are_skipped_quietly():
    _, run = _recorder()
    assert ostools.install_os_tools(M, ci=False, dry_run=False, run=run, which=_which(),
                                    euid=0, system="Darwin")[0][0][1].startswith("SKIP")
    rows, sudo = ostools.install_os_tools(M, ci=False, dry_run=False, run=run, which=_which(),
                                          euid=0, system="Linux")
    assert rows[0][1].startswith("SKIP(no-apt)") and sudo is None


def test_checklist_prints_the_sudo_command_once_then_the_human_steps():
    lines = ostools.checklist(M, "sudo apt-get install -y iproute2")
    text = "\n".join(lines)
    assert text.count("sudo apt-get install -y iproute2") == 1
    assert "/mcp" in text and "higgsfield" in text and "openart" in text and "gh auth login" in text


def test_checklist_without_sudo_has_only_human_only_steps():
    text = "\n".join(ostools.checklist(M, None))
    assert "sudo" not in text and "gh auth login" in text
