"""asset_auth.py — one login line per session when an asset server is registered but
waiting on OAuth (autonomy plan 2026-10-05, WP-C item 3).

The always-on rules push Higgsfield for every raster/video/3D/audio asset; while
``mcp-needs-auth-cache.json`` lists it, the model either fails the tool or stalls. For an
asset-looking prompt this emits ONE line (the router manifest dedups the id per session):
ask the user once, batched with any other pending login, to connect the Higgsfield
connector in claude.ai (OpenArt stays a user-scope server: its authenticate tool), say
assets are pending meanwhile, never fall back to placeholders. The rule fires only while
the user-scope ``higgsfield`` is registered AND needs auth; once it is removed the line
retires itself. Cache and registry are read through ``mcp_routes`` (key names only).
Pure stdlib; fail-open to [].
"""
from __future__ import annotations

import re

_ASSET = re.compile(
    r"\b(?:images?|photos?|pictures?|illustrations?|logos?|banners?|thumbnails?|favicons?|"
    r"artwork|textures?|mock-?ups?|videos?|animations?|3d (?:models?|assets?|elements?)|glb|"
    r"audio|sound effects?|sfx|music|og image|hero (?:image|video|section)|"
    r"background (?:image|video|loop)|assets?)\b", re.IGNORECASE)
_SERVERS = ("higgsfield", "openart")
_AUTH_TOOL = {"openart": "mcp__openart__authenticate"}  # higgsfield: the claude.ai connector


def _waiting(needs: set, avail: set) -> list[str]:
    return [s for s in _SERVERS
            if s in avail and any(k == s or k.startswith(s + ":") for k in needs)]


def item(profile, ctx: dict | None = None) -> list[dict]:
    """The login line as a router item, or []. Only Higgsfield triggers it; OpenArt joins
    the same line when it also waits (one batched ask)."""
    try:
        if not _ASSET.search(getattr(profile, "text", "") or ""):
            return []
        from prompt_router.modules import mcp_routes as _mcp  # noqa: PLC0415
        waiting = _waiting(_mcp.needs_auth(), _mcp.available_servers())
        if "higgsfield" not in waiting:
            return []
        text = ("Higgsfield needs a one-time login: ask the user once (batched with any other "
                "login) to connect the Higgsfield connector in claude.ai (tools "
                "mcp__claude_ai_higgsfield__*); until then say assets are pending, no placeholders.")
        if "openart" in waiting:
            text += f" OpenArt waits too: {_AUTH_TOOL['openart']} in the same ask."
        return [{"id": "route:higgsfield-auth", "tier": 3, "section": "ROUTING", "text": text}]
    except Exception:  # noqa: BLE001
        return []


__all__ = ["item"]
