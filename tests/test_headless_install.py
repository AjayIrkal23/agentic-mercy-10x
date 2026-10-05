"""One-command install wiring: --headless really installs (console, no UI), base tools come
first, and one batched checklist comes out at the end."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bootstrap  # noqa: E402
import deps  # noqa: E402
import ollama_setup  # noqa: E402
import ostools  # noqa: E402
import selfheal  # noqa: E402
import userspace  # noqa: E402
from lib import platform as plat  # noqa: E402

OK = [("link-doctor", "PASS", "")]
SUDO = "sudo apt-get install -y iproute2"


@pytest.fixture
def box(tmp_path, monkeypatch):
    home, target = tmp_path / "home", tmp_path / "claude"
    home.mkdir()
    target.mkdir()
    for mod in (deps, selfheal, bootstrap, userspace, ollama_setup, ostools):
        monkeypatch.setitem(sys.modules, mod.__name__, mod)
    for k, v in (("HOME", home), ("USERPROFILE", home), ("CLAUDE_CONFIG_DIR", target)):
        monkeypatch.setenv(k, str(v))
    monkeypatch.delenv("AGENTIC_MERCY_SKIP_BASE_TOOLS", raising=False)
    monkeypatch.setattr(plat, "run", lambda argv, **_k: subprocess.CompletedProcess(argv, 0, "", ""))
    monkeypatch.setattr(selfheal, "_doctor_rows", lambda ci=False: OK)
    order: list[str] = []
    monkeypatch.setattr(userspace, "ensure_userspace",
                        lambda *a, **k: order.append("userspace") or [("node", "INSTALLED")])
    monkeypatch.setattr(ollama_setup, "setup_ollama",
                        lambda *a, **k: order.append("ollama") or [("ollama", "PRESENT")])
    monkeypatch.setattr(ostools, "install_os_tools",
                        lambda *a, **k: order.append("ostools") or ([("os-tools", "NEEDS-SUDO")], SUDO))
    monkeypatch.setattr(deps, "install_deps", lambda *a, **k: order.append("deps") or [])
    return {"target": target, "order": order}


def test_headless_flag_is_a_real_install_and_ci_stays_a_plan(monkeypatch):
    seen: list = []
    monkeypatch.setattr(bootstrap, "_launch_ui", lambda: seen.append("ui") or 0)
    monkeypatch.setattr(bootstrap, "_run_headless", lambda ci: seen.append(f"headless:{ci}") or 0)
    monkeypatch.setattr(bootstrap, "_needs_relocate", lambda *a: False)
    assert bootstrap.main(["--headless"]) == 0
    assert bootstrap.main(["--ci"]) == 0
    assert seen == ["headless:False", "headless:True"]


def test_base_tools_install_before_the_deps_that_need_them(box):
    res = selfheal.self_heal(box["target"], lambda *a: None, ci=False)
    o = box["order"]
    # apt first (curl for the claude / uv installers), then ~/.local tools, then what needs them
    assert o.index("ostools") < o.index("userspace") < o.index("deps") < o.index("ollama")
    assert res["success"]


def test_the_users_settings_are_kept_before_anything_is_installed(box, monkeypatch):
    import settings_install
    monkeypatch.setitem(sys.modules, "settings_install", settings_install)
    monkeypatch.setattr(settings_install, "preserve_existing",
                        lambda *a, **k: box["order"].append("preserve-settings"))
    selfheal.self_heal(box["target"], lambda *a: None, ci=False)
    assert box["order"][0] == "preserve-settings"


def test_checklist_has_the_sudo_line_and_the_human_only_steps(box):
    res = selfheal.self_heal(box["target"], lambda *a: None, ci=False)
    text = "\n".join(res["todo"])
    assert text.count(SUDO) == 1
    assert "/mcp" in text and "gh auth login" in text


def test_the_skip_switch_keeps_an_offline_run_off_the_network(box, monkeypatch):
    monkeypatch.setenv("AGENTIC_MERCY_SKIP_BASE_TOOLS", "1")
    selfheal.self_heal(box["target"], lambda *a: None, ci=False)
    assert "userspace" not in box["order"] and "ostools" not in box["order"]


def test_ci_plan_installs_nothing_but_still_prints_the_human_steps(box):
    res = selfheal.self_heal(box["target"], lambda *a: None, ci=True)
    assert "gh auth login" in "\n".join(res["todo"])


def test_the_visual_installer_shows_the_checklist_too(monkeypatch):
    import ui
    monkeypatch.setattr(ui._selfheal, "pin_config_dir", lambda t: None)
    monkeypatch.setattr(ui._selfheal, "self_heal", lambda *a, **k: {
        "success": True, "rounds": 1, "todo": ["Human-only steps:", "  [ ] Run `gh auth login`"]})
    monkeypatch.setitem(ui._JOB, "running", False)
    ui._run_install()
    todo = [s["name"] for s in ui._JOB["steps"] if s["kind"] == "todo"]
    assert todo == ["Human-only steps:", "[ ] Run `gh auth login`"]


def test_headless_run_prints_the_checklist(box, monkeypatch, capsys):
    monkeypatch.setattr(bootstrap, "canonical_target", lambda: box["target"])
    assert bootstrap._run_headless(ci=False) == 0
    out = capsys.readouterr().out
    assert SUDO in out and "gh auth login" in out
