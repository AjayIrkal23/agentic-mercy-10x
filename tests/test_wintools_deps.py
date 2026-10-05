"""deps on Windows: Python tools through ``uv tool install`` (no pipx), PyYAML pinned, the graphify
serve venv, the ``{HOME}`` token, the python prereq that rejects the Store stub, and
``install_deps(skip_optional=True)`` (A5-05, A5-06, A5-07, A5-11)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks"), str(_ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import deps  # noqa: E402
from lib import platform as plat  # noqa: E402
from winfakes import Runs  # noqa: E402

M = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))
DEPS = {d["id"]: d for d in M["deps"]}
WIN = SimpleNamespace(os_name="windows", python="py -3", node="node", real_dir="/x/.claude")
POSIX = SimpleNamespace(os_name="posix", python="python3", node="node", real_dir="/x/.claude")


@pytest.fixture
def home(tmp_path, monkeypatch):
    for k in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(k, str(tmp_path))
    monkeypatch.setattr(deps.shutil, "which", lambda *a, **k: None)
    monkeypatch.setattr(deps, "_importable", lambda module, env: False)
    return tmp_path


def test_the_python_tools_install_through_uv_on_windows_and_pipx_is_gone():
    assert "pipx" not in DEPS
    for tool, pin in (("semgrep", "semgrep==1.178.0"), ("jcodemunch-mcp", "jcodemunch-mcp[openai]==1.108.319"),
                      ("jdocmunch-mcp", "jdocmunch-mcp[openai]==1.145.0")):
        argv = DEPS[tool]["install_windows"]
        assert argv[:3] == ["uv", "tool", "install"] and pin in argv, tool


def test_no_windows_installer_pipes_a_remote_script_or_names_pipx_or_winget():
    for d in M["deps"]:
        text = " ".join(str(a) for a in (d.get("install_windows") or []))
        assert not any(w in text.lower() for w in ("iex", "irm ", "pipx", "winget")), d["id"]
    assert "install_windows" not in DEPS["uv"]  # wintools installs uv from the pinned zip


def test_pyyaml_is_pinned_on_every_os():
    assert "pyyaml==6.0.3" in DEPS["pyyaml"]["install"] and "pyyaml==6.0.3" in DEPS["pyyaml"]["install_posix"]


def test_home_is_an_exec_token(home):
    assert deps._exec_tokens(WIN)["HOME"] == str(Path.home())
    assert deps._sub(["{HOME}\\x"], deps._exec_tokens(WIN)) == [f"{Path.home()}\\x"]


def _only(monkeypatch, dep):
    monkeypatch.setattr(deps, "_load_manifest", lambda: {"deps": [dep]})


def test_the_graphify_serve_venv_is_built_in_two_uv_steps(home, monkeypatch):
    runs = Runs()
    monkeypatch.setattr(plat, "run", runs)
    _only(monkeypatch, DEPS["graphify-serve-venv"])
    assert deps.install_deps(WIN, ci=False, dry_run=False) == [("graphify-serve-venv", "INSTALLED")]
    venv = f"{home}\\.local\\share\\claude-graphify-venv"
    assert runs.calls == [["uv", "venv", "--clear", venv],
                          ["uv", "pip", "install", "--python", f"{venv}\\Scripts\\python.exe",
                           "graphifyy==0.9.18", "mcp==1.28.1"]]


def test_a_failed_venv_step_stops_the_chain(home, monkeypatch):
    runs = Runs(rc={"uv": 2})
    monkeypatch.setattr(plat, "run", runs)
    _only(monkeypatch, DEPS["graphify-serve-venv"])
    assert deps.install_deps(WIN, ci=False, dry_run=False) == [("graphify-serve-venv", "WARN(rc=2)")]
    assert len(runs.calls) == 1


def test_the_serve_venv_counts_as_present_only_with_its_python(home, monkeypatch):
    _only(monkeypatch, DEPS["graphify-serve-venv"])
    venv = home / ".local" / "share" / "claude-graphify-venv"
    venv.mkdir(parents=True)  # interrupted `uv venv`: a dir, no interpreter
    assert deps.install_deps(WIN, ci=False, dry_run=True)[0][1].startswith("WOULD-INSTALL")
    (venv / "Scripts").mkdir()
    (venv / "Scripts" / "python.exe").write_bytes(b"x")
    assert deps.install_deps(WIN, ci=False, dry_run=True)[0][1] == "PRESENT"


def test_posix_still_builds_the_serve_venv_with_one_sh_command(home, monkeypatch):
    _only(monkeypatch, DEPS["graphify-serve-venv"])
    assert deps.install_deps(POSIX, ci=False, dry_run=True)[0][1].startswith("WOULD-INSTALL: sh -c ")


def test_skip_optional_leaves_optional_deps_out(home, monkeypatch):
    monkeypatch.setattr(deps, "_load_manifest", lambda: {"deps": [
        {"id": "req", "which": "a"}, {"id": "opt", "which": "b", "optional": True}]})
    assert [n for n, _ in deps.install_deps(WIN, dry_run=True)] == ["req", "opt"]
    assert [n for n, _ in deps.install_deps(WIN, dry_run=True, skip_optional=True)] == ["req"]


# --- prereqs ---------------------------------------------------------------------------- #
def _prereqs(monkeypatch, found: dict, out: dict | None = None, env=WIN):
    monkeypatch.setattr(deps.shutil, "which", lambda n, *a, **k: found.get(n))
    monkeypatch.setattr(deps.plat, "run", Runs(out=out or {}))
    return dict(deps.check_prereqs(env))


def test_the_store_python_stub_is_not_python(monkeypatch):
    stub = "X:\\Users\\a\\AppData\\Local\\Microsoft\\WindowsApps\\python3.exe"
    rows = _prereqs(monkeypatch, {"python3": stub, "python": stub})
    assert rows["python3"].startswith("MISSING") and "winget" not in rows["python3"]


def test_py_launcher_with_a_modern_python_is_present_and_an_old_one_is_not(monkeypatch):
    assert _prereqs(monkeypatch, {"py": "/w/py.exe"}, {"py": "3.14"})["python3"] == "PRESENT"
    assert _prereqs(monkeypatch, {"py": "/w/py.exe"}, {"py": "3.9"})["python3"].startswith("MISSING")


def test_a_store_node_shim_is_missing_and_no_windows_hint_says_winget(monkeypatch):
    rows = _prereqs(monkeypatch, {"node": "X:\\a\\WindowsApps\\node.exe"})
    assert rows["node"].startswith("MISSING")
    assert not [r for r in rows.values() if "winget" in r], rows


def test_posix_prereqs_are_unchanged(monkeypatch):
    rows = _prereqs(monkeypatch, {"python3": "/usr/bin/python3", "git": None}, env=POSIX)
    assert rows["python3"] == "PRESENT" and "sudo apt install git" in rows["git"]


def test_the_python_running_the_installer_is_present_even_when_it_is_on_no_path(monkeypatch, tmp_path):
    """A5v2-07: install.ps1 hands over <tools>\\python\\python.exe, which the registry PATH has but this
    process does not: the prereq row said `MISSING -> run install.cmd` under that very Python."""
    monkeypatch.setenv("AGENTIC_MERCY_TOOLS_DIR", str(tmp_path / "tools"))
    mine = Path(sys.executable).stem.lower()
    assert _prereqs(monkeypatch, {}, {mine: "3.14"})["python3"] == "PRESENT"
    assert _prereqs(monkeypatch, {}, {mine: "3.9"})["python3"].startswith("MISSING")  # still judged by version


def test_the_tools_dir_python_counts_too(monkeypatch, tmp_path):
    exe = tmp_path / "tools" / "python" / "python.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"x")
    monkeypatch.setenv("AGENTIC_MERCY_TOOLS_DIR", str(tmp_path / "tools"))
    assert _prereqs(monkeypatch, {}, {"python.exe": "3.14", "python": "3.14"})["python3"] == "PRESENT"


def test_a_planted_py_in_the_working_directory_is_never_run_by_the_prereq_check(monkeypatch, tmp_path):
    """A5v2-06: on Python 3.10/3.11 `shutil.which` answers `.\\py.EXE` first; the check ran it."""
    import os
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path / "elsewhere"))
    monkeypatch.setenv("AGENTIC_MERCY_TOOLS_DIR", str(tmp_path / "tools"))
    runs = Runs(out={"py": "3.14"})
    monkeypatch.setattr(deps.shutil, "which", lambda n, *a, **k: os.path.join(os.getcwd(), n + ".EXE") if n == "py" else None)
    monkeypatch.setattr(deps.plat, "run", runs)
    deps.check_prereqs(WIN)
    assert not [c for c in runs.calls if c[0].lower().endswith("py.exe")], runs.calls


def test_jcodemunch_config_never_runs_a_binary_planted_in_the_working_directory(monkeypatch, tmp_path):
    import importlib.util
    import os
    spec = importlib.util.spec_from_file_location("jcodemunch_config", _ROOT / "installer" / "jcodemunch_config.py")
    jc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(jc)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path / "elsewhere"))
    monkeypatch.setenv("CODE_INDEX_PATH", str(tmp_path / "idx"))
    runs = Runs()
    monkeypatch.setattr(jc.shutil, "which", lambda n, *a, **k: os.path.join(os.getcwd(), n + ".EXE"))
    monkeypatch.setattr(jc.plat, "run", runs)
    assert jc.configure()[1].startswith("SKIP") and runs.calls == []


# --- the MCP command a Windows registration carries (A5v2-03) ------------------------------------ #
@pytest.mark.parametrize("found,want", [
    (None, ["claude", "mcp", "add", "lean-ctx", "--", "cmd", "/c", "lean-ctx"]),  # npm-global not on PATH yet
    ("C:/np/lean-ctx.cmd", ["claude", "mcp", "add", "lean-ctx", "--", "cmd", "/c", "lean-ctx"]),
    ("C:/tools/jcodemunch-mcp.exe", ["claude", "mcp", "add", "lean-ctx", "--", "lean-ctx"]),  # a real exe stays direct
])
def test_a_shim_is_never_registered_as_a_bare_name_on_windows(monkeypatch, found, want):
    monkeypatch.setattr(deps.shutil, "which", lambda n, *a, **k: found)
    assert deps._win_shell_wrap(["claude", "mcp", "add", "lean-ctx", "--", "lean-ctx"]) == want


def test_npx_and_py_registrations_are_unchanged(monkeypatch):
    monkeypatch.setattr(deps.shutil, "which", lambda n, *a, **k: {"py": "C:/Windows/py.exe"}.get(n))
    assert deps._win_shell_wrap(["claude", "mcp", "add", "m", "--", "npx", "-y", "p@1"])[5:8] == ["cmd", "/c", "npx"]
    assert deps._win_shell_wrap(["claude", "mcp", "add", "g", "--", "py", "-3", "x.py"])[5] == "py"


# --- plan output (A5v2-11) ------------------------------------------------------------------------ #
def test_plan_rows_show_real_paths_not_the_raw_tokens(home, monkeypatch):
    monkeypatch.setattr(deps, "_load_manifest", lambda: {"deps": [DEPS["graphify-serve-venv"], DEPS["tdd-guard-pytest"]]})
    rows = deps.install_deps(WIN, ci=False, dry_run=True)
    text = " ".join(s for _, s in rows)
    assert "{HOME}" not in text and "{PYTHON}" not in text, rows
    assert str(home) in text and "py -3" in text
