"""Plugin skills of a plugin the template disables never enter the index (audit
2026-10-05 G-11: the router pushed a disabled plugin's skill the model cannot load)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import build_skills_index as B  # noqa: E402


def _plugin(root: Path, name: str) -> list:
    md = root / name / "skills" / "s" / "SKILL.md"
    md.parent.mkdir(parents=True)
    md.write_text("---\nname: s\ndescription: x.\n---\n", encoding="utf-8")
    return [{"installPath": str(root / name)}]


def test_disabled_plugin_skills_are_skipped(tmp_path, monkeypatch):
    installed = tmp_path / "installed_plugins.json"
    installed.write_text(json.dumps({"plugins": {
        "on@m": _plugin(tmp_path, "on"), "off@m": _plugin(tmp_path, "off"),
        "synced@m": _plugin(tmp_path, "synced")}}), encoding="utf-8")
    template = tmp_path / "settings.template.json"
    template.write_text(json.dumps({"enabledPlugins": {"on@m": True, "off@m": False}}), encoding="utf-8")
    monkeypatch.setattr(B, "INSTALLED_PLUGINS", installed)
    monkeypatch.setattr(B, "TEMPLATE", template)

    assert sorted(short for short, _ in B._plugin_skill_files()) == ["on", "synced"]


def test_plugin_skills_go_to_the_gitignored_sidecar_and_load_merges(tmp_path, monkeypatch):
    """FIX-r2 I2: the tracked index holds local skills only; plugin skills live in state/ per machine."""
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    payload = {"_meta": {"skill_count": 1, "plugin_count": 1, "checksum": "x"}, "aliases": {},
               "skills": {"local-a": {"name": "local-a", "source": "metadata"},
                          "p:s": {"name": "p:s", "source": "plugin", "plugin": "p"}}}
    monkeypatch.setattr(B, "build", lambda: payload)
    monkeypatch.setattr(B, "INDEX", hooks / "skills-index.json")
    monkeypatch.setattr(B, "SIDECAR", tmp_path / "state" / "skills-index.plugins.json")
    B.write_index()
    tracked = json.loads((hooks / "skills-index.json").read_text(encoding="utf-8"))
    assert list(tracked["skills"]) == ["local-a"] and tracked["_meta"]["plugin_count"] == 0
    first = (hooks / "skills-index.json").read_bytes()
    B.write_index()
    assert (hooks / "skills-index.json").read_bytes() == first
    sys.path.insert(0, str(_SCRIPTS.parent / "hooks"))
    from lib import skills_index as SI
    merged = SI.load(hooks)
    assert set(merged["skills"]) == {"local-a", "p:s"} and merged["_meta"]["plugin_count"] == 1
    (tmp_path / "state" / "skills-index.plugins.json").unlink()
    assert set(SI.load(hooks)["skills"]) == {"local-a"}


def test_plugin_description_keywords_are_marked_and_still_go_to_the_sidecar(tmp_path, monkeypatch):
    """RQ-5: a plugin skill whose keywords came from its description scores at half weight in
    select.py, like a local one; curated plugin metadata keeps source "plugin"."""
    desc = B._entry("p:s", {"description": "Use when executing implementation plans with tasks."}, {},
                    source_kind="plugin")
    assert desc["source"] == "plugin-description"
    for stop in ("implementation", "plan", "tasks", "report", "changes"):
        assert stop not in desc["keywords"], desc["keywords"]
    curated = B._entry("p:c", {"description": "x.", "metadata": {"triggers": {"keywords": ["foo"]}}}, {},
                       source_kind="plugin")
    assert curated["source"] == "plugin"
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    payload = {"_meta": {"skill_count": 1, "plugin_count": 1, "checksum": "x"}, "aliases": {},
               "skills": {"local-a": {"name": "local-a", "source": "metadata"}, "p:s": desc}}
    monkeypatch.setattr(B, "build", lambda: payload)
    monkeypatch.setattr(B, "INDEX", hooks / "skills-index.json")
    monkeypatch.setattr(B, "SIDECAR", tmp_path / "state" / "skills-index.plugins.json")
    B.write_index()
    tracked = json.loads((hooks / "skills-index.json").read_text(encoding="utf-8"))
    assert list(tracked["skills"]) == ["local-a"]
    side = json.loads((tmp_path / "state" / "skills-index.plugins.json").read_text(encoding="utf-8"))
    assert list(side["skills"]) == ["p:s"]
