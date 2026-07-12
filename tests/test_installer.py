"""test_installer.py — installer + doctor smoke (P6-T5 / P6-T6).

Import-level tests of the stdlib installer: manifest validity, OS detection,
idempotent dep planning, the argv-splitting substitution (Windows ``py -3``),
and the doctor's deterministic catalog checks. Networked steps are never run
(dry-run / --ci). Runs on both ubuntu-latest and windows-latest in CI.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _load(mod_name: str, rel: str):
    spec = importlib.util.spec_from_file_location(mod_name, _ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)  # type: ignore
    return mod


def test_manifest_valid_json_and_shape():
    m = json.loads((_ROOT / "installer" / "manifest.json").read_text())
    assert m["min_python"] == "3.10"
    assert isinstance(m["deps"], list) and m["deps"]
    assert isinstance(m["mcp_servers"], list)
    assert m["palette"]["skill_names"] == 218
    assert m["palette"]["command_files"] == 20
    assert m["palette"]["historic_command_names"] == 139


def test_detect_returns_env():
    detect = _load("detect", "installer/detect.py")
    env = detect.detect()
    assert env.os_name in {"posix", "windows"}
    assert env.python
    assert env.real_dir and env.real_dir.endswith(".claude")
    assert set(env.tokens) == {"PYTHON", "NODE", "CLAUDE_DIR"}


def test_sub_splits_multiword_interpreter():
    deps = _load("deps", "installer/deps.py")
    # {PYTHON} = 'py -3' must split into two argv elements (Windows py launcher)
    out = deps._sub(["{PYTHON}", "{CLAUDE_DIR}/x.py"], {"PYTHON": "py -3", "CLAUDE_DIR": "/c/u/.claude"})
    assert out == ["py", "-3", "/c/u/.claude/x.py"]
    # single-word interpreter stays one element; embedded path token replaced
    out2 = deps._sub(["{PYTHON}", "{CLAUDE_DIR}/y.py"], {"PYTHON": "python3", "CLAUDE_DIR": "/home/u/.claude"})
    assert out2 == ["python3", "/home/u/.claude/y.py"]


def test_deps_dry_run_no_exceptions():
    detect = _load("detect", "installer/detect.py")
    deps = _load("deps", "installer/deps.py")
    env = detect.detect()
    rows = deps.install_deps(env, ci=True, dry_run=True)
    assert rows
    # under --ci, no networked step is attempted; statuses are PRESENT/SKIP/WOULD-*
    for _name, status in rows:
        assert not status.startswith("INSTALLED")


def test_doctor_deterministic_checks_pass():
    doctor = _load("doctor", "installer/doctor.py")
    rows = doctor.run_doctor()
    by_name = {n: (s, d) for n, s, d in rows}
    # these must PASS on any faithful checkout
    for check in ("interpreters", "render-equivalence", "palette-skills",
                  "palette-commands", "command-resolution", "aliases", "zero-symlinks"):
        assert by_name[check][0] == "PASS", f"{check}: {by_name[check]}"
    # no check may hard-FAIL
    fails = [n for n, s, _ in rows if s == "FAIL"]
    assert not fails, f"doctor FAIL rows: {fails}"
