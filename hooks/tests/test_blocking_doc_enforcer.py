"""blocking-doc-enforcer: `git commit` in a doc-layout repo (GO_UDP / UDP_PLATFORM) is
denied until the touched surface's docs AND PROJECT_LINKAGES.md are written this
session; every other repo, amends, and sessions without code writes pass."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOOKS))


def _gate(tmp_path, monkeypatch, command: str, cwd: str, state: dict | None, extra: dict | None = None) -> dict:
    spec = importlib.util.spec_from_file_location("bde_t", HOOKS / "blocking-doc-enforcer.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    monkeypatch.setattr(mod, "STATE_DIR", tmp_path)
    monkeypatch.delenv("CLAUDE_WORKBENCH_UNATTENDED", raising=False)  # asks are judged interactive by default
    if state is not None:
        (tmp_path / "sid-1.doc-enforcer.json").write_text(json.dumps(state), encoding="utf-8")
    payload = {"session_id": "sid-1", "tool_name": "Bash", "cwd": cwd,
               "tool_input": {"command": command}, **(extra or {})}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    buf = io.StringIO()
    with redirect_stdout(buf):
        mod.main()
    return json.loads(buf.getvalue() or "{}")


BE = {"be_touched": True, "fe_touched": False, "code_files": ["/work/GO_UDP/server/a.go"]}


def _denied(out: dict) -> bool:
    return (out.get("hookSpecificOutput") or {}).get("permissionDecision") == "deny"


def test_blocks_backend_commit_without_docs(tmp_path, monkeypatch):
    out = _gate(tmp_path, monkeypatch, "git commit -m x", "/work/GO_UDP",
                {**BE, "be_docs_written": False, "linkages_written": False})
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert _denied(out) and "server_docs/" in reason and "PROJECT_LINKAGES.md" in reason


def test_passes_once_docs_and_linkages_are_written(tmp_path, monkeypatch):
    out = _gate(tmp_path, monkeypatch, "git commit -m x", "/work/GO_UDP",
                {**BE, "be_docs_written": True, "linkages_written": True})
    assert not _denied(out)


def test_linkages_alone_still_missing_docs_blocks(tmp_path, monkeypatch):
    out = _gate(tmp_path, monkeypatch, "git commit -m x", "/work/GO_UDP",
                {**BE, "be_docs_written": False, "linkages_written": True})
    assert _denied(out)


def test_other_repos_amends_and_no_state_pass(tmp_path, monkeypatch):
    bad = {**BE, "be_docs_written": False, "linkages_written": False}
    assert not _denied(_gate(tmp_path, monkeypatch, "git commit -m x", "/work/shop", bad))
    assert not _denied(_gate(tmp_path, monkeypatch, "git commit --amend", "/work/GO_UDP", bad))
    assert not _denied(_gate(tmp_path / "none", monkeypatch, "git commit -m x", "/work/GO_UDP", None))


# --- PKG gates: staged-secret scan (ECC pre-bash-commit-quality + codex pre-commit) ---------------------
import shutil  # noqa: E402
import subprocess  # noqa: E402

import pytest  # noqa: E402

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not on PATH")
# Fixture values are built by concatenation: this file holds no literal key, token or key header.
_PEM_HEAD = "-----BEGIN RSA " + "PRIVATE KEY-----"
_AKIA = "AKIA" + "ABCDEFGHIJKLMNOP"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *args],
                   check=True, capture_output=True)


@pytest.fixture()
def secret_repo(tmp_path_factory):
    repo = tmp_path_factory.mktemp("secrepo")
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    (repo / "README.md").write_text("# r\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-qm", "init")
    return repo


def _stage(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    _git(repo, "add", "-f", rel)


def _commit(tmp_path, monkeypatch, repo: Path, command: str = "git commit -m x", extra: dict | None = None) -> dict:
    return _gate(tmp_path, monkeypatch, command, str(repo), None, extra)


def _decision(out: dict) -> str:
    return (out.get("hookSpecificOutput") or {}).get("permissionDecision", "allow")


@needs_git
@pytest.mark.parametrize("rel,text,kind", [
    ("config.py", f'AWS_KEY = "{_AKIA}"\n', "AWS access key"),
    ("k.pem", _PEM_HEAD + "\nMIIB\n", "private key"),
    ("notes.md", 'token: "ghp_' + "a" * 36 + '"\n', "GitHub token"),
    ("a.ts", 'const key = "sk-ant-' + "Q7" * 12 + '"\n', "Anthropic API key"),   # not `x`*24: `xxxx` is a placeholder
    (".env", "A=1\n", ".env file staged"),
])
def test_staged_secret_is_denied_without_echoing_it(tmp_path, monkeypatch, secret_repo, rel, text, kind):
    _stage(secret_repo, rel, text)
    out = _commit(tmp_path, monkeypatch, secret_repo)
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert _denied(out) and f"({kind})" in reason and rel in reason
    assert _AKIA not in reason and "hunter2" not in reason and "ghp_" not in reason
    if rel == "config.py":
        assert "config.py:1 (AWS access key)" in reason


@needs_git
@pytest.mark.parametrize("rel,text", [
    ("p.py", 'password = "REPLACE_ME_WITH_REAL_ONE"\n'), ("q.js", "api_key = process.env.API_KEY\n"),
    ("r.py", 'token = "<your-token-here>"\n'), ("s.sh", 'secret = "${SECRET}"\n'),
    ("t.py", 'password = "hunter2' + 'hunter2hunter2"  # EXAMPLE\n'), (".env.example", "A=1\n"),
    ("package-lock.json", '{"k": "' + _AKIA + '"}\n'), ("img.png", _AKIA + "\n"),
])
def test_placeholders_examples_and_lockfiles_pass(tmp_path, monkeypatch, secret_repo, rel, text):
    _stage(secret_repo, rel, text)
    assert not _denied(_commit(tmp_path, monkeypatch, secret_repo))


@needs_git
def test_amend_with_a_new_secret_is_scanned(tmp_path, monkeypatch, secret_repo):
    _stage(secret_repo, "config.py", f'AWS = "{_AKIA}"\n')
    assert _denied(_commit(tmp_path, monkeypatch, secret_repo, "git commit --amend -m x"))


@needs_git
def test_commit_all_scans_unstaged_tracked_changes(tmp_path, monkeypatch, secret_repo):
    _stage(secret_repo, "config.py", "X = 1\n")
    _git(secret_repo, "commit", "-qm", "c")
    (secret_repo / "config.py").write_text(f'X = 1\nAWS = "{_AKIA}"\n', encoding="utf-8")
    assert not _denied(_commit(tmp_path, monkeypatch, secret_repo))           # not staged, no -a
    out = _commit(tmp_path, monkeypatch, secret_repo, "git commit -a -m x")
    assert _denied(out) and "config.py:2 (AWS access key)" in out["hookSpecificOutput"]["permissionDecisionReason"]


@needs_git
def test_no_repo_or_no_git_fails_open(tmp_path, monkeypatch, secret_repo):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert not _denied(_commit(tmp_path, monkeypatch, plain))
    _stage(secret_repo, "config.py", f'AWS = "{_AKIA}"\n')
    monkeypatch.setenv("PATH", "")
    assert not _denied(_commit(tmp_path, monkeypatch, secret_repo))


# --- REVIEW2 Fix 5: soft hits (credential assignment, .env.*) ask; hard hits deny -----------------------
_TOKEN = "a8F3kd92" + "Ldk3jf83kdjf"


@needs_git
@pytest.mark.parametrize("rel,text", [
    ("src/i18n/en.ts", 'export default {\n  password: "Password is required",\n'
                       '  token: "Session expired, sign in again",\n};\n'),     # UI strings: values have spaces
    ("seed.py", "password='adminpass" + "123'\n"),                               # 12 chars: under 16
])
def test_ordinary_strings_pass(tmp_path, monkeypatch, secret_repo, rel, text):
    _stage(secret_repo, rel, text)
    assert _commit(tmp_path, monkeypatch, secret_repo) == {}


@needs_git
@pytest.mark.parametrize("rel,text,kind", [
    ("cfg.ts", f'token: "{_TOKEN}"\n', "credential assignment"),
    ("db.py", 'password = "hunter2' + 'hunter2hunter2"\n', "credential assignment"),
    (".env.development", "VITE_API_URL=http://localhost\n", ".env.* file staged"),
    (".env.production", "VITE_API_URL=https://x\n", ".env.* file staged"),
])
def test_soft_hits_ask_interactively_and_deny_when_nobody_can_confirm(tmp_path, monkeypatch, secret_repo,
                                                                     rel, text, kind):
    _stage(secret_repo, rel, text)
    out = _commit(tmp_path, monkeypatch, secret_repo)
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "ask" and f"({kind})" in hso["permissionDecisionReason"]
    assert _TOKEN not in hso["permissionDecisionReason"] and "hunter2" not in hso["permissionDecisionReason"]
    out = _commit(tmp_path, monkeypatch, secret_repo, extra={"agent_id": "a1"})
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny" and "no one can confirm" in hso["permissionDecisionReason"].lower()


@needs_git
def test_a_hard_hit_denies_even_beside_a_soft_one(tmp_path, monkeypatch, secret_repo):
    _stage(secret_repo, "cfg.ts", f'token: "{_TOKEN}"\n')
    _stage(secret_repo, "config.py", f'AWS = "{_AKIA}"\n')
    assert _decision(_commit(tmp_path, monkeypatch, secret_repo)) == "deny"


@needs_git
def test_a_soft_ask_does_not_skip_the_docs_rule(tmp_path, monkeypatch, secret_repo):
    _stage(secret_repo, "server_docs/README.md", "# docs\n")
    _git(secret_repo, "commit", "-qm", "docs")
    _stage(secret_repo, "server/app.py", f'token = "{_TOKEN}"\n')
    out = _commit(tmp_path, monkeypatch, secret_repo)
    assert _denied(out) and "documentation" in out["hookSpecificOutput"]["permissionDecisionReason"]
