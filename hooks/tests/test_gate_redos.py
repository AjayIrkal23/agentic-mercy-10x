"""SEC1-01 / SANTA P5: the destructive-command gate stays linear on a padded command.

dispatch treats a gate that exceeds its 5 s timeout as "no decision", so a quadratic regex lets one
padded line switch the gate off. Every input here is ~50 KB and must be judged within a budget that
scales with the machine (20x a benign 50 KB run + 0.5 s; measured: ~0.2 s or less); the
padded-then-destructive forms must still DENY.
"""
from __future__ import annotations

import importlib.util
import io
import json
import sys
import time
import uuid
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]
N = 50_000
BAD = "\nRemove-Item -Recurse -Force " + "D" + ":\\Users\\X\\proj"


def _rep(unit: str) -> str:
    return unit * (N // len(unit))


# name -> (command, expected decision or None = only the time is judged)
CASES = {
    "del": (_rep("del "), None),
    "erase": (_rep("erase "), None),
    "remove-item": (_rep("Remove-Item "), None),
    "rd": (_rep("rd "), None),
    "rmdir": (_rep("rmdir "), None),
    "ri": (_rep("ri "), None),
    "rm": (_rep("rm "), None),
    "del-slash-q": (_rep("del /q x "), None),
    "git-clean": (_rep("git clean "), None),
    "git-clean-flags": (_rep("git clean -a "), None),
    "git-push-flags": (_rep("git push -a "), None),
    "digits-after-recurse": ("Remove-Item -Recurse " + "1" * N, "deny"),
    "padded-args": ("Remove-Item " + "x " * (N // 2) + BAD, "deny"),
    "padded-del": (_rep("del ") + BAD, "deny"),
    "padded-erase": (_rep("erase ") + BAD, "deny"),
    "padded-remove-item": (_rep("Remove-Item ") + BAD, "deny"),
    "padded-rd": (_rep("rd ") + BAD, "deny"),
    "padded-git-clean": (_rep("git clean ") + "\ngit clean -fdx", "deny"),
    "padded-git-clean-flags": (_rep("git clean -a ") + "\ngit clean -fdx", "deny"),
    "padded-semicolons": (";" * N + BAD, "deny"),
    "escaped-quotes": ('"' + '\\"' * (N // 2), None),
    "heredocs": (_rep("<<EOF\n"), None),
    # SANTA1C-01: the `git` prefix took every `-C` as the argument of the one before (Fibonacci parses)
    "git-C-flood": ("git " + "-C " * 16000 + "x status; git reset --hard", "deny"),
    "git-dir-flood": ("git " + "--git-dir " * 5000 + "x status; git reset --hard", "deny"),
    "git-work-tree-flood": ("git " + "--work-tree " * 4000 + "x status; git reset --hard", "deny"),
    "git-c-kv-flood": ("git " + "-c k=v " * 7000 + "status; git reset --hard", "deny"),
    "git-mixed-flood": ("git " + "-C -c --git-dir " * 3000 + "x status\ngit push --force", "deny"),
    "git-C-flood-push": ("git " + "-C " * 16000 + "x push -f", "deny"),
    "git-C-flood-clean": ("git " + "-C " * 16000 + "x clean -fd", "deny"),
    "git-C-flood-no-tail": ("git " + "-C " * 16000, None),
    "git-restarts": (_rep("git -C "), None),
    "git-restarts-reset": (_rep("git -C ") + "x status; git reset --hard", "deny"),
    "git-no-pager-flood": ("git " + "--no-pager " * 4500 + "reset --hard", "deny"),
    # worst-50KB sweep of every gate regex (FX2-DOC): these two were quadratic (3.5 s / 0.5 s)
    "mongo-db-dots": ("db." * 16000, None),
    "mongo-db-drops": ("db.x.drop(" * 5000, None),
    "mongo-padded": ("db." * 16000 + " db.users.drop()", "deny"),
    "mongo-same-token": ("db." + "x" * 40000 + ".drop()", "deny"),
    "rm-var-open": ("rm ${" * 12000, None),
    "rm-var-padded": ("rm ${" * 12000 + "\nrm ${A}", "deny"),
    # A4v2-01: the Windows spellings (git.exe, quoted exe path, pipelines, .NET, backticks, `//` flags)
    "git-exe-flood": (_rep("git.exe "), None),
    "git-exe-padded": (_rep("git.exe -C ") + "x status\ngit.exe reset --hard", "deny"),
    "quoted-exe-flood": (_rep('"/x/git '), None),
    "quoted-exe-paths": (_rep('"a/git" '), None),
    "pipe-flood": (_rep("| "), None),
    "pipe-delete-flood": (_rep("gci x | "), None),
    "pipe-delete-padded": (_rep("gci x | ") + "Remove-Item -Force", "deny"),
    "pipe-newline-flood": (_rep("a |\n"), None),
    "backtick-flood": (_rep("`\n"), None),
    "backtick-padded": (_rep("Remove-Item `\n") + "-Recurse D:\\x", "deny"),
    "dotnet-open-flood": (_rep("[io.directory]::delete("), None),
    "dotnet-padded": (_rep("[io.directory]::delete(") + "\n[IO.Directory]::Delete('D:\\x', $true)", "deny"),
    "dotnet-delete-flood": (_rep("delete("), None),
    "cmd-slash-flood": (_rep("cmd //x "), None),
    "cmd-slash-padded": (_rep("cmd /x ") + "\ncmd //c rd //s D:\\x", "deny"),
}


@pytest.fixture()
def gate(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(f"redos_{uuid.uuid4().hex}", HOOKS / "dangerous-bash-gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "STATE_DIR", tmp_path)

    def run(cmd: str, tool: str = "PowerShell") -> tuple[str, float]:
        payload = {"tool_name": tool, "tool_input": {"command": cmd}, "session_id": f"r-{uuid.uuid4().hex}"}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        out = io.StringIO()
        monkeypatch.setattr(sys, "stdout", out)
        t0 = time.perf_counter()
        mod.main()
        dt = time.perf_counter() - t0
        decision = (json.loads(out.getvalue() or "{}").get("hookSpecificOutput") or {}).get("permissionDecision")
        return decision or "allow", dt
    run.mod = mod

    def budget() -> float:
        """A linear gate judges a padded line like a benign one of the same size, so the allowance is
        measured on this machine right now (A7v2-05: a fixed 1 s flaked under load). A quadratic matcher
        takes 3.5 s or more per 50 KB unloaded, far past 20x a benign run."""
        return 20 * run("echo " + "x " * (N // 2))[1] + 0.5
    run.budget = budget
    return run


@pytest.mark.parametrize("name", sorted(CASES))
def test_adversarial_50kb_command_is_judged_in_linear_time(gate, name):
    cmd, want = CASES[name]
    assert len(cmd) >= 24_000
    decision, dt = gate(cmd)
    assert dt < gate.budget(), f"{name}: {dt:.2f}s"
    if want:
        assert decision == want, name


@pytest.mark.parametrize("name", ["padded-del", "padded-git-clean", "padded-remove-item"])
def test_the_bash_tool_is_just_as_fast(gate, name):
    cmd, want = CASES[name]
    decision, dt = gate(cmd, tool="Bash")
    assert dt < gate.budget() and decision == want, (name, dt)


def test_a_long_argument_run_before_the_recurse_flag_is_not_a_bypass(gate):
    """The fix must not bound the scan: a bounded `{0,400}` quantifier would let padding hide -Recurse."""
    assert gate("Remove-Item " + "a" * 5000 + " -Recurse D:\\x")[0] == "deny"
    assert gate("git clean " + "a " * 5000 + "-fd")[0] == "deny"
    assert gate("git push " + "a " * 5000 + "--force")[0] == "deny"


def test_git_option_forms_are_still_seen_through(gate):
    """The disjoint option arguments (`(?!-)`) keep every spelling of a global option caught."""
    for cmd in ("git -C repo push --force", "git -C a -C b reset --hard", "git --git-dir x/.git push -f",
                "git -c k=v push --force", "git -C repo -c k=v --no-pager clean -fd",
                "git --work-tree=w --git-dir=d reset --hard", "git -C -x reset --hard"):
        assert gate(cmd, tool="Bash")[0] == "deny", cmd
    assert gate("git -C repo status", tool="Bash")[0] == "allow"


def test_line_continuations_are_joined_before_matching(gate):
    """SANTA1C-02: bash runs `git push \\<newline> --force` as one line; so must the gate."""
    for cmd in ("git push \\\n  --force origin main", "git clean \\\n -fdx", "git reset \\\n --hard",
                "rm -rf \\\n /", "rm \\\n -rf x", "dd if=/dev/zero \\\n of=/dev/sda",
                "git push \\\r\n --force origin main"):
        assert gate(cmd, tool="Bash")[0] == "deny", cmd
    for cmd in ("git push \\\n origin main", "git log \\\n --oneline", "echo a \\\n && echo -f"):
        assert gate(cmd, tool="Bash")[0] == "allow", cmd


def test_mongo_drop_and_rm_var_forms_keep_their_verdicts(gate):
    for cmd in ("db.users.drop()", "mongosh --eval 'db.x.y.drop( )'", "db..drop()", "x(db.u.drop ( ))",
                "db.dropDatabase()", "rm $HOME/x", "rm ${HOME}/x", "rm ${A:-b c}", "rm ${A}"):
        assert gate(cmd, tool="Bash")[0] == "deny", cmd
    for cmd in ("db.users.drop(1)", "db.users.drop", "foo.drop()", "db.x foo.drop()", "mydb.x.drop()",
                "rm ${}", "rm ${A", "rm x $A"):
        assert gate(cmd, tool="Bash")[0] == "allow", cmd


def test_redirect_stripping_is_linear_on_a_long_digit_run(gate):
    t0 = time.perf_counter()
    gate.mod._REDIRECT_RE.sub(" ", "1" * N)
    assert time.perf_counter() - t0 < gate.budget()
    assert gate.mod._REDIRECT_RE.sub(" ", "rm -rf x 2>&1 >out.txt <in.txt a1>b").split() == ["rm", "-rf", "x", "a"]
