"""Timeout ladder: no dispatched event may outlive its harness timeout (audit 2026-10-05 A-02).

Claude Code kills a hook at its settings `timeout`; a kill drops every link output of
that event, including async execs not yet spawned (Stop: index flush, breadcrumb).
Worst case follows dispatch.py's real passes: gates, mutators and sync execs run in
sequence; advisories run in parallel (each waited up to timeout+1 s); once the
sequential part exceeds `budgets.ms`, only priority-0 advisories still run.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARGIN_S = 1.0  # interpreter start + dispatcher overhead


def _load():
    tpl = json.loads((ROOT / "settings.template.json").read_text(encoding="utf-8"))
    cfg = json.loads((ROOT / "hooks" / "dispatch.config.json").read_text(encoding="utf-8"))
    return tpl, cfg


def _chain_name(event: str) -> str:
    return re.sub(r"(?<!^)([A-Z])", r"-\1", event).lower()


def _matches(link: dict, tool: str) -> bool:
    pat = link.get("tools")
    return not pat or not tool or re.fullmatch(pat, tool) is not None


def worst_case_s(links: list[dict], budget_ms: float, tool: str) -> float:
    active = [ln for ln in links if ln.get("enabled", True) and _matches(ln, tool)]
    seq = sum(ln.get("timeout_ms", 5000) for ln in active
              if ln.get("type") in ("gate", "mutator")
              or (ln.get("type") == "exec" and not ln.get("async"))) / 1000.0
    adv = [ln for ln in active if ln.get("type", "advisory") == "advisory"]
    def wait(group):  # _run_link kills the subprocess at timeout_ms
        return max((ln.get("timeout_ms", 5000) / 1000.0 for ln in group), default=0.0)
    under = min(seq, budget_ms / 1000.0) + wait(adv)
    over = seq + wait([ln for ln in adv if int(ln.get("priority", 5)) == 0])
    return max(under, over)


def _cases():
    tpl, cfg = _load()
    for event, entries in tpl["hooks"].items():
        chain = cfg["chains"].get(_chain_name(event))
        if chain is None:
            continue
        budget = cfg.get("budgets", {}).get(_chain_name(event), {}).get("ms", 2000)
        for entry in entries:
            tools = [t for t in (entry.get("matcher") or "").split("|") if t and t != ".*"] or [""]
            for hook in entry.get("hooks", []):
                for tool in tools:
                    yield event, tool, float(hook.get("timeout", 60)), worst_case_s(chain, budget, tool)


def test_every_event_fits_its_harness_timeout():
    bad = [f"{ev}[{tool or '*'}]: worst {w:.1f}s + {MARGIN_S}s >= harness {h:.0f}s"
           for ev, tool, h, w in _cases() if w + MARGIN_S >= h]
    assert not bad, "timeout ladder inverted:\n" + "\n".join(bad)


def test_model_counts_budget_skip():
    links = [{"id": "g", "type": "gate", "timeout_ms": 19000},
             {"id": "slow", "type": "advisory", "priority": 2, "timeout_ms": 17000}]
    # slow gates (19 s) skip the priority-2 advisory; fast gates (<= 2 s budget) let it
    # run its 17 s. Worst path = 2 + 17, never the naive 19 + 17.
    assert worst_case_s(links, 2000, "Write") == 19.0
