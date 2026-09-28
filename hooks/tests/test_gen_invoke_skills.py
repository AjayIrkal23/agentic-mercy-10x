"""gen-invoke-skills.py: act table comes from config, output is deterministic, --check catches drift."""
import importlib.util
import json
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("gen_invoke_skills", HOOKS / "gen-invoke-skills.py")
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)

CFG = json.loads((HOOKS / "autonomous-skill-router.config.json").read_text())
POLICY = json.loads((HOOKS / "model-policy.json").read_text())


def test_act_table_is_canonical_and_from_config():
    acts = gen.load_acts(CFG)
    assert [a["act"] for a in acts] == (
        "audit spec plan debug test impl refactor design clean security review docs verify".split())
    assert {a["act"] for a in acts if a["mutates"]} == {"impl", "refactor", "design", "clean"}
    assert {a["act"] for a in acts if a["checkpoint"]} == {"spec", "plan"}
    assert gen.act_model(next(a for a in acts if a["act"] == "review"), POLICY) == "opus"


def test_render_is_deterministic_and_uses_arguments():
    a, b = gen.render_all(CFG, POLICY), gen.render_all(CFG, POLICY)
    assert a == b
    invoke = a[gen.SKILLS_DIR / "invoke" / "SKILL.md"]
    assert "$ARGUMENTS" in invoke and "fable" not in invoke.lower()
    assert len(a) == 2 + 13 + len(gen.UTILITIES)


def test_check_flags_unexpected_invoke_dir(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gen, "SKILLS_DIR", tmp_path)
    for path, content in gen.render_all(CFG, POLICY).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    monkeypatch.setattr(sys, "argv", ["gen", "--check"])
    assert gen.main() == 0
    (tmp_path / "invoke-cleanup").mkdir()
    assert gen.main() == 1
    assert "unexpected" in capsys.readouterr().out
