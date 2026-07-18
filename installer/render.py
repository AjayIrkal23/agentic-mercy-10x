#!/usr/bin/env python3
"""render.py — settings.json is a RENDERED ARTIFACT (P6-T3 / P6-T5).

``settings.json`` = ``settings.template.json`` (tokenized) ⊕ optional
``settings.user.json`` (per-machine overlay, user wins) with the interpreter/
path tokens substituted for this OS. This makes one template serve Windows and
Ubuntu, and makes ``git pull`` unable to clobber local settings deltas (they live
in the gitignored user overlay + the gitignored rendered output).

Tokens (kept to the three the plan specifies):
    {{PYTHON}}      python invocation      (e.g. "python3", "py -3", or a Windows python.exe path)
    {{NODE}}        node interpreter       (e.g. "/usr/bin/node", "node")
    {{CLAUDE_DIR}}  the ~/.claude dir path (kept as the literal ``${HOME}/.claude``
                    on POSIX so Claude Code expands it; a concrete path on Windows)

The default tokens REPRODUCE the live literals, so ``render(tokenize(live)) ==
live`` byte-for-byte (the P6-T3 equivalence gate). The installer overrides them
with OS-detected values.

CLI:
    render.py                      # render template(+overlay) -> settings.json
    render.py --check              # prove render(template) == live settings.json
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
}


def tokenize(text: str) -> str:
    """Live settings.json text -> tokenized template text."""
    for literal, token in _TOKEN_MAP:
        text = text.replace(literal, token)
    return text


def substitute(text: str, subs: dict[str, str] | None = None) -> str:
    """Tokenized template text -> concrete settings text for this OS."""
    subs = {**_DEFAULT_SUBS, **(subs or {})}
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
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def emit_template(live_path: Path = _LIVE, out_path: Path = _TEMPLATE) -> str:
    """(Re)generate the template from the live settings.json by tokenizing it."""
    text = tokenize(Path(live_path).read_text(encoding="utf-8"))
    Path(out_path).write_text(text, encoding="utf-8")
    return text


def check_equivalence(live_path: Path = _LIVE, template_path: Path = _TEMPLATE) -> tuple[bool, str]:
    """Prove render(template, default POSIX subs) == live settings.json byte-for-byte
    (modulo token substitution) — the P6-T3 acceptance gate."""
    live = Path(live_path).read_text(encoding="utf-8")
    # substitution round-trip on RAW TEXT (byte-equal after token substitution)
    rendered_text = substitute(Path(template_path).read_text(encoding="utf-8"))
    if rendered_text == live:
        return True, "render(template) == live settings.json (byte-identical)"
    # fall back to semantic (parsed) comparison for a clearer diff signal
    try:
        same = json.loads(rendered_text) == json.loads(live)
    except ValueError as exc:
        return False, f"rendered template is not valid JSON: {exc}"
    if same:
        return True, "render(template) semantically identical to live (whitespace only)"
    # find first differing line
    a = rendered_text.splitlines()
    b = live.splitlines()
    for i, (x, y) in enumerate(zip(a, b), 1):
        if x != y:
            return False, f"first diff at line {i}:\n  rendered: {x!r}\n  live:     {y!r}"
    return False, f"length differs: rendered {len(a)} lines vs live {len(b)} lines"


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

    text = render(args.template, args.user)
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
