"""test_installer.py — installer + doctor smoke (P6-T5 / P6-T6).

Import-level tests of the stdlib installer: manifest validity, OS detection,
idempotent dep planning, the argv-splitting substitution (Windows ``py -3``),
and the doctor's deterministic catalog checks. Networked steps are never run
(dry-run / --ci). Runs on both ubuntu-latest and windows-latest in CI.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

import live_interpreter

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
    live_interpreter.pin(monkeypatch)  # A7v2-03: not coupled to the Python that rendered the live settings.json
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Path.home() on Windows (A7-13)
    monkeypatch.setenv("CLAUDE_HOOK_DOCTOR", "1")
    live_interpreter.pin_tier(tmp_path, monkeypatch)  # FIX-r2 S3: this machine's tier, not a fallback
    # never depend on the installed claude CLI / tsc (same as test_doctor.py, I-17)
    real_which = shutil.which
    monkeypatch.setattr(shutil, "which", lambda n, *a, **k: None if n in ("claude", "tsc") else real_which(n, *a, **k))
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
# (full paths, like the real `which`: a bare name is a hit in the working directory, which `winutil.which` drops)
_WHICH = {"npx": "/n/npx.CMD", "lean-ctx": "/n/lean-ctx.cmd", "jcodemunch-mcp": "/n/jcodemunch-mcp.EXE", "py": "/w/py.exe"}


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


def test_register_mcps_skips_a_server_whose_binary_is_missing(monkeypatch):
    deps = _load("deps", "installer/deps.py")
    monkeypatch.setattr(deps.shutil, "which", lambda c: None)
    monkeypatch.setattr(deps, "registered_user_mcps", lambda: set())
    monkeypatch.setattr(deps, "_load_manifest", lambda: {"mcp_servers": [
        {"name": "lp", "which": "lightpanda", "add": ["claude", "mcp", "add", "lp", "--", "lightpanda", "mcp"]}]})
    monkeypatch.setattr(deps.plat, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not register")))
    assert deps.register_mcps(_env("posix", "python3")) == [("lp", "SKIP(no lightpanda on PATH)")]
    assert deps.register_mcps(_env("posix", "python3"), dry_run=True) == [("lp", "WOULD-ADD: claude mcp add lp -- lightpanda mcp")]


def test_manifest_github_has_windows_launcher():
    m = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))
    gh = next(s for s in m["mcp_servers"] if s["name"] == "github")
    assert gh["windows_add"][-1] == "{CLAUDE_DIR}/scripts/github-mcp-launcher.py"
    assert (_ROOT / "scripts" / "github-mcp-launcher.py").is_file()


def test_always_load_reconcile_plans_then_skips_when_set(tmp_path, monkeypatch):
    deps = _load("deps", "installer/deps.py")
    cfg = tmp_path / ".claude.json"
    cfg.write_text(json.dumps({"mcpServers": {"sequential-thinking": {"command": "npx", "args": ["x"]},
                                              "memory": {"command": "npx", "args": ["y"]}}}), encoding="utf-8")
    monkeypatch.setattr(deps, "user_config_file", lambda: cfg)
    assert deps.reconcile_mcp_always_load(dry_run=True) == [("sequential-thinking", "WOULD-SET-ALWAYS-LOAD true")]
    cfg.write_text(json.dumps({"mcpServers": {"sequential-thinking": {"command": "npx", "args": ["x"], "alwaysLoad": True}}}),
                   encoding="utf-8")
    assert deps.reconcile_mcp_always_load(dry_run=True) == []


def test_always_load_reconcile_goes_through_replace_entry(tmp_path, monkeypatch):
    deps = _load("deps", "installer/deps.py")
    cfg = tmp_path / ".claude.json"
    cfg.write_text(json.dumps({"mcpServers": {"sequential-thinking": {"command": "npx", "args": ["x"]}}}), encoding="utf-8")
    monkeypatch.setattr(deps, "user_config_file", lambda: cfg)
    monkeypatch.setattr(deps.winutil, "which", lambda n: "/x/claude")
    seen = {}
    monkeypatch.setattr(deps.mcp_restore, "replace_entry", lambda name, new, old, ok: seen.update(new=new) or ok)
    assert deps.reconcile_mcp_always_load() == [("sequential-thinking", "ALWAYS-LOAD true")]
    assert seen["new"] == {"command": "npx", "args": ["x"], "alwaysLoad": True}


def _install_pass(monkeypatch, tmp_path, ci=True, **fakes):
    """Run selfheal._install_pass with every outward step faked; returns the emitted rows."""
    import deps
    import jcodemunch_config as jc
    import selfheal
    for fn in ("check_prereqs", "install_deps", "register_mcps", "reconcile_mcp_env", "reconcile_mcp_pins",
               "reconcile_mcp_always_load", "warm_added_npx", "install_plugins", "run_post_steps"):
        monkeypatch.setattr(deps, fn, fakes.get(fn) or (lambda *a, **k: []))
    monkeypatch.setattr(deps, "configure_lean_ctx", lambda **k: ("lean-ctx-config", "x"))
    monkeypatch.setattr(selfheal, "_ensure_settings", lambda *a, **k: None)
    monkeypatch.setattr(selfheal, "_validate_fix", lambda *a, **k: None)
    monkeypatch.setattr(jc, "configure", lambda **k: ("jcodemunch-config", "x"))
    rows: list = []
    selfheal._install_pass(tmp_path, object(), lambda *a: rows.append(a), ci)
    return rows


def test_the_install_pass_sets_always_load(monkeypatch, tmp_path):
    """Rohit's PC, round 2 (tools F1): only the daily self-heal set sequential-thinking's alwaysLoad, so a
    fresh box ran a day without it."""
    calls: list = []
    rows = _install_pass(monkeypatch, tmp_path, reconcile_mcp_always_load=lambda **k: calls.append(k) or
                         [("sequential-thinking", "ALWAYS-LOAD true")])
    assert calls == [{"dry_run": True}]
    assert ("mcp-load", "sequential-thinking", "ALWAYS-LOAD true") in rows


def test_the_install_pass_warms_what_it_just_registered(monkeypatch, tmp_path):
    seen: list = []
    _install_pass(monkeypatch, tmp_path, register_mcps=lambda *a, **k: [("markdownify", "ADDED")],
                  warm_added_npx=lambda rows, **k: seen.append((rows, k)) or [])
    assert seen == [([("markdownify", "ADDED")], {"dry_run": True})]


def test_warm_added_npx_runs_only_newly_added_npx_servers(monkeypatch):
    """Rohit's PC, round 2 (tools F6): markdownify's npm preinstall builds a Python venv (pip install
    markitdown[all]); unwarmed, the first session's initialize took 35 s. Only re-pinned specs were warmed."""
    import deps
    ran: list = []

    def run(argv, timeout):
        ran.append(argv)
        return 0, ""
    rows = deps.warm_added_npx([("markdownify", "ADDED"), ("memory", "PRESENT"), ("semgrep", "ADDED"),
                                ("openart", "ADDED")], dry_run=False, run=run)
    assert ran == [["npx", "-y", "mcp-markdownify-server@1.1.0", "--version"]]  # semgrep / openart: no npx
    assert rows == [("markdownify", "WARMED mcp-markdownify-server@1.1.0")]
    ran.clear()
    assert deps.warm_added_npx([("markdownify", "PRESENT")], dry_run=False, run=run) == [] and ran == []
    assert deps.warm_added_npx([("markdownify", "ADDED")], dry_run=True, run=run) == [] and ran == []
    monkeypatch.setenv("AGENTIC_MERCY_SKIP_BASE_TOOLS", "1")
    monkeypatch.setattr(deps.npx_cache, "_run", lambda *a, **k: ran.append(a) or (0, ""))
    assert deps.warm_added_npx([("markdownify", "ADDED")], dry_run=False) == [] and ran == []


