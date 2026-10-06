"""FX2-INST: what the Windows installer may reuse, run and write (Santa 1b + Security 1b findings).

Git reuse (SANTA1B-01: the PortableGit download + `CLAUDE_CODE_GIT_BASH_PATH` overwrite incident),
the cwd-safe ``which`` (SEC1B-01), the sandbox and tools-dir rules (SANTA1B-04, SEC1B-02/03) and the
Authenticode check of the binaries we run (SEC1B-04). Fakes only: no network, process or registry.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks"), str(_ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import winutil  # noqa: E402
import wintools  # noqa: E402
from lib import platform as plat  # noqa: E402
from winfakes import ENV, FakeRegistry, Runs, World, short_limit, signature_out  # noqa: E402, F401  (autouse: A7v2-02)

M = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))
GIT_VAR = "CLAUDE_CODE_GIT_BASH_PATH"
SANDBOX = "AGENTIC_MERCY_SANDBOX"


@pytest.fixture
def w(tmp_path, monkeypatch):
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    return World(tmp_path, M)


def _file(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    return p


def _git_sets(w) -> list:
    return [c for c in w.registry.sets() if c[2] == GIT_VAR]


# --- SANTA1B-01: git reuse ---------------------------------------------------------------- #
@pytest.mark.parametrize("layout", ["cmd", "bin", "mingw64/bin", "ucrt64/bin"])
def test_a_complete_git_for_windows_is_present_wherever_its_git_exe_sits(w, tmp_path, layout):
    g = tmp_path / "Dev" / "Git"
    _file(g / "bin" / "bash.exe")
    w.found["git"] = str(_file(g / layout / "git.exe"))
    assert dict(w.ensure(ci=True))["git"] == "PRESENT"
    assert dict(w.ensure())["git"] == "PRESENT"
    assert not any("PortableGit" in u for u in w.urls) and _git_sets(w) == []
    assert not (w.tools / "git").exists()


def test_a_valid_git_bash_variable_makes_git_present_even_beside_no_bash(w, tmp_path):
    w.found["git"] = str(_file(tmp_path / "msys" / "usr" / "bin" / "git.exe"))
    w.env[GIT_VAR] = str(_file(tmp_path / "Dev" / "Git" / "bin" / "bash.exe"))
    assert dict(w.ensure())["git"] == "PRESENT"
    assert not any("PortableGit" in u for u in w.urls) and _git_sets(w) == []


@pytest.mark.parametrize("scope", ["user", "machine"])
def test_the_variable_is_also_read_from_the_user_and_machine_registry_scopes(w, tmp_path, scope):
    w.found["git"] = str(_file(tmp_path / "msys" / "usr" / "bin" / "git.exe"))
    bash = str(_file(tmp_path / "Dev" / "Git" / "bin" / "bash.exe"))
    if scope == "user":
        w.registry.values[(ENV, GIT_VAR)] = (bash, "REG_SZ")
    else:
        w.registry.machine[GIT_VAR] = (bash, "REG_SZ")
    assert dict(w.ensure(ci=True))["git"] == "PRESENT"
    assert [c for c in w.registry.calls if c[0] == "set"] == []


def test_mingit_with_a_dangling_variable_is_installed_and_the_variable_repaired(w, tmp_path):
    w.found["git"] = str(_file(tmp_path / "MinGit" / "cmd" / "git.exe"))
    w.env[GIT_VAR] = str(tmp_path / "gone" / "bin" / "bash.exe")
    assert dict(w.ensure())["git"].startswith("INSTALLED")
    assert w.env[GIT_VAR] == str(w.tools / "git" / "bin" / "bash.exe")
    assert _git_sets(w)[0][3] == w.env[GIT_VAR]


def test_our_git_never_overwrites_a_variable_that_points_at_an_existing_file(w, tmp_path):
    other = str(_file(tmp_path / "Dev" / "Git" / "bin" / "bash.exe"))
    w.env[GIT_VAR] = other  # valid, but no git.exe beside it and none on PATH: ours gets installed
    assert dict(w.ensure())["git"].startswith("INSTALLED")
    assert (w.tools / "git" / "bin" / "bash.exe").is_file()
    assert w.env[GIT_VAR] == other and _git_sets(w) == []
    assert dict(w.ensure())["git"] == "PRESENT" and _git_sets(w) == []  # and a re-run still leaves it alone


def test_git_bash_helper_walks_three_levels_up_and_ignores_missing_files(tmp_path):
    g = tmp_path / "Git"
    _file(g / "bin" / "bash.exe")
    deep = _file(g / "a" / "b" / "c" / "git.exe")  # four levels below the root: out of reach
    assert winutil.git_bash(str(deep), []) is None
    assert winutil.git_bash(str(g / "mingw64" / "bin" / "git.exe"), []) == g / "bin" / "bash.exe"
    assert winutil.git_bash(str(g / "cmd" / "git.exe"), [str(g / "nope" / "bash.exe"), ""]) == g / "bin" / "bash.exe"
    assert winutil.git_bash(None, [str(g / "bin" / "bash.exe")]) is None  # no git.exe beside it
    _file(g / "cmd" / "git.exe")
    assert winutil.git_bash(None, [str(g / "bin" / "bash.exe")]) == g / "bin" / "bash.exe"


# --- SEC1B-01: a binary in the working directory is never picked --------------------------- #
def _cwd_first(monkeypatch):
    """Python 3.10/3.11 ``shutil.which`` on Windows: the current directory is searched first."""
    def which(name, *a, **k):
        return os.path.join(os.curdir, name + ".exe") if (Path.cwd() / (name + ".exe")).is_file() else None
    monkeypatch.setattr(shutil, "which", which)


def test_which_drops_a_hit_from_the_cwd_unless_the_cwd_is_really_on_path(tmp_path, monkeypatch):
    _file(tmp_path / "claude.exe")
    monkeypatch.chdir(tmp_path)
    _cwd_first(monkeypatch)
    monkeypatch.setenv("PATH", os.pathsep.join(["", ".", str(tmp_path / "elsewhere")]))
    assert winutil.which("claude") is None  # `.` and the empty entry are not a real directory
    monkeypatch.setenv("PATH", os.pathsep.join([str(tmp_path)]))
    assert winutil.which("claude") is not None  # the user really put this directory on PATH


def test_planted_binaries_in_the_cwd_are_never_run_by_the_installer(tmp_path, monkeypatch):
    for n in ("claude", "py", "python", "node", "npm"):
        _file(tmp_path / (n + ".exe"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)  # the real which() then sees the cwd
    _cwd_first(monkeypatch)
    runs = Runs(out={"py": "3.14", "python": "3.14"})
    assert winutil.pick_python(run=runs) is None and runs.calls == []
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    from types import SimpleNamespace
    env = {"USERPROFILE": str(tmp_path / "h"), "AGENTIC_MERCY_TOOLS_DIR": str(tmp_path / "h" / "t"), "PATH": ""}
    wintools.ensure_wintools(SimpleNamespace(os_name="windows"), M, ci=True, dry_run=True, run=runs,
                             environ=env, registry=FakeRegistry())  # the default `which` is the one under test
    assert runs.calls == []


# --- SEC1B-03: the sandbox never runs the third-party `claude.exe install` ---------------------- #
def test_the_sandbox_flag_skips_claude_exe_install_and_its_download(w):
    w.env[SANDBOX] = "1"
    row = dict(w.ensure())["claude"]
    assert row.startswith("SKIP") and "sandbox" in row
    assert not [c for c in w.run.calls if c[1:2] == ["install"]]
    assert not any(u.endswith("claude.exe") for u in w.urls)


# --- SEC1B-02: a tools dir outside the profile is called out ------------------------------ #
def test_a_tools_dir_outside_the_profile_gets_a_warning_row_but_still_installs(tmp_path, monkeypatch):
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    w = World(tmp_path, M)
    w.env["AGENTIC_MERCY_TOOLS_DIR"] = str(tmp_path / "D" / "Dev" / "tools")
    rows = dict(w.ensure())
    assert rows["tools-dir"].startswith("WARN(") and "AGENTIC_MERCY_TOOLS_DIR" in rows["tools-dir"]
    assert rows["node"].startswith("INSTALLED")


def test_a_tools_dir_inside_the_profile_or_localappdata_is_silent(w, tmp_path):
    assert "tools-dir" not in dict(w.ensure(ci=True))
    w.env.update({"LOCALAPPDATA": str(tmp_path / "la"), "AGENTIC_MERCY_TOOLS_DIR": str(tmp_path / "la" / "t")})
    assert "tools-dir" not in dict(w.ensure(ci=True))


def test_a_profile_less_environment_is_a_warn_row_not_a_crash(w, monkeypatch):
    def boom(environ=None):
        raise RuntimeError("Could not determine home directory.")
    monkeypatch.setattr(wintools.winpath, "tools_dir", boom)
    rows = w.ensure()
    assert rows[0][0] == "base-tools" and rows[0][1].startswith("WARN(") and len(rows) == 1


# --- SEC1B-04: Authenticode of what we execute --------------------------------------------- #
def _claude_rows(w, reply):
    w.runs(out={"powershell": signature_out(default=reply)})
    return dict(w.ensure())["claude"]


def test_claude_exe_is_run_only_when_validly_signed_by_anthropic(w):
    assert _claude_rows(w, "Valid\nAnthropic, PBC").startswith("INSTALLED")
    ps = next(c for c in w.run.calls if c[0].lower().endswith("powershell.exe"))
    assert "System32" in ps[0] and "Get-AuthenticodeSignature" in " ".join(ps)  # absolute path, not a PATH lookup


@pytest.mark.parametrize("reply", ["Valid\nSomeone Else", "NotSigned\n", "HashMismatch\nAnthropic, PBC", ""])
def test_claude_exe_with_any_other_signature_is_refused_and_never_run(tmp_path, monkeypatch, reply):
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    w = World(tmp_path, M)
    row = _claude_rows(w, reply)
    assert row.startswith("WARN(") and "signature" in row
    assert not [c for c in w.run.calls if c[1:2] == ["install"]]
    assert not list((w.tools / "cache").glob("claude*"))  # the refused file is deleted


@pytest.mark.parametrize("reply,ok", [("Valid\nJohannes Schindelin", True), ("NotSigned\n", True),
                                      ("Valid\nAnyone", True), ("HashMismatch\nJohannes Schindelin", False),
                                      ("NotTrusted\nJohannes Schindelin", False), ("", False)])
def test_portable_git_sfx_runs_unless_its_signature_is_present_and_bad(tmp_path, monkeypatch, reply, ok):
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    w = World(tmp_path, M)
    w.runs(out={"powershell": signature_out({"-bit.7z.exe": reply})})
    row = dict(w.ensure())["git"]
    assert row.startswith("INSTALLED") is ok, row
    assert bool([c for c in w.run.calls if "-y" in c]) is ok


# --- P-3: the 387 MB SFX does not stay behind when its run fails -------------------------- #
def test_a_failing_sfx_run_leaves_no_installer_in_the_cache(w):
    def boom(argv):
        if "-y" in argv:
            raise TimeoutError("sfx hung")
    w.run.effect = boom
    assert dict(w.ensure())["git"].startswith("WARN(")
    assert not list((w.tools / "cache").glob("PortableGit*"))


# --- A5v2-10: the doctor and the installer read CLAUDE_CODE_GIT_BASH_PATH from the same places ------ #
def test_the_doctor_row_counts_a_bash_variable_that_only_the_registry_holds(tmp_path, monkeypatch):
    import doctor_basetools as db
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    bash = tmp_path / "elsewhere" / "bin" / "bash.exe"
    _file(bash)
    _file(tmp_path / "tools" / "git.exe")  # a git with no bash.exe within three levels of it
    have = {n: str(tmp_path / "tools" / (n + ".exe")) for n in ("claude", "node", "npm", "git", "uv", "gh", "ollama")}
    which = lambda n, *a, **k: have.get(n)  # noqa: E731
    assert db.check_base_tools(False, which=which, environ={})[0] == "WARN"  # nothing names a bash
    reg = FakeRegistry({(ENV, GIT_VAR): (str(bash), "REG_SZ")})
    assert db.check_base_tools(False, which=which, environ={}, registry=reg)[0] == "PASS"
