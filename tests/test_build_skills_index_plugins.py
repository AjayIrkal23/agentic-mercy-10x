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
