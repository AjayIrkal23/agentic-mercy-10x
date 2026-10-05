"""REAP-1 A7: Windows installs Python tools through `uv tool install`, so detect.Env carries no pipx."""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "installer", ROOT / "hooks"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
import detect  # noqa: E402


def test_env_has_no_pipx_field_and_the_summary_names_the_tools_it_uses():
    assert "pipx" not in {f.name for f in dataclasses.fields(detect.Env)}
    summary = detect._fmt(detect.detect())
    assert "pipx" not in summary and "uv=" in summary and "npm=" in summary
