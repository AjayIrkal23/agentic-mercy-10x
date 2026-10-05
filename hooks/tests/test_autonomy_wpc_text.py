"""WP-C (autonomy 2026-10-05) items 1 and 3.

1. No router or gate text tells the USER to type something: every line is an instruction
   the MODEL executes now (dispatch an agent with the Agent tool, use an MCP tool).
3. Higgsfield is pushed only when usable: a needs-auth Higgsfield gets ONE login line per
   session for asset-looking prompts, and the /invoke design text and the frontend rule
   say what to do when it is not logged in.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_HOOKS = Path(__file__).resolve().parents[1]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

from prompt_router import manifest as MF                 # noqa: E402
from prompt_router import router as R                    # noqa: E402
from prompt_router.classify import TaskProfile           # noqa: E402
from prompt_router.modules import mcp_routes as MR       # noqa: E402
from prompt_router.modules import model_advice as MA     # noqa: E402

POLICY = json.loads((_HOOKS / "model-policy.json").read_text(encoding="utf-8"))
OPUS_AGENTS = set(POLICY["agent_pins"]["opus"])


def _p(**kw) -> TaskProfile:
    return TaskProfile(**kw)


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, _HOOKS / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------- model advice
@pytest.mark.parametrize("profile,agent", [
    (_p(intents={"DESIGN": 1}, size="L", risk=2, text="design"), "frontend-uiux-designer"),
    (_p(is_arch=True, intents={"PLAN": 1}, size="L", risk=2, text="plan"), "planning-director"),
    (_p(is_arch=True, intents={"SPEC": 1}, size="L", risk=2, text="spec"), "spec-architect"),
    (_p(intents={"DEBUG": 1}, size="L", risk=2, text="debug"), "debug-detective"),
    (_p(intents={"IMPLEMENT": 1}, size="L", risk=2, text="build"), "planning-director"),
])
def test_heavy_advice_dispatches_an_opus_agent(profile, agent):
    out = MA.advise(profile)
    assert out and "/model" not in out and "consider" not in out
    assert f"dispatch the {agent} agent (Opus" in out and "Agent tool" in out
    assert agent in OPUS_AGENTS  # opus-guard pins it, so the dispatch really runs on Opus


def test_advice_agents_are_configured_in_the_policy_block():
    cfg = POLICY["main_session_advice"]
    assert set(cfg["agents"].values()) <= OPUS_AGENTS
    assert not re.search(r"/model\b", cfg["_comment"])


# --------------------------------------------------------------------------- router dispatch
def _routing(monkeypatch, tiers):
    monkeypatch.setattr(R._select, "dispatch_tiers", lambda profile, threshold=0: tiers)
    items = R._routing_items(_p(text="x"), {"config": {}, "payload": {}, "repo": None})
    return [i["text"] for i in items if i["id"].startswith("route:") and i["id"] != "route:ui"
            and not i["id"].startswith("route:higgsfield")]


def test_dispatch_line_names_the_agent_and_the_agent_tool(monkeypatch):
    txt = _routing(monkeypatch, [{"kind": "agent", "agent": "santa-reviewer", "act": "review",
                                  "category": "REVIEW", "score": 6}])
    assert txt and "/invoke" not in txt[0]
    assert "dispatch santa-reviewer" in txt[0] and "Agent tool" in txt[0]


def test_suggest_line_never_tells_the_user_to_type(monkeypatch):
    txt = _routing(monkeypatch, [{"kind": "suggest", "agent": "audit-specialist", "act": "audit",
                                  "category": "AUDIT", "score": 2}])
    assert txt and "/invoke" not in txt[0] and "audit-specialist" in txt[0]
    txt = _routing(monkeypatch, [{"kind": "suggest", "agent": None, "act": "audit",
                                  "category": "AUDIT", "score": 2}])
    assert txt and "/invoke" not in txt[0] and "Agent tool" in txt[0]


# --------------------------------------------------------------------------- graph missing
def test_missing_graph_line_says_it_is_building_and_gives_the_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(R, "_mcp_ok", lambda *a, **k: True)
    repo = SimpleNamespace(root=tmp_path, path=tmp_path, name="r")
    prof = _p(text="how is the auth module wired", intents={"PLAN": 1}, is_arch=True,
              arch_hit=["architecture"], surface_source="prompt")
    items = R._substrate_items(prof, {"repo": repo, "payload": {}})
    txt = next(i["text"] for i in items if i["id"] == "substrate:graphify")
    assert "graphify update" not in txt
    assert "graph is building in the background; use jcodemunch get_dependency_graph now" in txt


# --------------------------------------------------------------------------- gate texts
def _gate(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_HOOK_DOTSTATE_DIR", str(tmp_path / "dot"))
    monkeypatch.setenv("CLAUDE_HOOK_TELEMETRY_DIR", str(tmp_path / "tel"))
    return _load("hcg_wpc_text", "hard-completion-gate.py")


def _json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_every_gate_fix_is_a_model_action(monkeypatch, tmp_path):
    g = _gate(monkeypatch, tmp_path)
    cid = "c1"
    ws = tmp_path / "ws"
    (ws / "server_docs").mkdir(parents=True)
    _json(g.STATE_DIR / f"{cid}.doc-enforcer.json",
          {"code_files": ["/app/server/a.ts"], "be_touched": True})
    _json(g.STATE_DIR / f"{cid}.security-scan.json", {"security_files": ["/app/server/auth.ts"]})
    details = [g.gate2_docs(cid, [str(ws)])[2], g.gate3_security(cid, [], None)[2],
               g.gate4_santa(cid, 3)[2], g.gate5_dead_code(cid, 3)[2]]
    assert all(details), details
    for d in details:
        assert "/invoke" not in d and "/santa-review" not in d, d
        assert "run /" not in d, d
        assert "Agent tool" in d or "mcp__" in d, d
    assert "dispatch the docs-sync-agent now" in details[0]
    assert "dispatch the santa-reviewer agent now" in details[2]


# --------------------------------------------------------------------------- Higgsfield
_ASSET = "generate a hero image and a logo for the landing page"


def _auth(monkeypatch, *, needs=("higgsfield",), avail=("higgsfield", "openart")):
    monkeypatch.setattr(MR, "needs_auth", lambda: set(needs))
    monkeypatch.setattr(MR, "available_servers", lambda: set(avail))


def _asset_items(text: str):
    prof = R._classify.classify({"prompt": text, "session_id": "wpc-x", "cwd": "/tmp"})
    return [i for i in R._routing_items(prof, {"config": {}, "payload": {"prompt": text}, "repo": None})
            if i["id"] == "route:higgsfield-auth"]


def test_needs_auth_higgsfield_gets_one_login_line_for_asset_prompts(monkeypatch):
    _auth(monkeypatch)
    items = _asset_items(_ASSET)
    assert len(items) == 1
    txt = items[0]["text"]
    assert "Higgsfield needs a one-time login" in txt
    assert "ask the user once (batched with any other login)" in txt
    assert "mcp__higgsfield__authenticate" in txt
    assert "assets are pending" in txt and "no placeholders" in txt
    assert "mcp__openart__authenticate" not in txt  # openart is not waiting on auth


def test_login_line_batches_openart_when_it_also_waits(monkeypatch):
    _auth(monkeypatch, needs=("higgsfield", "openart"))
    assert "mcp__openart__authenticate" in _asset_items(_ASSET)[0]["text"]


def test_no_login_line_when_usable_or_unregistered_or_not_asset(monkeypatch):
    _auth(monkeypatch, needs=())
    assert _asset_items(_ASSET) == []
    _auth(monkeypatch, avail=("openart",))
    assert _asset_items(_ASSET) == []
    _auth(monkeypatch)
    assert _asset_items("fix the null check in the invoice controller") == []


def test_login_line_is_once_per_session(monkeypatch):
    _auth(monkeypatch)
    item = _asset_items(_ASSET)[0]
    kept, suppressed = MF.dedup([item], {item["id"]})
    assert kept == [] and len(suppressed) == 1


def test_design_template_and_frontend_rule_are_conditional_on_login():
    from lib import invoke_templates as T
    note = T.ACT_NOTES["design"]
    body = T.invoke_body(order="o", rows="r", impl="i", design_model="opus", checkpoints="c",
                         globs="g", mutating="m", closer_block="b")
    rule = (_HOOKS.parent / "rules" / "frontend.md").read_text(encoding="utf-8")
    for txt in (note, body[body.index("**`design`**"):][:700], rule):
        assert "mcp__higgsfield__authenticate" in txt and "pending" in txt, txt[:120]
    assert "Placeholder boxes" in note and "never acceptable" in note  # pending, not a fallback to boxes
