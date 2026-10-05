"""SEC1-04 / SEC1-06 / SANTA P3 for hooks/lib/platform.py, proven on every OS.

* At import on Windows the module sets ``NoDefaultCurrentDirectoryInExePath``: a bare tool name
  (`git`, `whoami`, `npm`) is then never resolved to a same-named file in the working directory
  (a hostile checkout). An explicit value is kept, and POSIX is untouched.
* ``spawn_worker`` pipes ``stdin_text`` as UTF-8 with replacement whatever the locale: a payload with
  a character outside cp1252 raised UnicodeEncodeError after the child had started ("never raises").
"""
from __future__ import annotations

import importlib.util
import os
import pathlib
import subprocess
import sys
import time
import uuid

_HOOKS = pathlib.Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

from lib import platform as plat  # noqa: E402

VAR = "NoDefaultCurrentDirectoryInExePath"
EMOJI = "x\U0001F600中"


def _fresh(monkeypatch, platform: str):
    """A new copy of lib/platform.py executed as if imported on ``platform``."""
    monkeypatch.setenv(VAR, "placeholder")  # records the original state for teardown
    monkeypatch.delenv(VAR)
    monkeypatch.setattr(sys, "platform", platform)
    spec = importlib.util.spec_from_file_location(f"plat_{uuid.uuid4().hex}", _HOOKS / "lib" / "platform.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_importing_on_windows_stops_cwd_shadowing_of_bare_tool_names(monkeypatch):
    mod = _fresh(monkeypatch, "win32")
    assert mod.IS_WINDOWS and os.environ[VAR] == "1"


def test_an_explicit_value_is_kept(monkeypatch):
    monkeypatch.setenv(VAR, "0")
    monkeypatch.setattr(sys, "platform", "win32")
    spec = importlib.util.spec_from_file_location(f"plat_{uuid.uuid4().hex}", _HOOKS / "lib" / "platform.py")
    spec.loader.exec_module(importlib.util.module_from_spec(spec))
    assert os.environ[VAR] == "0"


def test_importing_on_posix_sets_nothing(monkeypatch):
    mod = _fresh(monkeypatch, "linux")
    assert not mod.IS_WINDOWS and VAR not in os.environ


class _Stdin:
    def __init__(self):
        self.text = ""

    def write(self, s):
        self.text += s

    def close(self):
        pass


def test_spawn_worker_asks_popen_for_utf8_text_whatever_the_locale(monkeypatch):
    rec: list = []

    class _Popen:
        def __init__(self, cmd, **kw):
            self.pid, self.stdin = 7, _Stdin()
            rec.append(kw)
    monkeypatch.setattr(subprocess, "Popen", _Popen)
    assert plat.spawn_worker(["x"], stdin_text=EMOJI) == 7
    assert rec[-1]["encoding"] == "utf-8" and rec[-1]["errors"] == "replace"


def test_a_non_cp1252_payload_reaches_the_child_intact_without_pythonutf8(tmp_path):
    out = tmp_path / "got.bin"
    child = f"import sys;open({str(out)!r},'wb').write(sys.stdin.buffer.read())"
    parent = ("import sys;sys.path.insert(0, sys.argv[1]);from lib import platform as p;"
              "pid = p.spawn_worker([sys.executable, '-c', sys.argv[2]], stdin_text=sys.argv[3]);"
              "assert pid, 'spawn failed'")
    env = {**os.environ, "PYTHONUTF8": "0", "PYTHONIOENCODING": "cp1252"}
    cp = subprocess.run([sys.executable, "-c", parent, str(_HOOKS), child, EMOJI], env=env,
                        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    assert cp.returncode == 0, cp.stderr
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and not (out.exists() and out.stat().st_size):
        time.sleep(0.1)
    assert out.read_bytes().decode("utf-8") == EMOJI
