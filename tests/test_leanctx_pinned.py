"""F2 (a 16 GB laptop, 2026-10-30): lean-ctx-bin@3.10.5's postinstall fetched releases/latest (3.12.0) and
ran `lean-ctx onboard`: telemetry on, the [cloud] opt-outs dropped, 52 lean-ctx strings in settings.json, a
settings.json.v4-migration.lock, a `lean-ctx serve` daemon. Its scripts never run now; the binary comes from
the pinned release, sha256-checked; the config is merged again after the deps step."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "installer", ROOT / "hooks"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
import deps  # noqa: E402
import doctor_host  # noqa: E402
import npm_pack  # noqa: E402
import release_bin  # noqa: E402
import selfheal  # noqa: E402

M = json.loads((ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))
DEP = next(d for d in M["deps"] if d["id"] == "lean-ctx")
REL = M["user_space"].get("lean_ctx") or {}  # the owner's manifest edit adds it (FIX3 Owner edits)
ENV = SimpleNamespace(os_name="posix", python="python3", node="node", real_dir=None)


def test_lean_ctx_installs_without_npm_scripts():
    assert DEP["install"][:4] == ["npm", "install", "-g", "--ignore-scripts"]
    assert not npm_pack.needs_pack(DEP["install"])  # no preinstall pkill, so no tarball detour
    assert npm_pack.needs_pack(["npm", "install", "-g", "lean-ctx-bin@3.10.5"])  # a scripted install still is


def test_the_binary_pin_matches_the_npm_package():
    pkg_ver = next(a for a in DEP["install"] if a.startswith("lean-ctx-bin@")).split("@")[1]
    assert DEP["release_binary"] == "lean_ctx" and REL["version"] == pkg_ver and REL["npm_pkg"] == "lean-ctx-bin"
    assert "{asset}" in REL["download"] and "latest" not in REL["download"]
    for key in ("linux-x64", "linux-arm64", "darwin-x64", "darwin-arm64", "windows-x64"):
        a = REL["assets"][key]
        assert re.fullmatch(r"[0-9a-f]{64}", a["sha256"]) and a["name"].startswith("lean-ctx-")


def _pkg(tmp: Path) -> Path:
    pkg = tmp / "lib" / "node_modules" / "lean-ctx-bin"
    (pkg / "bin").mkdir(parents=True)
    (pkg / "package.json").write_text("{}", encoding="utf-8")
    (pkg / "bin" / "lean-ctx.js").write_text("// shim\n", encoding="utf-8")
    return pkg


def _tgz(dest: Path, member: str = "lean-ctx", data: bytes = b"\x7fELF fake") -> None:
    with tarfile.open(dest, "w:gz") as tf:
        info = tarfile.TarInfo(member)
        info.size, info.mode = len(data), 0o755
        tf.addfile(info, io.BytesIO(data))


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    return tmp_path


@pytest.mark.skipif(os.name != "posix", reason="exec bit")
def test_the_binary_is_fetched_into_the_package_and_checked(home, monkeypatch):
    monkeypatch.setattr(release_bin.plat, "IS_WINDOWS", False)
    pkg = _pkg(home)
    got: dict = {}

    def dl(url, dest, timeout=None, sha256=None):
        got.update(url=url, sha256=sha256)
        _tgz(Path(dest))
    ok, note = release_bin.ensure(REL, pkg, dry_run=False, download=dl, key="linux-x64")
    assert ok and "sha256 ok" in note
    assert got["url"] == ("https://github.com/yvgude/lean-ctx/releases/download/v3.10.5/"
                          "lean-ctx-x86_64-unknown-linux-musl.tar.gz")
    assert got["sha256"] == REL["assets"]["linux-x64"]["sha256"]
    assert (pkg / "bin" / "lean-ctx").read_bytes() == b"\x7fELF fake" and os.access(pkg / "bin" / "lean-ctx", os.X_OK)
    assert (pkg / "bin" / "lean-ctx.js").is_file()  # the npm shim stays
    assert release_bin.ensure(REL, pkg, dry_run=False, download=lambda *a, **k: 1 / 0, key="linux-x64",
                              version=lambda p: REL["version"]) == (True, "")


def _drifted(home: Path) -> Path:
    pkg = _pkg(home)
    (pkg / "bin" / "lean-ctx").write_bytes(b"old")
    return pkg


@pytest.mark.skipif(os.name != "posix", reason="exec bit")
def test_a_drifted_binary_is_replaced_by_the_pin(home, monkeypatch):
    """Rohit's PC, round 2: lean-ctx-bin's postinstall had already placed 3.12.0 before the pin existed, and
    `ensure` returned early on any existing binary, so 3.12.0 kept re-injecting hooks."""
    monkeypatch.setattr(release_bin.plat, "IS_WINDOWS", False)
    pkg = _drifted(home)
    ok, note = release_bin.ensure(REL, pkg, dry_run=False, download=lambda u, d, **k: _tgz(Path(d)),
                                  key="linux-x64", version=lambda p: "3.12.0")
    assert ok and "3.12.0" in note and f"v{REL['version']}" in note
    assert (pkg / "bin" / "lean-ctx").read_bytes() == b"\x7fELF fake"
    assert not (pkg / "bin" / "lean-ctx.old").exists()


def test_a_failed_replacement_puts_the_old_binary_back(home):
    pkg = _drifted(home)

    def dl(*_a, **_k):
        raise OSError("offline")
    ok, note = release_bin.ensure(REL, pkg, dry_run=False, download=dl, key="linux-x64", version=lambda p: "3.12.0")
    assert ok is False and "offline" in note
    assert (pkg / "bin" / "lean-ctx").read_bytes() == b"old"  # the npm shim never ends up without a binary


def test_a_pinned_binary_is_left_alone(home):
    pkg = _drifted(home)
    assert release_bin.ensure(REL, pkg, dry_run=False, download=lambda *a, **k: 1 / 0, key="linux-x64",
                              version=lambda p: REL["version"]) == (True, "")
    assert (pkg / "bin" / "lean-ctx").read_bytes() == b"old"


def test_a_dry_run_names_the_replacement(home):
    pkg = _drifted(home)
    ok, note = release_bin.ensure(REL, pkg, dry_run=True, version=lambda p: "3.12.0")
    assert ok and "would replace" in note and (pkg / "bin" / "lean-ctx").read_bytes() == b"old"


def test_a_drifted_lean_ctx_runtime_row_is_repaired_by_the_deps_step(tmp_path, monkeypatch):
    seen: list = []
    monkeypatch.setitem(sys.modules, "deps", deps)  # another test file may have re-loaded `deps`
    monkeypatch.setattr(deps, "install_deps", lambda env, **k: seen.append(env) or [("lean-ctx", "PRESENT (replaced)"),
                                                                                  ("uv", "PRESENT")])
    rows: list = []
    selfheal._repair(tmp_path, {"lean-ctx-runtime"}, ENV, lambda *a: rows.append(a))
    assert seen == [ENV]
    assert ("repair", "lean-ctx", "PRESENT (replaced)") in rows and ("repair", "uv", "PRESENT") not in rows


def test_windows_gets_the_exe_from_the_zip(home, monkeypatch):
    monkeypatch.setattr(release_bin.plat, "IS_WINDOWS", True)
    pkg = _pkg(home)

    def dl(url, dest, timeout=None, sha256=None):
        with zipfile.ZipFile(dest, "w") as zf:
            zf.writestr("lean-ctx.exe", b"MZ fake")
    ok, _ = release_bin.ensure(REL, pkg, dry_run=False, download=dl, key="windows-x64")
    assert ok and (pkg / "bin" / "lean-ctx.exe").read_bytes() == b"MZ fake"


def test_a_checksum_failure_is_a_warn_and_leaves_no_binary(home):
    pkg = _pkg(home)

    def dl(*_a, **_k):
        raise OSError("checksum mismatch — refused")
    ok, note = release_bin.ensure(REL, pkg, dry_run=False, download=dl, key="linux-x64")
    assert not ok and "checksum mismatch" in note and not (pkg / "bin" / "lean-ctx").exists()


def test_nothing_to_place_without_the_package_or_with_a_dry_run(home):
    assert release_bin.ensure(REL, home / "absent", dry_run=False) == (True, "")  # a hand-installed lean-ctx
    pkg = _pkg(home)
    assert release_bin.ensure(REL, pkg, dry_run=False, key="sunos-x64")[0] is False
    assert "would fetch" in release_bin.ensure(REL, pkg, dry_run=True)[1]


def test_a_failed_fetch_is_the_dep_rows_warn(tmp_path, monkeypatch):
    root = tmp_path / "lib" / "node_modules"
    monkeypatch.setattr(deps, "_NPM_ROOT_G", [root])
    monkeypatch.setattr(deps.winutil, "which", lambda n: None)
    monkeypatch.setattr(deps, "_run_install", lambda argv: (_pkg(tmp_path), subprocess.CompletedProcess(argv, 0, "", ""))[1])
    seen: list = []
    monkeypatch.setattr(deps.release_bin, "ensure", lambda cfg, pkg_dir, **k: seen.append(pkg_dir) or (False, "OSError: offline"))
    monkeypatch.setattr(deps, "_load_manifest", lambda: {"deps": [DEP], "user_space": M["user_space"]})
    assert deps.install_deps(ENV) == [("lean-ctx", "WARN(lean-ctx binary: OSError: offline)")]
    assert seen == [root / "lean-ctx-bin"]


def test_a_lean_ctx_string_makes_settings_json_stale(tmp_path, monkeypatch):
    st = tmp_path / "settings.json"
    st.write_text('{"hooks": {"PreToolUse": [{"command": "lean-ctx hook observe"}]}}', encoding="utf-8")
    monkeypatch.setattr(selfheal, "_render_sources", lambda: [])
    monkeypatch.setattr(selfheal, "interpreter_gone", lambda p: False)
    monkeypatch.setattr(selfheal, "_tier_drift", lambda p: False)
    assert selfheal._stale(st)
    st.write_text("{}", encoding="utf-8")
    assert not selfheal._stale(st)


def test_the_daily_deps_step_merges_the_lean_ctx_config_back(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("selfheal_daily_f2", ROOT / "hooks" / "tools" / "selfheal-daily.py")
    sd = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sd)  # type: ignore[union-attr]
    monkeypatch.setenv("AGENTIC_MERCY_SKIP_BASE_TOOLS", "1")
    monkeypatch.setitem(sys.modules, "deps", deps)
    monkeypatch.setitem(sys.modules, "selfheal", selfheal)
    monkeypatch.setattr(deps, "install_deps", lambda *a, **k: [("lean-ctx", "PRESENT")])
    monkeypatch.setattr(deps, "configure_lean_ctx", lambda **k: ("lean-ctx-config", "OK(merged)"))
    ctx = sd.Ctx(False, tmp_path, 60)
    ctx._env = ENV
    assert sd._deps(ctx) == [("dep", "lean-ctx", "PRESENT"), ("config", "lean-ctx-config", "OK(merged)")]


def test_migration_leftovers_are_gitignored():
    cp = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", "settings.json.v4-migration.lock"],
                        capture_output=True, timeout=20)
    if cp.returncode == 128:
        pytest.skip("not a git checkout")
    assert cp.returncode == 0


@pytest.mark.skipif(os.name != "posix", reason="/proc")
def test_runtime_row_warns_on_a_serve_daemon_and_on_version_drift(tmp_path):
    proc = tmp_path / "proc"
    for pid, argv in ((10, [b"/x/lean-ctx", b"serve", b"--_foreground-daemon"]), (11, [b"/x/lean-ctx"]),
                      (12, [b"bash", b"-c", b"lean-ctx serve"])):
        (proc / str(pid)).mkdir(parents=True)
        (proc / str(pid) / "cmdline").write_bytes(b"\0".join(argv) + b"\0")
    assert doctor_host.leanctx_daemons(proc) == [10]
    st, det = doctor_host.check_leanctx_runtime(M, False, proc_root=proc, version=lambda: "3.12.0",
                                                owned=lambda: False)
    assert st == "WARN" and "pid 10" in det and "3.12.0" in det and "3.10.5" in det
    (proc / "10" / "cmdline").write_bytes(b"/x/lean-ctx\0")
    assert doctor_host.check_leanctx_runtime(M, False, proc_root=proc, version=lambda: "3.10.5")[0] == "PASS"
    assert doctor_host.check_leanctx_runtime(M, True)[0] == "SKIP"


@pytest.mark.skipif(os.name != "posix", reason="/proc")
def test_version_drift_fails_only_on_an_installer_owned_binary(tmp_path):
    """The installer can replace its own lean-ctx-bin binary (FAIL, repaired by the deps step); a hand-installed
    lean-ctx (this PC's ~/.local/bin/lean-ctx) stays a WARN: no repair can change it."""
    proc = tmp_path / "proc"
    proc.mkdir()
    st, det = doctor_host.check_leanctx_runtime(M, False, proc_root=proc, version=lambda: "3.12.0", owned=lambda: True)
    assert st == "FAIL" and "3.12.0" in det
    assert doctor_host.check_leanctx_runtime(M, False, proc_root=proc, version=lambda: "3.12.0",
                                             owned=lambda: False)[0] == "WARN"
    assert doctor_host.check_leanctx_runtime(M, False, proc_root=proc, version=lambda: "3.10.5",
                                             owned=lambda: True)[0] == "PASS"