# --- R9: the jcodemunch uv tool is checked, not only its name on PATH (Rohit's PC, round 2) --- #
JCM_UV_TOOL = {"name": "jcodemunch-mcp", "version": "1.108.319", "import": "openai"}  # == the manifest's


def _jcm_box(monkeypatch, tmp_path, *, venv=True, version="1.108.319", import_ok=True):
    """deps with only the jcodemunch dep, `which` finding it, and a fake `uv tool dir` venv.
    Returns the list of install argvs run."""
    import subprocess
    import deps
    m = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))
    dep = {**next(d for d in m["deps"] if d["id"] == "jcodemunch-mcp"), "uv_tool": JCM_UV_TOOL}
    monkeypatch.setattr(deps, "_load_manifest", lambda: {"deps": [dep], "user_space": {}})
    monkeypatch.setattr(deps.winutil, "which", lambda n: "/x/" + n)
    monkeypatch.setattr(deps.plat, "IS_WINDOWS", False)
    tools = tmp_path / "uv-tools"
    if venv:
        (tools / "jcodemunch-mcp" / "bin").mkdir(parents=True)
        (tools / "jcodemunch-mcp" / "bin" / "python").write_text("", encoding="utf-8")

    def run(argv, **k):
        if argv[:3] == ["uv", "tool", "dir"]:
            return subprocess.CompletedProcess(argv, 0, f"{tools}\n", "")
        if argv[0].endswith("python"):
            assert "openai" in argv[-1]
            return subprocess.CompletedProcess(argv, 0 if import_ok else 1, f"{version}\n" if import_ok else "",
                                               "" if import_ok else "ModuleNotFoundError: No module named 'openai'")
        raise AssertionError(argv)
    monkeypatch.setattr(deps.plat, "run", run)
    installs: list = []
    monkeypatch.setattr(deps, "_run_install", lambda argv: installs.append(argv) or subprocess.CompletedProcess(argv, 0, "", ""))
    monkeypatch.setattr(deps, "_link_bins", lambda *a, **k: "")
    return deps, installs


