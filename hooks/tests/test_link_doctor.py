"""link-doctor must fail broken links (audit 2026-10-05 I-02).

A traceback, a non-zero exit or a renamed script all printed PASS, so the doctor
row could stay green while a hook was dead. stderr alone is not a failure.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1]


def _doctor(tmp_path, monkeypatch, links: list[dict]):
    spec = importlib.util.spec_from_file_location("ld", HOOKS / "tools" / "link-doctor.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    cfg = tmp_path / "dispatch.config.json"
    cfg.write_text(json.dumps({"chains": {"stop": links}}), encoding="utf-8")
    monkeypatch.setattr(m, "_CONFIG", cfg)
    _p, _f, rows = m.run_doctor()
    return {lid: status for _ev, lid, status, _ms in rows}


def test_crash_nonzero_and_missing_script_fail(tmp_path, monkeypatch):
    ok = tmp_path / "ok.py"
    ok.write_text("import sys; sys.stderr.write('noise'); print('{}')\n", encoding="utf-8")
    crash = tmp_path / "crash.py"
    crash.write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    seven = tmp_path / "seven.py"
    seven.write_text("import sys; print('{}'); sys.exit(7)\n", encoding="utf-8")
    st = _doctor(tmp_path, monkeypatch, [
        {"id": "ok", "type": "exec", "cmd": ["{PY}", str(ok)]},
        {"id": "crash", "type": "exec", "cmd": ["{PY}", str(crash)]},
        {"id": "seven", "type": "exec", "cmd": ["{PY}", str(seven)]},
        {"id": "gone", "type": "exec", "cmd": ["{PY}", str(tmp_path / "renamed.py")]},
    ])
    assert st["ok"] == "PASS"
    assert st["crash"].startswith("FAIL")
    assert st["seven"] == "FAIL(rc=7)"
    assert st["gone"] == "FAIL(missing-script)"
