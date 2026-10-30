"""Saved workflows follow hooks/model-policy.json (audit 2026-10-05 E-03; MERGE-PLAN R3.2 tiers).

workflows/invoke-fullstack.js once ran spec/plan on sonnet and backend/frontend/integrator on opus, the
inverse of the policy. workflow-model-guard never rewrites a saved script, so the generated literals must
be right for the tier they were rendered for (workflows/.rendered.json), including the escalated
`up(..., '<m>')` literal. The scripts come from workflows/src/*.js.tpl via scripts/build_workflows.py.
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "hooks" / "model-policy.json"
OPTS = re.compile(r"\{[^{}]*agentType:\s*'([\w-]+)',\s*model:\s*'(\w+)'[^{}]*\}")
LABEL = re.compile(r"label:\s*'([^']*)'")
UP = re.compile(r"up\(\{[^}]*agentType:\s*'([\w-]+)',\s*model:\s*'\w+'[^}]*\},\s*'(\w+)'\)")
sys.path.insert(0, str(ROOT / "hooks"))
from lib import model_mode as mm  # noqa: E402
from lib import plan_tier  # noqa: E402


def _builder():
    spec = importlib.util.spec_from_file_location("build_workflows", ROOT / "scripts" / "build_workflows.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = _builder()


def _policy() -> dict:
    return json.loads(POLICY.read_text(encoding="utf-8"))


def _rec() -> dict:
    return json.loads((ROOT / "workflows" / ".rendered.json").read_text(encoding="utf-8"))


def test_workflow_agent_models_match_rendered_tier():
    policy, rec = _policy(), _rec()
    tier, usage = rec["tier"], bool(rec["usage_guard"])
    bad = []
    files = sorted((ROOT / "workflows").glob("*.js"))
    assert files
    for wf in files:
        text = wf.read_text(encoding="utf-8")
        for mo in OPTS.finditer(text):
            agent, model = mo.group(1), mo.group(2)
            lab = LABEL.search(mo.group(0))
            exp = B.resolve(policy, tier, usage, mm.role_of(policy, agent, lab.group(1) if lab else None))
            if model != exp:
                bad.append(f"{wf.name}: {agent} on {model}, tier {tier} says {exp}")
        for agent, upm in UP.findall(text):
            role = mm.role_of(policy, agent)
            exp = B.resolve(policy, tier, usage, role, up=True)
            if upm != exp or role == "judge":
                bad.append(f"{wf.name}: up() {agent} -> {upm}, expected {exp} (role {role})")
    assert bad == [], "\n".join(bad)


def test_rendered_record_matches_policy():
    rec = _rec()
    assert rec["policy_sha"] == B.policy_sha(POLICY.read_bytes())
    assert rec["tier"] in plan_tier.TIERS


def test_no_fable_literal_in_any_render(tmp_path):
    for tier in ("pro", "max5", "max20", "api"):
        for usage in (False, True):
            out = tmp_path / f"{tier}-{int(usage)}"
            cp = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_workflows.py"), "--tier", tier,
                                 "--usage", "on" if usage else "off", "--out", str(out), "--quiet"],
                                capture_output=True, text=True, encoding="utf-8")
            assert cp.returncode == 0, cp.stderr
            for f in out.glob("*.js"):
                text = f.read_text(encoding="utf-8")
                assert "'fable'" not in text, f"{tier}/{usage}: {f.name}"
                if tier == "pro":
                    assert "'opus'" not in text, f"pro/{usage}: {f.name}"
