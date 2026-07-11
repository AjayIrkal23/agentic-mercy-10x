#!/usr/bin/env python3
"""
apply_merge.py — P5-T3/T4/T5 merge driver + P5-T6 alias mechanics.

Executes the 24 SKILL-FATE merges into 14 canonicals. For each merged skill:
  1. its unique body moves to <canonical>/references/<topic>.md (mode=move) OR a
     jcodemunch/MCP-backed rewrite is authored there (mode=rewrite);
  2. any supporting files (references/, scripts/, top-level .md) are carried into
     <canonical>/references/<alias>/ so nothing is orphaned;
  3. the alias dir KEEPS its old name and becomes a THIN ALIAS SKILL (old name,
     trigger-preserving short description, user-invocable, 1-2 line pointer body);
  4. the alias's distinctive trigger words are folded into the canonical's
     triggers.keywords AND the thin alias's keywords (token-diff gate);
  5. hooks/skill-aliases.json gains alias -> canonical (permanent).

Palette stays 218 names (trigger law). Idempotent (alias_of front-matter = done).

  python3 scripts/apply_merge.py --wave 1|2|3 [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import skills_lib as sl

ALIASES_JSON = sl.HOOKS_DIR / "skill-aliases.json"

# (wave, alias, canonical, topic-relpath under canonical/references/, mode)
MERGES = [
    # Wave 1 — debug, review, security, QA (7)
    (1, "debugging-and-error-recovery", "debug-investigation", "error-recovery.md", "move"),
    (1, "diagnose", "debug-investigation", "loop-method.md", "move"),
    (1, "backend-code-review", "code-review-and-quality", "backend-review.md", "move"),
    (1, "frontend-code-review", "code-review-and-quality", "frontend-review.md", "move"),
    (1, "security-and-hardening", "owasp-security", "hardening.md", "move"),
    (1, "browser-testing-with-devtools", "webapp-testing", "browser-devtools.md", "rewrite"),
    # Wave 2 — API, docs, intel, forensic (11)
    (2, "api-and-interface-design", "api-contract-standards", "interface-design.md", "move"),
    (2, "frontend-api-standards", "frontend-response-handling", "fetch-layer.md", "move"),
    (2, "documentation-and-adrs", "update-docs", "adrs.md", "move"),
    (2, "jcodemunch-token-saver", "codebase-intel-first", "jcodemunch-toolbox.md", "move"),
    (2, "project-structure-map", "codebase-intel-first", "structure-map.md", "move"),
    (2, "iterative-retrieval", "codebase-intel-first", "iterative-retrieval.md", "move"),
    (2, "zoom-out", "codebase-intel-first", "zoom-out.md", "move"),
    (2, "codebase-start-point-guide", "codebase-intel-first", "session-start-flow.md", "move"),
    (2, "forensic-change-coupling", "tech-debt-audit", "forensics/coupling.md", "rewrite"),
    (2, "forensic-complexity-trends", "tech-debt-audit", "forensics/trends.md", "rewrite"),
    (2, "forensic-debt-quantification", "tech-debt-audit", "forensics/debt-dollars.md", "rewrite"),
    (2, "forensic-hotspot-finder", "tech-debt-audit", "forensics/hotspots.md", "rewrite"),
    (2, "improve-codebase-architecture", "tech-debt-audit", "deepening.md", "move"),
    # Wave 3 — TDD, planning, context, impl/scaffold pairs (6, incl. ship designation)
    (3, "tdd", "test-driven-development", "loop.md", "move"),
    (3, "plan-exec-stack-guide", "workflow-orchestrator", "stack-ordering.md", "move"),
    (3, "strategic-compact", "context-engineering", "compaction.md", "move"),
    (3, "incremental-implementation", "code-execution-standard", "incremental-delivery.md", "move"),
    (3, "domain-scaffold-patterns", "scaffold-standards", "domain-file-trees.md", "move"),
]

# jcodemunch/MCP-backed rewrites (kill the GNU date -d/bc/awk POSIX class; use the
# installed playwright + browser-tools MCPs). Old bodies remain in git history.
REWRITES = {
    "browser-testing-with-devtools":
        "# Browser testing with DevTools (MCP-backed)\n\n"
        "> Absorbed into `webapp-testing`. This method now drives the **installed** "
        "`playwright` and `browser-tools` MCP servers, not the uninstalled "
        "chrome-devtools MCP.\n\n"
        "## Runtime inspection loop\n"
        "1. Navigate + snapshot: `mcp__playwright__browser_navigate`, "
        "`mcp__playwright__browser_snapshot`.\n"
        "2. Console + network evidence: `mcp__browser-tools-mcp__getConsoleErrors`, "
        "`getNetworkErrors`, `getNetworkLogs`.\n"
        "3. DOM + interaction: `mcp__playwright__browser_click/type/fill_form`, then "
        "re-snapshot to assert the change.\n"
        "4. Visual proof: `mcp__playwright__browser_take_screenshot`.\n"
        "5. Audits: `mcp__browser-tools-mcp__runAccessibilityAudit`, "
        "`runPerformanceAudit`, `runBestPracticesAudit`.\n\n"
        "Capture DOM, console errors, network requests, performance, and visual output "
        "with real runtime data. The legacy chrome-devtools-MCP steps require an "
        "uninstalled server and are intentionally not used here.\n",
    "forensic-change-coupling":
        "# Change coupling (jcodemunch-backed)\n\n"
        "> Absorbed into `tech-debt-audit`. Reveals temporal coupling / shotgun-surgery "
        "and hidden dependencies **without** POSIX-only git-history shell pipelines.\n\n"
        "Use `mcp__jcodemunch__get_coupling_metrics` (files that change together), "
        "`mcp__jcodemunch__get_churn_rate`, and `mcp__jcodemunch__get_related_symbols` / "
        "`find_importers` to find architectural violations and cross-module dependencies. "
        "No shell history pipelines or coreutils date arithmetic — the index computes the temporal-coupling graph "
        "directly.\n",
    "forensic-complexity-trends":
        "# Complexity trends (jcodemunch-backed)\n\n"
        "> Absorbed into `tech-debt-audit`. Tracks whether files are improving, stable, "
        "or deteriorating over git history.\n\n"
        "Use `mcp__jcodemunch__get_symbol_complexity`, `mcp__jcodemunch__get_churn_rate`, "
        "`mcp__jcodemunch__diff_health_radar`, and `mcp__jcodemunch__get_repo_health` to "
        "measure refactoring impact and validate technical-debt work. Replaces the "
        "POSIX-only history walk with cross-platform index queries.\n",
    "forensic-debt-quantification":
        "# Debt quantification — cost in dollars (jcodemunch-backed inputs)\n\n"
        "> Absorbed into `tech-debt-audit`. Translates code problems into ROI / dollars "
        "for executives and quality budgets (2-3x defect, productivity-multiplier "
        "formulas).\n\n"
        "Source the metrics from `mcp__jcodemunch__get_hotspots`, `get_coupling_metrics`, "
        "`get_repo_health`, and `get_symbol_complexity`; apply the research-backed cost "
        "formulas in-process. No POSIX-only shell arithmetic pipelines.\n",
    "forensic-hotspot-finder":
        "# Hotspot finder (jcodemunch-backed)\n\n"
        "> Absorbed into `tech-debt-audit`. Identifies high-risk files (change frequency × "
        "complexity, 4-9x defect-rate formula) to prioritise refactoring and investigate "
        "recurring bugs.\n\n"
        "Use `mcp__jcodemunch__get_hotspots` (frequency×complexity ranking already "
        "computed), plus `get_churn_rate` and `get_file_risk`. Replaces the "
        "POSIX-only git-history hotspot script with a cross-platform index query.\n",
}

# Garbled canonical descriptions -> clean single sentences (canonical-side fix).
CANONICAL_DESC_REWRITE = {
    "debug-investigation":
        "Use when the cause of a bug, regression, crash, or unexpected behavior is "
        "unknown and evidence is needed before proposing a fix.",
    "webapp-testing":
        "Use when testing a web application end-to-end in a real browser — driving "
        "flows, asserting UI, capturing console/network/performance evidence, and "
        "verifying visual output with real runtime data.",
    "workflow-orchestrator":
        "Use when work spans multiple phases, domains, or specialist roles and needs "
        "explicit sequencing, ownership, and quality gates across Architect, Code, and "
        "Debug modes.",
    "code-execution-standard":
        "Use when scope and root cause are already understood and the task is "
        "implementing a safe, validated, known-scope change.",
    "frontend-response-handling":
        "Use when frontend API work needs success parsing, normalized error handling, "
        "or backend-driven list, filter, sort, and pagination behavior.",
}


def _git(*args) -> None:
    subprocess.run(["git", "-C", str(sl.CLAUDE_DIR), *args],
                   capture_output=True, text=True)


def _load_aliases() -> dict:
    if ALIASES_JSON.exists():
        try:
            return json.loads(ALIASES_JSON.read_text())
        except json.JSONDecodeError:
            pass
    return {"_meta": {"purpose": "P5-T6 permanent alias->canonical map (trigger law). "
                                 "Consumed by select.py / skill_router.py / "
                                 "fullstack-skills-reminder.py — an alias hit surfaces "
                                 "the canonical and logs alias telemetry. No sunset.",
                      "schema": 1}}


def _save_aliases(d: dict) -> None:
    ALIASES_JSON.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")


def _carry_supporting(alias_dir: Path, canonical_dir: Path, alias: str, dry: bool) -> list[str]:
    """Move alias's non-SKILL.md files into canonical/references/<alias>/."""
    carried = []
    dest = canonical_dir / "references" / alias
    for entry in sorted(alias_dir.iterdir()):
        if entry.name == "SKILL.md":
            continue
        carried.append(entry.name)
        if dry:
            continue
        dest.mkdir(parents=True, exist_ok=True)
        target = dest / entry.name
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        # plain move only — NEVER git mv (would stage outside the flock and could
        # leak into a parallel sibling's commit). Staging happens later under flock
        # via `git add -A skills/`.
        shutil.move(str(entry), str(target))
    return carried


