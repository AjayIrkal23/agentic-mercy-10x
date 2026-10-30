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
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
TIER_FILTER = '"kind": ?"tier"'  # grep -E; json.dumps writes "kind": "tier"
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


# --- M7 monitors (hooks-hygiene-mod step 22) --------------------------------------- #
def _demo(tmp_path, plugin_extra: dict, monitors_file=None):
    folder = tmp_path / "mods" / "demo"
    (folder / ".claude-plugin").mkdir(parents=True)
    (folder / "hooks").mkdir()
    (folder / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "demo", **plugin_extra}), encoding="utf-8")
    (folder / "hooks" / "hooks.json").write_text(json.dumps({"modules": ["./register.ts"]}), encoding="utf-8")
    (folder / "hooks" / "register.ts").write_text("export const register = () => {}\n", encoding="utf-8")
    (folder / "x.test.ts").write_text("", encoding="utf-8")
    if monitors_file is not None:
        (folder / "monitors").mkdir()
        (folder / "monitors" / "monitors.json").write_text(json.dumps(monitors_file), encoding="utf-8")
    return tmp_path


def test_m7_monitors_contract(tmp_path):
    v = _validator()
    ok = [{"name": "oomguard", "command": f"tail -n0 -F \"$HOME/.claude/state/oomguard.events\" | grep -E --line-buffered '{TIER_FILTER}'",
           "description": "memory tier changes", "when": "always"}]
    assert v.static_problems("demo", _demo(tmp_path / "a", {"experimental": {"monitors": ok}}))[0] == []
    # the old literal never matched json.dumps output ("kind": "tier"), so it is refused
    old_literal = [{**ok[0], "command": "tail -n0 -F \"$HOME/.claude/state/oomguard.events\" | grep --line-buffered '\"kind\":\"tier\"'"}]
    assert any("tier filter" in line for line in v.static_problems("demo", _demo(tmp_path / "g", {"experimental": {"monitors": old_literal}}))[0])
    bad_cfg = [{**ok[0], "command": "tail ${user_config.path} '\"kind\":\"tier\"'"}]
    assert any(line.startswith("M7") for line in v.static_problems("demo", _demo(tmp_path / "b", {"experimental": {"monitors": bad_cfg}}))[0])
    no_filter = [{**ok[0], "command": "tail -n0 -F \"$HOME/.claude/state/oomguard.events\""}]
    assert any("tier filter" in line for line in v.static_problems("demo", _demo(tmp_path / "c", {"experimental": {"monitors": no_filter}}))[0])
    unknown_key = [{**ok[0], "extra": 1}]
    assert any(line.startswith("M7") for line in v.static_problems("demo", _demo(tmp_path / "d", {"experimental": {"monitors": unknown_key}}))[0])
    bad_when = [{**ok[0], "when": "sometimes"}]
    assert any(line.startswith("M7") for line in v.static_problems("demo", _demo(tmp_path / "f", {"experimental": {"monitors": bad_when}}))[0])
    assert v.static_problems("demo", _demo(tmp_path / "e", {}, monitors_file=ok))[0] == []      # monitors/monitors.json form


def test_mercy_declares_the_oomguard_monitor():
    plugin = json.loads((_ROOT / "mods/mercy/.claude-plugin/plugin.json").read_text(encoding="utf-8"))
    decl = (plugin.get("experimental") or {}).get("monitors")
    if decl is None and (_ROOT / "mods/mercy/monitors/monitors.json").is_file():
        decl = json.loads((_ROOT / "mods/mercy/monitors/monitors.json").read_text(encoding="utf-8"))
    assert any(m["name"] == "oomguard" and TIER_FILTER in m["command"] and "grep -E" in m["command"] for m in decl or [])


def test_oomguard_filter_matches_a_real_memwatch_event(tmp_path):
    """The monitor's grep stage must pass the line memwatch_state.append_event writes."""
    if not shutil.which("grep"):
        pytest.skip("no grep on PATH")
    sys.path.insert(0, str(_ROOT / "hooks"))
    try:
        from lib import memwatch_state
    finally:
        sys.path.remove(str(_ROOT / "hooks"))
    events = tmp_path / "oomguard.events"
    assert memwatch_state.append_event({"kind": "tier", "level": "warn"}, path=events)
    assert memwatch_state.append_event({"kind": "shed", "pid": 1}, path=events)
    text = events.read_text(encoding="utf-8")
    hit = subprocess.run(["grep", "-E", "--line-buffered", TIER_FILTER], input=text, capture_output=True, text=True)
    assert hit.returncode == 0 and hit.stdout.count("\n") == 1 and '"tier"' in hit.stdout
    # compact separators match too
    compact = subprocess.run(["grep", "-E", TIER_FILTER], input='{"kind":"tier"}\n', capture_output=True, text=True)
    assert compact.returncode == 0
