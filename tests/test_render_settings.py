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
