"""connector-ask-gate.py on the github MCP (P4) and destructive connector tools: they ask in an interactive
session and are DENIED whenever nobody can answer (subagent, workflow script, `-p`, restored session): an
advisory would let the push / send / delete run (REVIEW2 Fix 2). Read-only github tools and the two harmless
higgsfield tools (audit 07 issue 11) pass silently."""
from __future__ import annotations

import importlib.util
import io
import json
import re
import sys
import uuid
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1]

WRITE_TOOLS = ("merge_pull_request", "push_files", "create_or_update_file", "create_pull_request", "update_issue",
               "create_issue", "add_issue_comment", "create_branch", "create_repository", "fork_repository",
               "create_pull_request_review", "update_pull_request_branch", "delete_file")
READ_TOOLS = ("get_file_contents", "search_code", "list_commits", "get_pull_request", "list_issues",
              "search_repositories")


@pytest.fixture(autouse=True)
def _interactive(monkeypatch):
    monkeypatch.delenv("CLAUDE_WORKBENCH_UNATTENDED", raising=False)


def _run(monkeypatch, tool: str, **extra) -> dict:
    spec = importlib.util.spec_from_file_location(f"conn_{uuid.uuid4().hex}", HOOKS / "connector-ask-gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    payload = {"session_id": f"cg-{uuid.uuid4().hex}", "tool_name": tool, "tool_input": {}, **extra}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    mod.main()
    return json.loads(out.getvalue() or "{}")


@pytest.mark.parametrize("name", WRITE_TOOLS)
def test_github_write_tools_ask(monkeypatch, name):
    hso = _run(monkeypatch, f"mcp__github__{name}")["hookSpecificOutput"]
    assert hso["permissionDecision"] == "ask"
    assert name in hso["permissionDecisionReason"] and "GitHub" in hso["permissionDecisionReason"]


@pytest.mark.parametrize("name", READ_TOOLS)
def test_github_read_tools_pass(monkeypatch, name):
    assert _run(monkeypatch, f"mcp__github__{name}") == {}


@pytest.mark.parametrize("name", ["push_files", "merge_pull_request"])
def test_unattended_github_write_is_denied_and_logged(monkeypatch, tmp_path, name):
    """REVIEW2 Fix 2: nobody can confirm, so the write never downgrades to an advisory."""
    monkeypatch.setenv("CLAUDE_HOOK_TELEMETRY_DIR", str(tmp_path / "tel"))
    monkeypatch.setenv("CLAUDE_WORKBENCH_UNATTENDED", "1")
    hso = _run(monkeypatch, f"mcp__github__{name}")["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny" and "unattended" in hso["permissionDecisionReason"]
    rows = [json.loads(line) for p in (tmp_path / "tel").glob("*.jsonl")
            for line in p.read_text(encoding="utf-8").splitlines()]
    assert any(r.get("decision") == "deny" and r["link_id"] == "connector-ask-gate" for r in rows)
    assert not any(r.get("decision") == "ask_downgraded" for r in rows)


@pytest.mark.parametrize("extra", [{"agent_id": "a1"}, {"workflow_id": "wf1"}])
@pytest.mark.parametrize("name", ["push_files", "merge_pull_request"])
def test_subagents_and_workflows_never_write_to_github(monkeypatch, extra, name):
    hso = _run(monkeypatch, f"mcp__github__{name}", **extra)["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    assert "subagents" in hso["permissionDecisionReason"].lower()


@pytest.mark.parametrize("tool,extra,unattended", [
    ("mcp__claude_ai_Zoho_Books__delete_invoice", {"agent_id": "a1"}, False),
    ("mcp__claude_ai_Zoho_CRM__delete_records", {"agent_id": "a1"}, False),
    ("mcp__claude_ai_Apollo__emailer_send_now", {}, True),
    ("mcp__claude_ai_Shopify__create_refund", {"workflow_id": "wf1"}, False),
])
def test_destructive_connector_actions_are_denied_when_nobody_can_confirm(monkeypatch, tool, extra, unattended):
    """REVIEW2 Fix 2: a send / delete / refund never runs on an advisory."""
    if unattended:
        monkeypatch.setenv("CLAUDE_WORKBENCH_UNATTENDED", "1")
    hso = _run(monkeypatch, tool, **extra)["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    assert "CONNECTOR CHECK" in hso["permissionDecisionReason"]
    assert "no one can confirm" in hso["permissionDecisionReason"].lower()


def test_interactive_destructive_connector_action_asks(monkeypatch):
    hso = _run(monkeypatch, "mcp__claude_ai_Zoho_CRM__delete_records")["hookSpecificOutput"]
    assert hso["permissionDecision"] == "ask"


@pytest.mark.parametrize("tool", ["mcp__claude_ai_higgsfield__remove_background",
                                  "mcp__claude_ai_higgsfield__ads_studio_cancel_run"])
def test_harmless_higgsfield_tools_pass(monkeypatch, tool):
    assert _run(monkeypatch, tool) == {}


def test_github_tools_match_the_intended_regex():
    """Pins the INTEGRATE snippet: the connector link's `tools` regex reaches the github MCP."""
    rx = "mcp__claude_ai_.*|mcp__plugin_.*|mcp__github__.*"
    assert re.fullmatch(rx, "mcp__github__push_files")
    assert re.fullmatch(rx, "mcp__claude_ai_Zoho_Books__delete_invoice")
    assert not re.fullmatch(rx, "mcp__jcodemunch__search_symbols")
