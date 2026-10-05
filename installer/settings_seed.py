"""settings_seed.py — keep what a user already has in settings.json on the FIRST install.

The workbench renders settings.json from a template, so an existing file used to be replaced
with only a rotating backup left (Santa installer review). Instead:

* ``is_workbench_file``   True when the file is one we rendered (its hooks run our dispatch.py);
* ``seed_overlay``        the user's own keys as a ``settings.user.json`` overlay: env keys the
                          template lacks (and provider / proxy / auth-like keys on a clash, where the
                          user's value wins), ``apiKeyHelper``, ``model``, ``permissions.defaultMode``,
                          other top-level keys, and hook entries the template does not have;
* ``append_hooks``        how ``render`` applies overlay hooks: after the workbench's, never twice.

Anything naming the banned lean-ctx substring is lean-ctx's own injection and is never seeded.
Pure stdlib.
"""
from __future__ import annotations

import copy
import re

_BANNED = "lean-ctx"
_PROVIDER = re.compile(r"^(ANTHROPIC_|AWS_|CLAUDE_CODE_USE_|CLOUD_ML_|GOOGLE_|VERTEX_|AZURE_|NODE_EXTRA_CA)"
                       r"|PROXY|API_KEY|TOKEN|BASE_URL|CA_CERTS", re.I)
_HANDLED = frozenset({"env", "hooks", "permissions", "enabledPlugins", "extraKnownMarketplaces"})


def _commands(groups) -> set[str]:
    return {str(h.get("command")) for g in groups or [] if isinstance(g, dict)
            for h in g.get("hooks") or [] if isinstance(h, dict) and h.get("command")}


def is_workbench_file(data: dict) -> bool:
    hooks = data.get("hooks") if isinstance(data, dict) else None
    return isinstance(hooks, dict) and any(
        "hooks/dispatch.py" in c for groups in hooks.values() for c in _commands(groups))


def seed_overlay(user: dict, rendered: dict, skip: frozenset = frozenset()) -> dict:
    """The overlay that re-creates ``user``'s own settings on top of ``rendered``."""
    out: dict = {}
    renv = rendered.get("env") if isinstance(rendered.get("env"), dict) else {}
    uenv = user.get("env") if isinstance(user.get("env"), dict) else {}
    env = {k: v for k, v in uenv.items() if _BANNED not in f"{k}{v}"
           and (k not in renv or (_PROVIDER.search(k) and v != renv[k]))}
    if env:
        out["env"] = env
    for k, v in user.items():
        if k in _HANDLED or k in skip or _BANNED in f"{k}{v}":
            continue
        if k not in rendered or (k in ("apiKeyHelper", "model") and v != rendered.get(k)):
            out[k] = copy.deepcopy(v)
    perms, rperms = user.get("permissions"), rendered.get("permissions") or {}
    mode = perms.get("defaultMode") if isinstance(perms, dict) else None
    if mode and mode != rperms.get("defaultMode"):
        out["permissions"] = {"defaultMode": mode}
    hooks: dict = {}
    for event, groups in (user.get("hooks") if isinstance(user.get("hooks"), dict) else {}).items():
        have = _commands((rendered.get("hooks") or {}).get(event))
        kept = []
        for g in groups if isinstance(groups, list) else []:
            items = [h for h in (g.get("hooks") or []) if isinstance(h, dict)
                     and h.get("command") not in have and _BANNED not in str(h)] if isinstance(g, dict) else []
            if items:
                kept.append({**g, "hooks": items})
        if kept:
            hooks[event] = kept
    if hooks:
        out["hooks"] = hooks
    return out


def append_hooks(base: dict, extra: dict) -> dict:
    """``base`` hooks plus the overlay's groups after them; a group already present is not repeated."""
    out = copy.deepcopy(base) if isinstance(base, dict) else {}
    for event, groups in (extra or {}).items():
        lst = out.setdefault(event, [])
        lst += [g for g in groups if g not in lst]
    return out
