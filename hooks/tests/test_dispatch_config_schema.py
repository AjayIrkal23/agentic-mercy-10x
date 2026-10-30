"""dispatch.config.json shape (ECC validate-hooks idea as a pytest)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1]
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))
import dispatch as D  # noqa: E402

CFG = json.loads((HOOKS / "dispatch.config.json").read_text(encoding="utf-8"))
TYPES = {"gate", "mutator", "advisory", "exec"}


def _links():
    for ev, links in CFG["chains"].items():
        for ln in links:
            yield ev, ln


def test_every_chain_and_budget_names_a_known_event():
    assert set(CFG["chains"]) <= set(D._EVENT_NAME)
    assert set(CFG["budgets"]) <= set(D._EVENT_NAME)


def test_every_link_has_the_required_keys_and_types():
    for ev, ln in _links():
        assert isinstance(ln.get("id"), str) and ln["id"], (ev, ln)
        assert ln.get("type") in TYPES, (ev, ln["id"])
        assert isinstance(ln.get("cmd"), list) and ln["cmd"] and ln["cmd"][0] in ("{PY}", "{NODE}"), ln["id"]
        assert isinstance(ln.get("timeout_ms"), int) and 500 <= ln["timeout_ms"] <= 1_800_000, ln["id"]
        for flag in ("enabled", "async", "defer", "crit_exempt"):
            assert isinstance(ln.get(flag, False), bool), (ln["id"], flag)
        if "priority" in ln:
            assert isinstance(ln["priority"], int) and ln["priority"] >= 0, ln["id"]
        if ln["type"] != "advisory":
            assert "defer" not in ln and "priority" not in ln, ln["id"]
        if ln.get("async"):
            assert ln["type"] == "exec", ln["id"]


def test_ids_are_unique_across_the_whole_config():
    ids = [ln["id"] for _, ln in _links()]
    assert len(ids) == len(set(ids)), [i for i in ids if ids.count(i) > 1]


def test_regexes_compile():
    for _, ln in _links():
        for key in ("tools", "command_re"):
            if ln.get(key):
                re.compile(f"(?:{ln[key]})")


def test_enabled_scripts_exist():
    for _, ln in _links():
        if ln.get("enabled", True):
            script = ln["cmd"][1].replace("{HOOKS}", str(HOOKS))
            assert Path(script).is_file(), (ln["id"], script)


def test_budgets_fit_the_harness_cap():
    for ev, b in CFG["budgets"].items():
        # Claude Code caps additionalContext at 10,000; 7,800 leaves the [truncated] marker room
        assert 0 <= int(b.get("chars", 0)) <= 7800, ev
        assert int(b.get("ms", 0)) > 0, ev
