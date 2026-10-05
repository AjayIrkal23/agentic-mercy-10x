"""WP1 MCP availability fixes (audit 2026-10-05 G-03, G-14).

G-03  a server the user disabled for this project (``~/.claude.json``
      projects[root].disabledMcpServers) is not recommended; route targets that can
      never match an installed server (``plugin:context7``, ``plugin:playwright``) are gone.
G-14  browser verification names reticle only when the repo carries reticle
      instrumentation; otherwise playwright (router route and mcp-post-hints).
Runnable: `python3 -m pytest hooks/tests/test_router_wp1_mcp.py -q`.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys

HOOKS = pathlib.Path(__file__).resolve().parents[1]
if str(HOOKS) not in sys.path:
    sys.path.insert(0, str(HOOKS))

from prompt_router import classify as C              # noqa: E402
from prompt_router.modules import mcp_routes as MR   # noqa: E402

_spec = importlib.util.spec_from_file_location("mcp_post_hints_wp1", HOOKS / "mcp-post-hints.py")
H = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(H)  # type: ignore[union-attr]


def _root(tmp_path, reticle=False) -> pathlib.Path:
    r = tmp_path / ("ret" if reticle else "plain")
    (r / "src" / "components").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(r)], check=True)
    deps = {"react": "^19", "vite": "^7"}
    dev = {"@reticlehq/vite": "^1"} if reticle else {}
    (r / "package.json").write_text(json.dumps({"dependencies": deps, "devDependencies": dev}))
    return r


def test_reticle_instrumentation_is_detected(tmp_path):
    assert not MR.reticle_instrumented(str(_root(tmp_path)))
    assert MR.reticle_instrumented(str(_root(tmp_path, reticle=True)))


def _browser(monkeypatch, root) -> str:
    monkeypatch.setattr(MR, "available_servers", lambda: {"reticle", "playwright"})
    monkeypatch.setattr(MR, "needs_auth", lambda: set())
    monkeypatch.setattr(MR, "dev_server_port", lambda: 5173)
    prof = C.TaskProfile(text="take a screenshot, it looks wrong in the browser", intents={"QA": 2})
    ctx = {"repo": type("R", (), {"root": str(root)})()}
    return next(it["text"] for it in MR.items(prof, ctx) if it["id"] == "mcp:browser")


def test_browser_route_prefers_playwright_without_reticle_instrumentation(tmp_path, monkeypatch):
    txt = _browser(monkeypatch, _root(tmp_path))
    assert "playwright" in txt and "reticle" not in txt.lower()


def test_browser_route_uses_reticle_when_instrumented(tmp_path, monkeypatch):
    assert "reticle" in _browser(monkeypatch, _root(tmp_path, reticle=True))


def test_project_disabled_server_is_not_available(tmp_path, monkeypatch):
    root = str(tmp_path)
    monkeypatch.setattr(MR, "available_servers", lambda: {"jcodemunch", "graphify"})
    monkeypatch.setattr(MR, "needs_auth", lambda: set())
    monkeypatch.setattr(MR, "_user_cfg", lambda: {"projects": {root: {"disabledMcpServers": ["jcodemunch"]}}})
    assert MR.server_available(["jcodemunch"], root) is None
    assert MR.server_available(["graphify"], root) == "graphify"


def test_no_route_targets_dead_plugin_server_names():
    names = {s for r in MR.routes() for s in (r.get("server") or [])}
    assert not {"plugin:context7", "plugin:playwright"} & names


def test_post_hint_names_playwright_in_a_repo_without_reticle(tmp_path, monkeypatch):
    from lib import code_files
    monkeypatch.setattr(code_files, "is_code_file",
                        lambda p: pathlib.Path(str(p)).suffix in code_files.CODE_EXTENSIONS)
    monkeypatch.setattr(H, "_server", lambda name: name in {"reticle", "playwright"})
    monkeypatch.setattr(H, "_dev_port", lambda: 5173)
    fp = _root(tmp_path) / "src" / "components" / "Card.tsx"
    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(fp), "old_string": "", "new_string": "x"}}
    hint = next(h for h in H.hints(payload, {}) if ":5173" in h)
    assert "playwright" in hint and "reticle" not in hint.lower()
