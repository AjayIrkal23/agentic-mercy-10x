"""test_render_settings.py — settings.json render equivalence + overlay (P6-T3).

Proves:
  * render(settings.template.json) semantically == live settings.json (Claude-
    managed keys ignored; skipped on a fresh checkout without settings.json);
  * render refuses any "lean-ctx" substring and carries managed keys over;
  * a user overlay deep-merges with the user winning and base keys preserved;
  * every rendered hook command is interpreter-tokenized (no bare ``python3``/
    ``/usr/bin/node`` survives in the template — Windows portability).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def _load_render():
    spec = importlib.util.spec_from_file_location("render", _ROOT / "installer" / "render.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["render"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_template_exists_and_valid_json():
    tmpl = _ROOT / "settings.template.json"
    assert tmpl.exists()
    json.loads(_load_render().substitute(tmpl.read_text(encoding="utf-8")))


def test_render_semantically_equals_live():
    if not (_ROOT / "settings.json").exists():
        import pytest
        pytest.skip("settings.json not rendered (fresh checkout / CI)")
    r = _load_render()
    ok, msg = r.check_equivalence()
    assert ok, msg


def test_semantic_check_ignores_claude_managed_keys(tmp_path):
    r = _load_render()
    live = json.loads(r.render(user_path=None, subs=r.machine_subs()))  # same tokens check_equivalence uses
    live.update({"tui": "fullscreen", "theme": "dark-ansi", "voice": {"enabled": True}})
    p = tmp_path / "settings.json"
    p.write_text(json.dumps(live, indent=4))
    ok, msg = r.check_equivalence(live_path=p, user_path=None)
    assert ok, msg
    live["env"]["EXTRA"] = "1"
    p.write_text(json.dumps(live))
    ok, msg = r.check_equivalence(live_path=p, user_path=None)
    assert not ok and "env.EXTRA" in msg


def test_granted_allow_rules_are_claude_managed(tmp_path):
    """An "always allow" granted in Claude Code's own dialog lands in permissions.allow: the
    equivalence check ignores it and a re-render (the daily self-heal) keeps it, so the user
    is never asked twice (CLAUDE.md §11). User-added deny/ask rules are carried the same way
    (tests/test_settings_carry.py); only template-owned drift fails the check."""
    r = _load_render()
    live = json.loads(r.render(user_path=None, subs=r.machine_subs()))
    live.setdefault("permissions", {})["allow"] = ["mcp__reticle"]
    p = tmp_path / "settings.json"
    p.write_text(json.dumps(live))
    ok, msg = r.check_equivalence(live_path=p, user_path=None)
    assert ok, msg
    data = json.loads(r.carry_managed(r.render(user_path=None), p))
    assert data["permissions"]["allow"] == ["mcp__reticle"]
    live["permissions"]["deny"] = ["Bash(rm:*)"]
    p.write_text(json.dumps(live))
    ok, msg = r.check_equivalence(live_path=p, user_path=None)
    assert ok, msg  # a user-added deny rule is carried by the re-render, not drift
    live["hooks"] = {}
    p.write_text(json.dumps(live))
    ok, msg = r.check_equivalence(live_path=p, user_path=None)
    assert not ok and "hooks" in msg


def test_render_refuses_lean_ctx_and_carries_managed_keys(tmp_path):
    import pytest
    r = _load_render()
    overlay = tmp_path / "user.json"
    overlay.write_text(json.dumps({"statusLine": {"command": "lean-ctx statusline"}}))
    with pytest.raises(ValueError):
        r.render(user_path=overlay)
    old = tmp_path / "settings.json"
    old.write_text(json.dumps({"theme": "dark-ansi", "tui": "fullscreen", "env": {"X": "stale"}}))
    data = json.loads(r.carry_managed(r.render(user_path=None), old))
    assert data["theme"] == "dark-ansi" and data["tui"] == "fullscreen"
    assert "X" not in data["env"]  # only managed keys are carried


def test_template_has_no_bare_interpreter_literals():
    r = _load_render()
    tmpl = (_ROOT / "settings.template.json").read_text(encoding="utf-8")
    # every dispatch command must be tokenized, not a bare python3/usr-bin-node
    assert "python3 ${HOME}" not in tmpl
    assert "/usr/bin/node" not in tmpl
    assert "{{PYTHON}}" in tmpl and "{{CLAUDE_DIR}}" in tmpl
    # sanity: substitution restores a bare interpreter for POSIX
    rendered = r.substitute(tmpl)
    assert "python3 ${HOME}/.claude/hooks/dispatch.py" in rendered


def test_user_overlay_deep_merges_user_wins(tmp_path):
    r = _load_render()
    tmpl = _ROOT / "settings.template.json"
    user_path = tmp_path / "settings.user.json"
    user_path.write_text(json.dumps({"env": {"SCRATCH": "kept"}, "theme": "light"}))
    data = json.loads(r.render(template_path=tmpl, user_path=user_path))
    assert data["env"]["SCRATCH"] == "kept"                         # overlay key merged
    assert data["theme"] == "light"                                 # user wins over base "dark"
    assert data["env"]["CLAUDE_CODE_SUBAGENT_MODEL"] == "sonnet"    # base preserved
    assert "SessionStart" in data["hooks"]                          # hooks block intact


def test_windows_claude_dir_token_is_the_checkout_being_rendered(monkeypatch):
    """Windows renders a concrete CLAUDE_DIR. It must name the checkout whose settings.json
    is rendered/compared, not a HOME-derived dir (a sandboxed HOME broke the doctor)."""
    r = _load_render()
    fake_env = type("Env", (), {"tokens": {"PYTHON": "py -3", "CLAUDE_DIR": "C:/sandbox/home/.claude"}})
    monkeypatch.setitem(sys.modules, "detect", type("M", (), {"detect": staticmethod(lambda: fake_env)}))
    assert r.machine_subs()["CLAUDE_DIR"] == r._ROOT.as_posix()


def test_posix_claude_dir_token_stays_home_literal(monkeypatch):
    r = _load_render()
    fake_env = type("Env", (), {"tokens": {"PYTHON": "python3", "CLAUDE_DIR": "${HOME}/.claude"}})
    monkeypatch.setitem(sys.modules, "detect", type("M", (), {"detect": staticmethod(lambda: fake_env)}))
    assert r.machine_subs()["CLAUDE_DIR"] == "${HOME}/.claude"


def _mod_tree(tmp_path, ids, enabled):
    for mod_id in ids:
        (tmp_path / "mods" / mod_id / ".claude-plugin").mkdir(parents=True)
        (tmp_path / "mods" / mod_id / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": mod_id}))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"mods": {"enabled": enabled}}))
    return manifest


def test_mod_dirs_are_absolute_enabled_and_present(tmp_path):
    """CLAUDE_CODE_PLUGIN_DIRS only loads absolute or ~ paths: never the ${HOME} token."""
    r = _load_render()
    manifest = _mod_tree(tmp_path, ["mercy", "spare"], ["mercy", "missing", "Bad_Id", "has-lean-ctx"])
    dirs = r.mod_dirs(tmp_path, manifest)
    assert dirs == [(tmp_path / "mods" / "mercy").as_posix()]
    assert all(Path(d).is_absolute() and "${HOME}" not in d for d in dirs)


def test_windows_mod_dirs_join_with_semicolon(tmp_path, monkeypatch):
    r = _load_render()
    manifest = _mod_tree(tmp_path, ["a", "b"], ["a", "b"])
    monkeypatch.setattr(r, "mod_dirs", lambda *a, **k: ["/w/mods/a", "/w/mods/b"])
    monkeypatch.setattr(r, "PATHSEP", ";")
    data = json.loads(r.render(user_path=None))
    assert data["env"]["CLAUDE_CODE_PLUGIN_DIRS"] == "/w/mods/a;/w/mods/b"
    assert manifest.exists()


def test_no_enabled_mods_drops_the_env_key(monkeypatch):
    r = _load_render()
    monkeypatch.setattr(r, "mod_dirs", lambda *a, **k: [])
    assert "CLAUDE_CODE_PLUGIN_DIRS" not in json.loads(r.render(user_path=None))["env"]


def test_plugin_dirs_compare_as_a_set_and_plugin_configs_are_carried(tmp_path, monkeypatch):
    r = _load_render()
    monkeypatch.setattr(r, "mod_dirs", lambda *a, **k: ["/x/mods/a", "/x/mods/b"])
    live = json.loads(r.render(user_path=None, subs=r.machine_subs()))
    live["env"]["CLAUDE_CODE_PLUGIN_DIRS"] = r.PATHSEP.join(["/x/mods/b/", "/x/mods/a"])
    live["pluginConfigs"] = {"mercy@inline": {"options": {"pulse": "quiet"}}}
    p = tmp_path / "settings.json"
    p.write_text(json.dumps(live))
    ok, msg = r.check_equivalence(live_path=p, user_path=None)
    assert ok, msg
    carried = json.loads(r.carry_managed(r.render(user_path=None), p))
    assert carried["pluginConfigs"] == {"mercy@inline": {"options": {"pulse": "quiet"}}}
