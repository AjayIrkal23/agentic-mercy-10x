"""The daily re-render must not drop what the user (or Claude Code on the user's behalf) added
to settings.json: plugins enabled through /plugin, extra marketplaces, permission rules
(Santa autonomy review). Template-owned entries stay template-owned; additions are unioned."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, _ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.fixture
def r():
    return _load("render", "installer/render.py")


@pytest.fixture
def live(r, tmp_path):
    data = json.loads(r.render(user_path=None, subs=r.machine_subs()))
    data["enabledPlugins"]["mine@elsewhere"] = True
    data.setdefault("extraKnownMarketplaces", {})["elsewhere"] = {"source": {"source": "github", "repo": "u/r"}}
    perms = data.setdefault("permissions", {})
    perms["allow"] = ["mcp__reticle"]
    perms["deny"] = ["Bash(rm:*)"]
    perms["ask"] = ["Bash(git push:*)"]
    p = tmp_path / "settings.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p, data


def test_rerender_keeps_user_added_plugins_marketplaces_and_rules(r, live):
    p, _ = live
    out = json.loads(r.carry_managed(r.render(user_path=None), p))
    assert out["enabledPlugins"]["mine@elsewhere"] is True
    assert "elsewhere" in out["extraKnownMarketplaces"]
    assert out["permissions"]["deny"] == ["Bash(rm:*)"]
    assert out["permissions"]["ask"] == ["Bash(git push:*)"]
    assert out["permissions"]["allow"] == ["mcp__reticle"]


def test_rerender_keeps_the_templates_own_entries_and_template_wins_conflicts(r, live):
    p, data = live
    tmpl = json.loads(r.render(user_path=None))
    some_plugin = next(iter(tmpl["enabledPlugins"]))
    data["enabledPlugins"][some_plugin] = not tmpl["enabledPlugins"][some_plugin]
    mk = next(iter(tmpl["extraKnownMarketplaces"]))
    data["extraKnownMarketplaces"][mk] = {"source": {"source": "github", "repo": "evil/fork"}}
    p.write_text(json.dumps(data), encoding="utf-8")
    out = json.loads(r.carry_managed(r.render(user_path=None), p))
    assert out["enabledPlugins"][some_plugin] == tmpl["enabledPlugins"][some_plugin]
    assert out["extraKnownMarketplaces"][mk] == tmpl["extraKnownMarketplaces"][mk]
    assert set(tmpl["enabledPlugins"]) <= set(out["enabledPlugins"])


def test_user_additions_never_make_the_equivalence_check_fail_forever(r, live):
    p, _ = live
    ok, msg = r.check_equivalence(live_path=p, user_path=None)
    assert ok, msg


def test_the_check_still_catches_real_drift_next_to_user_additions(r, live):
    p, data = live
    data["hooks"] = {}
    p.write_text(json.dumps(data), encoding="utf-8")
    ok, msg = r.check_equivalence(live_path=p, user_path=None)
    assert not ok and "hooks" in msg
    data = json.loads(r.render(user_path=None, subs=r.machine_subs()))
    del data["enabledPlugins"][next(iter(data["enabledPlugins"]))]  # a template plugin went missing
    p.write_text(json.dumps(data), encoding="utf-8")
    ok, msg = r.check_equivalence(live_path=p, user_path=None)
    assert not ok and "enabledPlugins" in msg


def test_settings_safety_does_not_fail_on_a_user_added_deny_rule(live):
    import doctor_checks
    p, _ = live
    (p.parent / "settings.template.json").write_text((_ROOT / "settings.template.json").read_text(encoding="utf-8"),
                                                    encoding="utf-8")
    st, detail = doctor_checks.settings_safety_status(p.parent)
    assert st == "PASS", detail


def test_settings_safety_still_fails_on_a_templated_deny_or_lean_ctx(tmp_path):
    import doctor_checks
    (tmp_path / "settings.template.json").write_text(json.dumps({"permissions": {"deny": ["x"]}}), encoding="utf-8")
    assert doctor_checks.settings_safety_status(tmp_path)[0] == "FAIL"
    (tmp_path / "settings.template.json").write_text("{}", encoding="utf-8")
    (tmp_path / "settings.json").write_text('{"a": "lean-ctx"}', encoding="utf-8")
    assert doctor_checks.settings_safety_status(tmp_path)[0] == "FAIL"


def test_carry_never_brings_lean_ctx_injections_back(r, live):
    """lean-ctx-bin's first run writes hooks + 68 `mcp__lean-ctx__*` allow rules into
    settings.json; carrying those made doctor settings-safety FAIL on every fresh install."""
    p, data = live
    data["permissions"]["allow"] = ["mcp__reticle", "mcp__lean-ctx__ctx_read"]
    data["permissions"]["deny"] = ["Read(lean-ctx)"]
    data["enabledPlugins"]["lean-ctx@x"] = True
    p.write_text(json.dumps(data), encoding="utf-8")
    out = r.carry_managed(r.render(user_path=None), p)
    assert "lean-ctx" not in out
    assert json.loads(out)["permissions"]["allow"] == ["mcp__reticle"]


def test_an_injected_settings_json_is_re_rendered_even_when_it_looks_fresh(tmp_path, monkeypatch):
    selfheal = _load("selfheal", "installer/selfheal.py")
    target = tmp_path / "t"
    target.mkdir()
    st = target / "settings.json"
    st.write_text(json.dumps({"hooks": {"PostToolUse": [{"command": "lean-ctx hook observe"}]}}), encoding="utf-8")
    monkeypatch.setattr(selfheal, "_stale", lambda p: False)
    emitted: list = []
    selfheal._ensure_settings(target, None, lambda *a: emitted.append(a))
    assert "lean-ctx" not in st.read_text(encoding="utf-8")
    assert any("OK(rendered" in s for _, _, s in emitted)


def test_ensure_settings_writes_atomically(tmp_path, monkeypatch, r):
    selfheal = _load("selfheal", "installer/selfheal.py")
    swaps: list = []
    real = os.replace
    monkeypatch.setattr(os, "replace", lambda a, b: swaps.append((Path(a).name, Path(b).name)) or real(a, b))
    target = tmp_path / "t"
    target.mkdir()
    (target / "settings.json").write_text("{}", encoding="utf-8")
    emitted: list = []
    selfheal._ensure_settings(target, None, lambda *a: emitted.append(a), force=True)
    assert swaps and swaps[-1][1] == "settings.json" and swaps[-1][0].startswith(".settings-")
    json.loads((target / "settings.json").read_text(encoding="utf-8"))
