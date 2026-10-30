"""vendor_library.py (copy, sanitise, header, self-validate) and build_library_index.py (INDEX.json, --check)."""
from __future__ import annotations

import filecmp
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


VL = _load("vendor_library")
BI = _load("build_library_index")

_DEFENSE = "## Prompt Defense Baseline\n\n" + "".join(f"- rule {i}\n" for i in range(6)) + "\n"
_FENCE = "`" * 3


def _w(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


def _git(src: Path, *args: str) -> str:
    cmd = ["git", "-C", str(src), "-c", "user.name=t", "-c", "user.email=t@example.com",
           "-c", "commit.gpgsign=false", *args]
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip()


def _fake_ecc(tmp: Path) -> tuple[Path, str, dict]:
    src = tmp / "ecc-src"
    home = "/" + "home/alice/x"
    _w(src / "skills/alpha/SKILL.md",
       "---\nname: alpha\ndescription: Alpha clickhouse mergetree tuning for analytics tables.\n---\n\n"
       + _DEFENSE + "# Alpha\n\nState lives in ~/.claude/homunculus/instincts here.\n"
       + f"Project at {home} is personal.\n\nthe git commit message should be short.\n\n"
       + _FENCE + "bash\ngit commit -m \"x\"\nnpm run dev\n" + _FENCE + "\n")
    _w(src / "skills/alpha/references/r.md", "# Ref\n\nreference text\n")
    _w(src / "skills/alpha/scripts/run.py", "print('x')\n")
    _w(src / "skills/beta/SKILL.md", "---\nname: beta\ndescription: Beta osint notes for public records.\n---\n# Beta\n")
    _w(src / "rules/zed/coding-style.md", "---\npaths:\n  - \"**/*.zed\"\n---\n# Zed style\n\nshort lines\n")
    _w(src / "rules/zed/patterns.md", "# Zed patterns\n\nuse traits\n")
    _w(src / "rules/README.md", "# Rules\n\nhow packs work\n")
    _w(src / "agents/zed-reviewer.md",
       "---\nname: zed-reviewer\ndescription: Reviews zed code.\ntools: Read, Grep\nmodel: sonnet\n---\n\n"
       + _DEFENSE + "You review zed code.\n")
    _w(src / "commands/zed-build.md",
       "---\ndescription: Build zed\n---\n# Zed build\n\n" + _FENCE + "\ngo build -race ./...\n" + _FENCE + "\n")
    _w(src / "README.md", "# ECC\n\n## Install ECC\n\nnpm install\n\n## Guides\n\nread the guides\n")
    _w(src / "TROUBLESHOOTING.md", "# Troubleshooting\n\n## Hooks\n\nfix hooks\n")
    _w(src / "docs/TROUBLESHOOTING.md", "# More\n\ntext\n")
    _w(src / "docs/fixes/HOOK-FIX.md", "# Hook fix\n\nfixed\n")
    _w(src / "docs/fixes/apply.sh", "echo fix\n")
    _w(src / "docs/hook-bug-workarounds.md", "# Workarounds\n\nnone\n")
    _w(src / "examples/CLAUDE.md", "# Example CLAUDE.md\n\nexample\n")
    _w(src / "examples/proto/a.py", "print(1)\n")
    _w(src / "examples/proto/README.md", "# Proto\n\nprototype\n")
    _w(src / "manifests/context-packs/skill-triggers@1.json",
       json.dumps({"triggers": {"skill:alpha": ["ClickHouse Tuning"]}}))
    _w(src / "docs/COMMAND-REGISTRY.json",
       json.dumps({"commands": [{"command": "zed-build", "description": "Build a zed project", "type": "build",
                                 "path": "commands/zed-build.md"}]}))
    subprocess.run(["git", "init", "-q", str(src)], check=True)
    _git(src, "add", "-A")
    _git(src, "commit", "-q", "-m", "fake")
    sha = _git(src, "rev-parse", "HEAD")
    cfg = {"upstream": {"repo": "https://example.com/ecc", "sha": sha}, "skills": ["alpha", "beta"],
           "skills_keep_references": ["alpha"], "skills_extra_md_dirs": [],
           "skills_code_not_vendored": ["skills/alpha/scripts/run.py"], "rules": ["zed"],
           "rules_readme": "rules/README.md", "agents": ["zed-reviewer.md"], "commands": ["zed-build.md"],
           "examples": ["examples/CLAUDE.md", "examples/proto"], "guides": {"README.md": {"strip_h2": ["Install ECC"]}},
           "troubleshooting": ["TROUBLESHOOTING.md", "docs/TROUBLESHOOTING.md", "docs/fixes",
                               "docs/hook-bug-workarounds.md"],
           "digests": {"demo": ["scripts/demo.js"]}, "index_merge": [], "adopt_into_validate_imports": [],
           "licences": {"skills/beta": "CC-BY-SA-4.0"}}
    return src, sha, cfg


@pytest.fixture
def vendored(tmp_path):
    src, sha, cfg = _fake_ecc(tmp_path)
    root = tmp_path / "repo"
    out = root / "library" / "ecc"
    assert VL.vendor(src, sha, out, cfg) == 0
    return src, sha, cfg, root, out


def _files(base: Path) -> set[str]:
    return {p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()}


# ---------------------------------------------------------------- vendor

def test_vendor_copies_only_prose_and_keeps_layout(vendored):
    _, sha, _, _, out = vendored
    files = _files(out)
    for rel in ("skills/alpha/SKILL.md", "skills/alpha/references/r.md", "rules/zed/coding-style.md",
                "rules/README.md", "agents/zed-reviewer.md", "commands/zed-build.md", "guides/README.md",
                "docs/troubleshooting.md", "examples/CLAUDE.md", "examples/proto/README.md", "UPSTREAM.json",
                "VENDOR.json", "catalogue.json"):
        assert rel in files, rel
    assert "skills/alpha/scripts/run.py" not in files and "examples/proto/a.py" not in files
    up = json.loads((out / "UPSTREAM.json").read_text(encoding="utf-8"))
    assert up["sha"] == sha
    assert up["files"] == len(files - {"UPSTREAM.json", "VENDOR.json", "catalogue.json"})
    trouble = (out / "docs/troubleshooting.md").read_text(encoding="utf-8")
    assert "## Source: docs/fixes" in trouble and "Scripts not vendored: docs/fixes/apply.sh" in trouble
    assert "### Hooks" in trouble


def test_vendor_catalogue_from_registry_and_context_packs(vendored):
    """catalogue.json makes build_library_index --check reproducible without the ECC checkout."""
    out = vendored[4]
    cat = json.loads((out / "catalogue.json").read_text(encoding="utf-8"))
    assert cat["command_titles"] == {"zed-build": "Build a zed project"}
    assert cat["skill_triggers"] == {"alpha": ["clickhouse tuning"]}


def test_vendor_sanitizer_rules(vendored):
    _, sha, _, _, out = vendored
    skill = (out / "skills/alpha/SKILL.md").read_text(encoding="utf-8")
    assert "Prompt Defense Baseline" not in skill and "# Alpha" in skill
    assert "<learning-state-dir>/instincts" in skill and "homunculus" not in skill
    assert "~/x is personal" in skill and "/" + "home/" not in skill
    lines = skill.split("\n")
    close = lines.index("---", 1)
    assert lines[close + 1] == f"<!-- ecc:skills/alpha/SKILL.md@{sha} -->"
    i = lines.index('git commit -m "x"')
    assert lines[i - 1] == "<!-- ecc-conflict: commit -->"
    assert lines[lines.index("npm run dev") - 1] == "<!-- ecc-conflict: server -->"
    j = lines.index("the git commit message should be short.")
    assert not lines[j - 1].startswith("<!-- ecc-conflict")
    agent = (out / "agents/zed-reviewer.md").read_text(encoding="utf-8")
    assert "model:" not in agent and "name: zed-reviewer" in agent and "tools: Read, Grep" in agent
    assert "Prompt Defense" not in agent
    cmd = (out / "commands/zed-build.md").read_text(encoding="utf-8").split("\n")
    assert cmd[cmd.index("go build -race ./...") - 1] == "<!-- ecc-conflict: race -->"
    readme = (out / "guides/README.md").read_text(encoding="utf-8")
    assert readme.split("\n")[0] == f"<!-- ecc:README.md@{sha} -->"
    assert "## Install ECC" not in readme and "npm install" not in readme and "## Guides" in readme


def test_vendor_is_deterministic(tmp_path):
    src, sha, cfg = _fake_ecc(tmp_path)
    a, b = tmp_path / "a" / "ecc", tmp_path / "b" / "ecc"
    assert VL.vendor(src, sha, a, cfg) == 0 and VL.vendor(src, sha, b, cfg) == 0
    assert _files(a) == _files(b)
    for rel in _files(a):
        da, db = (a / rel).read_bytes(), (b / rel).read_bytes()
        assert da == db, rel
        assert b"\r\n" not in da
    assert not filecmp.dircmp(a, b).diff_files


def test_vendor_refuses_when_validation_fails(vendored, capsys):
    src, sha, cfg, _, out = vendored
    before = {rel: (out / rel).read_bytes() for rel in _files(out)}
    p = src / "skills/alpha/SKILL.md"
    p.write_text(p.read_text(encoding="utf-8") + "bidi ‮ here\n", encoding="utf-8")
    assert VL.vendor(src, sha, out, cfg) == 1
    assert "unicode-202e" in capsys.readouterr().out
    assert {rel: (out / rel).read_bytes() for rel in _files(out)} == before
    assert not out.with_name(out.name + ".tmp").exists()


def test_vendor_refuses_a_drifted_checkout(tmp_path):
    src, _, cfg = _fake_ecc(tmp_path)
    assert VL.vendor(src, "0" * 40, tmp_path / "o" / "ecc", cfg) == 2


def test_vendor_header_licence_line(vendored):
    out = vendored[4]
    lines = (out / "skills/beta/SKILL.md").read_text(encoding="utf-8").split("\n")
    i = next(n for n, line in enumerate(lines) if line.startswith("<!-- ecc:"))
    assert lines[i + 1] == "<!-- licence: CC-BY-SA-4.0 (upstream) -->"


def test_vendor_keeps_hand_written_digests(vendored):
    src, sha, cfg, _, out = vendored
    _w(out / "digests/demo.md", "# Demo\n")
    assert VL.vendor(src, sha, out, cfg) == 0
    assert (out / "digests/demo.md").read_text(encoding="utf-8") == "# Demo\n"


# ---------------------------------------------------------------- index

def _digest(out: Path, sha: str, topic: str, desc: str) -> None:
    _w(out / "digests" / f"{topic}.md",
       f"---\nname: ecc-digest-{topic}\ndescription: {desc}\n---\n<!-- ecc-digest:{topic}@{sha} -->\n"
       f"# {topic.title()}\n\n## What it is\n\ntext\n\n## Upstream paths\n- `scripts/demo.js`\n")


@pytest.fixture
def indexed(vendored):
    src, sha, cfg, root, out = vendored
    _digest(out, sha, "demo", "Demo digest about plan canvas annotations.")
    _digest(out, sha, "other", "Other digest about session stores.")
    assert BI.main(["--root", str(root)]) == 0
    data = json.loads((root / "library" / "INDEX.json").read_text(encoding="utf-8"))
    return root, sha, data, {e["id"]: e for e in data["entries"]}


def test_entry_shape_and_sort(indexed):
    root, _, data, by_id = indexed
    ids = [e["id"] for e in data["entries"]]
    assert ids == sorted(ids) and data["count"] == len(ids) and data["schema"] == 1
    for e in data["entries"]:
        assert set(e) == {"id", "path", "kind", "title", "triggers", "surfaces", "stacks", "token_estimate",
                          "conflicts", "upstream"}
        assert e["kind"] in {"rules-pack", "agent", "skill", "command", "digest", "guide", "doc", "example"}
        assert (root / e["path"]).exists() and "\\" not in e["path"]
    assert {"skill:alpha", "skill:beta", "agent:zed-reviewer", "command:zed-build", "digest:demo", "guide:README",
            "doc:troubleshooting", "example:CLAUDE", "example:proto-README", "rules:zed"} <= set(by_id)


def test_rules_pack_entry(indexed):
    root, _, _, by_id = indexed
    e = by_id["rules:zed"]
    assert e["path"] == "library/ecc/rules/zed/" and e["stacks"] == ["zed"] and e["kind"] == "rules-pack"
    assert e["triggers"] == [] and e["title"] == "zed rules pack (2 files)"
    pack = root / "library/ecc/rules/zed"
    assert e["token_estimate"] == sum(len(p.read_text(encoding="utf-8")) // 4 for p in pack.glob("*.md"))
    assert "rules:README" not in by_id


def test_reviewer_agent_entry_has_stack(indexed):
    e = indexed[3]["agent:zed-reviewer"]
    assert e["stacks"] == ["zed"] and e["surfaces"] == ["review"]


def test_skill_triggers_from_description_and_context_pack(indexed):
    e = indexed[3]["skill:alpha"]
    assert {"clickhouse", "mergetree", "analytics", "clickhouse tuning"} <= set(e["triggers"])
    assert e["conflicts"] == ["commit", "server"]
    assert indexed[3]["command:zed-build"]["title"] == "Build a zed project"
    assert indexed[3]["command:zed-build"]["conflicts"] == ["race"]
    assert indexed[3]["skill:alpha"]["upstream"]["extras"] == ["skills/alpha/scripts/run.py"]


def test_check_detects_drift_and_writes_nothing(indexed):
    root = indexed[0]
    idx = root / "library" / "INDEX.json"
    assert BI.main(["--root", str(root), "--check"]) == 0
    idx.write_bytes(idx.read_bytes() + b" ")
    before = idx.read_bytes()
    assert BI.main(["--root", str(root), "--check"]) == 1
    assert idx.read_bytes() == before
    idx.unlink()
    assert BI.main(["--root", str(root), "--check"]) == 1


def test_check_fails_when_library_missing(tmp_path, capsys):
    assert BI.main(["--root", str(tmp_path), "--check"]) == 1
    assert "library/ecc missing" in capsys.readouterr().out


def test_no_harness_loaded_paths_and_no_home_strings(indexed):
    root, sha, data, _ = indexed
    text = (root / "library" / "INDEX.json").read_text(encoding="utf-8")
    assert "/" + "home/" not in text
    assert data["upstream"]["sha"] == sha
    for e in data["entries"]:
        assert not e["path"].startswith(("skills/", "rules/", "agents/", "commands/"))
        assert e["upstream"]["sha"] == sha


def test_token_estimate_is_chars_div_4(indexed):
    root, _, _, by_id = indexed
    e = by_id["skill:alpha"]
    assert e["token_estimate"] == len((root / e["path"]).read_text(encoding="utf-8")) // 4


def test_live_index_is_in_sync():
    if not (_ROOT / "library" / "INDEX.json").exists():
        pytest.skip("library/INDEX.json not built")
    assert BI.main(["--check"]) == 0


def _routes_on_real_index(tmp_path, monkeypatch):
    import sys
    hooks = str(_ROOT / "hooks")
    if hooks not in sys.path:
        sys.path.insert(0, hooks)
    from prompt_router.classify import TaskProfile
    from prompt_router.modules import library_routes as L
    monkeypatch.setattr(L, "_INDEX_PATH", _ROOT / "library" / "INDEX.json")
    monkeypatch.setattr(L, "_cache_path", lambda: tmp_path / "cache.json")
    L._load.cache_clear()
    L._MATCHERS.clear()
    return L, TaskProfile


def test_real_index_does_not_route_generic_prompts(tmp_path, monkeypatch):
    """Description words ("server", "auth", "caching") alone never route; named stacks/skills still do."""
    if not (_ROOT / "library" / "INDEX.json").exists():
        pytest.skip("library/INDEX.json not built")
    L, TaskProfile = _routes_on_real_index(tmp_path, monkeypatch)
    try:
        for p in ["review my code for security issues", "add an endpoint to the express server with auth",
                  "write unit tests with mocking", "optimize the slow sql query",
                  "design an api with rate limiting and caching", "migrate the database schema",
                  "fix the failing build", "add a login form", "update the readme", "add a cache layer to the api",
                  "secure the login endpoint", "add websocket support to the server"]:
            prof = TaskProfile(text=p, intents={"REVIEW": 1} if "review" in p else {})
            assert L.items(prof, str(_ROOT), set()) == [], p
        for p, want in [("implement the kotlin ktor server auth plugin", "library:skill:kotlin-ktor-patterns"),
                        ("write rust unit tests with mocking", "library:skill:rust-testing"),
                        ("redis caching for the rate limiter", "library:skill:redis-patterns")]:
            assert [o["id"] for o in L.items(TaskProfile(text=p), str(_ROOT), set())] == [want], p
    finally:
        L._load.cache_clear()
        L._MATCHERS.clear()
