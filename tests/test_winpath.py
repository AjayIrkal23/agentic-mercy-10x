"""winpath: the tools dir and the user-environment helpers (PATH, env var, Run key) behind
``wintools`` (A5-05). The registry is injected (``FakeRegistry``): nothing touches ``HKCU``."""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks"), str(_ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import winpath  # noqa: E402
from winfakes import ENV, FakeRegistry  # noqa: E402

PATHKEY = (ENV, "Path")


def _env(path: str = "") -> dict:
    return {"PATH": path, "USERPROFILE": "/profile"}


def test_add_user_path_prepends_keeps_expand_sz_and_broadcasts_after_the_write():
    reg = FakeRegistry({PATHKEY: ("%USERPROFILE%\\bin;/old", "REG_EXPAND_SZ")})
    env = _env(os.pathsep.join(["/sys", "/old"]))
    winpath.add_user_path(["/tools/bin", "/tools/node"], reg, env)
    [(_, key, name, value, kind)] = reg.sets()
    assert (key, name, kind) == (ENV, "Path", "REG_EXPAND_SZ")
    assert value.split(";") == ["/tools/bin", "/tools/node", "%USERPROFILE%\\bin", "/old"]
    assert [c[0] for c in reg.calls if c[0] != "get"] == ["set", "broadcast"]
    assert env["PATH"].split(os.pathsep) == ["/tools/bin", "/tools/node", "/sys", "/old"]


def test_an_existing_reg_sz_path_keeps_its_kind_and_a_missing_one_is_expand_sz():
    reg = FakeRegistry({PATHKEY: ("/a", "REG_SZ")})
    winpath.add_user_path(["/t"], reg, _env())
    assert reg.sets()[0][4] == "REG_SZ"
    fresh = FakeRegistry()
    winpath.add_user_path(["/t"], fresh, _env())
    assert fresh.sets()[0][3:] == ("/t", "REG_EXPAND_SZ")


def test_dedupe_is_case_insensitive_and_expands_percent_variables():
    reg = FakeRegistry({PATHKEY: ("X:\\Tools\\BIN\\;%USERPROFILE%\\.local\\bin;/keep", "REG_EXPAND_SZ")})
    env = {"PATH": "", "USERPROFILE": "/profile"}
    winpath.add_user_path(["x:\\tools\\bin", "/profile\\.local\\bin"], reg, env)
    assert reg.sets()[0][3].split(";") == ["x:\\tools\\bin", "/profile\\.local\\bin", "/keep"]


def test_a_3000_char_path_is_not_truncated():
    old = [f"/very/long/existing/dir/{i:04d}" + "x" * 20 for i in range(100)]
    reg = FakeRegistry({PATHKEY: (";".join(old), "REG_EXPAND_SZ")})
    assert len(";".join(old)) > 3000
    winpath.add_user_path(["/t/bin"], reg, _env())
    got = reg.sets()[0][3].split(";")
    assert got[0] == "/t/bin" and got[1:] == old


def test_a_second_run_writes_and_broadcasts_nothing():
    reg = FakeRegistry()
    env = _env()
    winpath.add_user_path(["/t/bin"], reg, env)
    n = len(reg.calls)
    winpath.add_user_path(["/t/bin"], reg, env)
    assert [c for c in reg.calls[n:] if c[0] != "get"] == []
    assert env["PATH"].split(os.pathsep).count("/t/bin") == 1


def test_the_sandbox_flag_skips_the_registry_but_not_the_process_path():
    reg = FakeRegistry()
    env = {**_env("/sys"), "AGENTIC_MERCY_SANDBOX": "1"}
    winpath.add_user_path(["/t/bin"], reg, env)
    assert reg.sets() == [] and ("broadcast",) not in reg.calls
    assert env["PATH"].split(os.pathsep) == ["/t/bin", "/sys"]


def test_profile_paths_with_spaces_and_non_ascii_survive_untouched():
    odd = "/Users/Jürgen Müller/AppData/Local/Programs/agentic-mercy"
    env = {"LOCALAPPDATA": "/Users/Jürgen Müller/AppData/Local", "PATH": ""}
    tools = winpath.tools_dir(env)
    assert str(tools).replace("\\", "/") == odd
    reg = FakeRegistry()
    winpath.add_user_path([str(tools / "bin"), str(tools / "node")], reg, env)
    assert reg.sets()[0][3].split(";")[0] == str(tools / "bin")
    assert "Jürgen Müller" in env["PATH"]


def test_tools_dir_honours_the_override_and_defaults_under_localappdata():
    assert winpath.tools_dir({"AGENTIC_MERCY_TOOLS_DIR": "/x/tools"}) == Path("/x/tools")
    got = winpath.tools_dir({"LOCALAPPDATA": "/la"})
    assert got == Path("/la") / "Programs" / "agentic-mercy"


def test_the_sandbox_flag_keeps_the_default_tools_dir_inside_the_profile():
    """SANTA1B-04: a rehearsal redirects USERPROFILE but inherits the real LOCALAPPDATA; the tools dir
    must follow the redirected profile, an explicit override stays the caller's choice."""
    env = {"AGENTIC_MERCY_SANDBOX": "1", "USERPROFILE": "/sb", "LOCALAPPDATA": "/real/la"}
    assert winpath.tools_dir(env) == Path("/sb") / "AppData" / "Local" / "Programs" / "agentic-mercy"
    assert winpath.tools_dir({**env, "AGENTIC_MERCY_TOOLS_DIR": "/x/t"}) == Path("/x/t")
    assert winpath.tools_dir({**env, "AGENTIC_MERCY_SANDBOX": "0"}) == Path("/real/la/Programs/agentic-mercy")


