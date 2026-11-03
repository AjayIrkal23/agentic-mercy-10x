"""FIX-r2 I2: re-vendoring an unchanged sha keeps the marker's vendored_at (no daily git churn)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import vendor_skill as vs  # noqa: E402

SHA = "a" * 40


def _box(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    (src / "SKILL.md").write_text("---\nname: x\n---\nbody\n", encoding="utf-8")
    skills = tmp_path / "skills"
    skills.mkdir()
    monkeypatch.setattr(vs.sl, "SKILLS_DIR", skills)
    monkeypatch.setattr(vs, "fetch", lambda repo, ref: (src, SHA))
    return skills


def test_same_sha_keeps_the_old_stamp(tmp_path, monkeypatch):
    skills = _box(tmp_path, monkeypatch)
    (skills / "x").mkdir()
    (skills / "x" / vs.MARKER).write_text(json.dumps({"repo": "r", "ref": SHA, "sha": SHA,
                                                      "vendored_at": "2026-01-01"}), encoding="utf-8")
    vs.vendor("x", {"repo": "r", "ref": SHA})
    assert json.loads((skills / "x" / vs.MARKER).read_text(encoding="utf-8"))["vendored_at"] == "2026-01-01"


def _mtimes(d: Path) -> dict:
    return {p.relative_to(d).as_posix(): p.stat().st_mtime_ns for p in sorted(d.rglob("*"))}


def test_unchanged_bytes_keep_every_mtime(tmp_path, monkeypatch):
    """FIX-r3 I12: a re-vendor with identical bytes leaves the tree (and the marker) untouched."""
    import os
    skills = _box(tmp_path, monkeypatch)
    (tmp_path / "src" / "ref").mkdir()
    (tmp_path / "src" / "ref" / "a.md").write_text("a\n", encoding="utf-8")
    vs.vendor("x", {"repo": "r", "ref": SHA})
    for p in (skills / "x").rglob("*"):  # age every path so a rewrite would show
        os.utime(p, ns=(1_000_000_000, 1_000_000_000))
    os.utime(skills / "x", ns=(1_000_000_000, 1_000_000_000))
    os.utime(skills, ns=(1_000_000_000, 1_000_000_000))
    before = _mtimes(skills / "x")
    vs.vendor("x", {"repo": "r", "ref": SHA})
    assert _mtimes(skills / "x") == before and skills.stat().st_mtime_ns == 1_000_000_000
    assert sorted(p.name for p in skills.iterdir()) == ["x"]                    # no staging litter
    assert not list((tmp_path / ".cache" / "vendor-staging").iterdir())


def test_changed_upstream_byte_replaces_the_tree(tmp_path, monkeypatch):
    skills = _box(tmp_path, monkeypatch)
    vs.vendor("x", {"repo": "r", "ref": SHA})
    (skills / "x" / "stale.md").write_text("gone after the swap\n", encoding="utf-8")
    (tmp_path / "src" / "SKILL.md").write_text("---\nname: x\n---\nbody v2\n", encoding="utf-8")
    monkeypatch.setattr(vs, "fetch", lambda repo, ref: (tmp_path / "src", "c" * 40))
    vs.vendor("x", {"repo": "r", "ref": "c" * 40})
    assert "body v2" in (skills / "x" / "SKILL.md").read_text(encoding="utf-8")
    assert not (skills / "x" / "stale.md").exists()
    assert json.loads((skills / "x" / vs.MARKER).read_text(encoding="utf-8"))["sha"] == "c" * 40
    assert sorted(p.name for p in skills.iterdir()) == ["x"]


def test_new_sha_gets_todays_stamp(tmp_path, monkeypatch):
    skills = _box(tmp_path, monkeypatch)
    (skills / "x").mkdir()
    (skills / "x" / vs.MARKER).write_text(json.dumps({"sha": "b" * 40, "vendored_at": "2026-01-01"}),
                                          encoding="utf-8")
    vs.vendor("x", {"repo": "r", "ref": SHA})
    assert json.loads((skills / "x" / vs.MARKER).read_text(encoding="utf-8"))["vendored_at"] != "2026-01-01"


# --- SP-7: a moved tag is never taken silently --------------------------------------------------------------
def test_a_moved_tag_raises_and_leaves_the_tree(tmp_path, monkeypatch):
    skills = _box(tmp_path, monkeypatch)
    (skills / "x").mkdir()
    marker = {"repo": "r", "ref": "v3.3.0", "sha": "b" * 40, "vendored_at": "2026-01-01"}
    (skills / "x" / vs.MARKER).write_text(json.dumps(marker), encoding="utf-8")
    (skills / "x" / "SKILL.md").write_text("old\n", encoding="utf-8")
    before = _mtimes(skills / "x")
    try:
        vs.vendor("x", {"repo": "r", "ref": "v3.3.0"})
    except vs.RefMoved as exc:
        assert "b" * 12 in str(exc) and SHA[:12] in str(exc) and "--ref v3.3.0" in str(exc)
    else:
        raise AssertionError("RefMoved not raised")
    assert _mtimes(skills / "x") == before
    vs.vendor("x", {"repo": "r", "ref": "v3.3.0"}, ref="v3.3.0")   # explicit: the owner reviewed it
    assert json.loads((skills / "x" / vs.MARKER).read_text(encoding="utf-8"))["sha"] == SHA


def test_license_files_come_from_the_repo_root(tmp_path, monkeypatch):
    """An upstream LICENSE / NOTICE outside the subpath ships inside the vendored skill (Apache-2.0 4(a), 4(d))."""
    skills = _box(tmp_path, monkeypatch)
    sub = tmp_path / "src" / "pkg"
    sub.mkdir()
    (sub / "SKILL.md").write_text("---\nname: x\n---\nbody\n", encoding="utf-8")
    (tmp_path / "src" / "NOTICE.md").write_text("notice\n", encoding="utf-8")
    vs.vendor("x", {"repo": "r", "ref": SHA, "subpath": "pkg", "license_files": ["NOTICE.md"]})
    assert (skills / "x" / "NOTICE.md").read_text(encoding="utf-8") == "notice\n"


def test_same_tag_same_sha_is_unchanged(tmp_path, monkeypatch):
    skills = _box(tmp_path, monkeypatch)
    (skills / "x").mkdir()
    (skills / "x" / vs.MARKER).write_text(json.dumps({"repo": "r", "ref": "v1", "sha": SHA,
                                                      "vendored_at": "2026-01-01"}), encoding="utf-8")
    assert vs.vendor("x", {"repo": "r", "ref": "v1"}) == SHA