def _thin_alias_fm(alias: str, canonical: str, topic: str, old_desc: str) -> tuple[dict, str]:
    # short trigger-preserving description
    first = old_desc.split(". ")[0].strip().rstrip(".")
    words = first.split()
    short = " ".join(words[:14])
    desc = f"{short} (alias of {canonical})."
    kws = sorted(sl.trigger_words(old_desc) | sl.trigger_words(alias.replace("-", " ")))
    missing = sl.token_diff(old_desc, desc, kws)
    kws = sorted(set(kws) | missing)
    fm = {
        "name": alias,
        "description": desc,
        "user-invocable": True,
        "schema": 1,
        "alias_of": canonical,
        "triggers": {"keywords": kws, "paths": [], "intents": []},
        "provenance": "self",
    }
    body = (f"\n# {alias}\n\n"
            f"**Alias of [`{canonical}`](../{canonical}/SKILL.md).** The method content "
            f"now lives at `{canonical}/references/{topic}` (supporting material, if any, "
            f"at `{canonical}/references/{alias}/`). Invoke `{canonical}`.\n")
    return fm, body


def _fold_canonical(canonical: str, alias_desc: str, dry: bool) -> None:
    cdir = sl.SKILLS_DIR / canonical
    fm, body, ok = sl.read_frontmatter(cdir / "SKILL.md")
    if not ok:
        return
    changed = False
    # clean a garbled canonical description
    if canonical in CANONICAL_DESC_REWRITE and fm.get("description") != CANONICAL_DESC_REWRITE[canonical]:
        old = str(fm.get("description", ""))
        fm["description"] = CANONICAL_DESC_REWRITE[canonical]
        # preserve canonical's own trigger words
        trig = fm.setdefault("triggers", {"keywords": [], "paths": [], "intents": []})
        kws = set(trig.get("keywords", []))
        kws |= sl.token_diff(old, fm["description"], kws)
        trig["keywords"] = sorted(kws)
        changed = True
    # fold the absorbed skill's distinctive trigger words
    trig = fm.setdefault("triggers", {"keywords": [], "paths": [], "intents": []})
    kws = set(trig.get("keywords", []))
    add = sl.token_diff(alias_desc, fm.get("description", ""), kws)
    if add:
        kws |= add
        trig["keywords"] = sorted(kws)
        changed = True
    if changed and not dry:
        sl.write_skill(cdir / "SKILL.md", fm, body)


