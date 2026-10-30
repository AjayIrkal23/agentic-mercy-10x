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


# memory_high "" = unset: bin/claude derives the scope cap from RAM (MemTotal minus 4 GiB, never below half
# (memory_cap_mb))
DEFAULTS = (True, "own-builders", "", {"enabled": True}, [], [])


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
    assert ogc.shed_mode(p) == "own-builders" and ogc.memory_high(p) == ""
    assert ogc.kill_policy(p) == {"enabled": True} and ogc.protected_extra(p) == []
    assert ogc.shed_mode(_cfg(tmp_path, {"shed_mode": "known-heavy"})) == "known-heavy"
    assert ogc.memory_high(_cfg(tmp_path, {"memory_high": "16384M"})) == "16384M"


def test_ram_factor_is_relative_to_a_30_gb_reference():
    assert ogc.ram_factor(30669) == 1.0
    assert ogc.ram_factor(15900) == pytest.approx(0.53)
    assert ogc.ram_factor(0) == 1.0          # unknown RAM: shipped numbers


def test_scale_mb_respects_the_floor():
    assert ogc.scale_mb(3072, 1536, 0.53) == 1628
    assert ogc.scale_mb(1500, 768, 0.2) == 768
    assert ogc.scale_mb(8192, 0, 1.0) == 8192


@pytest.mark.parametrize("total,want", [(15650, 11554), (16384, 12288), (30669, 26573), (8192, 4096),
                                        (6144, 3072), (0, 0)])
def test_memory_cap_is_memtotal_minus_4g_never_below_half(total, want):
    """F7 (user, 2026-10-30): the desktop keeps 4 GiB; a small box still gets half its RAM."""
    assert ogc.memory_cap_mb(total) == want


def test_tiers_override_keeps_only_int_tier_values(tmp_path):
    p = _cfg(tmp_path, {"tiers": {"warn": {"mem_available_mb": 5000, "psi": "high", "x": True},
                                  "crit": {"mem_available_mb": 2000.0}, "junk": {"a": 1}}})
    assert ogc.tiers_override(p) == {"warn": {"mem_available_mb": 5000}, "crit": {"mem_available_mb": 2000}}
    assert ogc.tiers_override(_cfg(tmp_path, {"tiers": "off"})) == {}
    assert ogc.tiers_override(tmp_path / "absent.json") == {}


def test_linger_is_wanted_unless_literally_false(tmp_path):
    assert ogc.linger_wanted(tmp_path / "absent.json") is True
    assert ogc.linger_wanted(_cfg(tmp_path, {"linger": "no"})) is True
    assert ogc.linger_wanted(_cfg(tmp_path, {"linger": False})) is False
