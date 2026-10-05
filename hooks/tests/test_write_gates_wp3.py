"""Audit 2026-10-05 WP3 write/commit gates: bash-write-gate (B1-09), blocking-doc-enforcer
in any doc-tree repo (B1-10), dox-write-gate once per repo (B1-19), gateguard (B1-08),
and dangerous-bash-gate letting `--force-with-lease` through."""
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

HOOKS = Path(__file__).resolve().parent.parent
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))


def _load(file: str):
    spec = importlib.util.spec_from_file_location(f"g_{uuid.uuid4().hex}", HOOKS / file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _main(mod, payload: dict, monkeypatch, *args) -> dict:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    mod.main(*args)
    out = buf.getvalue().strip()
    return json.loads(out) if out else {}


def _decision(out: dict) -> str:
    return (out.get("hookSpecificOutput") or {}).get("permissionDecision") or "allow"


def _bash(cmd: str, sid: str = "") -> dict:
    return {"session_id": sid or f"wp3-{uuid.uuid4().hex}", "tool_name": "Bash", "tool_input": {"command": cmd}}


# ---- bash-write-gate (B1-09) ---------------------------------------------- #
@pytest.fixture()
def bwg(tmp_path, monkeypatch):
    mod = _load("bash-write-gate.py")
    monkeypatch.setattr(mod, "STATE_DIR", tmp_path / "state")
    return mod


@pytest.mark.parametrize("cmd", [
    "echo hi > /tmp/x.ts",
    "echo 'x = 1' > /tmp/claude-1000/audit/sg.py",
    "cat a.txt > /tmp/claude-1000/scratch/out.ts",
    "printf 'x' >> build.log",
])
def test_scratch_and_log_writes_get_no_advisory(bwg, monkeypatch, cmd):
    assert _main(bwg, _bash(cmd), monkeypatch) == {}


def test_tmpdir_writes_get_no_advisory(bwg, monkeypatch, tmp_path):
    scratch = tmp_path / "scratchdir"
    monkeypatch.setenv("TMPDIR", str(scratch))
    assert _main(bwg, _bash(f"echo hi > {scratch}/notes.py"), monkeypatch) == {}


def test_windows_temp_vars_are_scratch_too(bwg, monkeypatch):
    """%TEMP% / %TMP% are Windows' temp dirs (TMPDIR is unset there); a path that does not
    look like tmp/scratch to the regex still passes when it is under one of them."""
    monkeypatch.delenv("TMPDIR", raising=False)
    monkeypatch.delenv("TMP", raising=False)
    root = os.path.abspath(os.path.join(os.sep, "wintemp-root", "Local", "Temp"))
    monkeypatch.setenv("TEMP", root)
    assert _main(bwg, _bash(f"echo hi > {os.path.join(root, 'notes.py')}"), monkeypatch) == {}
    assert _main(bwg, _bash("echo hi > /wintemp-elsewhere/notes.py"), monkeypatch) != {}


def test_new_source_file_advisory_uses_hook_specific_output(bwg, monkeypatch, tmp_path):
    out = _main(bwg, _bash("echo 'x' >> src/lib/brandnewmodule.ts"), monkeypatch)
    assert "followup_message" not in out
    assert "brandnewmodule.ts" in out["hookSpecificOutput"]["additionalContext"]


def test_append_redirect_target_is_the_file(bwg):
    assert bwg._extract_target_paths("echo 'x' >> src/lib/service.ts") == ["src/lib/service.ts"]


def test_cat_and_cp_targets_are_seen(bwg):
    assert "src/app.ts" in bwg._extract_target_paths("cat a.ts > src/app.ts")
    assert "src/app.ts" in bwg._extract_target_paths("cp /x/new.ts src/app.ts")


@pytest.mark.parametrize("cmd", [
    "git commit -m 'note: tee foo.ts'",
    'echo "use tee out.ts" # just docs',
    'git commit -m "echo x > a.ts"',
])
def test_armed_layer_ignores_quoted_mentions(monkeypatch, tmp_path, cmd):
    monkeypatch.setenv("BASH_WRITE_GATE_DENY_SHELL_WRITES", "1")
    mod = _load("bash-write-gate.py")
    monkeypatch.setattr(mod, "STATE_DIR", tmp_path)
    assert _decision(_main(mod, _bash(cmd), monkeypatch)) == "allow"


def test_armed_layer_still_denies_real_writes(monkeypatch, tmp_path):
    monkeypatch.setenv("BASH_WRITE_GATE_DENY_SHELL_WRITES", "1")
    mod = _load("bash-write-gate.py")
    monkeypatch.setattr(mod, "STATE_DIR", tmp_path)
    for cmd in ("ls | tee src/out.ts", "echo x > src/a.ts", "echo x >> src/a.ts"):
        assert _decision(_main(mod, _bash(cmd), monkeypatch)) == "deny", cmd


def test_inner_grep_timeout_is_below_the_link_timeout(bwg):
    cfg = json.loads((HOOKS / "dispatch.config.json").read_text(encoding="utf-8"))
    link = next(ln for ln in cfg["chains"]["pre-tool-use"] if ln["id"] == "bash-write-gate")
    assert bwg._GREP_TIMEOUT_S * 1000 < link["timeout_ms"] - 1000


# ---- blocking-doc-enforcer (B1-10) ---------------------------------------- #
def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


@pytest.fixture()
def docrepo(tmp_path):
    repo = tmp_path / "proj"
    for rel in ("server/src/a.ts", "server_docs/01.md", "src/App.tsx", "frontend_docs/01.md", "README.md"):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    return repo


def _bde(repo: Path, cmd: str, monkeypatch) -> str:
    mod = _load("blocking-doc-enforcer.py")
    payload = {**_bash(cmd), "cwd": str(repo)}
    return _decision(_main(mod, payload, monkeypatch))


def test_doc_tree_repo_blocks_backend_commit_without_docs(docrepo, monkeypatch):
    (docrepo / "server/src/a.ts").write_text("y\n", encoding="utf-8")
    _git(docrepo, "add", "server/src/a.ts")
    assert _bde(docrepo, "git commit -m 'fix: thing'", monkeypatch) == "deny"
    assert _bde(docrepo, "git -C . commit -m x", monkeypatch) == "deny"
    (docrepo / "server_docs/01.md").write_text("z\n", encoding="utf-8")
    _git(docrepo, "add", "server_docs/01.md")
    assert _bde(docrepo, "git commit -m 'fix: thing'", monkeypatch) == "allow"


def test_add_in_the_same_command_counts(docrepo, monkeypatch):
    (docrepo / "src/App.tsx").write_text("y\n", encoding="utf-8")
    assert _bde(docrepo, "git add -A && git commit -m x", monkeypatch) == "deny"
    assert _bde(docrepo, "git commit -am x", monkeypatch) == "deny"


def test_amend_mention_in_message_is_not_an_amend(docrepo, monkeypatch):
    (docrepo / "server/src/a.ts").write_text("y\n", encoding="utf-8")
    _git(docrepo, "add", "server/src/a.ts")
    assert _bde(docrepo, 'git commit -m "fix: handle --amend flag docs"', monkeypatch) == "deny"
    assert _bde(docrepo, "git commit --amend --no-edit", monkeypatch) == "allow"


def test_commit_tree_and_docs_only_commits_pass(docrepo, monkeypatch):
    (docrepo / "server/src/a.ts").write_text("y\n", encoding="utf-8")
    _git(docrepo, "add", "server/src/a.ts")
    assert _bde(docrepo, "git commit-tree abc", monkeypatch) == "allow"
    _git(docrepo, "reset", "-q")
    (docrepo / "README.md").write_text("docs\n", encoding="utf-8")
    _git(docrepo, "add", "README.md")
    assert _bde(docrepo, "git commit -m docs", monkeypatch) == "allow"


def test_repo_without_doc_trees_is_never_gated(tmp_path, monkeypatch):
    repo = tmp_path / "plain"
    (repo / "server").mkdir(parents=True)
    (repo / "server/a.ts").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    _git(repo, "add", "-A")
    assert _bde(repo, "git commit -m x", monkeypatch) == "allow"


# ---- dox-write-gate (B1-19) ----------------------------------------------- #
def test_dox_denies_once_per_repo(tmp_path, monkeypatch):
    repo = tmp_path / "nodoc"
    (repo / ".git").mkdir(parents=True)
    mod = _load("dox-write-gate.py")
    monkeypatch.setattr(mod, "STATE_DIR", tmp_path / "state")
    sid = f"dox-{uuid.uuid4().hex}"

    def write(name):
        return _decision(_main(mod, {"session_id": sid, "tool_name": "Write",
                                     "tool_input": {"file_path": str(repo / name), "content": "x"}}, monkeypatch))
    assert write("a.ts") == "deny"
    assert write("b.ts") == "allow"
    assert write("c.py") == "allow"


# ---- dangerous-bash-gate: --force-with-lease ------------------------------ #
@pytest.mark.parametrize("cmd,want", [
    ("git push --force-with-lease origin feat", "allow"),
    ("git push --force-with-lease=main:abc origin main", "allow"),
    ("git push --force-if-includes --force-with-lease origin feat", "allow"),
    ("git push --force origin main", "deny"),
    ("git push -f origin main", "deny"),
    ("git push --force-with-lease --force origin main", "deny"),
])
def test_force_with_lease_is_not_a_force_push(tmp_path, monkeypatch, cmd, want):
    mod = _load("dangerous-bash-gate.py")
    monkeypatch.setattr(mod, "STATE_DIR", tmp_path)
    assert _decision(_main(mod, _bash(cmd), monkeypatch)) == want
