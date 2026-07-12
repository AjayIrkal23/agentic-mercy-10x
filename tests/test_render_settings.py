"""test_render_settings.py — settings.json render equivalence + overlay (P6-T3).

Proves:
  * render(settings.template.json) == live settings.json byte-for-byte (the
    template is a faithful tokenization — no hook registration drift);
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


def test_render_equals_live_byte_for_byte():
    r = _load_render()
    ok, msg = r.check_equivalence()
    assert ok, msg


def test_template_has_no_bare_interpreter_literals():
    r = _load_render()
    tmpl = (_ROOT / "settings.template.json").read_text(encoding="utf-8")
    # every dispatch command must be tokenized, not a bare python3/usr-bin-node
    assert "python3 ${HOME}" not in tmpl
    assert "/usr/bin/node" not in tmpl
    assert "{{PYTHON}}" in tmpl and "{{NODE}}" in tmpl and "{{CLAUDE_DIR}}" in tmpl
    # sanity: substitution restores a bare interpreter for POSIX
    rendered = r.substitute(tmpl)
    assert "python3 ${HOME}/.claude/hooks/dispatch.py" in rendered


def test_user_overlay_deep_merges_user_wins():
    r = _load_render()
    tmpl = _ROOT / "settings.template.json"
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump({"env": {"SCRATCH": "kept"}, "theme": "light"}, fh)
        user_path = Path(fh.name)
    text = r.render(template_path=tmpl, user_path=user_path)
    data = json.loads(text)
    assert data["env"]["SCRATCH"] == "kept"          # overlay key merged
    assert data["theme"] == "light"                   # user wins over base "dark"
    assert data["model"] == "opus[1m]"                # base preserved
    assert "SessionStart" in data["hooks"]            # hooks block intact
