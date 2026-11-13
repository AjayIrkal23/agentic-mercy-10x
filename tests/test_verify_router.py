"""test_verify_router.py — check.py's "router LIVE" row: the router is a dispatcher link now.

Since the router joined dispatch.py (link "router" in the user-prompt-submit chain), settings.json
registers `dispatch.py user-prompt-submit` and never names prompt_router/router.py, so the old
substring check reported a false MISS on every machine (Manashree's PC and the owner's, 2026-11-06).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "installer"))
import verify  # noqa: E402

DISPATCH = "python3 ${HOME}/.claude/hooks/dispatch.py user-prompt-submit"


def _root(tmp_path: Path, links) -> Path:
    (tmp_path / "hooks").mkdir()
    cfg = {"chains": {"user-prompt-submit": links}} if links is not None else {"chains": {}}
    (tmp_path / "hooks" / "dispatch.config.json").write_text(json.dumps(cfg), encoding="utf-8")
    return tmp_path


def _router(enabled=True):
    return {"id": "router", "type": "advisory", "cmd": ["{PY}", "{HOOKS}/prompt_router/router.py"], "enabled": enabled}


def test_router_link_in_the_dispatch_chain_is_live(tmp_path):
    assert verify.router_live(_root(tmp_path, [_router()]), DISPATCH)


def test_direct_registration_is_still_live(tmp_path):
    assert verify.router_live(tmp_path, "python3 ~/.claude/hooks/prompt_router/router.py")


def test_disabled_router_link_is_not_live(tmp_path):
    assert not verify.router_live(_root(tmp_path, [_router(enabled=False)]), DISPATCH)


def test_missing_config_or_chain_is_not_live(tmp_path):
    assert not verify.router_live(tmp_path, DISPATCH)  # no dispatch.config.json
    assert not verify.router_live(_root(tmp_path, None), DISPATCH)  # no user-prompt-submit chain


def test_unregistered_user_prompt_submit_is_not_live(tmp_path):
    assert not verify.router_live(_root(tmp_path, [_router()]), "")


def test_the_live_tree_reports_the_router_live():
    sj = json.loads((ROOT / "settings.template.json").read_text(encoding="utf-8")).get("hooks", {})
    ups = " ".join(h.get("command", "") for g in sj.get("UserPromptSubmit", []) for h in g.get("hooks", []))
    assert verify.router_live(ROOT, ups), ups
