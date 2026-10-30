"""workflow_script.py — pure script surgery for hooks/workflow-model-guard.py.

meta_end_index: where the `export const meta = {...}` declaration ends, or None.
build_wrapper:  the injected `__wfAgent` JS wrapper that pins agent() models per role and tier.
No I/O, no policy reads: the guard passes precomputed tables in (cfg).
"""
from __future__ import annotations

import json
import re

META_RE = re.compile(r"export\s+const\s+meta\s*=\s*\{")


def meta_end_index(script: str) -> int | None:
    """Index just past the meta declaration (closing brace + optional `;`), or None
    when it can't be located safely. Brace-matches from the meta object's `{`, skipping
    braces inside string literals (', ", `); meta is a pure literal."""
    m = META_RE.search(script)
    if not m:
        return None
    i = m.end() - 1  # position of the opening '{'
    depth = 0
    n = len(script)
    quote: str | None = None
    while i < n:
        c = script[i]
        if quote is not None:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in ("'", '"', "`"):
            quote = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                j = i + 1
                while j < n and script[j] in " \t":
                    j += 1
                if j < n and script[j] == ";":
                    j += 1
                return j
        i += 1
    return None


def build_wrapper(cfg: dict) -> str:
    """The `__wfAgent` wrapper. The guard precomputes every table; the JS only looks up.

    cfg = {"forced": str|None, "roles": {agent: role}, "labels": {prefix: role}, "default_role": str,
           "models": {role: model}, "models_up": {role: model}, "escalated": bool,
           "retry_markers": [regex], "explicit": {model: model}, "tier": str, "usage": bool}.
    models/models_up already include the usage step-down and the tier ceiling; explicit maps an
    opts.model the script passes to what it may run as. A label matches a labels key when one of its
    word tokens equals or starts with that key (`review:pkg`, `integrator`; not `preview`). A call
    whose prompt matches a retry marker takes models_up (per call; `escalated` lifts every call). A
    marker JS cannot compile is skipped. Arg-drop safe: every trailing arg is forwarded via `...rest`,
    and a 2nd arg that is not a plain object passes through untouched."""
    j = json.dumps
    return (
        "\n/* injected by workflow-model-guard: plan-tier " + str(cfg.get("tier"))
        + (" (usage-guard)" if cfg.get("usage") else "") + " */\n"
        "const __wfOrigAgent = agent;\n"
        f"const __wfForce = {j(cfg.get('forced'))};\n"
        f"const __wfRoles = {j(cfg.get('roles') or {})};\n"
        f"const __wfLabels = {j(cfg.get('labels') or {})};\n"
        f"const __wfModels = {j(cfg.get('models') or {})};\n"
        f"const __wfModelsUp = {j(cfg.get('models_up') or {})};\n"
        f"const __wfEscalated = {j(bool(cfg.get('escalated')))};\n"
        f"const __wfRetry = {j([str(s) for s in cfg.get('retry_markers') or []])}"
        ".flatMap((s) => { try { return [new RegExp(s, 'i')]; } catch (e) { return []; } });\n"
        f"const __wfExplicit = {j(cfg.get('explicit') or {})};\n"
        f"const __wfDefaultRole = {j(cfg.get('default_role') or 'default')};\n"
        "const __wfRole = (o) => {\n"
        "  const at = String(o.agentType || '').toLowerCase();\n"
        "  if (at && __wfRoles[at]) return __wfRoles[at];\n"
        "  const toks = String(o.label || '').toLowerCase().split(/[^a-z]+/).filter(Boolean);\n"
        "  for (const k in __wfLabels) { if (toks.some((t) => t.startsWith(k))) return __wfLabels[k]; }\n"
        "  return __wfDefaultRole;\n"
        "};\n"
        "const __wfAgent = (p, opts, ...rest) => {\n"
        "  if (opts !== undefined && (typeof opts !== 'object' || Array.isArray(opts))) {\n"
        "    return __wfOrigAgent(p, opts, ...rest);\n"
        "  }\n"
        "  const o = opts ? { ...opts } : {};\n"
        "  if (__wfForce) { o.model = __wfForce; return __wfOrigAgent(p, o, ...rest); }\n"
        "  const role = __wfRole(o);\n"
        "  if (o.model) { o.model = __wfExplicit[String(o.model).toLowerCase()] || __wfModels[role] || 'sonnet'; }\n"
        "  else {\n"
        "    const esc = __wfEscalated || __wfRetry.some((r) => r.test(String(p)));\n"
        "    o.model = (esc && __wfModelsUp[role]) || __wfModels[role] || 'sonnet';\n"
        "  }\n"
        "  return __wfOrigAgent(p, o, ...rest);\n"
        "};\n"
    )
