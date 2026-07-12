"""test_portability_gate.py — CI-enforced portability grep-gates (P6-T1/P6-T7).

Wraps ``scripts/grep_gates.py`` so the gate runs under pytest AND as a standalone
CI step. A failing gate lists the offending file:line so regressions are obvious.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_GATE = _ROOT / "scripts" / "grep_gates.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("grep_gates", _GATE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["grep_gates"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_portability_gates_pass():
    gate = _load_gate()
    failures, passes = gate.run_gates()
    assert not failures, "portability grep-gates FAILED:\n" + "\n".join(failures)
    assert passes, "expected at least one gate to have run"


def test_platform_lib_is_sole_sysplatform_site():
    """The one OS branching point: only platform.py may test sys.platform."""
    gate = _load_gate()
    failures, _ = gate.run_gates()
    assert not any(f.startswith("G1") for f in failures)
