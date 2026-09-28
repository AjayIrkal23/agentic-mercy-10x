"""mcp_routes.py — availability-aware MCP pointers for the prompt router.

Driven by ``hooks/tool-intelligence.json`` -> ``mcp_routes``:

  {id, when: {intents:[...], regex:"...", surfaces:[...], all:bool}, server: [names],
   tools:[...], text:"...", guard:"" | "dev_server_listening" | "not_in_repo_symbol",
   once_per:"session" | "match"}

A route fires when ANY ``when`` condition holds (``all: true`` requires every
listed condition), its guard passes, and its server is available: present in
``~/.claude.json`` ``mcpServers`` (or an enabled plugin, ``plugin:<name>``, or the
active repo's project scope: ``.mcp.json`` / ``projects[root].mcpServers``) and
NOT listed in ``~/.claude/mcp-needs-auth-cache.json``. One line per route, at
most ``max_mcp_routes`` per prompt. Never starts anything: the browser guard
only PROBES for a listening dev-server port (``ss -ltn``).

Pure stdlib; fail-open to no items.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

_HOOKS = Path(__file__).resolve().parents[2]
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))

_TOOLMAP = _HOOKS / "tool-intelligence.json"
_CLAUDE = _HOOKS.parent
MAX_ROUTES = 4

# ponytail: dev-server heuristic = a listener on a conventional dev port. Excludes
# 3025 (browser-tools companion). Upgrade path: read the project's package.json
# scripts / vite.config port if this misfires.
_DEV_PORT_RANGES = ((3000, 3999), (4173, 4173), (4200, 4200), (5000, 5010), (5173, 5199),
                    (8000, 8099), (8080, 8090), (9000, 9010))
_NOT_DEV_PORTS = {3025}


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


@lru_cache(maxsize=1)
def routes() -> list[dict]:
    r = _load_json(_TOOLMAP).get("mcp_routes")
    return [x for x in r if isinstance(x, dict)] if isinstance(r, list) else []


@lru_cache(maxsize=1)
def available_servers() -> set[str]:
    """User-scope MCP servers + enabled plugins (as ``plugin:<name>``)."""
    names: set[str] = set()
    names.update(str(k) for k in (_load_json(Path.home() / ".claude.json").get("mcpServers") or {}))
    plugins = _load_json(_CLAUDE / "settings.json").get("enabledPlugins") or {}
    for key, on in plugins.items():
        if on:
            names.add("plugin:" + str(key).split("@", 1)[0])
    return names


@lru_cache(maxsize=1)
def needs_auth() -> set[str]:
    return {str(k) for k in _load_json(_CLAUDE / "mcp-needs-auth-cache.json")}


@lru_cache(maxsize=8)
def project_servers(root: str) -> set[str]:
    """Project-scoped servers for a repo: ``<root>/.mcp.json`` (minus
    ``disabledMcpjsonServers``) + local scope ``~/.claude.json projects[root]``.
    Lets per-project servers (read-only DB MCPs) route only where connected."""
    entry = (_load_json(Path.home() / ".claude.json").get("projects") or {}).get(root) or {}
    names = {str(k) for k in (entry.get("mcpServers") or {})}
    disabled = {str(x) for x in (entry.get("disabledMcpjsonServers") or [])}
    names.update(str(k) for k in (_load_json(Path(root) / ".mcp.json").get("mcpServers") or {})
                 if str(k) not in disabled)
    return names


def server_available(servers, root: str | None = None) -> str | None:
    """First server name (from the route's list) that is registered (user scope,
    plugin, or — given ``root`` — project scope) and not waiting on auth, else None."""
    if isinstance(servers, str):
        servers = [servers]
    avail, auth = available_servers(), needs_auth()
    if root:
        avail = avail | project_servers(str(root))
    for s in servers or []:
        s = str(s)
        if s not in avail:
            continue
        if any(a == s or a.startswith(s + ":") for a in auth):
            continue
        return s
    return None


@lru_cache(maxsize=1)
def dev_server_port() -> int | None:
    """A listening dev-server port, or None. Probes only — never starts one."""
    try:
        cp = subprocess.run(["ss", "-ltn"], capture_output=True, text=True, timeout=1.0, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    ports: set[int] = set()
    for line in cp.stdout.splitlines():
        m = re.search(r":(\d+)\s+\S+:\*", line)
        if m:
            try:
                ports.add(int(m.group(1)))
            except ValueError:
                pass
    for p in sorted(ports):
        if p in _NOT_DEV_PORTS:
            continue
        if any(lo <= p <= hi for lo, hi in _DEV_PORT_RANGES):
            return p
    return None


def _match(route: dict, profile) -> tuple[bool, str]:
    """(fires, matched_token)."""
    when = route.get("when") or {}
    checks: list[bool] = []
    token = ""
    intents = set(when.get("intents") or [])
    if intents:
        checks.append(bool(intents & set(profile.intents)))
    surfaces = set(when.get("surfaces") or [])
    if surfaces:
        checks.append(bool(surfaces & set(profile.surfaces)))
    rx = when.get("regex")
    if rx:
        try:
            m = re.search(str(rx), profile.text, re.IGNORECASE)
        except re.error:
            m = None
        if m:
            token = next((g for g in m.groups() if g), m.group(0))
        checks.append(bool(m))
    if not checks:
        return False, ""
    ok = all(checks) if when.get("all") else any(checks)
    return ok, token


def _guard_ok(route: dict, token: str, ctx: dict) -> dict:
    """{} when the guard blocks, else a dict of format vars."""
    guard = route.get("guard") or ""
    if not guard:
        return {"ok": True}
    if guard == "dev_server_listening":
        port = dev_server_port()
        return {"ok": True, "port": port} if port else {}
    if guard == "not_in_repo_symbol":
        repo = ctx.get("repo")
        root = getattr(repo, "root", None) if repo is not None else None
        if root and token:
            try:
                from prompt_router.modules import code_intel as _ci  # noqa: PLC0415
                if _ci.is_repo_symbol(str(root), token):
                    return {}
            except Exception:  # noqa: BLE001
                pass
        return {"ok": True}
    return {"ok": True}


def items(profile, ctx: dict, *, max_routes: int = MAX_ROUTES) -> list[dict]:
    """Router items (section ROUTING, tier 3) for the MCP routes that apply."""
    out: list[dict] = []
    try:
        root = getattr(ctx.get("repo"), "root", None)
        for route in routes():
            if len(out) >= max_routes:
                break
            fires, token = _match(route, profile)
            if not fires:
                continue
            server = server_available(route.get("server"), root)
            if not server:
                continue
            g = _guard_ok(route, token, ctx)
            if not g:
                continue
            text = str(route.get("text") or "")
            try:
                text = text.format(server=server, token=token, port=g.get("port", ""))
            except (KeyError, IndexError, ValueError):
                pass
            rid = f"mcp:{route.get('id', server)}"
            if route.get("once_per") == "match" and token:
                rid += ":" + re.sub(r"[^\w.-]", "_", token.lower())[:32]
            out.append({"id": rid, "tier": 3, "section": "ROUTING", "text": text})
    except Exception:  # noqa: BLE001
        return out
    return out


__all__ = ["items", "routes", "available_servers", "project_servers", "needs_auth",
           "server_available", "dev_server_port"]
