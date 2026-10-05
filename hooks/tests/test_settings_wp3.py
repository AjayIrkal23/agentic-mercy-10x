"""settings.template.json hook matchers agree with dispatch.config.json (B1-13/A-05):
no spawn for tools no link handles; lean-ctx writes/shells and connector tools reach
the dispatcher (B1-04, G-02); still no literal lean-ctx string in the template."""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = (ROOT / "settings.template.json").read_text(encoding="utf-8")
HOOKS = json.loads(TEMPLATE)["hooks"]
CFG = json.loads((ROOT / "hooks" / "dispatch.config.json").read_text(encoding="utf-8"))


def _support():
    spec = importlib.util.spec_from_file_location("ds_wp3", ROOT / "hooks" / "dispatch_support.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _matcher(event: str) -> str:
    return HOOKS[event][0]["matcher"]


def _handled(event: str, tool: str, tool_input: dict | None = None) -> bool:
    """Some enabled link of ``event``'s chain runs for this call (after lean-ctx adaption)."""
    payload = {"tool_name": tool, "tool_input": tool_input or {}}
    shaped = _support().adapt(payload) or [payload]
    links = [ln for ln in CFG["chains"][event] if ln.get("enabled", True)]
    return any(re.fullmatch(f"(?:{ln['tools']})", p["tool_name"]) for p in shaped for ln in links if ln.get("tools"))


PRE_SAMPLES = {
    "Bash": None, "PowerShell": None, "Write": None, "Edit": None, "Read": None, "Grep": None, "Agent": None,
    "Workflow": None,
    "mcp__lean-ctx__ctx_read": None, "mcp__lean-ctx__ctx_search": None,
    "mcp__lean-ctx__ctx_shell": {"command": "ls"}, "mcp__lean-ctx__shell": {"command": "ls"},
    "mcp__lean-ctx__ctx_patch": {"path": "/r/a.py", "old_text": "a", "new_text": "b"},
    "mcp__claude_ai_Zoho_Books__delete_invoice": None, "mcp__plugin_small-business_shopify__graphql_mutation": None,
}


def test_every_pre_tool_use_sample_is_matched_and_handled():
    m = _matcher("PreToolUse")
    for tool, ti in PRE_SAMPLES.items():
        assert re.fullmatch(m, tool), tool
        assert _handled("pre-tool-use", tool, ti), tool


def test_no_dispatch_for_tools_without_a_link():
    m = _matcher("PreToolUse")
    for tool in ("Skill", "mcp__jcodemunch__search_symbols", "mcp__lean-ctx__ctx_tree", "mcp__memory__search_nodes"):
        assert not re.fullmatch(m, tool), tool
        assert not _handled("pre-tool-use", tool), tool


def test_lean_ctx_writes_reach_post_tool_use():
    m = _matcher("PostToolUse")
    for tool, ti in (("mcp__lean-ctx__ctx_patch", {"path": "/r/a.py", "new_text": "b", "op": "create"}),
                     ("mcp__lean-ctx__ctx_shell", {"command": "semgrep scan"})):
        assert re.fullmatch(m, tool), tool
        assert _handled("post-tool-use", tool, ti), tool


def test_powershell_reaches_every_shell_event():
    """The PowerShell tool is a shell tool (A1-02): the dispatcher is spawned for it on all three
    tool events and some enabled link handles it (dangerous gate, semgrep tracker, failure hint)."""
    for event, name in (("PreToolUse", "pre-tool-use"), ("PostToolUse", "post-tool-use"),
                        ("PostToolUseFailure", "post-tool-use-failure")):
        assert re.fullmatch(_matcher(event), "PowerShell"), event
        assert _handled(name, "PowerShell", {"command": "ls"}), name


def test_template_stays_lean_ctx_literal_free():
    assert "lean-ctx" not in TEMPLATE


def test_no_stale_lean_ctx_tool_names_in_config():
    assert "ctx_multi_read" not in json.dumps(CFG)
