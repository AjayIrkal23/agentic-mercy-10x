"""SECURITY-1b: `deps._sub` splits a multi-word launcher (`py -3`) but keeps a path with spaces whole.

`str(v).split()` turned `C:/Users/John Smith/.../python.exe` into two argv elements, so CreateProcess
tried `<drive>:\\Users\\John.exe` first (the classic unquoted-path search).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "installer", ROOT / "hooks"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
import deps  # noqa: E402

SPACED = "C:/Users/John Smith/AppData/Local/Programs/agentic-mercy/python/python.exe"


@pytest.mark.parametrize("value, argv", [
    ("py -3", ["py", "-3"]),
    ("python3", ["python3"]),
    (SPACED, [SPACED]),
    (r"D:\Program Files\Python\py.exe -3", [r"D:\Program Files\Python\py.exe", "-3"]),
    ("C:/Program Files/Python/py.exe -3 -u", ["C:/Program Files/Python/py.exe", "-3", "-u"]),
])
def test_a_whole_element_token_keeps_a_spaced_path_in_one_piece(value, argv):
    assert deps._sub(["{PYTHON}", "-m", "pip"], {"PYTHON": value}) == argv + ["-m", "pip"]


def test_embedded_tokens_are_replaced_in_place():
    assert deps._sub(["{CLAUDE_DIR}/x.py", "--k={HOME}"], {"CLAUDE_DIR": "C:/a b", "HOME": "C:/h i"}) \
        == ["C:/a b/x.py", "--k=C:/h i"]
