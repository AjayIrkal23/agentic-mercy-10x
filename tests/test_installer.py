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
    m = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))
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
                  "plugins-contract"):
        assert by_name[check][0] == "PASS", f"{check}: {by_name[check]}"
    # `drift:` lines from a generator that exits 0 are a WARN since WP7 (audit I-11)
    assert by_name["generated-in-sync"][0] in ("PASS", "WARN"), by_name["generated-in-sync"]
    assert by_name["render-equivalence"][0] in ("PASS", "SKIP")
    fails = [n for n, s, _ in rows if s == "FAIL"]
    assert not fails, f"doctor FAIL rows: {fails}"


# Claude Code spawns MCP stdio commands WITHOUT a shell. On Windows an npm .cmd/.bat
# shim (npx, lean-ctx) is not spawnable that way; it must be registered as `cmd /c ...`.
_WHICH = {"npx": "npx.CMD", "lean-ctx": "lean-ctx.cmd", "jcodemunch-mcp": "jcodemunch-mcp.EXE", "py": "py.exe"}


def _env(os_name: str, python: str):
    from types import SimpleNamespace
    return SimpleNamespace(os_name=os_name, python=python, node="node", real_dir=str(_ROOT), claude_cli=True)


def test_mcp_argv_windows_wraps_cmd_shims_only(monkeypatch):
    deps = _load("deps", "installer/deps.py")
    monkeypatch.setattr(deps.shutil, "which", lambda c: _WHICH.get(c))
    win = _env("windows", "py -3")
    head = ["claude", "mcp", "add", "--scope", "user"]

    npx = {"name": "memory", "add": head + ["memory", "--", "npx", "-y", "@modelcontextprotocol/server-memory"]}
    assert deps._mcp_argv(npx, win) == head + ["memory", "--", "cmd", "/c", "npx", "-y", "@modelcontextprotocol/server-memory"]
    shim = {"name": "lean-ctx", "add": head + ["lean-ctx", "-e", "A=1", "--", "lean-ctx"]}
    assert deps._mcp_argv(shim, win) == head + ["lean-ctx", "-e", "A=1", "--", "cmd", "/c", "lean-ctx"]
    exe = {"name": "jcodemunch", "add": head + ["jcodemunch", "--", "jcodemunch-mcp"]}
    assert deps._mcp_argv(exe, win) == head + ["jcodemunch", "--", "jcodemunch-mcp"]
    py = {"name": "graphify", "add": head + ["graphify", "--", "{PYTHON}", "{CLAUDE_DIR}/hooks/graphify_launcher.py"]}
    assert deps._mcp_argv(py, win)[-4:] == ["--", "py", "-3", f"{_ROOT}/hooks/graphify_launcher.py"]


def test_mcp_argv_posix_unchanged(monkeypatch):
    deps = _load("deps", "installer/deps.py")
    monkeypatch.setattr(deps.shutil, "which", lambda c: _WHICH.get(c))
    head = ["claude", "mcp", "add", "--scope", "user", "memory", "--", "npx", "-y", "pkg"]
    assert deps._mcp_argv({"name": "memory", "add": head}, _env("posix", "python3")) == head


def test_register_mcps_windows_uses_windows_add_for_posix_only(monkeypatch):
    deps = _load("deps", "installer/deps.py")
    monkeypatch.setattr(deps.shutil, "which", lambda c: _WHICH.get(c))
    monkeypatch.setattr(deps, "registered_user_mcps", lambda: set())
    manifest = {"mcp_servers": [
        {"name": "github", "posix_only": True, "add": ["claude", "mcp", "add", "github", "--", "sh", "-c", "x"],
         "windows_add": ["claude", "mcp", "add", "github", "--", "{PYTHON}", "{CLAUDE_DIR}/scripts/github-mcp-launcher.py"]},
        {"name": "posixonly", "posix_only": True, "add": ["claude", "mcp", "add", "posixonly", "--", "sh"]},
    ]}
    monkeypatch.setattr(deps, "_load_manifest", lambda: manifest)
    rows = dict(deps.register_mcps(_env("windows", "py -3"), dry_run=True))
    assert rows["github"] == f"WOULD-ADD: claude mcp add github -- py -3 {_ROOT}/scripts/github-mcp-launcher.py"
    assert rows["posixonly"] == "SKIP(posix-only)"
    posix = dict(deps.register_mcps(_env("posix", "python3"), dry_run=True))
    assert posix["github"] == "WOULD-ADD: claude mcp add github -- sh -c x"


def test_manifest_github_has_windows_launcher():
    m = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))
    gh = next(s for s in m["mcp_servers"] if s["name"] == "github")
    assert gh["windows_add"][-1] == "{CLAUDE_DIR}/scripts/github-mcp-launcher.py"
    assert (_ROOT / "scripts" / "github-mcp-launcher.py").is_file()
