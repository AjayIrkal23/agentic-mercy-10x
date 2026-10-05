"""Skills catalog references, counts, listing size and skill-text contracts (audit
2026-10-05 WP2: D-09, D-10, D-11, D-12, D-13, D-14, D-15, F-05). Split from
test_skills_wp2.py to keep both files under 250 lines; the shared helpers live there.
"""
from __future__ import annotations

import json
import re

import pytest

from test_skills_wp2 import GENERIC, LOCKED, ROOT, SKILLS, _fm, _keywords, sl

# --------------------------------------------------------------------------- D-09
# Names that resolve to nothing on this workbench: uninstalled plugins and skills that
# were never created. A mention is stale whether it is a link or prose.
STALE_NAMES = ["claude-mermaid", "build-web-apps", "Build Web Apps", "frontend-standards-always-follow:",
               "assets-organizing", "project-management", "frontend-design-gate", "backend-patterns",
               "clickhouse-io", "database-reviewer", "deepvue-docs", "find-docs",
               "agent-skills-orchestrator", "clickhouse:clickhouse-best-practices", "gsd-execute-phase",
               "workflow-overlay-optimizer", "skill-routing-matrix", "tdd-workflow", "refactoring-patterns",
               "deployment-patterns", "jpa-patterns", "springboot-patterns", "django-patterns",
               "jcodemunch-code-finder", "repo-memory-sync", "continuous-learning", "strategic-compact",
               "figma-implementation", "vercel-ai-architect", "domain-scaffold-patterns",
               "codebase-start-point-guide`", "pip install google-genai"]
# "Removed — do not re-add" inventories legitimately name retired servers.
_STALE_OK = {("skills/mcp-usage-standards/SKILL.md", "claude-mermaid"),
             ("skills/mcp-usage-standards/references/mcp-inventory.md", "claude-mermaid")}
_MD_LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")
_RULE_REF = re.compile(r"rules/([\w.-]+\.md)")
_RULE_OK = {"area-description.md"}  # composition-patterns: "copy _template.md to rules/<area>-<desc>.md"
_FENCE = re.compile(r"^```.*?^```", re.M | re.S)


def _owned_texts():
    """(path, text) for every markdown/python file under skills/ that WP2 may edit."""
    for d in sl.skill_dirs():
        if d.name in LOCKED or d.name.startswith("invoke"):
            continue
        for f in sorted(d.rglob("*")):
            if f.suffix in (".md", ".py") and f.is_file():
                yield f, f.read_text(encoding="utf-8", errors="replace")
    for r in ("frontend", "backend"):
        f = ROOT / "rules" / f"{r}.md"
        yield f, f.read_text(encoding="utf-8")


def test_skills_name_no_uninstalled_plugins_or_missing_skills():
    hits = []
    for f, t in _owned_texts():
        if f.suffix != ".md":  # legacy scripts under skills/design exit before their imports
            continue
        if t.startswith("# ") and "Absorbed into" in t[:300]:  # absorbed file keeps its old title
            t = t.split("\n", 1)[1]
        hits += [f"{f.relative_to(ROOT)}: {n}" for n in STALE_NAMES
                 if n in t and (str(f.relative_to(ROOT)), n) not in _STALE_OK]
    assert not hits, hits


def test_rules_files_named_by_skills_exist():
    missing = [f"{f.relative_to(ROOT)}: rules/{m}" for f, t in _owned_texts()
               for m in _RULE_REF.findall(t)
               if m not in _RULE_OK and not (ROOT / "rules" / m).exists()
               and not any((p / "rules" / m).exists() for p in f.parents if SKILLS in p.parents)]
    assert not missing, missing


def test_relative_markdown_links_resolve():
    broken = []
    for f, t in _owned_texts():
        if f.suffix != ".md" or "template" in f.name:  # templates carry placeholder links
            continue
        for target in _MD_LINK.findall(_FENCE.sub("", t)):  # fenced blocks are examples
            if re.match(r"^[a-z]+:", target) or target.startswith(("/", "~", "$")):
                continue
            if not (f.parent / target).exists():
                broken.append(f"{f.relative_to(ROOT)} -> {target}")
    assert not broken, broken


# --------------------------------------------------------------------------- D-12
def test_router_push_cap_in_skill_docs_matches_config():
    cfg = json.loads((ROOT / "hooks/prompt_router/router.config.json").read_text(encoding="utf-8"))
    cap = cfg["max_skill_pushes"]
    wrong = [f"{f.relative_to(ROOT)}: ≤{n}" for f, t in _owned_texts()
             for n in re.findall(r"(?:rank|router\.py`?) \(?≤(\d+) skills", t) if int(n) != cap]
    assert not wrong, f"router pushes at most {cap} skills: {wrong}"


# --------------------------------------------------------------------------- D-15
MEDIA = ["higgsfield-generate", "higgsfield-marketplace-cards", "higgsfield-product-photoshoot",
         "higgsfield-soul-id", "higgsfield-websites", "higgsfield-brandkit", "higgsfield-video-explainer",
         "higgsfield-youtube-thumbnail", "kokonutui"]


@pytest.mark.parametrize("name", MEDIA)
def test_media_skill_listing_entry_is_short_but_still_routable(name):
    fm, _ = _fm(name)
    assert "disable-model-invocation" not in fm, "must stay model-invocable (rules/frontend.md Assets)"
    entry = len(str(fm.get("description", ""))) + len(str(fm.get("when_to_use", "")))
    assert entry <= 420, f"{name}: {entry} listing chars"
    kws = _keywords(fm)
    assert 3 <= len(kws) <= 20 and not [k for k in kws if k.lower() in GENERIC], kws


# --------------------------------------------------------------------------- D-11
def test_no_skill_is_both_hidden_and_path_scoped():
    both = [d.name for d in sl.skill_dirs()
            if (lambda fm: fm.get("disable-model-invocation") and fm.get("paths"))(_fm(d.name)[0])]
    assert not both, f"hidden + paths = unloadable: {both}"


# --------------------------------------------------------------------------- D-10 / D-13 / F-05
def test_backend_baseline_loads_companions_lazily():
    body = _fm("backend-standards-always-follow")[1]
    assert not re.search(r"MUST\s+immediately|load ALL now", body)


def test_verification_loop_uses_repo_commands_and_semgrep():
    body = _fm("verification-loop")[1]
    assert "80%" not in body
    assert not re.search(r'grep -rn "(sk-|api_key|console\.log)', body)
    assert "semgrep" in body


def test_dead_code_audit_reports_preexisting_instead_of_deleting():
    body = _fm("dead-code-and-change-audit")[1]
    assert "DELETE UNUSED CODE" not in body
    assert "every coding task" not in body.lower()
    assert "pre-existing dead code is reported" in body.lower()


# --------------------------------------------------------------------------- D-14
def test_workflow_audit_body_is_lean_and_user_only():
    fm, body = _fm("workflow-audit")
    assert fm.get("disable-model-invocation") is True
    assert len(body) <= 16000, f"{len(body)} chars; move tables to references/"
