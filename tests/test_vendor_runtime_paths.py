"""runtime_paths (2026-11-16): files a vendored skill writes into its own dir when it runs (ghost-editor's
library downloads, its catalog / taste state) are skipped by R10 and survive a re-vendor."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import skills_lib as sl  # noqa: E402
import vendor_skill as vs  # noqa: E402

SHA = "a" * 40
RT = ["library/music/*.mp3", "library/emoji/*", "!library/emoji/set.json", "state.json"]


def test_last_match_wins_and_bang_reincludes():
    assert sl.is_runtime("library/music/a.mp3", RT)
    assert sl.is_runtime("library/emoji/x/y.webp", RT)          # * crosses /
    assert not sl.is_runtime("library/emoji/set.json", RT)      # re-included: still integrity-checked
    assert not sl.is_runtime("SKILL.md", RT)
    assert not sl.is_runtime("anything", [])


def test_hash_skips_runtime_files_only(tmp_path):
    d = tmp_path / "x"
    (d / "library" / "music").mkdir(parents=True)
    (d / "SKILL.md").write_text("a\n", encoding="utf-8")
    base = sl.dir_content_hash(d, ignore=RT)
    (d / "library" / "music" / "song.mp3").write_bytes(b"downloaded")
    (d / "state.json").write_text("{}", encoding="utf-8")
    assert sl.dir_content_hash(d, ignore=RT) == base
    (d / "SKILL.md").write_text("edited\n", encoding="utf-8")
    assert sl.dir_content_hash(d, ignore=RT) != base


def test_hash_looks_runtime_paths_up_by_dir_name(tmp_path, monkeypatch):
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    (hooks / "skills-sources.json").write_text(json.dumps({"_meta": {}, "x": {"runtime_paths": RT}}),
                                               encoding="utf-8")
    monkeypatch.setattr(sl, "HOOKS_DIR", hooks)
    d = tmp_path / "x"
    d.mkdir()
    (d / "SKILL.md").write_text("a\n", encoding="utf-8")
    base = sl.dir_content_hash(d)
    (d / "state.json").write_text("{}", encoding="utf-8")
    assert sl.dir_content_hash(d) == base
    assert sl.dir_content_hash(d, ignore=()) != base           # explicit () = hash everything


def _box(tmp_path, monkeypatch):
    src = tmp_path / "src"
    (src / "library" / "emoji").mkdir(parents=True)
    (src / "SKILL.md").write_text("---\nname: x\n---\nbody\n", encoding="utf-8")
    (src / "library" / "emoji" / "set.json").write_text("[]", encoding="utf-8")
    (src / "state.json").write_text("{\"upstream\": 1}", encoding="utf-8")
    skills = tmp_path / "skills"
    skills.mkdir()
    monkeypatch.setattr(vs.sl, "SKILLS_DIR", skills)
    monkeypatch.setattr(vs, "fetch", lambda repo, ref: (src, SHA))
    return src, skills


def test_unchanged_upstream_leaves_runtime_files_alone(tmp_path, monkeypatch):
    _, skills = _box(tmp_path, monkeypatch)
    entry = {"repo": "r", "ref": SHA, "runtime_paths": RT}
    vs.vendor("x", entry)
    (skills / "x" / "library" / "music").mkdir(parents=True)
    (skills / "x" / "library" / "music" / "song.mp3").write_bytes(b"downloaded")
    (skills / "x" / "state.json").write_text("{\"mine\": 1}", encoding="utf-8")
    vs.vendor("x", entry)
    assert (skills / "x" / "library" / "music" / "song.mp3").read_bytes() == b"downloaded"
    assert json.loads((skills / "x" / "state.json").read_text(encoding="utf-8")) == {"mine": 1}


def test_new_upstream_carries_runtime_files_and_drops_the_rest(tmp_path, monkeypatch):
    src, skills = _box(tmp_path, monkeypatch)
    vs.vendor("x", {"repo": "r", "ref": SHA, "runtime_paths": RT})
    (skills / "x" / "library" / "music").mkdir(parents=True)
    (skills / "x" / "library" / "music" / "song.mp3").write_bytes(b"downloaded")
    (skills / "x" / "library" / "emoji" / "smile.webp").write_bytes(b"emoji")
    (skills / "x" / "state.json").write_text("{\"mine\": 1}", encoding="utf-8")
    (skills / "x" / "stray.md").write_text("not runtime\n", encoding="utf-8")
    (src / "SKILL.md").write_text("---\nname: x\n---\nbody v2\n", encoding="utf-8")
    (src / "library" / "emoji" / "set.json").write_text("[1]", encoding="utf-8")
    monkeypatch.setattr(vs, "fetch", lambda repo, ref: (src, "c" * 40))
    vs.vendor("x", {"repo": "r", "ref": "c" * 40, "runtime_paths": RT})
    x = skills / "x"
    assert "body v2" in (x / "SKILL.md").read_text(encoding="utf-8")
    assert (x / "library" / "emoji" / "set.json").read_text(encoding="utf-8") == "[1]"   # upstream file updates
    assert (x / "library" / "music" / "song.mp3").read_bytes() == b"downloaded"
    assert (x / "library" / "emoji" / "smile.webp").read_bytes() == b"emoji"
    assert json.loads((x / "state.json").read_text(encoding="utf-8")) == {"mine": 1}      # the user's state wins
    assert not (x / "stray.md").exists()
    assert sorted(p.name for p in skills.iterdir()) == ["x"]


def test_symlinks_are_carried_and_pycache_never_forces_a_swap(tmp_path, monkeypatch):
    import os
    src, skills = _box(tmp_path, monkeypatch)
    rt = RT + [".venv-df/*"]
    vs.vendor("x", {"repo": "r", "ref": SHA, "runtime_paths": rt})
    x = skills / "x"
    (x / "__pycache__").mkdir()
    (x / "__pycache__" / "a.cpython-314.pyc").write_bytes(b"pyc")
    staged_before = x.stat().st_ino
    vs.vendor("x", {"repo": "r", "ref": SHA, "runtime_paths": rt})
    assert x.stat().st_ino == staged_before                                       # no swap for a pyc
    (x / ".venv-df" / "bin").mkdir(parents=True)
    (x / ".venv-df" / "bin" / "python3.14").write_bytes(b"elf")
    os.symlink("python3.14", x / ".venv-df" / "bin" / "python")
    (src / "SKILL.md").write_text("---\nname: x\n---\nbody v2\n", encoding="utf-8")
    monkeypatch.setattr(vs, "fetch", lambda repo, ref: (src, "c" * 40))
    vs.vendor("x", {"repo": "r", "ref": "c" * 40, "runtime_paths": rt})
    link = x / ".venv-df" / "bin" / "python"
    assert link.is_symlink() and os.readlink(link) == "python3.14" and link.read_bytes() == b"elf"


def test_a_failed_swap_puts_the_old_tree_and_its_runtime_files_back(tmp_path, monkeypatch):
    import pytest
    src, skills = _box(tmp_path, monkeypatch)
    vs.vendor("x", {"repo": "r", "ref": SHA, "runtime_paths": RT})
    x = skills / "x"
    (x / "state.json").write_text("{\"mine\": 1}", encoding="utf-8")
    (x / "library" / "music").mkdir(parents=True)
    (x / "library" / "music" / "song.mp3").write_bytes(b"downloaded")
    (src / "SKILL.md").write_text("---\nname: x\n---\nbody v2\n", encoding="utf-8")
    monkeypatch.setattr(vs, "fetch", lambda repo, ref: (src, "c" * 40))
    real = vs.os.replace

    def flaky(a, b):
        if Path(b) == x and Path(a).name == "x":                                  # staged -> live swap only
            raise PermissionError("file held open")
        return real(a, b)

    monkeypatch.setattr(vs.os, "replace", flaky)
    with pytest.raises(PermissionError):
        vs.vendor("x", {"repo": "r", "ref": "c" * 40, "runtime_paths": RT})
    assert "body v2" not in (x / "SKILL.md").read_text(encoding="utf-8")         # old tree back in place
    assert json.loads((x / "state.json").read_text(encoding="utf-8")) == {"mine": 1}
    assert (x / "library" / "music" / "song.mp3").read_bytes() == b"downloaded"


def test_ghost_editor_keeps_its_tracked_library_checked():
    rt = sl.runtime_paths("ghost-editor")
    assert rt, "ghost-editor needs runtime_paths in hooks/skills-sources.json"
    for runtime in ("library/music/a.mp3", "library/sfx/mixkit-x.wav", "library/models/face.onnx",
                    "library/me/emb.json", "recipes/clean-os/catalog.json", "taste.json", ".env",
                    # save_style.py, house_look.py, sfx_fetch.py, meme_add.py (Santa review 2026-11-16)
                    "styles/my-style.json", "examples/gallery/my-style.reel.json", "references/styles.md",
                    "recipes/clean-os/house.json", "library/music/manifest.json", "library/sfx/manifest.json",
                    "library/memes/oof/meta.json", ".venv-df/bin/python"):
        assert sl.is_runtime(runtime, rt), runtime
    for tracked in ("SKILL.md", "library/sfx/cc0-tada.wav", "library/emoji/set.json",
                    "library/models/face_landmarker.task", "scripts/build.mjs"):
        assert not sl.is_runtime(tracked, rt), tracked
