"""ollama on Windows: the pinned zip into the tools dir, a completion marker, a disk preflight and an
HKCU Run autostart that is created only for our binary and only when nothing answers on 11434 (A5-12).
Windows branch rehearsed on any OS: zip, registry, disk, probe and ``which`` are injected."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks"), str(_ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ollama_setup  # noqa: E402
import winpath  # noqa: E402
from lib import platform as plat  # noqa: E402
from winfakes import ENV, World, short_limit  # noqa: E402, F401  (autouse: A7v2-02)

M = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))
RUN = "agentic-mercy-ollama"


@pytest.fixture
def w(tmp_path, monkeypatch):
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    return World(tmp_path, M)


def inst(w, **kw):
    args = dict(ci=False, dry_run=False, which=w.which, download=w.download, system=("windows", "x64"),
                win_cfg=w.manifest["user_space"]["windows"]["ollama"], registry=w.registry,
                disk_free=lambda p: 10 ** 12, environ=w.env, probe=lambda: None)
    args.update(kw)
    return ollama_setup.install_ollama(M["user_space"]["ollama"], **args)


def _exe(w) -> Path:
    return w.tools / "ollama" / "ollama.exe"


def test_install_unpacks_the_zip_marks_it_complete_and_puts_it_on_path(w):
    status = inst(w)
    assert status.startswith("INSTALLED ollama v0.35.1") and "brew" not in status
    assert _exe(w).is_file() and (w.tools / "ollama" / "lib" / "ollama" / "a.dll").is_file()
    assert (w.tools / "ollama" / ".agentic-mercy-complete").read_text(encoding="utf-8") == "v0.35.1"
    assert str(w.tools / "ollama") in w.registry.values[(ENV, "Path")][0].split(";")
    assert w.urls == ["https://github.com/ollama/ollama/releases/download/v0.35.1/ollama-windows-amd64.zip"]
    assert not list((w.tools / "cache").glob("*.zip"))


def test_autostart_is_a_headless_hkcu_run_value_for_our_binary(w):
    inst(w)
    assert w.registry.values[(winpath.RUN_KEY, RUN)] == (f'conhost.exe --headless "{_exe(w)}" serve', "REG_SZ")
    assert inst(w, which=lambda n: None) == "PRESENT" and len(w.registry.sets()) == 2  # Path + Run, once


def test_no_autostart_when_a_server_answers_by_the_time_the_binary_is_ready(w):
    answers = iter([None, {"all-minilm"}])  # nothing at the reuse check, a server once ours is unpacked
    assert inst(w, probe=lambda: next(answers)).startswith("INSTALLED")
    assert (winpath.RUN_KEY, RUN) not in w.registry.values and _exe(w).is_file()


def test_the_users_own_ollama_or_a_running_server_is_present_and_untouched(w):
    assert inst(w, which=lambda n: "/apps/Ollama/ollama.exe") == "PRESENT"
    assert inst(w, probe=lambda: set()) == "PRESENT"
    assert w.urls == [] and w.registry.sets() == [] and not w.tools.exists()


def test_a_failed_extraction_keeps_the_verified_zip_and_the_rerun_does_not_download_again(w, monkeypatch):
    """A5v2-02: ollama is 1.47 GB; one denied rename must not cost a second download."""
    import safe_fetch
    real = safe_fetch.os.replace
    monkeypatch.setattr(safe_fetch.os, "replace", lambda a, b, *x, **k: (_ for _ in ()).throw(PermissionError(5, "denied")))
    monkeypatch.setattr(safe_fetch.time, "sleep", lambda s: None)
    monkeypatch.setattr(safe_fetch, "RENAME_WAIT_S", 0.01)
    assert inst(w).startswith("WARN(PermissionError")
    assert len(list((w.tools / "cache").glob("ollama*.zip"))) == 1
    monkeypatch.setattr(safe_fetch.os, "replace", real)
    assert inst(w).startswith("INSTALLED") and len(w.urls) == 1
    assert not list((w.tools / "cache").glob("*.zip"))


def test_a_second_installer_holding_the_tools_dir_lock_gets_nothing_done(w):
    import winlock
    peer = winlock.InstallLock(w.tools)
    assert peer.take()
    status = inst(w)
    peer.release()
    assert status == winlock.BUSY and w.urls == [] and w.registry.sets() == [] and not _exe(w).exists()


def test_the_plan_marks_models_the_local_server_already_has_as_present(monkeypatch):
    """A5v2-11: `--ci` printed WOULD-PULL for both models on a box that has them (the real path says PRESENT)."""
    monkeypatch.setattr(ollama_setup, "install_ollama", lambda *a, **k: "PRESENT")
    rows = dict(ollama_setup.setup_ollama(M, ci=True, dry_run=False, probe=lambda: {"all-minilm:latest"}))
    assert rows["ollama:all-minilm"] == "PRESENT" and rows["ollama:qwen2.5-coder:3b"] == "WOULD-PULL"
    rows = dict(ollama_setup.setup_ollama(M, ci=False, dry_run=True, probe=lambda: None))  # no server: all planned
    assert rows["ollama:all-minilm"] == rows["ollama:qwen2.5-coder:3b"] == "WOULD-PULL"


def test_a_binary_without_its_libs_is_repaired_not_present(w):
    _exe(w).parent.mkdir(parents=True)
    _exe(w).write_bytes(b"truncated")  # an interrupted extraction: exe first, no libs, no marker
    w.env["PATH"] = str(w.tools / "ollama")
    assert inst(w).startswith("INSTALLED")
    assert (w.tools / "ollama" / "lib" / "ollama" / "a.dll").is_file()
    assert (w.tools / "ollama" / ".agentic-mercy-complete").is_file() and _exe(w).read_bytes() == b"O"


def test_disk_preflight_wants_4_gb_before_downloading(w):
    status = inst(w, disk_free=lambda p: 1 << 30)
    assert status.startswith("WARN") and "4 GB" in status
    assert w.urls == [] and not w.tools.exists()


@pytest.mark.parametrize("kw", [{"ci": True}, {"dry_run": True}])
def test_plan_modes_only_report_the_zip(w, kw):
    status = inst(w, **kw)
    assert status.startswith("WOULD-INSTALL") and status.endswith("ollama-windows-amd64.zip")
    assert w.urls == [] and not w.tools.exists() and w.registry.sets() == []


def test_the_sandbox_flag_writes_no_registry_value(w):
    w.env["AGENTIC_MERCY_SANDBOX"] = "1"
    assert inst(w).startswith("INSTALLED")
    assert w.registry.sets() == [] and _exe(w).is_file()


def test_a_bad_hash_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    bad = World(tmp_path, M, real_hashes=True)
    assert inst(bad) == "WARN(checksum mismatch — refused)"
    assert not (bad.tools / "ollama").exists()


def test_windows_without_a_pin_never_mentions_brew(w):
    status = inst(w, win_cfg=None)
    assert status.startswith("SKIP") and "brew" not in status


def test_setup_ollama_hands_the_windows_pin_to_the_installer(monkeypatch):
    seen = {}
    monkeypatch.setattr(ollama_setup, "install_ollama", lambda cfg, **kw: seen.update(kw) or "WOULD-INSTALL")
    rows = ollama_setup.setup_ollama(M, ci=True, dry_run=True)
    assert seen["win_cfg"] == M["user_space"]["windows"]["ollama"]
    assert [n for n, _ in rows] == ["ollama", "ollama:all-minilm", "ollama:qwen2.5-coder:3b"]


def test_the_system_is_windows_when_the_platform_switch_says_so(monkeypatch):
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    assert ollama_setup._system({"PROCESSOR_ARCHITECTURE": "ARM64"}) == ("windows", "arm64")
    monkeypatch.setattr(plat, "IS_WINDOWS", False)
    assert ollama_setup._system()[0] != "windows"


def test_an_archive_without_ollama_exe_is_kept_for_the_retry(w):
    """A5v2-02: the verified zip is deleted only once the install worked, here as in `wintools.unzip`."""
    import io
    import zipfile
    from winfakes import sha
    url = w._url(w.manifest["user_space"]["windows"]["ollama"], "x64")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("lib/ollama/a.dll", b"d")
    w.blobs[url] = buf.getvalue()
    w.manifest["user_space"]["windows"]["ollama"]["sha256"]["x64"] = sha(buf.getvalue())
    assert inst(w) == "WARN(ollama.exe missing after extraction)"
    assert list((w.tools / "cache").glob("*.zip"))
