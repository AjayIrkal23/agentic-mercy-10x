"""B-02/B-03/B-04: the jcodemunch read gate sees shell reads, keys its state per agent,
spends one deny per agent per user turn, and names the exact call with the repo id."""
from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from lib import shell_reads  # noqa: E402


def _load():
    spec = importlib.util.spec_from_file_location("jcm_shell_ut", HOOKS / "jcodemunch-enforce.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "src" / "auth.ts").write_text("export const useAuth = 1\n", encoding="utf-8")
    (root / "README.md").write_text("# hi\n", encoding="utf-8")
    return root


# ---- lib/shell_reads ---------------------------------------------------------------

@pytest.mark.parametrize("cmd,leaf,hint", [
    ("grep -rn useAuth src", "x", "useAuth"),  # no glob: the code-path rule (src/) decides
    ("rg useAuth -g '*.ts'", "x.ts", "useAuth"),
    ("cat src/auth.ts", "auth.ts", "auth.ts"),
    ("sed -n 1,40p src/auth.ts", "auth.ts", "auth.ts"),
    ("cd src && head -50 auth.ts | tail -5", "auth.ts", "auth.ts"),
    ("grep -rn --include=*.ts useAuth .", "x.ts", "useAuth"),
    ("find . -name '*.ts'", "x.ts", ""),
])
def test_shell_targets(repo, cmd, leaf, hint):
    target, got_hint = shell_reads.code_target(cmd, str(repo))
    assert Path(target).name == leaf, cmd
    assert got_hint == hint


@pytest.mark.parametrize("cmd", [
    "git grep useAuth", "npm test", "grep foo README.md", "sed -i s/a/b/ src/auth.ts",
    "pytest -q", "ls src", "cat README.md", "echo grep foo", "git log | head",
])
def test_non_reads_pass(repo, cmd):
    target, _ = shell_reads.code_target(cmd, str(repo))
    assert not target or Path(target).suffix in (".md",), cmd


# ---- the gate ----------------------------------------------------------------------

@pytest.fixture
def gate(tmp_path, repo, monkeypatch):
    jcm = _load()
    monkeypatch.setattr(jcm, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(jcm, "_check_index_exists", lambda t: True)
    monkeypatch.setattr(jcm, "_index_building", lambda p: True)  # a STALE rebuild must not relax the gate
    monkeypatch.setattr(jcm, "_repo_id", lambda root: "Owner/proj")
    monkeypatch.setattr(jcm, "_turn", lambda payload: payload.get("turn", "t1"))
    cfg = {**jcm._load_enforce_config(), "initial_block_count": 1, "exempt_paths": ["~/.claude/"]}
    monkeypatch.setattr(jcm, "_load_enforce_config", lambda: cfg)  # the repo lives under /tmp

    def _io(fn, payload):
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        buf = io.StringIO()
        monkeypatch.setattr(sys, "stdout", buf)
        fn()
        out = buf.getvalue().strip()
        return json.loads(out) if out else {}

    def bash(cmd, agent="", turn="t1"):
        p = {"session_id": "s", "tool_name": "Bash", "cwd": str(repo), "turn": turn,
             "tool_input": {"command": cmd}}
        if agent:
            p["agent_id"] = agent
        return _io(jcm.pre_tool_use, p)

    def read(agent="", turn="t1"):
        p = {"session_id": "s", "tool_name": "Read", "cwd": str(repo), "turn": turn,
             "tool_input": {"file_path": str(repo / "src" / "auth.ts")}}
        if agent:
            p["agent_id"] = agent
        return _io(jcm.pre_tool_use, p)

    def used(agent="", tool="mcp__jcodemunch__search_symbols", turn="t1"):
        p = {"session_id": "s", "tool_name": tool, "turn": turn}
        if agent:
            p["agent_id"] = agent
        return _io(jcm.mcp_used, p)

    return {"jcm": jcm, "bash": bash, "read": read, "used": used, "state": tmp_path / "state"}


def test_shell_grep_denied_once_with_exact_call(gate):
    first = gate["bash"]("grep -rn useAuth src")
    reason = first.get("permissionDecisionReason", "")
    assert first.get("permissionDecision") == "deny"
    assert 'mcp__jcodemunch__search_symbols(repo="Owner/proj", query="useAuth")' in reason
    assert "token" not in reason.lower()
    second = gate["bash"]("grep -rn useAuth src")
    assert "permissionDecision" not in second and "jcodemunch" in second.get("additionalContext", "")


def test_shell_non_reads_untouched(gate):
    for cmd in ("git grep useAuth", "npm test", "grep foo README.md"):
        assert gate["bash"](cmd) == {}, cmd


@pytest.mark.parametrize("cmd", [
    # santa review 2026-10-31: stdin filters and non-source searches were denied once per turn
    "ps aux | grep node", "git log --oneline | grep fix", "env | grep PATH", "docker ps | grep mongo",
    'echo "$out" | grep -q error', "grep -r TODO docs/", "find . -maxdepth 2 -type d",
])
def test_stdin_filters_and_non_source_searches_pass(gate, cmd):
    assert gate["bash"](cmd) == {}, cmd


@pytest.mark.parametrize("cmd", ["grep -rn useAuth src", "cat src/auth.ts", "find . -name '*.ts'", "rg -t ts foo"])
def test_source_reads_still_gated(gate, cmd):
    assert gate["bash"](cmd).get("permissionDecision") == "deny", cmd


def test_shell_after_jcodemunch_allowed(gate):
    gate["used"]()
    assert gate["bash"]("grep -rn useAuth src") == {}


def test_subagent_has_its_own_state(gate):
    gate["used"]()                       # the parent consulted jcodemunch
    assert gate["read"]().get("permissionDecision") is None
    assert gate["read"](agent="a1").get("permissionDecision") == "deny"
    gate["used"](agent="a1")
    assert gate["read"](agent="a1") == {}
    assert gate["read"](agent="a2").get("permissionDecision") == "deny"


def test_new_turn_gets_one_fresh_deny(gate):
    assert gate["read"](turn="t1").get("permissionDecision") == "deny"
    assert gate["read"](turn="t1").get("permissionDecision") is None
    assert gate["read"](turn="t2").get("permissionDecision") == "deny"


def test_deadcode_marker_stays_on_the_session(gate):
    gate["used"](agent="a1", tool="mcp__jcodemunch__find_dead_code")
    assert (gate["state"] / "s.deadcode.json").is_file()
