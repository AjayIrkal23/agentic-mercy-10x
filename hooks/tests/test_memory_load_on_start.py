"""Memory MCP SessionStart injection (audit 2026-10-05 F-02).

It promised <=5 entities but cut each of 3 observations to 200 chars and sliced the
block at 1,200 chars mid-line, so ~3 entities reached the model, picked in file
order. Now: every picked entity fits (equal share of the same budget, latest
observation first), ranked fragile > decision > pattern > other, newest first.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1]


def _mod():
    spec = importlib.util.spec_from_file_location("mem_load_t", HOOKS / "memory-load-on-start.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _ent(name, kind, *obs):
    return {"type": "entity", "name": name, "entityType": kind, "observations": list(obs)}


LONG = "x" * 400 + "END"


def _entities():
    return [
        _ent("pattern::proj::a", "pattern", f"[2026-10-01] {LONG}"),
        _ent("decision::proj::b", "decision", f"[2026-09-01] {LONG}", f"[2026-10-03] {LONG}"),
        _ent("note::proj::c", "note", f"[2026-10-04] {LONG}"),
        _ent("fragile::proj::old", "fragile_area", f"[2026-06-01] {LONG}"),
        _ent("fragile::proj::new", "fragile_area", f"[2026-10-04] {LONG}", f"[2026-10-04] {LONG}"),
        _ent("pattern::proj::d", "pattern", f"[2026-10-02] {LONG}"),
        _ent("other::unrelated", "x", "nope"),
    ]


def test_five_entities_fit_the_budget_without_mid_line_cuts():
    m = _mod()
    out = m.render(m.select(_entities(), "proj"))
    names = [ln for ln in out.splitlines() if ln.startswith("- ")]
    assert len(names) == 5, out
    assert len(out) <= m.MAX_CHARS
    for ln in out.splitlines():
        assert not ln.startswith("  - ") or ln.endswith(("…", "END")), ln


def test_repo_name_matches_across_underscore_hyphen_and_space():
    """F-10: `fragile::watch-sdk::*` never loaded in the WATCH_SDK repo."""
    m = _mod()
    ents = [_ent("fragile::watch-sdk::a", "fragile_area", "[2026-10-01] a"),
            _ent("decision::WATCH_SDK::b", "decision", "[2026-10-01] b"),
            _ent("pattern::jashn events::c", "pattern", "[2026-10-01] c"),
            _ent("fragile::watchsdk-other::d", "fragile_area", "[2026-10-01] d")]
    assert {e["name"] for e in m.select(ents, "WATCH_SDK")} == {
        "fragile::watch-sdk::a", "decision::WATCH_SDK::b"}
    assert [e["name"] for e in m.select(ents, "jashn-events")] == ["pattern::jashn events::c"]


def test_rank_fragile_then_decision_then_pattern_newest_first():
    m = _mod()
    order = [e["name"] for e in m.select(_entities(), "proj")]
    assert order == ["fragile::proj::new", "fragile::proj::old", "decision::proj::b",
                     "pattern::proj::d", "pattern::proj::a"]
