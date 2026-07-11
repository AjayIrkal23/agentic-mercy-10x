#!/usr/bin/env python3
"""
enrich_locked_sidecar.py — P5-T5 locked-cluster sidecar enrichment (one pass).

Writes cluster cross-links (member-of / lead-of), exec-notes, extra disambiguation
keywords, the C24 Higgsfield MCP-default posture, and the /gsd:<x> -> gsd-<x>
name-resolution map into hooks/skills-index-overrides.json — WITHOUT editing any
locked skill body (SKILL-FATE §2/§7, Charter §4d). Idempotent.
"""
from __future__ import annotations

import json
import sys

import skills_lib as sl

OVERRIDES = sl.HOOKS_DIR / "skills-index-overrides.json"

# locked skill -> sidecar cluster metadata (SKILL-FATE §3/§7 cluster notes)
CLUSTER_LINKS: dict[str, dict] = {
    # C6 UI/UX — impeccable is the untouched sidecar LEAD
    "impeccable": {"lead_of": "C6-ui-ux", "note": "UI/UX cluster lead (ui-ux-playbook.mdc)"},
    "taste-skill": {"member_of": "C6-ui-ux", "alias": "design-taste-frontend"},
    "ui-ux-pro-max": {"member_of": "C6-ui-ux",
                      "exec_note": "invoke via absolute path: "
                                   "python3 ~/.claude/skills/ui-ux-pro-max/scripts/search.py"},
    "huashu-design": {"member_of": "C6-ui-ux"},
    "design-extract": {"member_of": "C6-ui-ux"},
    # C1 Debug
    "investigate": {"member_of": "debug-investigation", "niche": "gstack loop w/ browse daemon"},
    "gsd-debug": {"member_of": "debug-investigation"},
    # C2 Review
    "review": {"member_of": "code-review-and-quality", "niche": "gstack pre-landing PR review"},
    "gsd-code-review": {"member_of": "code-review-and-quality"},
    # C3 Security
    "cso": {"member_of": "owasp-security", "niche": "gstack Chief Security Officer mode"},
    "gsd-secure-phase": {"member_of": "owasp-security"},
    # C4 QA
    "qa": {"member_of": "webapp-testing"}, "qa-only": {"member_of": "webapp-testing"},
    "browse": {"member_of": "webapp-testing"}, "canary": {"member_of": "webapp-testing"},
    # C8 Docs
    "document-generate": {"member_of": "update-docs"},
    "document-release": {"member_of": "update-docs"},
    "gsd-docs-update": {"member_of": "update-docs"},
    # C9 Intel
    "gsd-map-codebase": {"member_of": "codebase-intel-first"},
    "gsd-graphify": {"member_of": "codebase-intel-first", "extra_keywords": ["plan-graph"]},
    # C10 Forensic
    "health": {"member_of": "tech-debt-audit", "niche": "gstack code-quality dashboard"},
    # C12 Planning — gstack plan-review quartet + autoplan + plan-tune
    "plan-ceo-review": {"member_of": "workflow-orchestrator"},
    "plan-eng-review": {"member_of": "workflow-orchestrator"},
    "plan-design-review": {"member_of": "workflow-orchestrator"},
    "plan-devex-review": {"member_of": "workflow-orchestrator"},
    "autoplan": {"member_of": "workflow-orchestrator"},
    "plan-tune": {"member_of": "workflow-orchestrator"},
    "gsd-plan-phase": {"member_of": "workflow-orchestrator"},
    # C18 Context
    "context-save": {"member_of": "context-engineering"},
    "context-restore": {"member_of": "context-engineering"},
    "learn": {"member_of": "context-engineering"},
    "gsd-thread": {"member_of": "context-engineering"},
    "gsd-pause-work": {"member_of": "context-engineering"},
    "gsd-resume-work": {"member_of": "context-engineering"},
    # C5 Ship — natural lead land-and-deploy is LOCKED; shipping-and-launch designated
    "ship": {"member_of": "shipping-and-launch"},
    "land-and-deploy": {"member_of": "shipping-and-launch", "note": "natural cluster lead (locked)"},
    "setup-deploy": {"member_of": "shipping-and-launch"},
    "gsd-ship": {"member_of": "shipping-and-launch"},
    "gsd-pr-branch": {"member_of": "shipping-and-launch"},
    # gstack safety quartet cross-links
    "guard": {"cross_links": ["careful", "freeze", "unfreeze"]},
    "careful": {"cross_links": ["guard"]},
    "freeze": {"cross_links": ["unfreeze", "guard"]},
    "unfreeze": {"cross_links": ["freeze"]},
}

HIGGSFIELD = ["higgsfield-generate", "higgsfield-marketplace-cards",
              "higgsfield-product-photoshoot", "higgsfield-soul-id",
              "higgsfield-websites"]


def main() -> int:
    ov = json.loads(OVERRIDES.read_text()) if OVERRIDES.exists() else {"skills": {}}
    ov.setdefault("skills", {})
    locked = sl.locked_skills()

    for name, meta in CLUSTER_LINKS.items():
        if name not in locked:
            print(f"  WARN {name} not locked — skipping", file=sys.stderr)
            continue
        entry = ov["skills"].setdefault(name, {})
        links = entry.setdefault("links", {})
        for k in ("lead_of", "member_of", "niche", "note", "cross_links"):
            if k in meta:
                links[k] = meta[k]
        if "exec_note" in meta:
            entry["exec-note"] = meta["exec_note"]
        if "alias" in meta:
            entry["alias"] = meta["alias"]
        if "extra_keywords" in meta:
            trig = entry.setdefault("triggers", {"keywords": [], "paths": [], "intents": []})
            kws = set(trig.get("keywords", [])) | set(meta["extra_keywords"])
            trig["keywords"] = sorted(kws)

    # C24 Higgsfield MCP-default posture (sidecar/rule layer, NOT the skill body)
    for name in HIGGSFIELD:
        if name in ov["skills"]:
            ov["skills"][name]["exec-note"] = (
                "MCP-default posture: prefer mcp__higgsfield__* as the asset surface; "
                "CLI is the fallback. Posture lives here, not in the upstream skill body.")

    # /gsd:<x> -> gsd-<x> name-resolution map (broken in-body handoffs resolve without
    # editing any gsd file; the real fix ships upstream via gsd-update)
    gsd_map = {f"/gsd:{n[4:]}": n for n in locked if n.startswith("gsd-")}
    ov["_gsd_name_map"] = dict(sorted(gsd_map.items()))

    ov.setdefault("_meta", {})["clusterEnriched"] = True
    OVERRIDES.write_text(json.dumps(ov, indent=2) + "\n", encoding="utf-8")
    linked = len([1 for e in ov["skills"].values() if e.get("links")])
    print(f"cluster-enriched: {linked} locked skills linked, "
          f"{len(gsd_map)} /gsd: name-map entries, {len(HIGGSFIELD)} Higgsfield MCP notes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