def apply_wave(wave: int, dry: bool = False) -> int:
    aliases = _load_aliases()
    palette_before = set(sl.skill_names())
    done = 0
    for w, alias, canonical, topic, mode in MERGES:
        if w != wave:
            continue
        adir = sl.SKILLS_DIR / alias
        cdir = sl.SKILLS_DIR / canonical
        fm, body, ok = sl.read_frontmatter(adir / "SKILL.md")
        if not ok:
            print(f"  SKIP {alias}: unreadable")
            continue
        if fm.get("alias_of") == canonical:
            aliases[alias] = canonical  # ensure row present
            continue
        old_desc = str(fm.get("description", ""))

        ref_path = cdir / "references" / topic
        if not dry:
            ref_path.parent.mkdir(parents=True, exist_ok=True)
            if mode == "rewrite":
                ref_path.write_text(REWRITES[alias], encoding="utf-8")
            else:
                header = (f"# {alias}\n\n> Absorbed into `{canonical}` (P5 consolidation). "
                          f"Method content preserved verbatim below.\n\n---\n\n")
                ref_path.write_text(header + body.lstrip("\n"), encoding="utf-8")

        _carry_supporting(adir, cdir, alias, dry)
        _fold_canonical(canonical, old_desc, dry)

        tfm, tbody = _thin_alias_fm(alias, canonical, topic, old_desc)
        # trigger-law proof
        leftover = sl.token_diff(old_desc, tfm["description"], tfm["triggers"]["keywords"])
        if leftover:
            print(f"  TOKEN-DIFF FAIL {alias}: {sorted(leftover)}")
            return 1
        if not dry:
            sl.write_skill(adir / "SKILL.md", tfm, tbody)
        aliases[alias] = canonical
        done += 1
        print(f"  merged {alias} -> {canonical} (references/{topic})")

    if not dry:
        _save_aliases(aliases)
    palette_after = set(sl.skill_names())
    if palette_before != palette_after:
        print(f"  PALETTE CHANGED: -{palette_before - palette_after} +{palette_after - palette_before}")
        return 1
    print(f"wave {wave}: {done} merges applied; palette stable ({len(palette_after)} names)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wave", type=int, required=True, choices=[1, 2, 3])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    rc = apply_wave(args.wave, dry=args.dry_run)
    if rc == 0 and not args.dry_run:
        import build_skills_index
        payload = build_skills_index.build()
        (sl.HOOKS_DIR / "skills-index.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"  skills-index.json: {payload['_meta']['count']} skills, "
              f"{payload['_meta']['aliases']} aliases")
    return rc


if __name__ == "__main__":
    sys.exit(main())
