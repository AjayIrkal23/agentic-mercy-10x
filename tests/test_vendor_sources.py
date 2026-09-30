"""WP-9: vendored-git skills match hooks/skills-sources.json and pass R10."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import skills_lib as sl  # noqa: E402

SOURCES = sl.vendored_sources()
PROV = json.loads((ROOT / "hooks" / "skills-provenance.json").read_text(encoding="utf-8"))


def test_every_source_vendored_at_pinned_ref():
    assert SOURCES
    for name, e in SOURCES.items():
        d = ROOT / "skills" / name
        assert (d / "SKILL.md").is_file(), name
        mk = json.loads((d / ".vendored.json").read_text(encoding="utf-8"))
        assert mk["ref"] == e["ref"], name
        assert mk["repo"] == e["repo"], name


def test_no_symlinks_under_skills():
    assert [p for p in (ROOT / "skills").rglob("*") if p.is_symlink()] == []


def test_override_paths_are_string_lists():
    for name, e in SOURCES.items():
        ov = e.get("frontmatter_overrides") or {}
        for paths in (ov.get("paths"), ((ov.get("metadata") or {}).get("triggers") or {}).get("paths")):
            if paths is not None:
                assert isinstance(paths, list) and all(isinstance(p, str) and p for p in paths), name


def test_r10_clean_and_complete():
    reg = {k: v for k, v in PROV.items() if not k.startswith("_")}
    assert set(reg) == set(SOURCES)
    assert all(v["family"] == "vendored-git" for v in reg.values())
    assert [r for r in sl.r10_check(reg) if r[1] != "OK"] == []


def test_server_guards_applied():
    img = (ROOT / "skills" / "img2threejs" / "SKILL.md").read_text(encoding="utf-8")
    assert "never start a dev or preview server yourself" in img
    ui = (ROOT / "skills" / "verify-ui-change" / "SKILL.md").read_text(encoding="utf-8")
    assert "in the background yourself" not in ui
    assert "npx @reticlehq/server@latest init" not in ui
