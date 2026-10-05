"""Santa installer review: an interrupted ollama install is repaired (item 4), and the installer
never takes over a systemd unit it does not own (item 5)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ollama_setup  # noqa: E402

M = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))
CFG = M["user_space"]["ollama"]


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    (tmp_path / ".local" / "bin").mkdir(parents=True)
    return tmp_path


def _which(path):
    return lambda n: path if n in ("ollama", "systemctl") else None


# --- 4. pinned, verified, repairable -------------------------------------------------------- #
def test_the_download_is_the_pinned_release_with_its_sha256(home):
    seen: dict = {}

    def download(url, dest, timeout=0, sha256=None, **_k):
        seen.update(url=url, sha256=sha256)
        Path(dest).write_bytes(b"z")
    st = ollama_setup.install_ollama(CFG, ci=False, dry_run=False, which=lambda n: None, download=download,
                                     extract=lambda a, d: None, system=("linux", "x64"))
    assert st.startswith("INSTALLED")
    assert seen["url"] == "https://github.com/ollama/ollama/releases/download/v0.35.1/ollama-linux-amd64.tar.zst"
    assert seen["sha256"] == CFG["sha256"]["linux-amd64"]
    assert (home / ".local" / "lib" / "ollama" / ollama_setup.COMPLETE).is_file()


def test_a_bin_without_its_libs_is_a_partial_install_and_is_repaired(home):
    (home / ".local" / "bin" / "ollama").write_text("bin", encoding="utf-8")
    ran: list = []

    def extract(archive, dest):
        ran.append(dest)
    st = ollama_setup.install_ollama(CFG, ci=False, dry_run=False, which=_which(str(home / ".local/bin/ollama")),
                                     download=lambda u, d, **k: Path(d).write_bytes(b"z"), extract=extract,
                                     system=("linux", "x64"))
    assert st.startswith("INSTALLED") and ran == [home / ".local"]


def test_a_complete_install_is_present(home):
    (home / ".local" / "bin" / "ollama").write_text("bin", encoding="utf-8")
    lib = home / ".local" / "lib" / "ollama"
    lib.mkdir(parents=True)
    (lib / ollama_setup.COMPLETE).write_text("", encoding="utf-8")
    assert ollama_setup.install_ollama(CFG, ci=False, dry_run=False,
                                       which=_which(str(home / ".local/bin/ollama"))) == "PRESENT"


def test_an_ollama_somewhere_else_is_not_ours_to_repair(home):
    assert ollama_setup.install_ollama(CFG, ci=False, dry_run=False, which=_which("/usr/local/bin/ollama")) == "PRESENT"


def test_a_failed_extraction_removes_the_half_installed_binary(home):
    def extract(archive, dest):
        (home / ".local" / "bin" / "ollama").write_text("first member", encoding="utf-8")
        raise OSError("No space left on device")
    st = ollama_setup.install_ollama(CFG, ci=False, dry_run=False, which=lambda n: None,
                                     download=lambda u, d, **k: Path(d).write_bytes(b"z"), extract=extract,
                                     system=("linux", "x64"))
    assert st.startswith("WARN") and not (home / ".local" / "bin" / "ollama").exists()


def test_an_interrupt_during_extraction_also_cleans_up(home):
    def extract(archive, dest):
        (home / ".local" / "bin" / "ollama").write_text("first member", encoding="utf-8")
        raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        ollama_setup.install_ollama(CFG, ci=False, dry_run=False, which=lambda n: None,
                                    download=lambda u, d, **k: Path(d).write_bytes(b"z"), extract=extract,
                                    system=("linux", "x64"))
    assert not (home / ".local" / "bin" / "ollama").exists()


def test_the_archive_goes_under_the_home_cache_not_tmp(home):
    seen: list = []
    ollama_setup.install_ollama(CFG, ci=False, dry_run=False, which=lambda n: None,
                                download=lambda u, d, **k: seen.append(str(d)) or Path(d).write_bytes(b"z"),
                                extract=lambda a, d: None, system=("linux", "x64"))
    assert seen[0].startswith(str(home / ".cache" / "agentic-mercy"))


# --- 5. a unit the user owns is never touched ----------------------------------------------- #
class _Sys:
    """run() fake: records argv, answers `systemctl --user` calls."""

    def __init__(self, enabled="enabled", systemd=True):
        self.calls, self.enabled, self.systemd, self.state = [], enabled, systemd, {"up": False}

    def __call__(self, argv, **_k):
        argv = [str(a) for a in argv]
        self.calls.append(argv)
        if argv[2:3] in (["enable"], ["start"]):  # systemd brings the service (and the server) up
            self.state["up"] = True
        if argv[:3] == ["systemctl", "--user", "show-environment"]:
            return subprocess.CompletedProcess(argv, 0 if self.systemd else 1, "", "")
        if argv[:3] == ["systemctl", "--user", "is-enabled"]:
            return subprocess.CompletedProcess(argv, 0 if self.enabled == "enabled" else 1, self.enabled + "\n", "")
        return subprocess.CompletedProcess(argv, 0, "", "")


def _server(home, exe, run, unit_text=None):
    unit = home / ".config" / "systemd" / "user" / "ollama.service"
    if unit_text is not None:
        unit.parent.mkdir(parents=True)
        unit.write_text(unit_text, encoding="utf-8")
    state, spawned = run.state, []

    def spawn(cmd, **_k):
        spawned.append(list(cmd))
        state["up"] = True
    ok = ollama_setup.ensure_server(probe=lambda: {"x"} if state["up"] else None, spawn=spawn, run=run,
                                    which=_which(exe), sleep=lambda s: None, wait_s=2)
    return ok, spawned, unit


def test_a_user_owned_unit_is_never_overwritten_or_enabled(home):
    mine = "[Service]\nEnvironment=OLLAMA_MODELS=/data/models\nExecStart=/opt/ollama serve\n"
    run = _Sys()
    ok, spawned, unit = _server(home, str(home / ".local/bin/ollama"), run, unit_text=mine)
    assert unit.read_text(encoding="utf-8") == mine
    assert not [c for c in run.calls if c[2:3] in (["enable"], ["start"], ["daemon-reload"])]
    assert ok and spawned == [["ollama", "serve"]]


def test_no_unit_is_written_for_an_ollama_that_is_not_in_the_users_local_bin(home):
    run = _Sys()
    ok, spawned, unit = _server(home, "/usr/local/bin/ollama", run)
    assert not unit.exists() and ok and spawned == [["ollama", "serve"]]
    assert not [c for c in run.calls if "enable" in c]


def test_our_unit_points_at_the_real_binary_and_is_marked(home):
    exe = str(home / ".local/bin/ollama")
    run = _Sys()
    ok, spawned, unit = _server(home, exe, run)
    text = unit.read_text(encoding="utf-8")
    assert f"ExecStart={exe} serve" in text and "agentic-mercy" in text
    assert ["systemctl", "--user", "enable", "--now", "ollama"] in run.calls
    assert ok and spawned == []  # systemd started it: no stray detached serve


def test_our_own_unit_that_the_user_disabled_is_not_re_enabled(home):
    exe = str(home / ".local/bin/ollama")
    ours = f"[Unit]\nDescription=ollama (user-space, agentic-mercy)\n[Service]\nExecStart={exe} serve\n"
    run = _Sys(enabled="disabled")
    ok, spawned, unit = _server(home, exe, run, unit_text=ours)
    assert not [c for c in run.calls if "enable" in c or "start" in c]
    assert unit.read_text(encoding="utf-8") == ours


def test_a_running_server_of_any_kind_means_no_systemd_changes_at_all(home):
    run = _Sys()
    ok = ollama_setup.ensure_server(probe=lambda: {"all-minilm"}, spawn=lambda *a, **k: None, run=run,
                                    which=_which("/usr/bin/ollama"), sleep=lambda s: None)
    assert ok and run.calls == []
