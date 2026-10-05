"""Windows-only production branches, exercised on every OS (audit A7-04, A7-05, A7-10).

Each test flips the module's own Windows flag (or patches `ntpath` in for the path helpers) and
asserts the behaviour the Windows branch promises, so Ubuntu CI catches a regression that used
to show only on a Windows runner:

  * `installer/detect.py`: `py -3` when the launcher exists, else a forward-slash interpreter path
  * `installer/deps.py`: the post-step script is the first `.py` arg (`{PYTHON}` -> `py -3`),
    and `install_<os_name>` picks the Windows installer
  * `hooks/graphify_launcher.py`: `Scripts/python.exe` venv, no `os.execve` on Windows
  * `hooks/bash-write-gate.py`, `hooks/jcodemunch-enforce.py`: Windows case folding
  * `hooks/lib/repo_context.py`: `$HOME` with a `.git` is still a walk-up ceiling

These pin current, correct behaviour: they pass on the first run.
"""
from __future__ import annotations

import importlib.util
import ntpath
import os
import subprocess
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib import repo_context as rc  # noqa: E402


def _load(rel: str):
    """Load a script under a throwaway module name (never replaces a sys.modules entry)."""
    name = f"winbr_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, _ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # @dataclass looks its module up here
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------- #
# installer/detect.py
# --------------------------------------------------------------------------- #
@pytest.fixture
def detect_win(monkeypatch):
    mod = _load("installer/detect.py")
    monkeypatch.setattr(mod.plat, "IS_WINDOWS", True)
    return mod


def test_detect_windows_prefers_the_py_launcher(detect_win, monkeypatch):
    monkeypatch.setattr(detect_win.shutil, "which", lambda n, *a, **k: "C:/Windows/py.exe" if n == "py" else None)
    assert detect_win._python_invocation() == "py -3"


def test_detect_windows_without_py_uses_the_running_interpreter_with_forward_slashes(detect_win, monkeypatch):
    monkeypatch.setattr(detect_win.shutil, "which", lambda n, *a, **k: None)
    out = detect_win._python_invocation()
    assert out == Path(sys.executable).as_posix()
    if "\\" in sys.executable:  # a backslash path breaks the rendered JSON and Git Bash commands
        assert "\\" not in out


def test_detect_posix_keeps_python3_even_when_py_exists(monkeypatch):
    mod = _load("installer/detect.py")
    monkeypatch.setattr(mod.plat, "IS_WINDOWS", False)
    monkeypatch.setattr(mod.shutil, "which", lambda n, *a, **k: "/usr/bin/py" if n == "py" else None)
    assert mod._python_invocation() == "python3"  # keeps the rendered settings.json byte-identical


def test_detect_windows_env_carries_the_windows_tokens(detect_win, monkeypatch, tmp_path):
    monkeypatch.setattr(detect_win.shutil, "which", lambda n, *a, **k: "C:/x/py.exe" if n == "py" else None)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / ".claude"))
    env = detect_win.detect()
    assert env.os_name == "windows" and env.is_windows
    assert env.python == "py -3" and env.tokens["PYTHON"] == "py -3"
    # the concrete forward-slash path: `${HOME}` is not expanded by Claude Code on Windows
    assert env.tokens["CLAUDE_DIR"] == (tmp_path / ".claude").as_posix()
    assert "${HOME}" not in env.tokens["CLAUDE_DIR"]


# --------------------------------------------------------------------------- #
# installer/deps.py
# --------------------------------------------------------------------------- #
@pytest.fixture
def deps():
    return _load("installer/deps.py")


def _win_env():
    return SimpleNamespace(os_name="windows", python="py -3", node="node", real_dir="/nonexistent-xyz/.claude")


def test_post_steps_find_the_script_when_python_is_py_dash_3(deps):
    """The documented regression: `{PYTHON}` = `py -3` shifted the script to cmd[2]; reading
    cmd[1] ('-3') reported every post-step as MISSING(script)."""
    rows = dict(deps.run_post_steps(_win_env(), dry_run=True))
    assert rows, "no post steps"
    assert not [s for s, st in rows.items() if st.startswith(("MISSING", "SKIP"))], rows
    cmd = rows["validate-skills"]
    assert cmd.startswith("WOULD-RUN: py -3 "), cmd
    script = next(tok for tok in cmd.split() if tok.endswith(".py"))
    assert Path(script).is_file()
    assert "/nonexistent-xyz/.claude" not in cmd  # repo-local scripts resolve against the checkout


def test_post_steps_run_the_script_through_the_py_launcher(deps, monkeypatch):
    calls: list = []
    monkeypatch.setattr(deps.plat, "run",
                        lambda cmd, **k: calls.append(list(cmd)) or subprocess.CompletedProcess(cmd, 0, "", ""))
    rows = dict(deps.run_post_steps(_win_env()))
    scripted = [c for c in calls if any(str(t).endswith(".py") for t in c)]
    assert scripted and all(c[:2] == ["py", "-3"] for c in scripted), scripted
    assert rows["validate-skills"] == "OK"
    assert not [s for s, st in rows.items() if st.startswith(("MISSING", "FAIL"))], rows


