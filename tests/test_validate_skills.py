"""Focused regression tests for skill-reference validation."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


def _load_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_skills_under_test", _SCRIPTS / "validate_skills.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_skill(skill_dir: Path, body: str) -> None:
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: reference-test\ndescription: Validates reference paths.\n---\n" + body,
        encoding="utf-8",
    )


def _isolate_validator(monkeypatch, validator, skill_dir: Path, skills_root: Path) -> None:
    monkeypatch.setattr(validator.sl, "skill_dirs", lambda: [skill_dir])
    monkeypatch.setattr(validator.sl, "locked_skills", lambda: set())
    monkeypatch.setattr(validator.sl, "SKILLS_DIR", skills_root)
    monkeypatch.setattr(validator, "_load_json", lambda _path: {})


def test_r6_accepts_backticked_absolute_claude_reference(tmp_path, monkeypatch):
    validator = _load_validator()
    claude_root = tmp_path / ".claude"
    reference = claude_root / "rules/references/tool-intelligence.md"
    reference.parent.mkdir(parents=True)
    reference.write_text("routing\n", encoding="utf-8")
    monkeypatch.setattr(validator.sl, "CLAUDE_DIR", claude_root)
    skill_dir = tmp_path / "skills" / "reference-test"
    _write_skill(
        skill_dir,
        "See `~/.claude/rules/references/tool-intelligence.md` for routing.\n",
    )
    _isolate_validator(monkeypatch, validator, skill_dir, tmp_path / "skills")

    assert validator.validate() == 0


def test_r6_does_not_truncate_mdc_reference_to_md(tmp_path, monkeypatch):
    validator = _load_validator()
    claude_root = tmp_path / ".claude"
    reference = claude_root / "rules/user-mcp-inventory.mdc"
    reference.parent.mkdir(parents=True)
    reference.write_text("inventory\n", encoding="utf-8")
    monkeypatch.setattr(validator.sl, "CLAUDE_DIR", claude_root)
    skill_dir = tmp_path / "skills" / "reference-test"
    _write_skill(
        skill_dir,
        "Read `~/.claude/rules/user-mcp-inventory.mdc` for the inventory.\n",
    )
    _isolate_validator(monkeypatch, validator, skill_dir, tmp_path / "skills")

    assert validator.validate() == 0


def test_r6_does_not_match_supported_extension_inside_longer_suffix(tmp_path, monkeypatch):
    validator = _load_validator()
    skill_dir = tmp_path / "skills" / "reference-test"
    _write_skill(skill_dir, "Ignore `references/not-markdown.mdcx`.\n")
    _isolate_validator(monkeypatch, validator, skill_dir, tmp_path / "skills")

    assert validator.validate() == 0


def test_r6_retains_skill_relative_reference_resolution(tmp_path, monkeypatch):
    validator = _load_validator()
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "reference-test"
    _write_skill(
        skill_dir,
        "Read `references/local.md` and `shared/references/common.md`.\n",
    )
    (skill_dir / "references").mkdir()
    (skill_dir / "references" / "local.md").write_text("local\n", encoding="utf-8")
    shared = skills_root / "shared" / "references"
    shared.mkdir(parents=True)
    (shared / "common.md").write_text("shared\n", encoding="utf-8")
    _isolate_validator(monkeypatch, validator, skill_dir, skills_root)

    assert validator.validate() == 0
