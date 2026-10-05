"""PyYAML is NOT optional: without it validate_skills falls back to a naive parser (29 false
R12 HARD failures) and gen-agent-skill-blocks.py cannot import. A fresh Ubuntu has no pip
and PEP 668 blocks `pip install`, so it is installed with uv into the user site."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import deps  # noqa: E402
from lib import platform as plat  # noqa: E402

M = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))
DEP = next(d for d in M["deps"] if d["id"] == "pyyaml")


def test_pyyaml_is_a_required_dep_installed_by_uv_into_the_user_site():
    assert not DEP.get("optional")
    argv = DEP["install_posix"]
    assert argv[:3] == ["uv", "pip", "install"] and "--target" in argv and "{USER_SITE}" in argv
    assert any(a.startswith("pyyaml") for a in argv)


def test_exec_tokens_carry_the_user_site():
    env = SimpleNamespace(real_dir="/x/.claude", python="python3", node="node")
    assert deps._exec_tokens(env)["USER_SITE"].endswith("site-packages")


def test_posix_never_runs_the_pep668_pip_installs():
    pipx = next(d for d in M["deps"] if d["id"] == "pipx")
    assert "install" not in pipx and pipx.get("install_windows")  # POSIX uses uv


def test_install_deps_runs_the_uv_target_install_when_yaml_is_missing(monkeypatch):
    ran: list = []

    def fake_run(argv, **_k):
        ran.append([str(a) for a in argv])
        return subprocess.CompletedProcess(argv, 1 if argv[-2:-1] == ["-c"] else 0, "", "")
    monkeypatch.setattr(plat, "run", fake_run)
    monkeypatch.setattr(deps, "_load_manifest", lambda: {"deps": [DEP]})
    env = SimpleNamespace(os_name="posix", python="python3", node="node", real_dir=str(Path.home() / ".claude"))
    rows = deps.install_deps(env, ci=False, dry_run=False)
    assert rows == [("pyyaml", "INSTALLED")]
    cmd = next(c for c in ran if c[:3] == ["uv", "pip", "install"])
    assert "{USER_SITE}" not in " ".join(cmd) and cmd[cmd.index("--target") + 1].endswith("site-packages")