def test_install_deps_picks_the_windows_installer(deps, monkeypatch, tmp_path):
    for var in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(var, str(tmp_path))  # `exists:` deps resolve under the sandbox
    monkeypatch.setattr(deps.shutil, "which", lambda *a, **k: None)
    monkeypatch.setattr(deps, "_importable", lambda module, env: False)
    manifest = deps._load_manifest()
    windows_deps = [d for d in manifest["deps"] if d.get("install_windows")]
    assert windows_deps, "manifest declares no install_windows"
    rows = dict(deps.install_deps(_win_env(), ci=False, dry_run=True))
    for dep in windows_deps:  # the plan shows the argv that would run: tokens resolved (A5v2-11)
        want = " ".join(deps._sub(dep["install_windows"], deps._exec_tokens(_win_env())))
        assert rows[dep["id"]] == "WOULD-INSTALL: " + want, dep["id"]
    # the dispatch is only proven by a dep whose Windows installer differs from the POSIX one
    assert [d for d in windows_deps if d["install_windows"] != d.get("install_posix")]


def test_install_deps_posix_ignores_install_windows(deps, monkeypatch, tmp_path):
    for var in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(var, str(tmp_path))
    monkeypatch.setattr(deps.shutil, "which", lambda *a, **k: None)
    monkeypatch.setattr(deps, "_importable", lambda module, env: False)
    env = SimpleNamespace(os_name="posix", python="python3", node="node", real_dir=str(tmp_path / ".claude"))
    rows = dict(deps.install_deps(env, ci=False, dry_run=True))
    differing = [d for d in deps._load_manifest()["deps"]
                 if d.get("install_windows") and d["install_windows"] != d.get("install_posix")]
    assert differing
    for dep in differing:
        assert rows[dep["id"]] != "WOULD-INSTALL: " + " ".join(dep["install_windows"]), dep["id"]


# --------------------------------------------------------------------------- #
# hooks/graphify_launcher.py
# --------------------------------------------------------------------------- #
@pytest.fixture
def launcher(monkeypatch, tmp_path):
    mod = _load("hooks/graphify_launcher.py")
    for var in ("GRAPHIFY_PYTHON", "GRAPHIFY_VENV", "GRAPHIFY_SITE_PACKAGES", "GRAPHIFY_GRAPH",
                "CLAUDE_PROJECT_DIR", "WORKSPACE_FOLDER_PATHS"):
        monkeypatch.delenv(var, raising=False)
    return mod


def _venv(root: Path, with_scripts: bool = True, with_bin: bool = True) -> Path:
    for flag, parts in ((with_scripts, ("Scripts", "python.exe")), (with_bin, ("bin", "python"))):
        if flag:
            f = root.joinpath(*parts)
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("", encoding="utf-8")
    return root


def test_venv_python_is_scripts_python_exe_on_windows(launcher, monkeypatch, tmp_path):
    venv = _venv(tmp_path / "venv")
    monkeypatch.setattr(launcher, "_IS_WINDOWS", True)
    assert launcher._venv_python(venv) == venv / "Scripts" / "python.exe"
    only_bin = _venv(tmp_path / "posix-venv", with_scripts=False)
    assert launcher._venv_python(only_bin) is None  # a POSIX layout is not a Windows venv


def test_venv_python_is_bin_python_on_posix(launcher, monkeypatch, tmp_path):
    venv = _venv(tmp_path / "venv")
    monkeypatch.setattr(launcher, "_IS_WINDOWS", False)
    assert launcher._venv_python(venv) == venv / "bin" / "python"
    assert launcher._venv_python(_venv(tmp_path / "win-venv", with_bin=False)) is None


def test_serve_command_uses_the_windows_venv_interpreter(launcher, monkeypatch, tmp_path):
    venv = _venv(tmp_path / "venv")
    monkeypatch.setattr(launcher, "_IS_WINDOWS", True)
    monkeypatch.setenv("GRAPHIFY_VENV", str(venv))
    argv, _env = launcher._serve_command("g.json")
    assert argv == [str(venv / "Scripts" / "python.exe"), "-m", "graphify.serve", "g.json"]


def _serve_setup(launcher, monkeypatch, tmp_path):
    graph = tmp_path / "graph.json"
    graph.write_text('{"nodes": [], "edges": []}', encoding="utf-8")
    py = tmp_path / "serve-python"
    py.write_text("", encoding="utf-8")
    monkeypatch.setenv("GRAPHIFY_PYTHON", str(py))
    monkeypatch.setattr(sys, "argv", ["graphify_launcher.py", str(graph)])
    return [str(py), "-m", "graphify.serve", str(graph)]


