#!/usr/bin/env python3
"""gen-agent-skill-blocks.py — render / check the `skills:` frontmatter of every agent.

AGENT_SKILLS below is the single source of truth for what each agent preloads
(WP-7 frontmatter table, 2026-09-27). Every name is collapsed through the alias map
(hooks/lib/skill_aliases.py when present, else hooks/skill-aliases.json) and capped at
MAX_SKILLS, so no agent can preload an alias stub or an over-long list.

  python3 gen-agent-skill-blocks.py          # rewrite `skills:` in agents/*.md
  python3 gen-agent-skill-blocks.py --check  # exit 1 if any agent differs or is missing

--check covers every agent in AGENT_SKILLS — there is no "no markers, skipped" path.
Both modes also print non-fatal `drift:` lines for preloaded skills the routing sources
do not know (FRONTEND/BACKEND_SKILLS in fullstack-skills-reminder.py and
categories.<CAT>.local_skills in autonomous-skill-router.config.json) and `missing:`
lines for local skills with no SKILL.md yet, so table and routing config are
reconciled deliberately rather than drifting silently.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

HOOKS = Path(__file__).resolve().parent
ROOT = HOOKS.parent
AGENTS = ROOT / "agents"
MAX_SKILLS = 13

# agent -> preloaded skills (canonical names; plugin skills as plugin:skill).
AGENT_SKILLS: dict[str, list[str]] = {
    "backend-implementor-specialist": [
        "backend-standards-always-follow", "backend-api-standards", "api-contract-standards",
        "service-layer-standards", "backend-error-handling", "scaffold-standards",
        "golang-patterns", "golang-testing", "postgres-patterns", "owasp-security",
        "test-driven-development", "dead-code-and-change-audit", "codebase-intel-first",
    ],
    "frontend-implementor-specialist": [
        "frontend-standards-always-follow", "frontend-structure-standards",
        "frontend-response-handling", "frontend-server-data-patterns", "react-hooks-patterns",
        "tailwind-design-system", "shadcn", "motion-dev", "design-taste-frontend",
        "higgsfield-generate", "webapp-testing", "dead-code-and-change-audit",
        "codebase-intel-first",
    ],
    "integrator-specialist": [
        "api-contract-standards", "webapp-testing", "verification-loop", "codebase-intel-first",
    ],
    "implementation-engineer": [
        "codebase-intel-first", "architect-system-design", "test-driven-development",
        "source-driven-development", "doubt-driven-development", "dead-code-and-change-audit",
        "verification-loop", "code-execution-standard",
    ],
    "frontend-uiux-designer": [
        "design-taste-frontend", "frontend-design:frontend-design", "frontend-ui-engineering",
        "motion-dev", "animejs-motion", "tailwind-design-system", "shadcn",
        "higgsfield-generate", "webapp-testing",
    ],
    "santa-reviewer": ["santa-review", "code-review-and-quality"],
    "security-sentinel": ["owasp-security", "verification-loop"],
    "qa-verifier": ["verification-loop", "webapp-testing"],
    "audit-specialist": ["tech-debt-audit", "codebase-intel-first", "dead-code-and-change-audit"],
    "planning-director": [
        "planning-and-task-breakdown", "superpowers:writing-plans", "architect-system-design",
        "codebase-intel-first",
    ],
    "spec-architect": ["spec-driven-development", "api-contract-standards", "architect-system-design"],
    "debug-detective": [
        "debug-investigation", "doubt-driven-development", "superpowers:systematic-debugging",
        "codebase-intel-first",
    ],
    "deadcode-reaper": ["dead-code-and-change-audit", "codebase-intel-first", "fix-lint-format"],
    "docs-sync-agent": ["update-docs", "dox-doc-tree"],
    "refactor-specialist": [
        "code-simplification", "codebase-design", "test-driven-development", "codebase-intel-first",
    ],
    "test-author": ["test-driven-development", "golang-testing", "webapp-testing"],
    "memory-codex": [],
    "team-lead": ["invoke", "api-contract-standards"],
}

FM_RE = re.compile(r"\A---\n(.*?)\n---\n", re.S)
SKILLS_BLOCK = re.compile(r"^skills:[^\n]*\n(?:[ \t]+-[^\n]*\n)*", re.M)


def _canon():
    """Alias resolver: WP-3's lib.skill_aliases when importable, else the JSON map."""
    sys.path.insert(0, str(HOOKS))
    try:
        from lib import skill_aliases as sa  # type: ignore
        fn = next((getattr(sa, n) for n in ("canonical", "resolve", "to_canonical")
                   if callable(getattr(sa, n, None))), None)
        if fn:
            return fn
    except Exception:
        pass
    try:
        m = json.loads((HOOKS / "skill-aliases.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        m = {}
    m = {k: v for k, v in m.items() if not k.startswith("_")}
    return lambda s: m.get(s, s)


def _collapse(skills: list[str], canon) -> list[str]:
    out: list[str] = []
    for s in skills:
        c = canon(s)
        if c not in out:
            out.append(c)
    return out


def _sources(canon) -> set[str]:
    """Union of the routing sources, alias-collapsed (drift reference only)."""
    names: list[str] = []
    try:
        src = (HOOKS / "fullstack-skills-reminder.py").read_text(encoding="utf-8")
        for var in ("FRONTEND_SKILLS", "BACKEND_SKILLS"):
            m = re.search(rf"{var}\s*(?::[^=]*)?=\s*\[(.*?)\]", src, re.S)
            names += re.findall(r'"([\w:-]+)"', m.group(1)) if m else []
    except OSError:
        pass
    try:
        cfg = json.loads((HOOKS / "autonomous-skill-router.config.json").read_text(encoding="utf-8"))
        for cat in cfg.get("categories", {}).values():
            names += cat.get("local_skills") or []
    except (OSError, json.JSONDecodeError):
        pass
    return set(_collapse(names, canon))


def _current(parsed: dict) -> list[str]:
    v = parsed.get("skills")
    if v is None:
        return []
    if isinstance(v, str):
        return [s.strip() for s in v.split(",") if s.strip()]
    return [str(s) for s in v]


def _render(skills: list[str]) -> str:
    return f"skills: [{', '.join(skills)}]\n"


def _apply(text: str, m: re.Match, skills: list[str]) -> str:
    fm = m.group(1) + "\n"
    line = _render(skills) if skills else ""
    if SKILLS_BLOCK.search(fm):
        fm = SKILLS_BLOCK.sub(lambda _: line, fm, count=1)
    elif line:
        cm = re.search(r"^color:", fm, re.M)  # keep color last, like every agent file
        fm = fm[:cm.start()] + line + fm[cm.start():] if cm else fm + line
    return "---\n" + fm + "---\n" + text[m.end():]


def main(argv: list[str]) -> int:
    check = "--check" in argv
    canon = _canon()
    universe = _sources(canon)
    stale: list[str] = []
    written: list[str] = []
    for agent, raw in AGENT_SKILLS.items():
        skills = _collapse(raw, canon)[:MAX_SKILLS]
        p = AGENTS / f"{agent}.md"
        if not p.is_file():
            stale.append(f"{agent}: file missing")
            continue
        text = p.read_text(encoding="utf-8")
        m = FM_RE.match(text)
        if not m:
            stale.append(f"{agent}: no frontmatter")
            continue
        parsed = yaml.safe_load(m.group(1)) or {}
        drift = [s for s in skills if s not in universe]
        if drift:
            print(f"drift: {agent}: {', '.join(drift)} (not in routing sources)")
        miss = [s for s in skills if ":" not in s and not (ROOT / "skills" / s / "SKILL.md").is_file()]
        if miss:
            print(f"missing: {agent}: {', '.join(miss)} (no skills/<name>/SKILL.md yet)")
        cur = _current(parsed)
        if cur == skills:
            continue
        if check:
            stale.append(f"{agent}: has {cur or 'none'}, want {skills or 'none'}")
        else:
            p.write_text(_apply(text, m, skills), encoding="utf-8")
            written.append(agent)
    if check:
        if stale:
            print("agent-skills: STALE\n  " + "\n  ".join(stale))
            return 1
        print(f"agent-skills: all {len(AGENT_SKILLS)} agents in sync")
        return 0
    print(f"agent-skills: rewrote {len(written)} ({', '.join(written) or 'none'}); "
          f"{len(AGENT_SKILLS)} agents covered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
