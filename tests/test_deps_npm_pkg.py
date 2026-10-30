"""FIX-r2 I6: a bin-less global npm package is probed under `npm root -g` (no reinstall every run),
and a sandbox-HOME rehearsal installs npm globals under $HOME/.npm-global, never the real prefix."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "installer", ROOT / "hooks"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
import deps  # noqa: E402


def _fake_npm(monkeypatch, root: Path, calls: list):
    def run(argv, timeout=None, **_):
        calls.append(list(argv))
        out = str(root) + "\n" if argv[:3] == ["npm", "root", "-g"] else ""
        return subprocess.CompletedProcess(argv, 0, out, "")
    monkeypatch.setattr(deps.plat, "run", run)
    monkeypatch.setattr(deps, "_NPM_ROOT_G", [])


def test_npm_pkg_present_reads_npm_root(tmp_path, monkeypatch):
    calls: list = []
    _fake_npm(monkeypatch, tmp_path, calls)
    assert not deps.npm_pkg_present("tdd-guard-vitest")
    (tmp_path / "tdd-guard-vitest").mkdir()
    (tmp_path / "tdd-guard-vitest" / "package.json").write_text("{}", encoding="utf-8")
    assert deps.npm_pkg_present("tdd-guard-vitest") and not deps.npm_pkg_present(None)


def test_sandbox_npm_install_gets_a_home_prefix(tmp_path, monkeypatch):
    calls: list = []
    _fake_npm(monkeypatch, tmp_path, calls)
    monkeypatch.setenv("HOME", str(tmp_path / "h"))
    monkeypatch.setattr(deps.npm_pack, "needs_pack", lambda step: False)
    monkeypatch.setenv("AGENTIC_MERCY_SANDBOX", "1")
    deps._run_install(["npm", "install", "-g", "x"])
    assert calls[-1][-2:] == ["--prefix", str(Path.home() / ".npm-global")]
    monkeypatch.delenv("AGENTIC_MERCY_SANDBOX")
    deps._run_install(["npm", "install", "-g", "x"])
    assert "--prefix" not in calls[-1]


def test_manifest_probes_tdd_guard_vitest_by_package():
    import json
    man = json.loads((ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))
    dep = next(d for d in man["deps"] if d["id"] == "tdd-guard-vitest")
    assert dep.get("npm_pkg") == "tdd-guard-vitest" and "which" not in dep
