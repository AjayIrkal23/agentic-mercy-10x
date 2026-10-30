"""self_heal / relocate / install.py --ci rehearsed in a sandbox (audit 2026-10-05 I-03,
I-06, I-08, I-16). HOME, CLAUDE_CONFIG_DIR and the target are tmp dirs; every subprocess
goes through a recorder (no network, no claude CLI, no npm); the doctor is stubbed."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bootstrap  # noqa: E402
import deps  # noqa: E402
import selfheal  # noqa: E402
from lib import platform as plat  # noqa: E402

OK = [("link-doctor", "PASS", "")]


@pytest.fixture
def box(tmp_path, monkeypatch):
    home, target = tmp_path / "home", tmp_path / "claude"
    home.mkdir()
    target.mkdir()
    # other test files re-exec installer modules into sys.modules; pin the objects this
    # file patches so selfheal's lazy `import deps` sees the same module (I-17 isolation)
    for mod in (deps, selfheal, bootstrap):
        monkeypatch.setitem(sys.modules, mod.__name__, mod)
    for k, v in (("HOME", home), ("USERPROFILE", home), ("CLAUDE_CONFIG_DIR", target)):
        monkeypatch.setenv(k, str(v))
    calls: list[list[str]] = []

    def fake_run(argv, **_kw):
        calls.append([str(a) for a in argv])
        return subprocess.CompletedProcess(argv, 0, "", "")
    monkeypatch.setattr(plat, "run", fake_run)
    rounds: list = []
    monkeypatch.setattr(selfheal, "_doctor_rows", lambda ci=False: rounds.pop(0) if rounds else OK)
    return {"home": home, "target": target, "calls": calls, "rounds": rounds}


def _emits():
    seen: list = []
    return seen, (lambda kind, name, status: seen.append((kind, name, status)))


def test_ci_rehearsal_writes_nothing_outside_the_checkout(box):
    seen, emit = _emits()
    res = selfheal.self_heal(box["target"], emit, ci=True)
    assert res["success"] and res["rounds"] == 1
    flat = [" ".join(c) for c in box["calls"]]
    assert not [c for c in flat if "npm install" in c or "mcp add" in c or "plugin install" in c]
    assert not (box["home"] / ".config" / "lean-ctx" / "config.toml").exists()
    assert (box["target"] / "settings.json").is_file()
    assert any(k == "config" and n == "lean-ctx-config" and s.startswith("WOULD") for k, n, s in seen)


def test_lean_ctx_config_is_written_before_lean_ctx_is_installed(box, monkeypatch):
    order: list[str] = []
    for name in ("configure_lean_ctx", "install_deps", "register_mcps"):
        real = getattr(deps, name)
        monkeypatch.setattr(deps, name, lambda *a, _r=real, _n=name, **k: order.append(_n) or _r(*a, **k))
    _, emit = _emits()
    selfheal.self_heal(box["target"], emit, ci=False)
    assert order == ["configure_lean_ctx", "install_deps", "register_mcps"]
    assert (box["home"] / ".config" / "lean-ctx" / "config.toml").is_file()


def test_a_crashing_lean_ctx_config_is_a_warn_not_an_abort(box, monkeypatch):
    def boom(**_k):
        raise PermissionError("read-only home")
    monkeypatch.setattr(deps, "configure_lean_ctx", boom)
    seen, emit = _emits()
    assert selfheal.self_heal(box["target"], emit, ci=True)["success"]
    assert any(n == "lean-ctx-config" and s.startswith("WARN") for _, n, s in seen)


def test_loop_stops_when_a_repair_changes_nothing(box):
    fail = [("mods", "FAIL", "M3 console")]
    box["rounds"].extend([fail, fail, fail, fail])
    _, emit = _emits()
    res = selfheal.self_heal(box["target"], emit, ci=True)
    assert not res["success"] and res["rounds"] == 2 and res["fails"] == ["mods"]


def test_repair_routes_failed_rows(box, monkeypatch):
    ran: list[str] = []
    monkeypatch.setattr(selfheal, "_run_script", lambda _t, rel, _e, *a: ran.append(rel))
    rendered: list[bool] = []
    monkeypatch.setattr(selfheal, "_ensure_settings", lambda *a, force=False: rendered.append(force))
    _, emit = _emits()
    selfheal._repair(box["target"], {"generated-in-sync"}, None, emit)
    assert ran == ["hooks/gen-invoke-skills.py", "hooks/gen-agent-skill-blocks.py"]
    selfheal._repair(box["target"], {"mods"}, None, emit)
    assert rendered == [True]  # mods.enabled feeds CLAUDE_CODE_PLUGIN_DIRS: re-render
    ran.clear()
    selfheal._repair(box["target"], {"workflows-rendered"}, None, emit)  # I10: the per-machine render
    assert ran == ["scripts/build_workflows.py"] and rendered == [True]  # no settings re-render for it


def test_repair_routes_oomguard_rows_only_when_allowed(box, monkeypatch):
    import types
    seen, emit = _emits()
    monkeypatch.delenv("OOMGUARD_REPAIR_ALLOW_TEST", raising=False)
    monkeypatch.setitem(sys.modules, "oomguard_setup", None)       # importing it would raise
    selfheal._repair(box["target"], {"memwatch-unit"}, None, emit)
    assert seen == [("repair", "oomguard", "SKIP(pytest)")]
    seen.clear()
    monkeypatch.setenv("OOMGUARD_REPAIR_ALLOW_TEST", "1")
    monkeypatch.setitem(sys.modules, "oomguard_setup",
                        types.SimpleNamespace(ensure=lambda dry=False: ["memwatch: CREATED"]))
    selfheal._repair(box["target"], {"memwatch-unit"}, None, emit)
    assert ("repair", "oomguard", "memwatch: CREATED") in seen
    seen.clear()
    selfheal._repair(box["target"], {"memwatch-code"}, None, emit)  # O7: a stale daemon is repaired too
    assert ("repair", "oomguard", "memwatch: CREATED") in seen


def test_memwatch_code_warn_runs_the_oomguard_repair_without_a_fail(box, monkeypatch):
    rows = [("memwatch-code", "WARN", "daemon older than hooks/tools/memwatch.py"), ("render", "PASS", "")]
    repaired = []
    monkeypatch.setattr(selfheal, "pin_config_dir", lambda target: None)
    monkeypatch.setattr(selfheal, "_heal_line_endings", lambda *a, **k: None)
    monkeypatch.setattr(selfheal, "_install_pass", lambda *a, **k: None)
    monkeypatch.setattr(selfheal, "_doctor_rows", lambda ci: rows)
    monkeypatch.setattr(selfheal, "_repair", lambda target, failed, env, emit: repaired.append(set(failed)))
    monkeypatch.setitem(sys.modules, "detect", __import__("types").SimpleNamespace(detect=lambda: None))
    _, emit = _emits()
    res = selfheal.self_heal(box["target"], emit)
    assert res["success"] is True and repaired == [{"memwatch-code"}]


def test_forced_rerender_keeps_a_bounded_backup(box, monkeypatch):
    st = box["target"] / "settings.json"
    st.write_text("{}\n", encoding="utf-8")
    _, emit = _emits()
    for _ in range(5):
        selfheal._repair(box["target"], {"render-equivalence"}, None, emit)
        st.write_text("{}\n", encoding="utf-8")
        time.sleep(0.01)
    assert len(list(box["target"].glob("settings.json.bak-2*"))) <= 3


def test_stale_settings_are_rerendered(box, monkeypatch, tmp_path):
    st = box["target"] / "settings.json"
    st.write_text("{}\n", encoding="utf-8")
    src = tmp_path / "settings.template.json"
    src.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(selfheal, "_render_sources", lambda: [src])
    seen, emit = _emits()
    old = time.time() - 3600
    os.utime(st, (old, old))
    selfheal._ensure_settings(box["target"], None, emit)
    assert seen[-1][2].startswith("OK(rendered")
    seen.clear()
    selfheal._ensure_settings(box["target"], None, emit)  # now newer than its sources
    assert seen[-1][2].startswith("PRESENT")


def test_a_plan_tier_change_re_renders_the_tier_keys(box, monkeypatch, tmp_path):
    """REVIEW2 integrate Fix 1: a tier change touches no render source, so the mtime check alone
    kept model / fallbackModel / CLAUDE_CODE_SUBAGENT_MODEL from the old tier forever."""
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(state))
    monkeypatch.setattr(selfheal, "_render_sources", lambda: [])
    monkeypatch.setattr(selfheal, "interpreter_gone", lambda st: False)
    st = box["target"] / "settings.json"
    seen, emit = _emits()
    selfheal._ensure_settings(box["target"], None, emit)        # missing: no tier file -> max20
    selfheal._ensure_settings(box["target"], None, emit)
    assert seen[-1][2].startswith("PRESENT")
    (state / "plan-tier.json").write_text('{"tier": "pro"}\n', encoding="utf-8")
    assert selfheal._stale(st)
    selfheal._ensure_settings(box["target"], None, emit)
    assert seen[-1][2].startswith("OK(rendered")
    data = json.loads(st.read_text(encoding="utf-8"))
    assert (data["model"], data["fallbackModel"], data["env"]["CLAUDE_CODE_SUBAGENT_MODEL"]) == \
        ("sonnet", ["haiku"], "haiku")
    assert not selfheal._stale(st)
    selfheal._ensure_settings(box["target"], None, emit)
    assert seen[-1][2].startswith("PRESENT")


def test_a_removed_model_key_is_not_tier_drift(box, monkeypatch, tmp_path):
    """FIX-r2 I4: `/model` → Default deletes `model`; that is the user's choice, not drift."""
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(state))
    (state / "plan-tier.json").write_text('{"tier": "max20"}\n', encoding="utf-8")
    monkeypatch.setattr(selfheal, "_render_sources", lambda: [])
    monkeypatch.setattr(selfheal, "interpreter_gone", lambda st: False)
    st = box["target"] / "settings.json"
    _, emit = _emits()
    selfheal._ensure_settings(box["target"], None, emit)
    data = json.loads(st.read_text(encoding="utf-8"))
    data.pop("model")
    st.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    assert not selfheal._tier_drift(st)
    data["model"] = "sonnet"  # present with another tier's value: drift
    st.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    assert selfheal._tier_drift(st)


def test_relocate_merges_and_skips_vcs_dirs(tmp_path):
    src, target = tmp_path / "clone", tmp_path / "claude"
    for rel in ("skills/a/SKILL.md", ".git/HEAD", "hooks/node_modules/x.js", "install-ui.py"):
        (src / rel).parent.mkdir(parents=True, exist_ok=True)
        (src / rel).write_text("x", encoding="utf-8")
    (target / "projects").mkdir(parents=True)
    (target / "projects" / "keep.jsonl").write_text("mine", encoding="utf-8")
    n = bootstrap.relocate(src, target, emit=lambda *a: None)
    assert n == 2
    assert (target / "skills" / "a" / "SKILL.md").is_file() and (target / "install-ui.py").is_file()
    assert not (target / ".git").exists() and not (target / "hooks" / "node_modules").exists()
    assert (target / "projects" / "keep.jsonl").read_text(encoding="utf-8") == "mine"


def test_ci_wording_says_what_runs():
    for text in (bootstrap.__doc__, (_ROOT / "PREREQUISITES.md").read_text(encoding="utf-8")):
        assert "deps.py" in text and "local" in text, text[:200]
