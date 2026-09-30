#!/usr/bin/env python3
"""render.py — settings.json is a RENDERED ARTIFACT (P6-T3 / P6-T5).

``settings.json`` = ``settings.template.json`` (tokenized) ⊕ optional
``settings.user.json`` (per-machine overlay, user wins) with the interpreter/
path tokens substituted for this OS. This makes one template serve Windows and
Ubuntu, and makes ``git pull`` unable to clobber local settings deltas (they live
in the gitignored user overlay + the gitignored rendered output).

Tokens:
    {{PYTHON}}      python invocation      (e.g. "python3", "py -3", or a Windows python.exe path)
    {{NODE}}        node interpreter       (e.g. "/usr/bin/node", "node")
    {{CLAUDE_DIR}}  the ~/.claude dir path (kept as the literal ``${HOME}/.claude``
                    on POSIX so Claude Code expands it; a concrete path on Windows)
    {{LEANCTX}}     lean-ctx binary — supported, but the template must NOT use it:
                    render() refuses any output containing "lean-ctx" (see below).

The equivalence gate is SEMANTIC (parsed JSON, Claude-managed keys ignored), and a
write carries the existing Claude-managed keys (theme, tui, voice …) over.

CLI:
    render.py                      # render template(+overlay) -> settings.json
    render.py --check              # prove render(template) semantically == live settings.json
    render.py --emit-template      # (re)generate settings.template.json from live
    render.py --out PATH --template PATH --user PATH --dry-run
Pure stdlib. Windows+POSIX. Fail-loud on a broken template (a bad settings.json
is worse than an error).
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_LIVE = _ROOT / "settings.json"
_TEMPLATE = _ROOT / "settings.template.json"
_USER = _ROOT / "settings.user.json"

# Ordered so the longest/most-specific literal is tokenized first.
# (live literal, token) — tokenize replaces literal->token; render replaces token->value.
_TOKEN_MAP = [
    ("${HOME}/.local/bin/lean-ctx", "{{LEANCTX}}"),
    ("${HOME}/.claude", "{{CLAUDE_DIR}}"),
    ("python3 ", "{{PYTHON}} "),
    ("${HOME}/.local/bin/node", "{{NODE}}"),
    ("/usr/bin/node", "{{NODE}}"),
]

# Default substitution values == the live POSIX literals (equivalence gate).
_DEFAULT_SUBS = {
    "{{PYTHON}}": "python3",
    "{{NODE}}": "${HOME}/.local/bin/node",
    "{{CLAUDE_DIR}}": "${HOME}/.claude",
    "{{LEANCTX}}": "${HOME}/.local/bin/lean-ctx",
}

# Keys Claude Code itself writes into settings.json (/config, /theme, voice …).
# They are never rendered from the template and never compared: a re-render
# carries the existing live values over instead of clobbering them.
CLAUDE_MANAGED_KEYS = frozenset({
    "tui", "voice", "voiceEnabled", "theme", "remoteControlAtStartup",
    "agentPushNotifEnabled", "skipWorkflowUsageWarning", "autoCompactWindow",
    "contextWindow", "effortLevel", "skipDangerousModePermissionPrompt",
})

# lean-ctx >= 3.10 re-injects its own hooks / statusLine / permissions.deny into
# any settings.json that mentions it. The rendered file must never contain it
# (the dispatch matcher spells the MCP prefix as the regex `mcp__lean.ctx__`).
FORBIDDEN_SUBSTRING = "lean-ctx"


def tokenize(text: str) -> str:
    """Live settings.json text -> tokenized template text."""
    for literal, token in _TOKEN_MAP:
        text = text.replace(literal, token)
    return text


def substitute(text: str, subs: dict[str, str] | None = None) -> str:
    """Tokenized template text -> concrete settings text for this OS."""
    # accept detect()'s bare keys ("PYTHON") as well as "{{PYTHON}}"
    subs = {**_DEFAULT_SUBS, **{(k if k.startswith("{{") else "{{" + k + "}}"): v
                                for k, v in (subs or {}).items()}}
    for token, value in subs.items():
        text = text.replace(token, value)
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


def render(
    template_path: Path = _TEMPLATE,
    user_path: Path | None = _USER,
    subs: dict[str, str] | None = None,
) -> str:
    """Return the fully rendered settings.json TEXT (validated JSON)."""
    tmpl_text = Path(template_path).read_text(encoding="utf-8")
    rendered = substitute(tmpl_text, subs)
    data = json.loads(rendered)  # fail loud on a broken template
    if user_path and Path(user_path).exists():
        overlay = json.loads(Path(user_path).read_text(encoding="utf-8"))
        data = deep_merge(data, overlay)
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if FORBIDDEN_SUBSTRING in text:
        raise ValueError(f"rendered settings contain {FORBIDDEN_SUBSTRING!r} — lean-ctx would "
                         "re-inject hooks/statusLine/deny; remove it from the template/overlay")
    return text


def carry_managed(text: str, existing: Path) -> str:
    """Keep Claude-managed keys from an existing settings.json (user /config choices)."""
    try:
        old = json.loads(Path(existing).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return text
    data = json.loads(text)
    for k in CLAUDE_MANAGED_KEYS & set(old):
        data[k] = old[k]
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def emit_template(live_path: Path = _LIVE, out_path: Path = _TEMPLATE) -> str:
    """(Re)generate the template from the live settings.json by tokenizing it."""
    text = tokenize(Path(live_path).read_text(encoding="utf-8"))
    Path(out_path).write_text(text, encoding="utf-8", newline="\n")
    return text


def _diff_paths(a, b, path="") -> list[str]:
    if isinstance(a, dict) and isinstance(b, dict):
        out: list[str] = []
        for k in sorted(set(a) | set(b)):
            out += _diff_paths(a.get(k, "<absent>"), b.get(k, "<absent>"), f"{path}.{k}" if path else k)
        return out
    return [] if a == b else [path or "<root>"]


def _normalized(data: dict) -> dict:
    return {k: v for k, v in data.items() if k not in CLAUDE_MANAGED_KEYS}


def machine_subs() -> dict[str, str] | None:
    """THIS machine's path tokens (Windows: py -3, C:/Users/<you>/.claude); None falls back
    to the POSIX defaults. On POSIX they equal the defaults, so output is unchanged."""
    try:
        import detect as _d  # type: ignore
        return _d.detect().tokens
    except Exception:  # noqa: BLE001
        return None


def check_equivalence(live_path: Path = _LIVE, template_path: Path = _TEMPLATE,
                      user_path: Path | None = _USER) -> tuple[bool, str]:
    """SEMANTIC check: parsed render(template ⊕ overlay) == parsed live settings.json,
    ignoring the Claude-managed keys (Claude Code rewrites those itself)."""
    try:
        live = json.loads(Path(live_path).read_text(encoding="utf-8"))
        rendered = json.loads(render(template_path, user_path, machine_subs()))
    except (OSError, ValueError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    diffs = _diff_paths(_normalized(rendered), _normalized(live))
    if not diffs:
        return True, "render(template) semantically equals live settings.json"
    return False, f"{len(diffs)} differing key path(s): {diffs[:8]}"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Render settings.json from settings.template.json")
    ap.add_argument("--template", type=Path, default=_TEMPLATE)
    ap.add_argument("--user", type=Path, default=_USER)
    ap.add_argument("--out", type=Path, default=_LIVE)
    ap.add_argument("--check", action="store_true", help="prove render(template)==live and exit")
    ap.add_argument("--emit-template", action="store_true", help="regenerate the template from live")
    ap.add_argument("--dry-run", action="store_true", help="print rendered output, do not write")
    args = ap.parse_args(argv)

    if args.emit_template:
        emit_template(_LIVE, args.template)
        print(f"wrote template: {args.template}")
        return 0

    if args.check:
        ok, msg = check_equivalence(_LIVE, args.template)
        print(("OK   " if ok else "FAIL ") + msg)
        return 0 if ok else 1

    text = render(args.template, args.user, machine_subs())
    if args.out.exists():
        text = carry_managed(text, args.out)
    if args.dry_run:
        sys.stdout.write(text)
        return 0
    from tempfile import mkstemp
    import os

    fd, tmp = mkstemp(dir=str(args.out.parent), prefix=".settings-", suffix=".swap")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, args.out)
    print(f"rendered -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