ENV_POSIX = type("E", (), {"os_name": "posix", "python": "python3", "node": "node", "real_dir": None})()


def test_jcodemunch_without_openai_is_reinstalled(monkeypatch, tmp_path):
    deps, installs = _jcm_box(monkeypatch, tmp_path, import_ok=False)
    rows = deps.install_deps(ENV_POSIX)
    assert rows[0][0] == "jcodemunch-mcp" and rows[0][1].startswith("INSTALLED")
    assert installs == [["uv", "tool", "install", "--force", "--upgrade", "jcodemunch-mcp[openai]==1.108.319"]]


def test_jcodemunch_off_the_pin_is_reinstalled(monkeypatch, tmp_path):
    deps, installs = _jcm_box(monkeypatch, tmp_path, version="1.108.399")
    assert deps.install_deps(ENV_POSIX)[0][1].startswith("INSTALLED") and len(installs) == 1


def test_jcodemunch_at_the_pin_with_openai_is_present(monkeypatch, tmp_path):
    deps, installs = _jcm_box(monkeypatch, tmp_path)
    assert deps.install_deps(ENV_POSIX) == [("jcodemunch-mcp", "PRESENT")] and installs == []


def test_jcodemunch_without_a_uv_venv_is_left_alone(monkeypatch, tmp_path):
    deps, installs = _jcm_box(monkeypatch, tmp_path, venv=False, import_ok=False)  # pipx or a hand install
    assert deps.install_deps(ENV_POSIX) == [("jcodemunch-mcp", "PRESENT")] and installs == []


def test_uv_tool_version_matches_the_install_pins():
    m = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))
    for d in (d for d in m["deps"] if d.get("uv_tool")):
        ut = d["uv_tool"]
        for key in ("install_posix", "install_windows"):
            pin = next(a for a in d[key] if a.startswith(ut["name"]) and "==" in a)
            assert pin.split("==", 1)[1] == ut["version"], (d["id"], key)
    assert next(d for d in m["deps"] if d["id"] == "jcodemunch-mcp").get("uv_tool") == JCM_UV_TOOL
