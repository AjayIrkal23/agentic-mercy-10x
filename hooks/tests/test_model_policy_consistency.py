"""model-policy.json is the single model truth: agent frontmatter, the template env and
the escalation list must agree with it (Sonnet 5.5 plan, slice D)."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY = json.loads((ROOT / "hooks" / "model-policy.json").read_text(encoding="utf-8"))
ENV = json.loads((ROOT / "settings.template.json").read_text(encoding="utf-8"))["env"]
EFFORTS = {"low", "medium", "high", "xhigh"}


def _frontmatter(path: Path) -> dict:
    m = re.match(r"---\n(.*?)\n---", path.read_text(encoding="utf-8"), re.S)
    out: dict = {}
    for key, val in re.findall(r"^(\w+):\s*(.+?)\s*$", m.group(1) if m else "", re.M):
        out.setdefault(key, val)  # first hit wins; examples inside description come later
    return out


AGENTS = {p.stem: _frontmatter(p) for p in (ROOT / "agents").glob("*.md")
          if p.stem not in ("README", "CLAUDE", "AGENTS")}


def test_agent_frontmatter_model_matches_pins():
    opus = set(POLICY["agent_pins"]["opus"])
    wrong = {n: fm.get("model") for n, fm in AGENTS.items()
             if fm.get("model") != ("opus" if n in opus else POLICY["default"])}
    assert not wrong, wrong


def test_agent_efforts_are_valid_and_never_max():
    bad = {n: fm.get("effort") for n, fm in AGENTS.items() if fm.get("effort") not in EFFORTS}
    assert not bad, bad
    assert "max" in POLICY["effort_defaults"]["banned"]


def test_template_env_matches_policy_defaults():
    assert ENV["CLAUDE_CODE_SUBAGENT_MODEL"] == POLICY["default"]
    # Claude Code reads no subagent-effort env var; a key here would look live and do nothing.
    assert "CLAUDE_CODE_SUBAGENT_EFFORT" not in ENV


def test_escalation_targets_unpinned_execution_agents():
    esc = POLICY["escalation"]
    pinned = {a for k, v in POLICY["agent_pins"].items() if not k.startswith("_") for a in v}
    assert esc["enabled"] and esc["to"] == "opus"
    assert not set(esc["agents"]) & pinned
    assert set(esc["agents"]) <= set(AGENTS)
    assert not POLICY["agent_pins"]["fable"]
