"""Wiring of the Windows base tools into the install pass: ``basetools`` dispatches on the platform
switch (POSIX untouched), Windows has no apt/sudo step, base tools still come before prereqs + deps,
and the doctor repair of ``base-tools`` routes per OS (A5-02, A5-03)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks"), str(_ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import basetools  # noqa: E402
import deps  # noqa: E402
import ollama_setup  # noqa: E402
import ostools  # noqa: E402
import selfheal  # noqa: E402
import userspace  # noqa: E402
import wintools  # noqa: E402
from lib import platform as plat  # noqa: E402

MANIFEST = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))
WIN, POSIX = SimpleNamespace(os_name="windows"), SimpleNamespace(os_name="posix")


@pytest.fixture
def calls(monkeypatch):
    monkeypatch.delenv("AGENTIC_MERCY_SKIP_BASE_TOOLS", raising=False)
    seen: list[str] = []
    monkeypatch.setattr(wintools, "ensure_wintools", lambda *a, **k: seen.append("wintools") or [("git", "INSTALLED git")])
    monkeypatch.setattr(userspace, "ensure_userspace", lambda *a, **k: seen.append("userspace") or [("node", "PRESENT")])
    monkeypatch.setattr(ostools, "install_os_tools",
                        lambda *a, **k: seen.append("ostools") or ([("os-tools", "PRESENT")], None))
    monkeypatch.setattr(basetools.detect, "detect", lambda: SimpleNamespace(os_name="redetected"))
    return seen


def test_windows_dispatches_to_wintools_with_no_apt_and_no_userspace(calls, monkeypatch):
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    rows: list = []
    env, sudo = basetools.before_deps(WIN, MANIFEST, False, lambda *r: rows.append(r))
    assert calls == ["wintools"] and sudo is None
    assert rows == [("base", "git", "INSTALLED git")]
    assert env.os_name == "redetected"  # the new PATH is picked up


def test_windows_ci_keeps_the_env_it_was_given(calls, monkeypatch):
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    env, _ = basetools.before_deps(WIN, MANIFEST, True, lambda *r: None)
    assert env is WIN


def test_posix_path_is_untouched(calls, monkeypatch):
    monkeypatch.setattr(plat, "IS_WINDOWS", False)
    basetools.before_deps(POSIX, MANIFEST, False, lambda *r: None)
    assert calls == ["ostools", "userspace"]


def test_the_skip_switch_skips_windows_too(calls, monkeypatch):
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    monkeypatch.setenv("AGENTIC_MERCY_SKIP_BASE_TOOLS", "1")
    assert basetools.before_deps(WIN, MANIFEST, False, lambda *r: None) == (WIN, None)
    assert calls == []


@pytest.mark.parametrize("windows,expect", [(True, "wintools"), (False, "userspace")])
def test_ensure_base_tools_routes_per_os(calls, monkeypatch, windows, expect):
    monkeypatch.setattr(plat, "IS_WINDOWS", windows)
    basetools.ensure_base_tools(WIN if windows else POSIX, MANIFEST, ci=False, dry_run=False)
    assert calls == [expect]


@pytest.mark.parametrize("windows,expect", [(True, "wintools"), (False, "userspace")])
def test_a_base_tools_doctor_fail_is_repaired_by_the_os_installer(calls, monkeypatch, tmp_path, windows, expect):
    monkeypatch.setattr(plat, "IS_WINDOWS", windows)
    out: list = []
    selfheal._repair(tmp_path, {"base-tools"}, WIN if windows else POSIX, lambda *r: out.append(r))
    assert calls == [expect] and out and out[0][0] == "repair"


def test_windows_installs_base_tools_before_prereqs_and_deps(monkeypatch, tmp_path):
    monkeypatch.delenv("AGENTIC_MERCY_SKIP_BASE_TOOLS", raising=False)
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    for k in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(k, str(tmp_path))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "c"))
    (tmp_path / "c").mkdir()
    order: list[str] = []
    for mod in (deps, selfheal, basetools, ollama_setup, wintools):
        monkeypatch.setitem(sys.modules, mod.__name__, mod)
    monkeypatch.setattr(plat, "run", lambda argv, **k: subprocess.CompletedProcess(argv, 0, "", ""))
    monkeypatch.setattr(selfheal, "_doctor_rows", lambda ci=False: [("link-doctor", "PASS", "")])
    monkeypatch.setattr(wintools, "ensure_wintools", lambda *a, **k: order.append("wintools") or [])
    monkeypatch.setattr(ollama_setup, "setup_ollama", lambda *a, **k: order.append("ollama") or [])
    monkeypatch.setattr(deps, "check_prereqs", lambda env: order.append("prereqs") or [])
    monkeypatch.setattr(deps, "install_deps", lambda *a, **k: order.append("deps") or [])
    selfheal.self_heal(tmp_path / "c", lambda *a: None, ci=False)
    assert order.index("wintools") < order.index("prereqs") < order.index("deps") < order.index("ollama")
