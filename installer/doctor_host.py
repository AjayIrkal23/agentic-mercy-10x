"""Doctor rows about THIS machine's state (skipped or empty under ``--ci``).

  plugins-installed  every manifest plugin is installed AND enabled, read from
                     `claude plugin list --json` (audit I-10). A ``mandatory`` plugin
                     missing/disabled -> FAIL; any other -> WARN; no CLI -> SKIP.
  secret-perms       secret-adjacent files in ~/.claude are not group/world readable
                     (J-06). WARN with the exact chmod; the doctor never chmods.
  lean-ctx floor     ZERO_INJECTION: the keys that keep lean-ctx from injecting into
                     ~/.claude are asserted even if the manifest ever drops one (G-13).
Pure stdlib; all external calls injectable.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"

SECRET_GLOBS = (".env", ".env.*", "CLAUDE.machines.local.md", ".credentials.json", "settings.user.json")

ZERO_INJECTION = {
    "top": {"shadow_mode": False, "rules_injection": "off", "shell_hook_disabled": True,
            "read_redirect": "off", "read_dedup": "off"},
    "setup": {"auto_inject_skills": False, "auto_inject_rules": False},
}


def leanctx_required_with_floor(required: dict) -> dict:
    out = copy.deepcopy(required)
    for table, keys in ZERO_INJECTION.items():
        out.setdefault(table, {}).update(keys)
    return out


def leanctx_unmanaged_note(path: Path, required: dict) -> str:
    """Root ``shell_*`` keys the manifest does not manage (audit G-13: shell_security
    off, a leftover allowlist). Info only: their policy is the user's call."""
    try:
        import tomllib
        data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except (ImportError, OSError, ValueError):
        return ""
    managed = set((required.get("top") or {}))
    out = []
    for k, v in sorted(data.items()):
        if not k.startswith("shell_") or k in managed or isinstance(v, dict):
            continue
        out.append(f"{k}({len(v)})" if isinstance(v, list) else f"{k}={v}")
    return ", ".join(out)


def plugins_status(declared: list[dict], listed: list[dict] | None) -> tuple[str, str]:
    if listed is None:
        return SKIP, "claude CLI absent or `claude plugin list --json` unreadable"
    state = {p.get("id"): bool(p.get("enabled")) for p in listed if isinstance(p, dict)}
    bad_hard, bad_soft = [], []
    for p in declared:
        pid = p["id"]
        if state.get(pid):
            continue
        why = f"{pid} ({'disabled' if pid in state else 'not installed'})"
        (bad_hard if p.get("mandatory") else bad_soft).append(why)
    if bad_hard:
        return FAIL, f"mandatory plugin off: {bad_hard}" + (f"; also {bad_soft}" if bad_soft else "")
    if bad_soft:
        return WARN, f"declared but off: {bad_soft} (claude plugin install <id> --scope user)"
    return PASS, f"{len(declared)} declared plugins installed + enabled"


def _plugin_list(which: Callable, run: Callable) -> list[dict] | None:
    claude = which("claude")
    if not claude:
        return None
    try:
        data = json.loads(run([claude, "plugin", "list", "--json"]) or "null")
    except ValueError:
        return None
    return data if isinstance(data, list) else None


def _stdout(argv: list[str]) -> str:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=60, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def check_plugins_installed(manifest: dict, ci: bool, which: Callable | None = None,
                            run: Callable = _stdout) -> tuple[str, str]:
    if ci:
        return SKIP, "--ci (no claude CLI)"
    declared = (manifest.get("plugins") or {}).get("install") or []
    return plugins_status(declared, _plugin_list(which or shutil.which, run))


def check_ollama(manifest: dict, ci: bool) -> tuple[str, str]:
    """Semantic search needs a local ollama + the embedding model — WARN only."""
    probe = (manifest.get("doctor_probes") or {}).get("ollama") or {}
    if ci or not probe:
        return SKIP, "--ci" if ci else "no probe declared"
    import urllib.request
    try:
        with urllib.request.urlopen(probe["url"], timeout=3) as resp:  # noqa: S310 (localhost)
            full = {m.get("name", "") for m in json.load(resp).get("models", [])}
    except Exception as exc:  # noqa: BLE001
        return WARN, f"ollama unreachable ({type(exc).__name__}) — {probe.get('note', '')}"
    base = {n.split(":")[0] for n in full}
    # a tagged probe entry (qwen2.5-coder:3b) needs that exact tag; an untagged one any tag
    missing = [m for m in probe.get("models", []) if (m not in full if ":" in m else m not in base)]
    if missing:
        return WARN, f"missing models {missing}: ollama pull {' '.join(missing)}"
    return PASS, f"models ok: {probe['models']}"


def check_secret_perms(root: Path) -> tuple[str, str]:
    if os.name == "nt":
        return SKIP, "POSIX modes only"
    seen = sorted({p for g in SECRET_GLOBS for p in Path(root).glob(g) if p.is_file()})
    loose = [p for p in seen if p.stat().st_mode & 0o077]
    if not loose:
        return PASS, f"{len(seen)} secret-adjacent file(s), none group/world readable"
    names = " ".join(str(p) for p in loose)
    return WARN, f"group/world readable: {[p.name for p in loose]} -> chmod 600 {names}"
