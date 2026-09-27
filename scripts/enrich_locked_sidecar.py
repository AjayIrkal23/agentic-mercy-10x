#!/usr/bin/env python3
"""
enrich_locked_sidecar.py — P5-T5 locked-cluster sidecar enrichment (one pass).

Writes cluster cross-links (member-of / lead-of), exec-notes, extra disambiguation
keywords, and the C24 Higgsfield MCP-default posture into
hooks/skills-index-overrides.json — WITHOUT editing any locked skill body
(SKILL-FATE §2/§7, Charter §4d). Idempotent.
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
}

HIGGSFIELD = ["higgsfield-generate", "higgsfield-marketplace-cards",
              "higgsfield-product-photoshoot", "higgsfield-soul-id",
              "higgsfield-websites"]


def main() -> int:
    ov = json.loads(OVERRIDES.read_text()) if OVERRIDES.exists() else {"skills": {}}
    ov.setdefault("skills", {})
    locked = sl.locked_skills()
    ov["skills"] = {
        name: metadata
        for name, metadata in ov["skills"].items()
        if name in locked
    }

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

    ov.pop("_gsd_name_map", None)

    ov.setdefault("_meta", {})["clusterEnriched"] = True
    OVERRIDES.write_text(json.dumps(ov, indent=2) + "\n", encoding="utf-8")
    linked = len([1 for e in ov["skills"].values() if e.get("links")])
    print(f"cluster-enriched: {linked} locked skills linked, "
          f"{len(HIGGSFIELD)} Higgsfield MCP notes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
