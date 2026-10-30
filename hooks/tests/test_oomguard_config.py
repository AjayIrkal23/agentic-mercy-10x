"""test_oomguard_config.py — ~/.claude/oomguard.local.json readers fall back to defaults."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import oomguard_config as ogc  # noqa: E402


def _cfg(tmp_path, data) -> Path:
    p = tmp_path / "oomguard.local.json"
    p.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return p


def _all(p):
    return (ogc.restore_enabled(p), ogc.shed_mode(p), ogc.memory_high(p), ogc.kill_policy(p),
            ogc.protected_extra(p), ogc.victims_extra(p))


DEFAULTS = (True, "own-builders", "12G", {"enabled": True}, [], [])


def test_no_file_gives_defaults(tmp_path):
    assert _all(tmp_path / "absent.json") == DEFAULTS


def test_default_path_is_under_claude_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    assert ogc.path() == tmp_path / "oomguard.local.json"
    _cfg(tmp_path, {"shed_mode": "none"})
    assert ogc.shed_mode() == "none"


def test_file_values_are_reflected(tmp_path):
    p = _cfg(tmp_path, {"restore_enabled": False, "kill_policy": {"enabled": False, "idle_min": 5, "junk": 1},
                        "protected_extra": ["ollama", " "], "victims_extra": ["mongod"], "memory_high": "8G"})
    assert ogc.restore_enabled(p) is False
    assert ogc.kill_policy(p) == {"enabled": False, "idle_min": 5}
    assert ogc.protected_extra(p) == ["ollama"] and ogc.victims_extra(p) == ["mongod"]
    assert ogc.memory_high(p) == "8G"


@pytest.mark.parametrize("raw", ["{not json", "[1,2]", "null", ""])
def test_malformed_gives_defaults(tmp_path, raw):
    assert _all(_cfg(tmp_path, raw)) == DEFAULTS


def test_only_literal_false_disables_restore(tmp_path):
    assert ogc.restore_enabled(_cfg(tmp_path, {"restore_enabled": "no"})) is True
    assert ogc.restore_enabled(_cfg(tmp_path, {"restore_enabled": 0})) is True


def test_bad_values_fall_back(tmp_path):
    p = _cfg(tmp_path, {"shed_mode": "everything", "memory_high": "12 GB", "kill_policy": "off",
                        "protected_extra": "ollama"})
    assert ogc.shed_mode(p) == "own-builders" and ogc.memory_high(p) == "12G"
    assert ogc.kill_policy(p) == {"enabled": True} and ogc.protected_extra(p) == []
    assert ogc.shed_mode(_cfg(tmp_path, {"shed_mode": "known-heavy"})) == "known-heavy"
    assert ogc.memory_high(_cfg(tmp_path, {"memory_high": "16384M"})) == "16384M"
