"""Saved workflows follow hooks/model-policy.json (audit 2026-10-05 E-03).

workflows/invoke-fullstack.js ran spec/plan on sonnet and backend/frontend/integrator
on opus, the inverse of the policy; workflow-model-guard only advises for saved
scripts on disk, so the file itself must be right.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CALL = re.compile(r"agentType:\s*'([\w-]+)',\s*model:\s*'(\w+)'")


def _expected(agent: str, pins: dict) -> str:
    for model in ("opus", "fable", "sonnet"):
        if agent in (pins.get(model) or []):
            return model
    return "sonnet"


def test_workflow_agent_models_match_policy():
    policy = json.loads((ROOT / "hooks" / "model-policy.json").read_text(encoding="utf-8"))
    pins = policy["agent_pins"]
    bad = []
    for wf in sorted((ROOT / "workflows").glob("*.js")):
        for agent, model in CALL.findall(wf.read_text(encoding="utf-8")):
            if model != _expected(agent, pins):
                bad.append(f"{wf.name}: {agent} on {model}, policy says {_expected(agent, pins)}")
    assert not bad, "\n".join(bad)
