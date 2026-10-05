"""lean-ctx-bin's preinstall runs `pkill -f lean-ctx`, which kills the very `npm install -g
lean-ctx-bin@…` that runs it (npm: "process terminated, signal SIGTERM", rc 1, package rolled
back, dangling bin links). The install therefore goes through a tarball whose path does not
contain that name."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import deps  # noqa: E402
import npm_pack  # noqa: E402
from lib import platform as plat  # noqa: E402


def test_only_packages_whose_scripts_pkill_themselves_are_packed():
    assert npm_pack.needs_pack(["npm", "install", "-g", "lean-ctx-bin@3.10.5"])
    assert not npm_pack.needs_pack(["npm", "install", "-g", "tdd-guard"])
    assert not npm_pack.needs_pack(["uv", "tool", "install", "semgrep==1.178.0"])


def _fake(calls, pack_rc=0, install_rc=0):
    def run(argv, **_k):
        argv = [str(a) for a in argv]
        calls.append(argv)
        if argv[:2] == ["npm", "pack"]:
            dest = Path(argv[argv.index("--pack-destination") + 1])
            if pack_rc == 0:
                (dest / "lean-ctx-bin-3.10.5.tgz").write_bytes(b"x")
            return subprocess.CompletedProcess(argv, pack_rc, "", "")
        return subprocess.CompletedProcess(argv, install_rc, "", "")
    return run


def test_install_packs_then_installs_a_tarball_whose_path_hides_the_name(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    calls: list = []
    cp = npm_pack.install(["npm", "install", "-g", "lean-ctx-bin@3.10.5"], run=_fake(calls))
    assert cp.returncode == 0
    assert calls[0][:3] == ["npm", "pack", "lean-ctx-bin@3.10.5"]
    inst = calls[1]
    assert inst[:3] == ["npm", "install", "-g"] and inst[3].endswith(".tgz")
    assert "lean-ctx" not in " ".join(inst)


def test_dangling_bin_links_from_a_killed_install_are_removed_first(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    bin_dir = tmp_path / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "lean-ctx").symlink_to(tmp_path / "gone" / "lean-ctx")
    live = tmp_path / "real"
    live.write_text("x")
    (bin_dir / "keep").symlink_to(live)
    npm_pack.install(["npm", "install", "-g", "lean-ctx-bin@3.10.5"], run=_fake([]))
    assert not (bin_dir / "lean-ctx").is_symlink() and (bin_dir / "keep").is_symlink()


def test_only_dangling_links_into_the_lean_ctx_install_are_removed(tmp_path, monkeypatch):
    """Santa: every dangling link in ~/.local/bin was deleted, e.g. a tool on an unmounted drive."""
    monkeypatch.setenv("HOME", str(tmp_path))
    bin_dir = tmp_path / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    pkg = tmp_path / ".local" / "lib" / "node_modules" / "lean-ctx-bin" / "bin" / "lean-ctx"
    (bin_dir / "lean-ctx").symlink_to(pkg)            # dangling, into the lean-ctx install: ours
    (bin_dir / "mytool").symlink_to("/media/usb/tools/mytool")  # dangling, the user's
    (bin_dir / "other").symlink_to(tmp_path / ".local" / "lib" / "node_modules" / "tdd-guard" / "cli.js")
    npm_pack.install(["npm", "install", "-g", "lean-ctx-bin@3.10.5"], run=_fake([]))
    assert not (bin_dir / "lean-ctx").is_symlink()
    assert (bin_dir / "mytool").is_symlink() and (bin_dir / "other").is_symlink()


def test_a_failed_pack_or_install_returns_its_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    spec = ["npm", "install", "-g", "lean-ctx-bin@3.10.5"]
    assert npm_pack.install(spec, run=_fake([], pack_rc=1)).returncode == 1
    assert npm_pack.install(spec, run=_fake([], install_rc=7)).returncode == 7


def test_install_deps_routes_lean_ctx_through_the_pack(monkeypatch):
    seen: list = []
    monkeypatch.setattr(npm_pack, "install", lambda cmd, run=None: seen.append(cmd) or subprocess.CompletedProcess(cmd, 0, "", ""))
    monkeypatch.setattr(plat, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, "", ""))
    dep = {"id": "lean-ctx", "which": "definitely-not-a-binary", "install": ["npm", "install", "-g", "lean-ctx-bin@3.10.5"]}
    monkeypatch.setattr(deps, "_load_manifest", lambda: {"deps": [dep]})
    env = SimpleNamespace(os_name="posix", python="python3", node="node", real_dir=str(Path.home() / ".claude"))
    assert deps.install_deps(env, ci=False, dry_run=False) == [("lean-ctx", "INSTALLED")]
    assert seen == [["npm", "install", "-g", "lean-ctx-bin@3.10.5"]]
