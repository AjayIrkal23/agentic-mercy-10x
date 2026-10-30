"""FIX-r2 I7: a fresh install detects the plan tier before its first settings render (one round)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "installer", ROOT / "hooks"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
import settings_install as si  # noqa: E402


class _Render:
    def __init__(self):
        self.calls = []

    def _detect_tier_first(self, root):
        self.calls.append(root)


def test_detects_only_when_the_tier_file_is_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_HOOK_STATE_DIR", str(tmp_path / "state"))
    r = _Render()
    si._tier_first(tmp_path, r)
    assert r.calls == [tmp_path]
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "plan-tier.json").write_text('{"tier": "max5"}', encoding="utf-8")
    si._tier_first(tmp_path, r)
    assert r.calls == [tmp_path]
