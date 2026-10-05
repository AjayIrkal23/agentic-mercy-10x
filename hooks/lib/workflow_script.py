"""workflow_script.py — pure script surgery for hooks/workflow-model-guard.py.

meta_end_index: where the `export const meta = {...}` declaration ends, or None.
build_wrapper:  the injected `__wfAgent` JS wrapper that pins agent() models.
No I/O, no policy reads: the guard passes the agent sets in.
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


def build_wrapper(forced: str | None, sonnet_agents: list[str], opus_agents: list[str],
                  fable_agents: list[str]) -> str:
    """The `__wfAgent` wrapper. Arg-drop safe: every trailing arg is forwarded via
    `...rest`, and a 2nd arg that is not a plain object passes through untouched."""
    forced_js = f"'{forced}'" if forced else "null"
    return (
        "\n/* injected by workflow-model-guard: default subagents to sonnet */\n"
        "const __wfOrigAgent = agent;\n"
        "const __wfForce = " + forced_js + ";\n"
        "const __wfFableAgents = new Set(" + json.dumps(fable_agents) + ");\n"
        "const __wfOpusAgents = new Set(" + json.dumps(opus_agents) + ");\n"
        "const __wfSonnetAgents = new Set(" + json.dumps(sonnet_agents) + ");\n"
        "const __wfAgent = (p, opts, ...rest) => {\n"
        "  if (opts !== undefined && (typeof opts !== 'object' || Array.isArray(opts))) {\n"
        "    return __wfOrigAgent(p, opts, ...rest);\n"
        "  }\n"
        "  const o = opts ? { ...opts } : {};\n"
        "  if (__wfForce) { o.model = __wfForce; return __wfOrigAgent(p, o, ...rest); }\n"
        "  if (!o.model) {\n"
        "    const at = (o.agentType || '').toLowerCase();\n"
        "    if (__wfFableAgents.has(at)) o.model = 'fable';\n"
        "    else if (__wfOpusAgents.has(at)) o.model = 'opus';\n"
        "    else if (__wfSonnetAgents.has(at)) o.model = 'sonnet';\n"
        "    else o.model = 'sonnet';\n"
        "  }\n"
        "  return __wfOrigAgent(p, o, ...rest);\n"
        "};\n"
    )
