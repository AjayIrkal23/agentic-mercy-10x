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


def test_r13_warns_on_intents_the_router_never_matches(tmp_path, monkeypatch, capsys):
    """C-03 (audit 2026-10-05): the router matches intents against its category names
    exactly, so a `design` or `planning` label is inert. Warn, never fail."""
    validator = _load_validator()
    skill_dir = tmp_path / "skills" / "reference-test"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: reference-test\ndescription: Validates intents.\nmetadata:\n"
        "  triggers:\n    intents: [design, REVIEW]\n---\nbody\n", encoding="utf-8")
    _isolate_validator(monkeypatch, validator, skill_dir, tmp_path / "skills")
    router = {"categories": {"DESIGN": {}, "REVIEW": {}}}
    monkeypatch.setattr(validator, "_load_json",
                        lambda p: router if p == validator.ROUTER else {})

    assert validator.validate() == 0
    out = capsys.readouterr().out
    assert "R13 WARN" in out and "reference-test: ['design']" in out


def test_r14_warns_on_block_scalar_description(tmp_path, monkeypatch, capsys):
    """R14 (graft of ecc:scripts/ci/validate-skills.js@25278e7d rule 4): a `description: |`
    block scalar breaks flat renderers that key off one line. Warn, never fail."""
    validator = _load_validator()
    skill_dir = tmp_path / "skills" / "reference-test"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: reference-test\ndescription: |\n  two\n  lines\n---\nbody\n", encoding="utf-8")
    _isolate_validator(monkeypatch, validator, skill_dir, tmp_path / "skills")

    assert validator.validate() == 0
    out = capsys.readouterr().out
    assert any(line.startswith("  R14 WARN") for line in out.splitlines()), out


def test_skip_fix_reports_r4_and_leaves_a_tracked_skill_untouched(tmp_path, monkeypatch, capsys):
    """FIX-r2 I2: self-heal passes --fix-untracked; a tracked skill's token-cost is a WARN, not a rewrite."""
    validator = _load_validator()
    skill_dir = tmp_path / "skills" / "reference-test"
    skill_dir.mkdir(parents=True)
    md = skill_dir / "SKILL.md"
    md.write_text("---\nname: reference-test\ndescription: Validates reference paths.\nmetadata:\n"
                  "  token-cost: 5\n---\n" + ("word " * 400) + "\n", encoding="utf-8")
    _isolate_validator(monkeypatch, validator, skill_dir, tmp_path / "skills")
    before = md.read_bytes()
    validator.validate(fix=True, skip_fix={"reference-test"})
    assert md.read_bytes() == before and "R4  WARN reference-test" in capsys.readouterr().out
    validator.validate(fix=True)
    assert md.read_bytes() != before


def test_missing_pyyaml_is_one_clear_failure(monkeypatch, capsys):
    """FI-7: without PyYAML the stdlib fallback cannot read block lists; say so once, exit 2."""
    validator = _load_validator()
    monkeypatch.setattr(validator.sl, "yaml", None)
    monkeypatch.setattr(sys, "argv", ["validate_skills.py"])
    assert validator.main() == 2
    out = capsys.readouterr()
    text = out.out + out.err
    assert "PyYAML missing (pip install pyyaml==6.0.3)" in text and "R12" not in text


def test_gen_agent_skill_blocks_without_pyyaml_exits_2(tmp_path):
    import subprocess  # noqa: PLC0415
    shim = tmp_path / "shim"
    shim.mkdir()
    (shim / "yaml.py").write_text("raise ModuleNotFoundError(\"No module named 'yaml'\")\n", encoding="utf-8")
    import os  # noqa: PLC0415
    cp = subprocess.run([sys.executable, str(_ROOT / "hooks" / "gen-agent-skill-blocks.py"), "--check"],
                        capture_output=True, text=True, timeout=60,
                        env={**os.environ, "PYTHONPATH": str(shim)})
    assert cp.returncode == 2 and "PyYAML missing (pip install pyyaml==6.0.3)" in cp.stderr
