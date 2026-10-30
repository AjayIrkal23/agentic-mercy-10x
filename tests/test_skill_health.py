"""scripts/skill_health.py: pushed-vs-invoked report + the skillOverrides map."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
LEGAL = {"on", "name-only", "user-invocable-only"}


def _mod():
    spec = importlib.util.spec_from_file_location("skill_health", _ROOT / "scripts" / "skill_health.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


sh = _mod()


def _tree(tmp_path: Path, sessions: int = 12) -> tuple[Path, Path]:
    root, tel = tmp_path / "root", tmp_path / "tel"
    tel.mkdir()
    for name in ("update-docs", "invoke-review", "higgsfield-generate", "graphify", "img2threejs"):
        d = root / "skills" / name
        d.mkdir(parents=True)
        extra = "disable-model-invocation: true\n" if name == "img2threejs" else ""
        (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {name} does a thing.\n{extra}---\nbody\n",
                                    encoding="utf-8")
    (root / "hooks").mkdir()
    (root / "hooks" / "skills-index.json").write_text(json.dumps({"skills": {
        "ponytail:ponytail": {"name": "ponytail:ponytail", "description": "lazy"}}}), encoding="utf-8")
    for n in range(1, sessions + 1):
        sid = f"a{n:02d}"
        rows = [json.dumps({"ts": "x", "skills": ["update-docs", "invoke-review", "higgsfield-generate", "unknown-skill"],
                            "categories": [], "source": "router", "enforce": "soft"})]
        if n == 1:
            rows.append("{not json")
        p = tel / f"{sid}.pushed-skills.jsonl"
        p.write_text("\n".join(rows) + "\n", encoding="utf-8")
        os.utime(p, (1_700_000_000 + n, 1_700_000_000 + n))
        if n % 2 == 0:
            q = tel / f"{sid}.skill-invocations.jsonl"
            q.write_text(json.dumps({"ts": "x", "skill": "update-docs", "via": "skill"}) + "\n"
                         + json.dumps({"ts": "x", "skill": "graphify", "via": "read"}) + "\n", encoding="utf-8")
            os.utime(q, (1_700_000_000 + n, 1_700_000_000 + n))
    # test litter is dropped
    (tel / "doctor-x.pushed-skills.jsonl").write_text(json.dumps({"skills": ["update-docs"]}) + "\n", encoding="utf-8")
    (tel / "s.pushed-skills.jsonl").write_text(json.dumps({"skills": ["update-docs"]}) + "\n", encoding="utf-8")
    return root, tel


def test_window_and_counts(tmp_path):
    root, tel = _tree(tmp_path)
    data = sh.collect(root, tel, window=30)
    st = data["stats"]
    assert data["window_sessions"] == 12
    assert st["update-docs"]["pushed"] == 12 and st["update-docs"]["invoked"] == 6
    assert st["update-docs"]["ratio"] == 0.5
    assert "never-invoked" in st["invoke-review"]["flags"]
    assert "never-pushed" in st["graphify"]["flags"]
    assert "missing" in st["unknown-skill"]["flags"]
    assert "dmi" in st["img2threejs"]["flags"]
    assert data["skipped_lines"] == 1
    report = sh.render_report(data)
    assert "Pushed, never invoked" in report and "Invoked, never pushed" in report


def test_overrides_policy(tmp_path):
    root, tel = _tree(tmp_path)
    data = sh.collect(root, tel, window=30)
    ov = sh.overrides(data["inventory"], data["stats"], data["window_sessions"])
    assert ov["invoke-review"] == "name-only"
    assert "user-invocable-only" not in ov.values()
    assert ov["higgsfield-generate"] == "name-only"
    assert ov["img2threejs"] == "name-only"
    assert "update-docs" not in ov and "ponytail:ponytail" not in ov and "unknown-skill" not in ov


def test_invoked_skills_are_never_hidden_from_the_model(tmp_path):
    """The model calls invoke-* through Skill(); user-invocable-only would hide them from it."""
    root, tel = _tree(tmp_path)
    d = root / "skills" / "invoke-design"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: invoke-design\ndescription: design act.\n---\nbody\n", encoding="utf-8")
    (tel / "a01.skill-invocations.jsonl").write_text(
        json.dumps({"ts": "x", "skill": "invoke-design", "via": "skill"}) + "\n", encoding="utf-8")
    data = sh.collect(root, tel, window=30)
    assert data["stats"]["invoke-design"]["invoked"] == 1
    ov = sh.overrides_doc(data)["skillOverrides"]
    assert ov["invoke-design"] == "name-only"


def test_small_window_skips_telemetry_rule(tmp_path):
    root, tel = _tree(tmp_path, sessions=5)
    data = sh.collect(root, tel, window=30)
    doc = sh.overrides_doc(data)
    assert "img2threejs" not in doc["skillOverrides"]
    assert doc["telemetry_rule_applied"] is False
    assert "Window too small" in sh.render_report(data)


def test_values_are_legal(tmp_path):
    root, tel = _tree(tmp_path)
    doc = sh.overrides_doc(sh.collect(root, tel, window=30))
    assert set(doc["skillOverrides"].values()) <= LEGAL


def _run_live(out: Path) -> subprocess.CompletedProcess:
    # an empty telemetry dir of its own: other tests in the run write pushed-skills rows to the shared one
    tel = out.parent / "empty-telemetry"
    tel.mkdir(exist_ok=True)
    return subprocess.run([sys.executable, str(_ROOT / "scripts" / "skill_health.py"), "--root", str(_ROOT),
                           "--overrides", "--out", str(out)], capture_output=True, encoding="utf-8", timeout=60,
                          env={**os.environ, "CLAUDE_HOOK_TELEMETRY_DIR": str(tel)})


def test_live_tree_overrides_run(tmp_path):
    out = tmp_path / "o.json"
    r = _run_live(out)
    assert r.returncode == 0, r.stderr
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["window_sessions"] == 0
    ov = doc["skillOverrides"]
    local = {p.parent.name for p in (_ROOT / "skills").glob("*/SKILL.md")}
    assert set(ov.values()) <= {"on", "name-only"}  # the generator never hides a skill from the model
    for name in local:
        if name.startswith("invoke-"):
            assert ov.get(name) == "name-only", name
    assert "invoke" not in ov
    for name in sh.NAME_ONLY_STATIC:
        if name in local and name != "lean-ctx":
            assert ov.get(name) == "name-only", name
    assert "lean-ctx" not in ov  # FIX-r2 T6: settings.json may never name it


def test_never_writes_settings(tmp_path):
    before = {n: (_ROOT / n).exists() for n in ("settings.json", "settings.user.json")}
    _run_live(tmp_path / "o.json")
    assert {n: (_ROOT / n).exists() for n in before} == before


def test_deterministic(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    _run_live(a)
    _run_live(b)
    da, db = (json.loads(p.read_text(encoding="utf-8")) for p in (a, b))
    da.pop("generated_at")
    db.pop("generated_at")
    assert da == db
    assert a.read_bytes().count(b"\n") == b.read_bytes().count(b"\n")
