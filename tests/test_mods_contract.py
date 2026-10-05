"""test_mods_contract.py — the Claude Code mods kept in mods/<id>/ (stdlib, both CI legs).

CI has no `claude` binary and no `tsc`, so this pins the static contract that
`scripts/validate_mods.py --static` enforces: manifest ids are well-formed and never
contain "lean-ctx" (render would refuse the env), every enabled mod has a matching
plugin.json, loadable hooks modules, no APIs the mod environment lacks, a declared
types contract, tests, and no tracked engine-laid type files.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))


def _validator():
    spec = importlib.util.spec_from_file_location("validate_mods", _ROOT / "scripts" / "validate_mods.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["validate_mods"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_manifest_mods_section_is_well_formed():
    mods = MANIFEST["mods"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", mods["claude_version"])
    for mod_id in mods["enabled"]:
        assert re.fullmatch(r"[a-z0-9][a-z0-9-]*", mod_id)
        assert "lean-ctx" not in mod_id


def test_every_enabled_mod_meets_the_static_contract():
    v = _validator()
    for mod_id in MANIFEST["mods"]["enabled"]:
        hard, _warn = v.static_problems(mod_id, _ROOT)
        assert hard == [], f"{mod_id}: {hard}"


def test_forbidden_api_scan_ignores_comments_but_catches_code(tmp_path):
    v = _validator()
    folder = tmp_path / "mods" / "demo"
    (folder / ".claude-plugin").mkdir(parents=True)
    (folder / "hooks").mkdir()
    (folder / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "demo"}), encoding="utf-8")
    (folder / "hooks" / "hooks.json").write_text(json.dumps({"modules": ["./register.ts"]}), encoding="utf-8")
    (folder / "hooks" / "register.ts").write_text("// no console.log here\nexport const register = () => {}\n", encoding="utf-8")
    hard, warn = v.static_problems("demo", tmp_path)
    assert hard == [] and warn == ["M5 no *.test.ts[x] files"]
    (folder / "hooks" / "register.ts").write_text("export const register = () => { setTimeout(() => {}, 1) }\n", encoding="utf-8")
    hard, _ = v.static_problems("demo", tmp_path)
    assert any(line.startswith("M3") for line in hard)


def test_rollout_switch_off_is_a_warning_not_a_failure(monkeypatch, tmp_path):
    v = _validator()

    def run(cmd, **_kw):
        if "validate" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout='{"success": true}', stderr="")
        return subprocess.CompletedProcess(cmd, 1, stdout="claude plugin test: hooks modules are turned off in this process", stderr="")

    monkeypatch.setattr(v.shutil, "which", lambda _name: "claude")
    monkeypatch.setattr(v.subprocess, "run", run)
    warn: list[str] = []
    assert v.cli_problems("demo", True, True, tmp_path, warn=warn) == []
    assert warn and "rollout switch" in warn[0]
