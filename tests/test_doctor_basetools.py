"""Doctor row ``base-tools`` (A5-03): an install is not "SUCCESS" while Claude Code, node + npm, git
or uv cannot be resolved. FAIL for those (the self-heal repairs it), WARN for gh / ollama, SKIP
under ``--ci`` and when ``AGENTIC_MERCY_SKIP_BASE_TOOLS`` says nothing would be installed anyway."""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks"), str(_ROOT / "hooks" / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import doctor  # noqa: E402
import doctor_basetools as db  # noqa: E402
from lib import platform as plat  # noqa: E402

ALL = {n: f"/bin/{n}" for n in ("claude", "node", "npm", "git", "uv", "gh", "ollama")}


@pytest.fixture(autouse=True)
def _posix(monkeypatch):
    monkeypatch.setattr(plat, "IS_WINDOWS", False)  # the Windows tests turn it on themselves


def _which(have: dict):
    return lambda n, *a, **k: have.get(n)


def check(have, *, ci=False, env=None):
    return db.check_base_tools(ci, which=_which(have), environ={} if env is None else env)


def test_ci_is_a_skip_so_ci_is_unchanged():
    assert check({}, ci=True)[0] == "SKIP"


def test_the_skip_switch_is_a_skip_because_nothing_would_be_installed():
    status, detail = check({}, env={"AGENTIC_MERCY_SKIP_BASE_TOOLS": "1"})
    assert status == "SKIP" and "AGENTIC_MERCY_SKIP_BASE_TOOLS" in detail


def test_nothing_resolvable_fails_and_names_every_missing_tool():
    status, detail = check({})
    assert status == "FAIL"
    for n in ("claude", "node", "npm", "git", "uv"):
        assert n in detail


@pytest.mark.parametrize("gone", ["claude", "node", "npm", "git", "uv"])
def test_each_required_tool_alone_is_a_fail(gone):
    status, detail = check({k: v for k, v in ALL.items() if k != gone})
    assert status == "FAIL" and gone in detail


@pytest.mark.parametrize("gone", ["gh", "ollama"])
def test_gh_and_ollama_are_only_a_warn(gone):
    status, detail = check({k: v for k, v in ALL.items() if k != gone})
    assert status == "WARN" and gone in detail


def test_everything_on_the_path_passes():
    assert check(ALL)[0] == "PASS"


def test_a_required_fail_outranks_a_missing_optional_tool():
    assert check({"claude": "/c"})[0] == "FAIL"


def test_on_windows_a_store_shim_is_not_a_node(monkeypatch):
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    shim = {**ALL, "node": "X:\\u\\AppData\\Local\\Microsoft\\WindowsApps\\node.exe"}
    status, detail = check(shim)
    assert status == "FAIL" and "node" in detail


def test_on_windows_a_git_without_bash_is_a_warn(monkeypatch, tmp_path):
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    g = tmp_path / "MinGit" / "cmd" / "git.exe"
    g.parent.mkdir(parents=True)
    g.write_bytes(b"x")
    status, detail = check({**ALL, "git": str(g)})
    assert status == "WARN" and "bash" in detail
    (tmp_path / "MinGit" / "bin").mkdir()
    (tmp_path / "MinGit" / "bin" / "bash.exe").write_bytes(b"x")
    assert check({**ALL, "git": str(g)})[0] == "PASS"


def test_on_windows_a_git_under_ucrt64_with_the_root_bash_passes(monkeypatch, tmp_path):
    """Git for Windows from a Git Bash PATH resolves to `<root>\\ucrt64\\bin\\git.exe`; its bash is
    `<root>\\bin\\bash.exe` (this box). The installer's `winutil.git_bash` walks up for it
    (SANTA1B-01); the doctor must judge git the same way, not two levels up only."""
    monkeypatch.setattr(plat, "IS_WINDOWS", True)
    g = tmp_path / "Git" / "ucrt64" / "bin" / "git.exe"
    g.parent.mkdir(parents=True)
    g.write_bytes(b"x")
    (tmp_path / "Git" / "bin").mkdir()
    (tmp_path / "Git" / "bin" / "bash.exe").write_bytes(b"x")
    assert check({**ALL, "git": str(g)}) == ("PASS", "claude, node + npm, git, uv resolve; gh and ollama present")


def test_the_doctor_runs_the_row():
    assert doctor.doctor_basetools is db and '"base-tools"' in inspect.getsource(doctor.run_doctor)