def test_outside_profile_names_a_tools_dir_beyond_userprofile_and_localappdata():
    env = {"USERPROFILE": "/u/me", "LOCALAPPDATA": "/u/me/AppData/Local"}
    assert not winpath.outside_profile(Path("/u/me/AppData/Local/Programs/agentic-mercy"), env)
    assert not winpath.outside_profile(Path("/u/me/tools"), env)
    assert winpath.outside_profile(Path("/d/Dev/tools"), env)
    assert winpath.outside_profile(Path("/u/me-other/tools"), env)  # a sibling with the same prefix


def test_set_user_env_writes_reg_sz_then_broadcasts_and_updates_the_process():
    reg = FakeRegistry()
    env = _env()
    winpath.set_user_env("CLAUDE_CODE_GIT_BASH_PATH", "/t/git/bin/bash.exe", reg, env)
    assert reg.sets() == [("set", ENV, "CLAUDE_CODE_GIT_BASH_PATH", "/t/git/bin/bash.exe", "REG_SZ")]
    assert reg.calls[-1] == ("broadcast",) and env["CLAUDE_CODE_GIT_BASH_PATH"] == "/t/git/bin/bash.exe"
    n = len(reg.calls)
    winpath.set_user_env("CLAUDE_CODE_GIT_BASH_PATH", "/t/git/bin/bash.exe", reg, env)
    assert [c for c in reg.calls[n:] if c[0] != "get"] == []  # unchanged: no rewrite, no broadcast
    sandbox = FakeRegistry()
    winpath.set_user_env("X", "1", sandbox, {"AGENTIC_MERCY_SANDBOX": "1"})
    assert sandbox.sets() == []


def test_set_run_value_uses_the_hkcu_run_key_and_skips_in_the_sandbox():
    reg = FakeRegistry()
    assert winpath.set_run_value("agentic-mercy-ollama", "cmd", reg, {}) is True
    assert reg.sets() == [("set", winpath.RUN_KEY, "agentic-mercy-ollama", "cmd", "REG_SZ")]
    assert ("broadcast",) not in reg.calls
    assert winpath.set_run_value("agentic-mercy-ollama", "cmd", reg, {}) is True and len(reg.sets()) == 1
    other = FakeRegistry()
    assert winpath.set_run_value("n", "c", other, {"AGENTIC_MERCY_SANDBOX": "1"}) is False
    assert other.sets() == []


def _fake_winreg(store: dict):
    m = types.SimpleNamespace(HKEY_CURRENT_USER="HKCU", KEY_READ=1, KEY_SET_VALUE=2, REG_SZ=1, REG_EXPAND_SZ=2)

    class _K:
        def __init__(self, key):
            self.key = key

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    m.OpenKey = lambda root, key, res, acc: _K(key)
    m.CreateKeyEx = lambda root, key, res, acc: _K(key)

    def query(k, name):
        if (k.key, name) not in store:
            raise FileNotFoundError(name)
        return store[(k.key, name)]
    m.QueryValueEx = query
    m.SetValueEx = lambda k, name, r, kind, value: store.__setitem__((k.key, name), (value, kind))
    return m


def test_winregistry_maps_kinds_and_a_missing_value_is_none(monkeypatch):
    store = {("Environment", "Path"): ("a;b", 2), ("Environment", "TEMP"): ("t", 1)}
    monkeypatch.setitem(sys.modules, "winreg", _fake_winreg(store))
    reg = winpath.WinRegistry()
    assert reg.get("Path") == ("a;b", "REG_EXPAND_SZ") and reg.get("TEMP") == ("t", "REG_SZ")
    assert reg.get("Nope") is None
    reg.set("Path", "z", "REG_EXPAND_SZ")
    reg.set("CLAUDE_X", "v", "REG_SZ", key="Other")
    assert store[("Environment", "Path")] == ("z", 2) and store[("Other", "CLAUDE_X")] == ("v", 1)


def test_winregistry_reads_the_machine_environment_and_has_no_machine_writer(monkeypatch):
    store = {(winpath.MACHINE_ENV_KEY, "CLAUDE_CODE_GIT_BASH_PATH"): ("/g/bin/bash.exe", 1)}
    fake = _fake_winreg(store)
    fake.HKEY_LOCAL_MACHINE = "HKLM"
    monkeypatch.setitem(sys.modules, "winreg", fake)
    reg = winpath.WinRegistry()
    assert reg.get_machine("CLAUDE_CODE_GIT_BASH_PATH") == ("/g/bin/bash.exe", "REG_SZ")
    assert reg.get_machine("Nope") is None and not hasattr(reg, "set_machine")


def test_winregistry_broadcast_sends_wm_settingchange_with_the_environment_string(monkeypatch):
    import ctypes
    sent = []

    class _U32:
        def __getattr__(self, name):
            assert name == "SendMessageTimeoutW"
            return lambda *a: sent.append(a) or 1
    monkeypatch.setattr(ctypes, "windll", types.SimpleNamespace(user32=_U32()), raising=False)
    winpath.WinRegistry().broadcast()
    hwnd, msg, wparam, lparam, flags, timeout, _res = sent[0]
    assert (hwnd, msg, wparam, lparam, flags, timeout) == (0xFFFF, 0x001A, 0, "Environment", 0x2, 5000)


def test_module_never_imports_winreg_at_import_time():
    import ast
    tree = ast.parse((_ROOT / "installer" / "winpath.py").read_text(encoding="utf-8"))
    top = {a.name.split(".")[0] for n in tree.body if isinstance(n, ast.Import) for a in n.names}
    top |= {n.module.split(".")[0] for n in tree.body if isinstance(n, ast.ImportFrom) and n.module}
    assert not top & {"winreg", "ctypes", "msvcrt"}