def test_main_on_windows_runs_a_child_and_never_calls_execve(launcher, monkeypatch, tmp_path):
    expected = _serve_setup(launcher, monkeypatch, tmp_path)
    monkeypatch.setattr(launcher, "_IS_WINDOWS", True)
    execs: list = []
    monkeypatch.setattr(os, "execve", lambda *a: execs.append(a))
    runs: list = []
    monkeypatch.setattr(subprocess, "run", lambda argv, **k: runs.append(list(argv)) or SimpleNamespace(returncode=7))
    assert launcher.main() == 7  # the serve child's exit code is passed through
    assert execs == []
    assert runs == [expected]


def test_main_on_posix_replaces_the_process_with_execve(launcher, monkeypatch, tmp_path):
    expected = _serve_setup(launcher, monkeypatch, tmp_path)
    monkeypatch.setattr(launcher, "_IS_WINDOWS", False)
    execs: list = []

    def fake_execve(path, argv, env):
        execs.append((path, list(argv)))
        raise OSError("stop here")  # execve never returns; the launcher falls through (fail-open)

    monkeypatch.setattr(os, "execve", fake_execve)
    monkeypatch.setattr(subprocess, "run", lambda argv, **k: SimpleNamespace(returncode=0))
    assert launcher.main() == 0
    assert execs == [(expected[0], expected)]


# --------------------------------------------------------------------------- #
# Windows case folding in the gates (normcase is a no-op on POSIX)
# --------------------------------------------------------------------------- #
def _windows_os(real_os):
    """The module's `os` with ntpath for the path helpers, as on Windows."""
    return SimpleNamespace(path=ntpath, sep="\\", environ=real_os.environ)


def test_bash_write_gate_temp_dir_match_ignores_case_on_windows(monkeypatch):
    bwg = _load("hooks/bash-write-gate.py")
    monkeypatch.setattr(bwg, "os", _windows_os(os))
    for var in ("TMPDIR", "TMP"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("TEMP", r"D:\Users\X\AppData\Local\Temp")
    assert bwg._in_temp_dir(r"D:\USERS\X\APPDATA\LOCAL\TEMP\notes.py")
    assert bwg._in_temp_dir(r"d:\users\x\appdata\local\temp\sub\notes.py")
    assert bwg._is_allowed_path(r'"d:\users\x\appdata\local\temp\notes.py"')
    assert not bwg._in_temp_dir(r"D:\Users\X\AppData\Local\Tempest\notes.py")  # sibling prefix
    assert not bwg._in_temp_dir(r"D:\Users\X\proj\notes.py")
    assert not bwg._in_temp_dir(r"D:\Users\X\AppData\Local\Temp")  # the bare temp dir is not a file in it


def test_jcodemunch_gate_exempts_the_claude_dir_regardless_of_case_on_windows(monkeypatch):
    jcm = _load("hooks/jcodemunch-enforce.py")
    cfg = jcm._load_enforce_config()
    monkeypatch.setenv("HOME", r"D:\Users\X")
    monkeypatch.setenv("USERPROFILE", r"D:\Users\X")
    monkeypatch.setattr(jcm, "os", SimpleNamespace(path=ntpath, sep="\\", environ=os.environ))
    assert jcm._norm(r"D:\USERS\X\.CLAUDE\hooks\A.PY") == "d:/users/x/.claude/hooks/a.py"
    assert jcm._is_exempt(r"D:\USERS\X\.CLAUDE\hooks\dispatch.py", cfg)
    assert jcm._is_exempt(r"d:\users\x\.claude\installer\doctor.py", cfg)
    assert not jcm._is_exempt(r"D:\USERS\X\PROJECT\src\app.py", cfg)
    assert not jcm._is_exempt(r"D:\USERS\X\.CLAUDEX\src\app.py", cfg)  # sibling prefix of ~/.claude/


# --------------------------------------------------------------------------- #
# $HOME stays a ceiling even when it holds a .git (A7-10)
# --------------------------------------------------------------------------- #
def test_home_with_a_dot_git_is_still_a_ceiling(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".git").mkdir(parents=True)
    (home / "sub").mkdir()
    repo = home / "work" / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))  # Path.home() on Windows
    assert Path.home().resolve() == home.resolve(), "sandbox home does not hold"

    assert rc.git_root(str(home)) is None
    assert rc.git_root(str(home / "sub")) is None
    assert rc.active_repo(cwd=str(home)) is None
    assert rc.active_repo(cwd=str(home / "sub")) is None
    # the walk itself still works below the ceiling
    assert rc.git_root(str(repo)) == repo.resolve()
    ctx = rc.active_repo(cwd=str(repo))
    assert ctx is not None and Path(ctx.root) == repo.resolve()
