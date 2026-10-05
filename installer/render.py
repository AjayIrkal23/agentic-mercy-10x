#!/usr/bin/env python3
"""render.py — settings.json is a RENDERED ARTIFACT (P6-T3 / P6-T5).

``settings.json`` = ``settings.template.json`` (tokenized) ⊕ optional
``settings.user.json`` (per-machine overlay, user wins) with the interpreter/
path tokens substituted for this OS. This makes one template serve Windows and
Ubuntu, and makes ``git pull`` unable to clobber local settings deltas (they live
in the gitignored user overlay + the gitignored rendered output).

Tokens:
    {{PYTHON}}      python invocation      (e.g. "python3", "py -3", or a Windows python.exe path)
    {{PYTHON_EXE}}  status line interpreter: Windows = real python.exe (forward slashes, no ``py``
                    launcher), POSIX = ``python3``. Hooks keep {{PYTHON}}. Spaced paths get quoted.
    {{NODE}}        node interpreter       (e.g. "/usr/bin/node", "node")
    {{CLAUDE_DIR}}  the ~/.claude dir path (kept as the literal ``${HOME}/.claude``
                    on POSIX so Claude Code expands it; a concrete path on Windows)
    {{LEANCTX}}     lean-ctx binary — supported, but the template must NOT use it:
                    render() refuses any output containing "lean-ctx" (see below).
    {{MOD_DIRS}}    absolute paths of the enabled mods (manifest.json ``mods.enabled``
                    present under ``mods/<id>/``), joined by ``os.pathsep``. Claude Code
                    loads ``env.CLAUDE_CODE_PLUGIN_DIRS`` only from absolute or ``~`` paths,
                    so the POSIX ``${HOME}`` form of {{CLAUDE_DIR}} cannot be reused.
                    Empty → the env key is dropped.

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
import json
import os
import re
import sys
from pathlib import Path
from tempfile import mkstemp

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "installer") not in sys.path:
    sys.path.insert(0, str(_ROOT / "installer"))
if str(_ROOT / "hooks") not in sys.path:
    sys.path.insert(0, str(_ROOT / "hooks"))
import backups  # noqa: E402
import settings_diff  # noqa: E402
import settings_seed  # noqa: E402
from lib import platform as plat  # noqa: E402
from settings_diff import deep_merge, tokenize  # noqa: E402,F401 (public API of render)
_LIVE = _ROOT / "settings.json"
_TEMPLATE = _ROOT / "settings.template.json"
_USER = _ROOT / "settings.user.json"

PATHSEP = os.pathsep
PLUGIN_DIRS_KEY = "CLAUDE_CODE_PLUGIN_DIRS"
_MOD_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# Default substitution values == the live POSIX literals (equivalence gate).
_DEFAULT_SUBS = {
    "{{PYTHON}}": "python3",
    "{{PYTHON_EXE}}": "python3",
    "{{NODE}}": "${HOME}/.local/bin/node",
    "{{CLAUDE_DIR}}": "${HOME}/.claude",
    "{{LEANCTX}}": "${HOME}/.local/bin/lean-ctx",
    "{{MOD_DIRS}}": "",
}

# Keys Claude Code itself writes into settings.json (/config, /theme, voice …).
# They are never rendered from the template and never compared: a re-render
# carries the existing live values over instead of clobbering them.
CLAUDE_MANAGED_KEYS = frozenset({
    "tui", "voice", "voiceEnabled", "theme", "remoteControlAtStartup",
    "agentPushNotifEnabled", "skipWorkflowUsageWarning", "autoCompactWindow",
    "contextWindow", "effortLevel", "modelSettings", "skipDangerousModePermissionPrompt",
    "switchModelsOnFlag", "pluginConfigs",
})

# lean-ctx >= 3.10 re-injects its own hooks / statusLine / permissions.deny into
# any settings.json that mentions it. The rendered file must never contain it
# (the dispatch matcher spells the MCP prefix as the regex `mcp__lean.ctx__`).
FORBIDDEN_SUBSTRING = "lean-ctx"


def substitute(text: str, subs: dict[str, str] | None = None) -> str:
    """Tokenized template text -> concrete settings text for this OS."""
    # accept detect()'s bare keys ("PYTHON") as well as "{{PYTHON}}"
    subs = {**_DEFAULT_SUBS, **{(k if k.startswith("{{") else "{{" + k + "}}"): v
                                for k, v in (subs or {}).items()}}
    for token, value in subs.items():
        text = settings_diff.fill_token(text, token, value)
    return text


def mod_dirs(root: Path = _ROOT, manifest: Path | None = None) -> list[str]:
    """Absolute (forward-slash) dirs of the enabled mods that exist under ``root/mods``."""
    try:
        data = json.loads(Path(manifest or root / "installer" / "manifest.json").read_text(encoding="utf-8"))
        enabled = (data.get("mods") or {}).get("enabled") or []
    except (OSError, ValueError, AttributeError):
        return []
    out = []
    for mod_id in enabled:
        if not isinstance(mod_id, str) or not _MOD_ID.match(mod_id) or FORBIDDEN_SUBSTRING in mod_id:
            continue
        folder = Path(root) / "mods" / mod_id
        if (folder / ".claude-plugin" / "plugin.json").is_file():
            out.append(folder.as_posix())
    return out


def render(
    template_path: Path = _TEMPLATE,
    user_path: Path | None = _USER,
    subs: dict[str, str] | None = None,
) -> str:
    """Return the fully rendered settings.json TEXT (validated JSON)."""
    tmpl_text = Path(template_path).read_text(encoding="utf-8")
    # mods come from the manifest next to the TEMPLATE, so a sandbox --template never
    # pulls the live checkout's mods (audit A-11)
    mods = PATHSEP.join(mod_dirs(Path(template_path).resolve().parent))
    rendered = substitute(tmpl_text, {"MOD_DIRS": mods, **(subs or {})})
    data = json.loads(rendered)  # fail loud on a broken template
    if plat.IS_WINDOWS and isinstance(data.get("env"), dict):  # semgrep-core has no posix backend there
        data["env"].pop("EIO_BACKEND", None)
    if user_path and Path(user_path).exists():
        overlay = json.loads(Path(user_path).read_text(encoding="utf-8"))
        own_hooks = overlay.pop("hooks", None)  # the user's hooks go AFTER the workbench's, never twice
        data = deep_merge(data, overlay)
        if isinstance(own_hooks, dict):
            data["hooks"] = settings_seed.append_hooks(data.get("hooks") or {}, own_hooks)
    env = data.get("env")
    if isinstance(env, dict) and env.get(PLUGIN_DIRS_KEY) == "":
        del env[PLUGIN_DIRS_KEY]
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if FORBIDDEN_SUBSTRING in text:
        raise ValueError(f"rendered settings contain {FORBIDDEN_SUBSTRING!r} — lean-ctx would "
                         "re-inject hooks/statusLine/deny; remove it from the template/overlay")
    return text


def carry_managed(text: str, existing: Path) -> str:
    """Keep Claude-managed keys from an existing settings.json (user /config choices) and
    what the user added: permission allow/deny/ask rules, plugins enabled through /plugin and
    extra marketplaces (unioned with the template's; ``settings_diff.carry``)."""
    return settings_diff.carry(text, existing, CLAUDE_MANAGED_KEYS)


def emit_template(live_path: Path = _LIVE, out_path: Path = _TEMPLATE) -> str:
    """(Re)generate the template from the live settings.json by tokenizing it."""
    text = tokenize(Path(live_path).read_text(encoding="utf-8"))
    data = json.loads(text)
    env = data.get("env")
    if isinstance(env, dict) and PLUGIN_DIRS_KEY in env:
        env[PLUGIN_DIRS_KEY] = "{{MOD_DIRS}}"  # machine paths never enter the template
        text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    Path(out_path).write_text(text, encoding="utf-8", newline="\n")
    return text


def _normalized(data: dict) -> dict:
    out = settings_diff.normalized(data, CLAUDE_MANAGED_KEYS, PLUGIN_DIRS_KEY, PATHSEP)
    perms = out.get("permissions")
    if isinstance(perms, dict) and "allow" in perms:  # granted in Claude Code's dialog: Claude-managed
        out["permissions"] = {k: v for k, v in perms.items() if k != "allow"}
    return out


def machine_subs() -> dict[str, str] | None:
    """THIS machine's path tokens (Windows: py -3, C:/Users/<you>/.claude); None falls back
    to the POSIX defaults. On POSIX they equal the defaults, so output is unchanged.
    A concrete (Windows) CLAUDE_DIR names this checkout — the one whose settings.json is
    rendered — not a HOME/CLAUDE_CONFIG_DIR-derived dir (a sandboxed HOME must not move it)."""
    try:
        import detect as _d  # type: ignore
        env = _d.detect()
        tokens = {**env.tokens, "PYTHON_EXE": getattr(env, "python_exe", None) or "python3"}
    except Exception:  # noqa: BLE001
        return None
    if not tokens.get("CLAUDE_DIR", "").startswith("${HOME}"):
        tokens["CLAUDE_DIR"] = _ROOT.as_posix()
    return tokens


def check_equivalence(live_path: Path = _LIVE, template_path: Path = _TEMPLATE,
                      user_path: Path | None = _USER) -> tuple[bool, str]:
    """SEMANTIC check: parsed render(template ⊕ overlay) == parsed live settings.json,
    ignoring the Claude-managed keys (Claude Code rewrites those itself)."""
    try:
        live = json.loads(Path(live_path).read_text(encoding="utf-8"))
        rendered = json.loads(render(template_path, user_path, machine_subs()))
    except (OSError, ValueError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    want = _normalized(rendered)  # entries the user added (rules, /plugin, marketplaces) are not drift
    diffs = settings_diff.diff_paths(settings_diff.prune_empty_rules(want), settings_diff.prune_empty_rules(
        settings_diff.without_additions(_normalized(live), want)))
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

    if args.check:  # --out is the file under test, --user its overlay (audit A-11 / I-15)
        ok, msg = check_equivalence(args.out, args.template, args.user)
        print(("OK   " if ok else "FAIL ") + msg)
        return 0 if ok else 1

    text = render(args.template, args.user, machine_subs())
    old = args.out.read_text(encoding="utf-8") if args.out.exists() else None
    if old is not None:
        text = carry_managed(text, args.out)
    if args.dry_run:
        sys.stdout.write(text)
        return 0
    if old is not None and old != text:  # bounded, dated backups (audit A-09 / J-11)
        backups.backup(args.out)
    fd, tmp = mkstemp(dir=str(args.out.parent), prefix=".settings-", suffix=".swap")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, args.out)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    print(f"rendered -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
