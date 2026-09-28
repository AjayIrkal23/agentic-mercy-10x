"""test_template_contract.py — the settings template + install manifest contract (WP-11).

Fresh-machine invariants: the template has no MCP block, no home literal, no
"lean-ctx" string (lean-ctx >= 3.10 re-injects hooks into any settings.json that
mentions it), registers every dispatch event, and enables exactly the manifest's
plugins; the lean-ctx config merge sets the required keys without clobbering.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

TEXT = (_ROOT / "settings.template.json").read_text(encoding="utf-8")
TMPL = json.loads(TEXT)
MANIFEST = json.loads((_ROOT / "installer" / "manifest.json").read_text(encoding="utf-8"))


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, _ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore
    return mod


def test_template_is_portable_and_leanctx_free():
    assert "mcpServers" not in TMPL and "model" not in TMPL
    assert not re.search(r"/home/[A-Za-z0-9._-]+/|/Users/[A-Za-z0-9._-]+/", TEXT)
    assert "lean-ctx" not in TEXT
    assert TMPL["permissions"]["deny"] == []
    assert "statusLine" not in TMPL


def test_template_registers_every_dispatch_event():
    want = {"PreToolUse", "PostToolUse", "PostToolUseFailure", "UserPromptSubmit", "SessionStart",
            "SubagentStart", "SubagentStop", "TeammateIdle", "Stop", "PreCompact", "PostCompact",
            "ConfigChange", "SessionEnd"}
    assert want <= set(TMPL["hooks"])
    for groups in TMPL["hooks"].values():
        for g in groups:
            for h in g["hooks"]:
                assert h["command"].startswith("{{PYTHON}} {{CLAUDE_DIR}}/hooks/")


def test_env_and_marketplaces():
    env = TMPL["env"]
    assert env["CLAUDE_CODE_SUBAGENT_MODEL"] == "sonnet"
    assert env["RETICLE_TELEMETRY"] == "0"
    assert re.fullmatch(env["PONYTAIL_SUBAGENT_MATCHER"], "implementation-engineer")
    assert not re.search(env["PONYTAIL_SUBAGENT_MATCHER"], "Explore")
    mk = TMPL["extraKnownMarketplaces"]
    assert "claude-mermaid" not in mk
    for name in ("ponytail", "nateherk", "karpathy-skills", "superpowers-marketplace"):
        assert mk[name]["autoUpdate"] is True, name


def test_enabled_plugins_equal_manifest():
    enabled = {k for k, v in TMPL["enabledPlugins"].items() if v}
    declared = {p["id"] for p in MANIFEST["plugins"]["install"]}
    assert enabled == declared
    assert "pyright-lsp@claude-plugins-official" in enabled
    assert not {p for p in enabled if p.split("@")[0] in
                {"claude-mermaid", "clickhouse", "context7", "playwright", "double-shot-latte"}}


def test_leanctx_merge_sets_keys_and_keeps_the_rest(tmp_path):
    deps = _load("deps", "installer/deps.py")
    req = deps.leanctx_required()
    src = ('shell_allowlist_extra = ["claude"]\nshadow_mode = true\n\n'
           '[setup]\nauto_update_mcp = true\n\n[gain]\nlast = "x"\n')
    out = deps.merge_leanctx_text(src, req)
    p = tmp_path / "config.toml"
    p.write_text(out)
    assert deps.leanctx_config_gaps(req, p) == []
    assert 'shell_allowlist_extra = ["claude"]' in out and '[gain]\nlast = "x"' in out
    assert deps.merge_leanctx_text(out, req) == out  # idempotent
    p.write_text(src)
    assert "root.shadow_mode" in deps.leanctx_config_gaps(req, p)
