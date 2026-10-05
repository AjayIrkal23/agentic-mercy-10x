"""Template contract from the 2026-10-05 audit (A-03): personal-repo marketplaces whose
plugins run hooks every session under bypassPermissions do not auto-update; updates
are taken by hand and followed by the doctor.
Runnable: `python3 -m pytest tests/test_settings_wp8.py -q`.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PERSONAL = {"forrestchang/andrej-karpathy-skills", "nateherkai/scroll-craft", "DietrichGebert/ponytail"}


def _markets(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {v["source"]["repo"]: v for v in data["extraKnownMarketplaces"].values()}


def test_personal_marketplaces_do_not_auto_update():
    markets = _markets(ROOT / "settings.template.json")
    assert PERSONAL <= set(markets)
    assert {r: markets[r].get("autoUpdate") for r in PERSONAL} == {r: False for r in PERSONAL}
