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
    assert "palette" not in m  # counts are computed from disk, never pinned
    names = [s["name"] for s in m["mcp_servers"]]
    assert names == m["doctor_probes"]["mcp_roster"]
    assert not {"fetch", "ast-grep", "figma", "gbrain"} & set(names)
    steps = [s["id"] for s in m["post_steps"]]
    assert "gen-invoke-skills" in steps and "gen-invoke-commands" not in steps
    assert m["externals"] == []


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
    out2 = deps._sub(["{PYTHON}", "{CLAUDE_DIR}/y.py"], {"PYTHON": "python3", "CLAUDE_DIR": "/opt/u/.claude"})
    assert out2 == ["python3", "/opt/u/.claude/y.py"]


def test_deps_dry_run_no_exceptions():
    detect = _load("detect", "installer/detect.py")
    deps = _load("deps", "installer/deps.py")
    env = detect.detect()
    rows = deps.install_deps(env, ci=True, dry_run=True)
    assert rows
    # under --ci, no networked step is attempted; statuses are PRESENT/SKIP/WOULD-*
    for _name, status in rows:
        assert not status.startswith("INSTALLED")


def test_user_facing_entrypoint_rejects_cli_verbs(monkeypatch):
    """A mistyped read-only command must never launch the mutating UI installer."""
    bootstrap = _load("bootstrap", "installer/bootstrap.py")
    launched: list[bool] = []
    monkeypatch.setattr(bootstrap, "_launch_ui", lambda: launched.append(True) or 0)

    assert bootstrap.main(["doctor"]) == 2
    assert launched == []


def test_ci_flag_is_headless_never_the_web_ui(monkeypatch):
    """--ci must run the console self-heal, never start the (blocking) web UI."""
    bootstrap = _load("bootstrap", "installer/bootstrap.py")
    launched: list[str] = []
    monkeypatch.setattr(bootstrap, "_launch_ui", lambda: launched.append("ui") or 0)
    monkeypatch.setattr(bootstrap, "_run_headless", lambda ci: launched.append(f"headless:{ci}") or 0)
    monkeypatch.setattr(bootstrap, "_needs_relocate", lambda *a: False)
    assert bootstrap.main(["--ci"]) == 0
    assert launched == ["headless:True"]


def test_doctor_deterministic_checks_pass(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CLAUDE_HOOK_DOCTOR", "1")
    doctor = _load("doctor", "installer/doctor.py")
    rows = doctor.run_doctor(ci=True)
    by_name = {n: (s, d) for n, s, d in rows}
    # these must PASS on any faithful checkout (render-equivalence SKIPs without settings.json)
    for check in ("interpreters", "palette-skills", "aliases", "locked-source-links",
                  "plugins-contract", "generated-in-sync"):
        assert by_name[check][0] == "PASS", f"{check}: {by_name[check]}"
    assert by_name["render-equivalence"][0] in ("PASS", "SKIP")
    fails = [n for n, s, _ in rows if s == "FAIL"]
    assert not fails, f"doctor FAIL rows: {fails}"
