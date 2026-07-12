"""test_doctor.py — the install-time doctor + its regression-detection (P6-T6).

Asserts the doctor is GREEN on a faithful checkout, that the model-routing and
workflow-args checks hold, and — the P6-T6 acceptance bar — that the doctor
actually catches a deliberately BROKEN dispatch link and a DELETED command
(otherwise a green doctor would be worthless).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks"), str(_ROOT / "hooks" / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, _ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore
    return mod


def test_doctor_is_green():
    doctor = _load("doctor", "installer/doctor.py")
    rows = doctor.run_doctor()
    fails = [(n, d) for n, s, d in rows if s == "FAIL"]
    assert not fails, f"doctor FAIL rows: {fails}"
    # the T6-added checks must be present and PASS
    by = {n: s for n, s, _ in rows}
    assert by.get("model-routing") == "PASS"
    assert by.get("workflow-args") == "PASS"
    assert by.get("hook-fixtures") == "PASS"


def test_command_resolution_detects_a_deleted_command():
    doctor = _load("doctor", "installer/doctor.py")
    # a historic name with neither a command file nor a translator entry is UNRESOLVED
    unresolved = doctor.resolve_historic_commands(
        ["invoke-audit", "invoke-deleted-xyz"], _ROOT / "commands", {"invoke-audit": ["audit"]})
    assert "invoke-deleted-xyz" in unresolved
    assert "invoke-audit" not in unresolved


def test_link_doctor_detects_a_broken_link(tmp_path):
    ld = _load("link_doctor", "hooks/tools/link-doctor.py")
    # a minimal dispatch config whose one GATE link emits NON-JSON garbage -> FAIL
    broken = {
        "chains": {
            "pre-tool-use": [
                {"id": "broken-gate", "type": "gate", "tools": "Bash",
                 "cmd": [sys.executable, "-c", "print('garbage-not-json')"], "enabled": True}
            ]
        }
    }
    cfg = tmp_path / "dispatch.config.json"
    cfg.write_text(json.dumps(broken))
    ld._CONFIG = cfg  # point link-doctor at the broken config
    passed, failed, rows = ld.run_doctor()
    assert failed >= 1, f"expected a FAIL row, got {rows}"
    assert any("broken-gate" in r[1] and r[2].startswith("FAIL") for r in rows)
