"""A4v2-03: the commit doc gate sees a `git commit` however a PowerShell or Bash script spells it.

`git.exe`, a quoted path to git, `Set-Location x;`, a command inside `{ }`, a command on its own line, a
backtick continuation, a payload of `powershell -c` / `cmd /c` / `iex`. Before this every one of them made
`git_commits` return nothing, so the doc gate failed open. The parse tests are portable (no repo needed);
the end-to-end ones build a real repo with `server_docs/` and one staged backend file.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOOKS))
import commit_docs_check as cdc  # noqa: E402

REPO = os.path.normpath("/repo")


def _one(cmd: str, cwd: str = "/cwd"):
    commits, add_seen = cdc.git_commits(cmd, cwd)
    assert len(commits) == 1, (cmd, commits)
    return commits[0], add_seen


@pytest.mark.parametrize("cmd", [
    "git add -A\ngit commit -m x",
    "echo hi\ngit commit -m x",
    "echo hi\r\ngit commit -m x",
    "git.exe commit -m x",
    "GIT.EXE commit -m x",
    '& "D:\\Program Files\\Git\\cmd\\git.exe" commit -m x',
    "& git commit -m x",
    "if ($LASTEXITCODE -eq 0) { git commit -m x }",
    "try { git commit -m x } catch { }",
    "& { git commit -m x }",
    "git commit `\n  -m x",
    'powershell -Command "git commit -m x"',
    "pwsh -NoProfile -c 'git commit -m x'",
    "cmd /c git commit -m x",
    "iex 'git commit -m x'",
    "bash -c 'git commit -m x'",
])
def test_commit_is_seen_in_every_spelling(cmd):
    (args, _), _ = _one(cmd)
    assert args == ["-m", "x"]


@pytest.mark.parametrize("cmd", [
    "git commit -m @'\nfix: don't break it\n'@",
    'git commit -m @"\nfix: don\'t break $it\n"@',
])
def test_a_here_string_message_with_an_apostrophe_still_counts(cmd):
    """SANTA2A-02: shlex choked on the lone `'` inside a PowerShell here-string, so no commit was
    seen and the doc gate let it through unchecked."""
    (args, _), _ = _one(cmd)
    assert args[0] == "-m" and len(args) == 2


@pytest.mark.parametrize("cmd", [
    f"Set-Location {REPO}; git commit -m x",
    f"set-location {REPO}\ngit commit -m x",
    f"Set-Location -Path {REPO}; git commit -m x",
    f"sl {REPO}; git commit -m x",
    f"Push-Location {REPO}; git commit -m x",
    f"pushd {REPO} && git commit -m x",
    f"cd {REPO}\ngit commit -m x",
    f"chdir {REPO} && git commit -m x",
    f"git -C {REPO} commit -m x",
    f"git.exe -C {REPO} commit -m x",
    f'pwsh -c "cd {REPO}; git commit -m x"',
    f"if ($ok) {{ Set-Location {REPO}; git commit -m x }}",
])
def test_directory_changers_and_dash_c_point_the_check_at_the_right_repo(cmd):
    (_, directory), _ = _one(cmd)
    assert directory == REPO


def test_add_on_another_line_counts_as_add_seen():
    assert _one("git add -A\ngit commit -m x")[1] is True
    assert _one("git add -A; git.exe commit -m x")[1] is True
    assert _one("pwsh -c 'git add -A; git commit -m x'")[1] is True
    assert _one("git commit -m x")[1] is False


def test_a_multi_line_message_stays_one_argument():
    (args, _), _ = _one('git commit -m "line one\nline two"')
    assert args == ["-m", "line one\nline two"]


@pytest.mark.parametrize("cmd", [
    "git status",
    "git status\ngit log --oneline",
    "git commit-tree HEAD^{tree}",
    "git.exe commit-tree HEAD",
    'git log --format="git commit"',
    "echo git commit",
    "Write-Host 'git commit -m x'",
    "# git commit\ngit status",
    "Set-Location /repo; git status",
    'powershell -Command "git status"',
])
def test_no_commit_where_none_runs(cmd):
    assert cdc.git_commits(cmd, "/cwd")[0] == [], cmd


def test_trailing_backslash_from_tab_completion_on_windows(monkeypatch):
    monkeypatch.setattr(cdc.plat, "IS_WINDOWS", True)
    for cmd in (r"git -C D:\Projects\x\ commit -m x", r'cd D:\Projects\x\ ; git commit -m x',
                "Set-Location D:\\Projects\\x\\\ngit commit -m x"):
        (_, directory), _ = _one(cmd, "C:/Users/me")
        assert directory == "D:/Projects/x", cmd


# ---- end to end: the enforcer denies --------------------------------------- #
def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


@pytest.fixture()
def docrepo(tmp_path):
    repo = tmp_path / "proj"
    for rel in ("server/a.py", "server_docs/01.md"):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    (repo / "server/a.py").write_text("y\n", encoding="utf-8")
    _git(repo, "add", "server/a.py")
    return repo


def _verdict(cmd: str, cwd: Path, tool: str, monkeypatch) -> str:
    spec = importlib.util.spec_from_file_location(f"bde_{uuid.uuid4().hex}", HOOKS / "blocking-doc-enforcer.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    payload = {"session_id": "s", "tool_name": tool, "cwd": str(cwd), "tool_input": {"command": cmd}}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    mod.main()
    return (json.loads(out.getvalue() or "{}").get("hookSpecificOutput") or {}).get("permissionDecision", "allow")


@pytest.mark.parametrize("tool", ["Bash", "PowerShell"])
def test_the_enforcer_denies_every_spelling_and_allows_a_docs_commit(docrepo, tool, tmp_path, monkeypatch):
    other = tmp_path / "elsewhere"
    other.mkdir()
    for cmd, cwd in (("git.exe commit -m x", docrepo), ("echo hi\ngit commit -m x", docrepo),
                     (f"Set-Location '{docrepo}'; git commit -m x", other),
                     ("if ($true) { git commit -m x }", docrepo), ("git commit `\n -m x", docrepo),
                     (f'git.exe -C "{docrepo}" commit -m x', other), ("cmd /c git commit -m x", docrepo)):
        assert _verdict(cmd, cwd, tool, monkeypatch) == "deny", (tool, cmd)
    (docrepo / "server_docs/01.md").write_text("z\n", encoding="utf-8")
    _git(docrepo, "add", "server_docs/01.md")
    assert _verdict("git.exe commit -m x", docrepo, tool, monkeypatch) == "allow"
