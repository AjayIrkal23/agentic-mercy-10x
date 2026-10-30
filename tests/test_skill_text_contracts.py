"""Skill text agrees with the always-on rules (ECC merge, package agents-skills, 2026-10-29).

No remote-script installers, no commit/reset imperatives, no server starts, the dead helpers
stay deleted, aliases resolve, and every ECC graft is short, cited and linked."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
SKILL_MD = sorted(SKILLS.glob("*/SKILL.md"))
ALL_MD = sorted(p for p in SKILLS.glob("**/*.md") if "library" not in p.relative_to(SKILLS).parts[:1])
_FENCE = re.compile(r"^```.*?^```", re.M | re.S)
CURL_PIPE = re.compile(r"curl[^\n|`]*\|\s*(?:ba)?sh\b")
GUARD_WORDS = ("never", "do not", "don't", "without an explicit yes", "ask the user")
# prerequisites.md: upstream reference text inside a vendored skill whose prepend_body guard already
# forbids running it. areas.md: lists `curl … | sh` as a payload the dangerous-bash gate must block.
_UPSTREAM_REF_OK = {"skills/higgsfield-brandkit/references/prerequisites.md",
                    "skills/workflow-audit/references/areas.md"}
HIGGSFIELD = sorted(p.parent.name for p in SKILL_MD if p.parent.name.startswith("higgsfield-"))
VENDORED_GRAFTS = {"fixing-accessibility", "design-taste-frontend", "improve-ui", "debug-broken-ui",
                   "verify-ui-change", "false-green-tests", "find-skills", "vite-react-best-practices",
                   "design-system-compliance"}


def _rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def _texts(paths, strip_fences=False):
    for p in paths:
        t = p.read_text(encoding="utf-8")
        yield _rel(p), (_FENCE.sub("", t) if strip_fences else t)


def _violations(pattern, texts, allow=GUARD_WORDS):
    return [f"{rel}:{i}" for rel, text in texts for i, line in enumerate(text.splitlines(), 1)
            if pattern.search(line) and not any(w in line.lower() for w in allow)]


def _body(p: Path) -> str:
    t = p.read_text(encoding="utf-8")
    m = re.match(r"---\n.*?\n---\n?(.*)", t, re.S)
    return m.group(1) if m else t


def _frontmatter(p: Path) -> dict:
    m = re.match(r"---\n(.*?)\n---", p.read_text(encoding="utf-8"), re.S)
    return dict(re.findall(r"^(\w+):\s*(.+?)\s*$", m.group(1) if m else "", re.M))


def test_no_remote_script_execution():
    paths = [p for p in ALL_MD if _rel(p) not in _UPSTREAM_REF_OK]
    assert _violations(CURL_PIPE, _texts(paths)) == []


def test_no_commit_imperative_without_ask():
    commit = re.compile(r"\b(?:stage everything and commit|and commits?\b|then commit\b|commit (?:all|every|each) )", re.I)
    allow = ("when asked", "only when", "never", "user commits", "the user")
    texts = ((_rel(p), _FENCE.sub("", _body(p))) for p in SKILL_MD)
    assert _violations(commit, texts, allow) == []


def test_no_destructive_git_recovery():
    hits = [f"{rel}:{i}" for rel, text in _texts(SKILL_MD) for i, line in enumerate(text.splitlines(), 1)
            if "git reset --hard" in line and not any(w in line.lower() for w in ("never", "do not"))]
    assert hits == []


def test_no_server_or_watcher_start():
    server = re.compile(r"(?<![\w=])(--watch(?!=false)|--mcp\b|npm run dev\b|pnpm(?: run)? dev\b|yarn dev\b)")
    allow = ("user", "never", "not ", "dev:", "# ")
    assert _violations(server, _texts(SKILL_MD), allow) == []


def test_suggest_compact_is_gone():
    assert not (SKILLS / "context-engineering/references/strategic-compact").exists()
    scan = [p for p in SKILLS.rglob("*") if p.is_file()] + list((ROOT / "agents").glob("*.md"))
    scan.append(ROOT / "docs/SKILL-HARMONIZATION.md")
    hits = [_rel(p) for p in scan if "suggest-compact.sh" in p.read_text(encoding="utf-8", errors="ignore")]
    assert hits == []


def test_dead_helpers_deleted():
    # the tracked tree decides: a gitignored local leftover (lean-ctx/SKILL.md.bak) is the user's file
    import subprocess
    cp = subprocess.run(["git", "-c", "safe.directory=*", "-C", str(ROOT), "ls-files", "skills"],
                        capture_output=True, text=True)
    tracked = set(cp.stdout.split()) if cp.returncode == 0 else set()
    for rel in ("design/scripts/logo/generate.py", "design/scripts/cip/generate.py",
                "design/scripts/icon/generate.py", "plan-mode-gate/scripts", "lean-ctx/SKILL.md.bak"):
        if tracked:
            assert not any(t == f"skills/{rel}" or t.startswith(f"skills/{rel}/") for t in tracked), rel
        else:  # no git checkout: fall back to the disk
            assert not (SKILLS / rel).exists(), rel
    for rel in ("design/scripts/logo/search.py", "design/scripts/cip/search.py",
                "design/scripts/logo/core.py", "design/scripts/cip/core.py"):
        assert (SKILLS / rel).exists(), rel
    assert "scripts/plan-mode-check.js" not in (SKILLS / "plan-mode-gate/SKILL.md").read_text(encoding="utf-8")


def test_lean_ctx_is_installer_only():
    text = (SKILLS / "lean-ctx/SKILL.md").read_text(encoding="utf-8")
    assert "curl" not in text
    for line in text.splitlines():  # the setup commands may only be named inside the "never run" guard
        if "init --global" in line or "lean-ctx setup" in line:
            assert "never run" in line.lower(), line
    head = "\n".join((SKILLS / "lean-ctx/scripts/install.sh").read_text(encoding="utf-8").splitlines()[:6])
    assert "installer-only" in head and "never run from a session" in head


def test_higgsfield_skills_default_to_the_connector():
    assert len(HIGGSFIELD) == 8, HIGGSFIELD
    for name in HIGGSFIELD:
        p = SKILLS / name / "SKILL.md"
        body = _body(p)
        assert "mcp__claude_ai_higgsfield__" in body, name
        assert "CLI only when the user asks" in body, name
        assert _violations(CURL_PIPE, [(_rel(p), body)]) == [], name


def test_tech_debt_and_webapp_descriptions():
    fm = _frontmatter(SKILLS / "tech-debt-audit/SKILL.md")
    assert "does not auto-fire" not in fm["description"]
    assert "router" in fm.get("when_to_use", "")
    lines = (SKILLS / "webapp-testing/SKILL.md").read_text(encoding="utf-8").splitlines()
    assert all("user" in ln for ln in lines if "with_server.py" in ln)


def test_dox_doc_tree_defaults_match_config():
    cfg = json.loads((ROOT / "hooks/dox-tree-guard.config.json").read_text(encoding="utf-8"))
    text = (SKILLS / "dox-doc-tree/SKILL.md").read_text(encoding="utf-8")
    rows = dict(re.findall(r"^\| `(\w+)` \| `([^`]+)` \|", text, re.M))
    assert rows["documentAllDirs"] == json.dumps(cfg["documentAllDirs"]) == "false"
    assert rows["maxSweepDirs"] == str(cfg["maxSweepDirs"]) == "300"
    assert "per-repo opt-in" in text


def test_alias_map_is_consistent():
    sys.path.insert(0, str(ROOT / "hooks"))
    from lib.skill_aliases import canonical  # noqa: PLC0415
    data = json.loads((ROOT / "hooks/skill-aliases.json").read_text(encoding="utf-8"))
    aliases = {k: v for k, v in data.items() if not k.startswith("_")}
    local = {p.parent.name for p in SKILL_MD}
    for key, val in aliases.items():
        assert val in local, (key, val)
        assert key not in local, key
        assert key != val, key
        assert canonical(key) in local, key
    required = {"tdd-workflow": "test-driven-development", "e2e-testing": "webapp-testing",
                "security-review": "owasp-security", "strategic-compact": "context-engineering"}
    for key, val in required.items():
        assert aliases.get(key) == val, key


def test_grafts_are_short_cited_and_linked():
    grafts = sorted(SKILLS.glob("*/references/ecc-*.md"))
    head = re.compile(r"^<!-- ecc:[\w./ ,#-]+@25278e7d -->$")
    for g in grafts:
        lines = g.read_text(encoding="utf-8").splitlines()
        assert len(lines) <= 60, _rel(g)
        assert head.match(lines[0]), _rel(g)
        owner = g.parent.parent / "SKILL.md"
        assert f"references/{g.name}" in owner.read_text(encoding="utf-8"), _rel(g)
    for name in VENDORED_GRAFTS:
        assert "ECC graft (ecc:" in (SKILLS / name / "SKILL.md").read_text(encoding="utf-8"), name
    assert len(grafts) + len(VENDORED_GRAFTS) >= 40, len(grafts)


def test_invoke_family_shape():
    for p in SKILLS.glob("invoke-*/SKILL.md"):
        assert len(p.read_text(encoding="utf-8").splitlines()) <= 40, _rel(p)
    invoke = (SKILLS / "invoke/SKILL.md").read_text(encoding="utf-8")
    assert "workflows/invoke.js" in invoke and "## Size tiers" in invoke
    assert re.search(r"^\| XL \|", invoke, re.M)
    assert "## Optional deterministic flow" not in invoke
    santa = (SKILLS / "santa-review/SKILL.md").read_text(encoding="utf-8")
    for needle in ("workflows/review.js", "fresh reviewer", "never push"):
        assert needle in santa, needle


def test_mmx_cli_link_is_reachable():
    text = (SKILLS / "mmx-cli/SKILL.md").read_text(encoding="utf-8")
    assert "mmx-h3-video skill" not in text
    assert "h3-video/SKILL.md" in text and "not a registered skill" in text
