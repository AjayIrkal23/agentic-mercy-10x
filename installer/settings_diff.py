"""settings_diff.py — pure settings-JSON helpers behind render.py (tokenize, overlay merge,
and the semantic comparison of ``render.py --check``). Split out of render.py to keep it
under the 250-line limit; render re-exports ``tokenize`` and ``deep_merge``. Pure stdlib."""
from __future__ import annotations

import copy
import os

# Ordered so the longest/most-specific literal is tokenized first.
# (live literal, token) — tokenize replaces literal->token; render replaces token->value.
_TOKEN_MAP = [
    ("${HOME}/.local/bin/lean-ctx", "{{LEANCTX}}"),
    ("${HOME}/.claude", "{{CLAUDE_DIR}}"),
    ("python3 ", "{{PYTHON}} "),
    ("${HOME}/.local/bin/node", "{{NODE}}"),
    ("/usr/bin/node", "{{NODE}}"),
]


def tokenize(text: str) -> str:
    """Live settings.json text -> tokenized template text."""
    for literal, token in _TOKEN_MAP:
        text = text.replace(literal, token)
    return text


def deep_merge(base: dict, overlay: dict) -> dict:
    """Recursive dict merge; overlay (user) wins. Non-dict values replace."""
    out = copy.deepcopy(base)
    for k, v in overlay.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def diff_paths(a, b, path="") -> list[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        out: list[str] = []
        for k in sorted(set(a) | set(b)):
            out += diff_paths(a.get(k, "<absent>"), b.get(k, "<absent>"), f"{path}.{k}" if path else k)
        return out
    return [] if a == b else [path or "<root>"]


def plugin_dirs_set(value, sep: str = os.pathsep) -> list[str]:
    """CLAUDE_CODE_PLUGIN_DIRS as a sorted set: order, `~` and slash style never cause a diff."""
    parts = str(value or "").split(sep)
    return sorted({os.path.normcase(os.path.normpath(os.path.expanduser(p.strip()))) for p in parts if p.strip()})


def normalized(data: dict, managed: frozenset, plugin_key: str, sep: str = os.pathsep) -> dict:
    out = {k: v for k, v in data.items() if k not in managed}
    env = out.get("env")
    if isinstance(env, dict) and plugin_key in env:
        out["env"] = {**env, plugin_key: plugin_dirs_set(env[plugin_key], sep)}
    return out


# Added by the user or by Claude Code on their behalf (/plugin, the permission dialog): a
# re-render unions them with the template's; the check ignores entries the template lacks.
_BANNED = "lean-ctx"  # see render.FORBIDDEN_SUBSTRING: its first run injects hooks + allow rules
ADDITIVE_RULES = ("allow", "deny", "ask")
ADDITIVE_MAPS = ("enabledPlugins", "extraKnownMarketplaces")


def carry(text: str, existing, managed: frozenset) -> str:
    """Rendered ``text`` plus what ``existing`` (the live settings.json) holds that the
    template does not own: the Claude-managed keys, permission rules (union) and plugin /
    marketplace entries the template does not define (the template wins a shared key)."""
    import json
    from pathlib import Path
    try:
        old = json.loads(Path(existing).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return text
    data = json.loads(text)
    for k in managed & set(old):
        data[k] = old[k]
    oldp = old.get("permissions") if isinstance(old.get("permissions"), dict) else {}
    for k in ADDITIVE_RULES:  # entries naming the banned tool are lean-ctx's own injection: never carried
        extra = [x for x in (oldp.get(k) or []) if _BANNED not in str(x)] if isinstance(oldp.get(k), list) else []
        if extra:
            perms = data.setdefault("permissions", {})
            perms[k] = list(dict.fromkeys([*(perms.get(k) or []), *extra]))
    for k in ADDITIVE_MAPS:
        extra = old.get(k)
        if isinstance(extra, dict) and extra:
            mine = data.get(k) or {}
            data[k] = {**mine, **{n: v for n, v in extra.items() if n not in mine and _BANNED not in n}}
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def without_additions(live: dict, rendered: dict) -> dict:
    """``live`` minus what the user added on top of ``rendered`` (see ADDITIVE_*)."""
    out = copy.deepcopy(live)
    for k in ADDITIVE_MAPS:
        if isinstance(out.get(k), dict) and isinstance(rendered.get(k), dict):
            out[k] = {n: v for n, v in out[k].items() if n in rendered[k]}
    perms, ref = out.get("permissions"), rendered.get("permissions")
    if isinstance(perms, dict):
        for k in ADDITIVE_RULES:
            if isinstance(perms.get(k), list):
                perms[k] = [x for x in perms[k] if x in ((ref or {}).get(k) or [])]
    return out


def prune_empty_rules(data: dict) -> dict:
    """Copy of ``data`` without empty permission rule lists (``[]`` and absent compare equal)."""
    out = copy.deepcopy(data)
    perms = out.get("permissions")
    if isinstance(perms, dict):
        for k in ADDITIVE_RULES:
            if perms.get(k) == []:
                del perms[k]
    return out
