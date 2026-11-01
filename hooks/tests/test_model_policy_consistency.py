"""model-policy.json is the single model truth (version 2, plan-tier redesign 2026-10-29): the
tiers x roles matrix, agent frontmatter (= the max20 column), the legacy agent_pins/escalation
views, the per-tier task_matrix and the template env must agree with it."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY = json.loads((ROOT / "hooks" / "model-policy.json").read_text(encoding="utf-8"))
ENV = json.loads((ROOT / "settings.template.json").read_text(encoding="utf-8"))["env"]
EFFORTS = {"low", "medium", "high", "xhigh"}
TIERS, ROLES = POLICY["tiers"], POLICY["roles"]
ORDER = POLICY["model_order"]
VALID = set(POLICY["model_ids"])
ROLE_NAMES = {"explore", "docs", "verify", "test", "impl", "integrate", "security", "judge", "default"}


def _frontmatter(path: Path) -> dict:
    m = re.match(r"---\n(.*?)\n---", path.read_text(encoding="utf-8"), re.S)
    out: dict = {}
    for key, val in re.findall(r"^(\w+):\s*(.+?)\s*$", m.group(1) if m else "", re.M):
        out.setdefault(key, val)  # first hit wins; examples inside description come later
    return out


# A file with no frontmatter (team-lead.md, the main session's team playbook) is not an agent.
AGENTS = {p.stem: fm for p in (ROOT / "agents").glob("*.md")
          if p.stem not in ("README", "CLAUDE", "AGENTS") and (fm := _frontmatter(p))}


def rank(m: str) -> int:
    return ORDER.index(m)


def role_of(agent: str) -> str:
    return ROLES["agents"].get(agent, "default")


def tier_model(tier: str, role: str) -> str:
    return TIERS[tier]["roles"][role]


def test_tiers_block_shape():
    assert set(TIERS) == {"pro", "max5", "max20", "api"}  # no _comment inside tiers (acceptance 2)
    assert ORDER == ["haiku", "sonnet", "opus", "fable"] and VALID == set(ORDER)
    for t, blk in TIERS.items():
        assert set(blk["roles"]) == ROLE_NAMES, t
        assert all(m in VALID for m in blk["roles"].values()), t
        assert blk["ceiling"] in VALID and blk["main"] in VALID and blk["subagent_env"] in VALID
        assert all(rank(m) <= rank(blk["ceiling"]) for m in blk["roles"].values()), t
        assert all(rank(m) <= rank(blk["ceiling"]) for m in blk["escalate"].values()), t
        assert all(f in VALID for f in blk["fallback"]) and blk["fallback"]
        ug = blk["usage_guard"]
        assert ug["ceiling"] in VALID and ug["judge"] in VALID
        assert rank(ug["ceiling"]) <= rank(blk["ceiling"])


def test_ceilings_monotone_and_fable_only_in_max20():
    assert rank(TIERS["pro"]["ceiling"]) <= rank(TIERS["max5"]["ceiling"]) <= rank(TIERS["max20"]["ceiling"])
    assert "fable" not in json.dumps({k: v for k, v in TIERS.items() if k != "max20"})
    assert "fable" not in json.dumps(TIERS["max20"]["roles"]) and "fable" not in json.dumps(TIERS["max20"]["escalate"])
    # ask_only lists models a Pro call may NOT use without the user's phrase (D6): naming opus there is the guard
    pro_routes = {k: v for k, v in TIERS["pro"].items() if k != "ask_only"}
    assert TIERS["pro"]["ceiling"] == "sonnet" and "opus" not in json.dumps(pro_routes)
    assert set(TIERS["pro"]["ask_only"]) == {"sonnet", "opus"}


def test_api_is_a_copy_of_max5():
    assert TIERS["api"] == TIERS["max5"]


def test_haiku_is_the_default_worker_on_pro_max5_api():
    for t in ("pro", "max5", "api"):
        for role in ("explore", "docs", "verify"):
            assert tier_model(t, role) == "haiku", (t, role)
    assert TIERS["pro"]["roles"]["impl"] == "haiku" and TIERS["pro"]["subagent_env"] == "haiku"


def test_max20_runs_sonnet_floor_and_opus_executors():
    # 2026-10-31 (owner: smartest agents, tokens do not matter): no Haiku role on max20
    roles = TIERS["max20"]["roles"]
    assert "haiku" not in roles.values()
    assert {r: roles[r] for r in ("explore", "docs", "default")} == dict.fromkeys(("explore", "docs", "default"), "sonnet")
    assert all(roles[r] == "opus" for r in ("verify", "test", "impl", "integrate", "security", "judge"))
    assert TIERS["max20"]["main"] == "opus" and TIERS["max20"]["size_bumps"] == {}


def test_roles_cover_every_agent_and_only_known_roles():
    assert set(ROLES["agents"].values()) <= ROLE_NAMES
    missing = {a for a in AGENTS if a not in ROLES["agents"]}
    assert not missing, missing  # every local agent has an explicit role
    assert set(ROLES["guarded"]) == {"judge", "impl", "integrate", "security", "test"}
    assert set(ROLES["labels"].values()) <= ROLE_NAMES


def test_agent_frontmatter_model_is_the_max20_column():
    wrong = {n: (fm.get("model"), tier_model("max20", role_of(n))) for n, fm in AGENTS.items()
             if fm.get("model") != tier_model("max20", role_of(n))}
    assert not wrong, wrong


def test_agent_pins_are_the_max20_view():
    pins = POLICY["agent_pins"]
    for model in ("haiku", "sonnet", "opus", "fable"):
        derived = sorted(a for a, r in ROLES["agents"].items() if tier_model("max20", r) == model
                         and model != TIERS["max20"]["roles"]["default"])
        assert sorted(pins.get(model) or []) == derived, model
    assert not pins["fable"]


def test_escalation_legacy_keys_agree_with_tiers():  # doctor_checks.py reads to/agents/enabled
    esc = POLICY["escalation"]
    assert esc["enabled"] is True and esc["to"] == TIERS["max20"]["escalate"]["impl"] == "opus"
    executors = {a for a, r in ROLES["agents"].items() if any(r in TIERS[t]["escalate"] for t in TIERS)}
    assert set(esc["agents"]) == executors and executors <= set(AGENTS)
    # 2026-10-31 (owner): on max20 executors run Opus outright; elsewhere they still escalate to it
    assert all(tier_model("max20", ROLES["agents"][a]) == "opus" for a in executors)
    for p in esc["retry_markers"] + esc["plan_markers"]:
        re.compile(p)


def test_task_matrix_is_per_tier_and_pro_never_names_opus():
    tm = POLICY["task_matrix"]
    assert {k for k in tm if not k.startswith("_")} == {"pro", "max5", "max20"}
    assert "opus" not in json.dumps(tm["pro"]) and "fable" not in json.dumps(tm)
    for t in tm:
        if not t.startswith("_"):
            assert set(tm[t]) == {"DESIGN", "HEAVY_ARCHITECTURE", "DEEP_DEBUG", "IMPLEMENT_SUITE"}


def test_override_phrases_and_flags_know_haiku():
    assert POLICY["override_phrases"]["haiku"]
    sf = POLICY["session_flags"]
    assert sf["haiku"] == "haiku-only-mode" and sf["precedence"] == ["haiku", "sonnet", "opus", "fable"]


def test_agent_efforts_are_valid_and_never_max():
    bad = {n: fm.get("effort") for n, fm in AGENTS.items() if fm.get("effort") not in EFFORTS}
    assert not bad, bad
    assert "max" in POLICY["effort_defaults"]["banned"]


def test_template_env_matches_policy_defaults():
    assert ENV["CLAUDE_CODE_SUBAGENT_MODEL"] == POLICY["default"] == TIERS["max20"]["subagent_env"]
    # Claude Code reads no subagent-effort env var; a key here would look live and do nothing.
    assert "CLAUDE_CODE_SUBAGENT_EFFORT" not in ENV


TEMPLATES = sorted((ROOT / "workflows" / "src").glob("*.js.tpl"))
AGENT_TYPE = re.compile(r"agentType:\s*'([\w-]+)'")


def test_turn_caps_block_shape():
    tc = POLICY["turn_caps"]
    assert isinstance(tc["report_reserve"], int) and 3 <= tc["report_reserve"] <= 10
    assert set(tc["schema_floor"]) == ROLE_NAMES - {"explore"}  # general-purpose has no frontmatter
    assert all(isinstance(v, int) and v >= 10 for v in tc["schema_floor"].values())
    assert set(tc["agents"]) == set(AGENTS), set(tc["agents"]) ^ set(AGENTS)
    assert all(isinstance(v, int) and 10 <= v <= 200 for v in tc["agents"].values())


def test_every_agent_frontmatter_cap_equals_the_policy_table():
    caps = POLICY["turn_caps"]["agents"]
    bad = {n: (fm.get("maxTurns"), caps[n]) for n, fm in AGENTS.items() if int(fm.get("maxTurns", 0)) != caps[n]}
    assert not bad, bad


def test_every_agent_a_saved_workflow_calls_meets_its_role_floor():
    tc = POLICY["turn_caps"]
    assert TEMPLATES
    low = []
    for tpl in TEMPLATES:
        for agent in sorted(set(AGENT_TYPE.findall(tpl.read_text(encoding="utf-8")))):
            if agent == "general-purpose":
                continue  # harness default cap; no frontmatter to size
            assert agent in tc["agents"], f"{tpl.name}: unknown agentType {agent}"
            floor = tc["schema_floor"][role_of(agent)]
            if tc["agents"][agent] < floor:
                low.append(f"{tpl.name}: {agent} cap {tc['agents'][agent]} < {role_of(agent)} floor {floor}")
    assert low == [], "\n".join(low)
