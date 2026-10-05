"""test_render_win.py — render.py / detect.py behaviour that exists for Windows, proven on every OS
(plan W6a + W5): EIO_BACKEND, spaced profile paths, the status line's {{PYTHON_EXE}} token.

Split from test_render_settings.py (250-line cap).
"""

from __future__ import annotations

import importlib.util
import json
import shlex
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]


def _load_render():
    spec = importlib.util.spec_from_file_location("render", _ROOT / "installer" / "render.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["render"] = mod
    spec.loader.exec_module(mod)
    return mod


def _commands(data: dict) -> list[str]:
    cmds = [h["command"] for groups in data["hooks"].values() for g in groups for h in g["hooks"]]
    return cmds + [data["statusLine"]["command"]]


def test_windows_render_drops_eio_backend_and_posix_keeps_it(monkeypatch):
    """EIO_BACKEND=posix aborts every semgrep scan on Windows (no posix backend compiled in);
    Linux needs it (io_uring memlock). The template keeps it, the render decides (A1-03)."""
    r = _load_render()
    monkeypatch.setattr(r.plat, "IS_WINDOWS", True)
    assert "EIO_BACKEND" not in json.loads(r.render(user_path=None))["env"]
    monkeypatch.setattr(r.plat, "IS_WINDOWS", False)
    assert json.loads(r.render(user_path=None))["env"]["EIO_BACKEND"] == "posix"


def test_equivalence_check_applies_the_same_eio_transform(tmp_path, monkeypatch):
    r = _load_render()
    p = tmp_path / "settings.json"
    for windows in (True, False):
        monkeypatch.setattr(r.plat, "IS_WINDOWS", windows)
        p.write_text(r.render(user_path=None, subs=r.machine_subs()), encoding="utf-8")
        assert r.check_equivalence(live_path=p, user_path=None)[0], windows
    monkeypatch.setattr(r.plat, "IS_WINDOWS", True)  # the POSIX-rendered file is drift on Windows
    ok, msg = r.check_equivalence(live_path=p, user_path=None)
    assert not ok and "env.EIO_BACKEND" in msg


SPACED = {"PYTHON": "py -3", "CLAUDE_DIR": "C:/Users/John Smith/.claude",
          "PYTHON_EXE": "C:/Program Files/Python314/python.exe"}


def test_spaced_paths_are_quoted_in_every_command():
    """A profile like C:/Users/John Smith broke every rendered hook command (A1-09)."""
    r = _load_render()
    data = json.loads(r.render(user_path=None, subs=SPACED))
    hooks = [h["command"] for groups in data["hooks"].values() for g in groups for h in g["hooks"]]
    assert all(c.startswith('py -3 "C:/Users/John Smith/.claude/hooks/') for c in hooks), hooks
    assert hooks[0] == 'py -3 "C:/Users/John Smith/.claude/hooks/dispatch.py" pre-tool-use'
    assert data["statusLine"]["command"] == ('"C:/Program Files/Python314/python.exe" '
                                             '"C:/Users/John Smith/.claude/scripts/statusline.py"')
    for c in _commands(data):  # what a shell sees: the path is ONE argument
        assert any(t.endswith(".py") and " " in t for t in shlex.split(c)), c


ODD_DIRS = ["C:/Users/A&B/.claude", "C:/Users/O'Brien/.claude", "C:/Users/a(1)/.claude", "C:/Users/me;x/.claude",
            "C:/Users/a b&c/.claude", "C:/Users/a%b/.claude", "C:/Users/a^b/.claude", "C:/Users/\u00e9t\u00e9/.claude"]


def test_a_path_with_any_shell_special_character_is_quoted_as_one_word():
    """SEC1-08: quoting used to trigger on whitespace only, so `A&B` / `O'Brien` / `a(1)` broke or split every hook."""
    r = _load_render()
    for d in ODD_DIRS:
        subs = {"PYTHON": "py -3", "CLAUDE_DIR": d, "PYTHON_EXE": d.replace(".claude", "py/python.exe")}
        data = json.loads(r.render(user_path=None, subs=subs))
        for c in _commands(data):
            words = shlex.split(c)
            assert any(w.startswith(d.split(".claude")[0]) and w.endswith((".py", ".exe")) for w in words), (d, c)
        assert data["hooks"]["Stop"][0]["hooks"][0]["command"] == f'py -3 "{d}/hooks/dispatch.py" stop', d


@pytest.mark.parametrize("token,bad", [
    ("CLAUDE_DIR", 'C:/Users/a"b/.claude'), ("CLAUDE_DIR", "C:/Users/J $(id)/.claude"),
    ("CLAUDE_DIR", "C:/Users/a`id`/.claude"), ("CLAUDE_DIR", "C:/Users/$HOME/.claude"),
    ("PYTHON_EXE", 'C:/py"x/python.exe'), ("PYTHON", "C:/py$x/python.exe"), ("PYTHON", "py `id`"),
])
def test_a_value_with_a_quote_dollar_or_backtick_is_refused_with_a_clear_error(token, bad):
    r = _load_render()
    with pytest.raises(ValueError, match=token):
        r.render(user_path=None, subs={token: bad})


def test_the_posix_literals_and_mod_dirs_are_not_touched():
    r = _load_render()
    assert r.settings_diff.fill_token("x {{CLAUDE_DIR}}/s", "{{CLAUDE_DIR}}", "${HOME}/.claude") == "x ${HOME}/.claude/s"
    assert r.settings_diff.fill_token("{{NODE}}", "{{NODE}}", "${HOME}/.local/bin/node") == "${HOME}/.local/bin/node"
    mods = "C:/a b;D:/c&d"  # an env value, never a shell word: no quoting, no refusal
    assert r.settings_diff.fill_token("{{MOD_DIRS}}", "{{MOD_DIRS}}", mods) == mods
    assert r.settings_diff.fill_token("{{PYTHON}}", "{{PYTHON}}", "py -3") == "py -3"


def test_check_equivalence_passes_on_a_special_character_render(tmp_path, monkeypatch):
    r = _load_render()
    subs = {"PYTHON": "py -3", "CLAUDE_DIR": ODD_DIRS[0], "PYTHON_EXE": "C:/Program Files (x86)/Py/python.exe"}
    monkeypatch.setattr(r, "machine_subs", lambda: dict(subs))
    p = tmp_path / "settings.json"
    p.write_text(r.render(user_path=None, subs=r.machine_subs()), encoding="utf-8")
    ok, msg = r.check_equivalence(live_path=p, user_path=None)
    assert ok, msg
    assert r.main(["--check", "--out", str(p), "--user", str(tmp_path / "no-overlay.json")]) == 0


def test_spaced_python_path_is_quoted_but_the_py_launcher_is_not():
    r = _load_render()
    subs = {"PYTHON": "C:/Program Files/Python314/python.exe", "CLAUDE_DIR": "E:/prof/.claude"}
    assert json.loads(r.render(user_path=None, subs=subs))["hooks"]["Stop"][0]["hooks"][0]["command"] == (
        '"C:/Program Files/Python314/python.exe" E:/prof/.claude/hooks/dispatch.py stop')
    subs["PYTHON"] = "py -3"
    assert json.loads(r.render(user_path=None, subs=subs))["hooks"]["Stop"][0]["hooks"][0]["command"] == (
        "py -3 E:/prof/.claude/hooks/dispatch.py stop")


def test_check_equivalence_passes_on_a_spaced_render(tmp_path, monkeypatch):
    r = _load_render()
    monkeypatch.setattr(r, "machine_subs", lambda: dict(SPACED))
    p = tmp_path / "settings.json"
    p.write_text(r.render(user_path=None, subs=r.machine_subs()), encoding="utf-8")
    ok, msg = r.check_equivalence(live_path=p, user_path=None)
    assert ok, msg
    assert r.main(["--check", "--out", str(p), "--user", str(tmp_path / "no-overlay.json")]) == 0


def test_unspaced_renders_are_unquoted_and_the_posix_default_is_unchanged():
    r = _load_render()
    posix = json.loads(r.render(user_path=None))
    assert posix["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == (
        "python3 ${HOME}/.claude/hooks/dispatch.py pre-tool-use")
    assert posix["statusLine"]["command"] == "python3 ${HOME}/.claude/scripts/statusline.py"
    win = json.loads(r.render(user_path=None, subs={
        "PYTHON": "py -3", "CLAUDE_DIR": "E:/prof/.claude", "PYTHON_EXE": "E:/py/python.exe"}))
    assert win["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == (
        "py -3 E:/prof/.claude/hooks/dispatch.py pre-tool-use")
    assert win["statusLine"]["command"] == "E:/py/python.exe E:/prof/.claude/scripts/statusline.py"
    assert not any('"' in c for c in _commands(win) + _commands(posix))


def test_statusline_alone_uses_the_python_exe_token():
    tmpl = json.loads((_ROOT / "settings.template.json").read_text(encoding="utf-8"))
    assert tmpl["statusLine"]["command"] == "{{PYTHON_EXE}} {{CLAUDE_DIR}}/scripts/statusline.py"
    hooks = [h["command"] for groups in tmpl["hooks"].values() for g in groups for h in g["hooks"]]
    assert hooks and all(c.startswith("{{PYTHON}} ") for c in hooks)


def _load_detect():
    spec = importlib.util.spec_from_file_location("detect_p1", _ROOT / "installer" / "detect.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["detect_p1"] = mod  # @dataclass resolves its module through sys.modules
    spec.loader.exec_module(mod)
    return mod


def test_python_exe_token_is_a_forward_slash_interpreter_on_windows_and_python3_elsewhere(monkeypatch):
    d = _load_detect()
    monkeypatch.setattr(d.plat, "IS_WINDOWS", True)
    monkeypatch.setattr(sys, "_base_executable", "E:\\py\\python.exe", raising=False)
    assert d._python_exe() == "E:/py/python.exe"  # Git Bash eats backslashes
    monkeypatch.setattr(d.plat, "IS_WINDOWS", False)
    assert d._python_exe() == "python3"
    assert d.detect().python_exe == "python3"


def test_machine_subs_carries_the_python_exe_token(monkeypatch):
    r = _load_render()
    fake_env = type("Env", (), {"tokens": {"PYTHON": "py -3", "CLAUDE_DIR": "E:/x/.claude"},
                                "python_exe": "E:/py/python.exe"})
    monkeypatch.setitem(sys.modules, "detect", type("M", (), {"detect": staticmethod(lambda: fake_env)}))
    assert r.machine_subs()["PYTHON_EXE"] == "E:/py/python.exe"


def test_emit_template_keeps_the_statusline_python_exe_token(tmp_path):
    r = _load_render()
    live = tmp_path / "settings.json"
    live.write_text(r.render(user_path=None), encoding="utf-8")
    out = tmp_path / "template.json"
    r.emit_template(live, out)
    tmpl = json.loads(out.read_text(encoding="utf-8"))
    assert tmpl["statusLine"]["command"] == "{{PYTHON_EXE}} {{CLAUDE_DIR}}/scripts/statusline.py"
    assert tmpl["hooks"]["Stop"][0]["hooks"][0]["command"].startswith("{{PYTHON}} ")
