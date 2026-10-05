"""Doctor rows about THIS machine's state (skipped or empty under ``--ci``).

  plugins-installed  every manifest plugin is installed AND enabled, read from
                     `claude plugin list --json` (audit I-10). A ``mandatory`` plugin
                     missing/disabled -> FAIL; any other -> WARN; no CLI -> SKIP.
  secret-perms       secret-adjacent files in ~/.claude, and ~/.claude.json, are not group/world
                     readable (J-06). POSIX: WARN with the exact chmod. Windows: the DACL from
                     `icacls <file> /save` (SDDL, SIDs, no locale) must grant read only to the
                     user, SYSTEM and Administrators. The doctor never chmods or changes ACLs.
  lean-ctx floor     ZERO_INJECTION: the keys that keep lean-ctx from injecting into
                     ~/.claude are asserted even if the manifest ever drops one (G-13).
Pure stdlib; all external calls injectable.
"""
from __future__ import annotations

import codecs
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

_HOOKS = Path(__file__).resolve().parents[1] / "hooks"
if str(_HOOKS) not in sys.path:
    sys.path.insert(0, str(_HOOKS))
from lib import platform as plat  # noqa: E402

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"

# settings.json and its copies can hold provider keys (env, apiKeyHelper): the live file, the permanent
# first-install copy, the rotating backups and the user overlay.
SECRET_GLOBS = (".env", ".env.*", "CLAUDE.machines.local.md", ".credentials.json", "settings.json",
                "settings.json.pre-install", "settings.json.bak-*", "settings.user.json")

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
        return subprocess.run(argv, capture_output=True, encoding="utf-8", errors="replace",
                              timeout=60, check=False).stdout
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


# --- Windows: the DACL as SDDL from `icacls <file> /save` (SIDs and aliases, never a localized name) --- #
_ACE = re.compile(r"\(([A-Z]+);([A-Z]*);([^;]*);[^;]*;[^;]*;([^)]+)\)")
# File aliases, generic rights, and the letter pairs Windows writes for the access-mask bits of a file
# (`ConvertSecurityDescriptorToStringSecurityDescriptorW` uses the directory-service names: CC = 0x1 =
# FILE_READ_DATA, so 0x20089 reads `CCSWLORC`).
_RIGHTS = {"FA": 0x1F01FF, "FR": 0x120089, "FW": 0x120116, "FX": 0x1200A0,
           "GA": 0x10000000, "GR": 0x80000000, "GW": 0x40000000, "GX": 0x20000000,
           "CC": 0x1, "DC": 0x2, "LC": 0x4, "SW": 0x8, "RP": 0x10, "WP": 0x20, "DT": 0x40, "LO": 0x80,
           "CR": 0x100, "SD": 0x10000, "RC": 0x20000, "WD": 0x40000, "WO": 0x80000}
_CAN_READ = 0x1 | 0x80000000 | 0x10000000  # FILE_READ_DATA | GENERIC_READ | GENERIC_ALL
_TRUSTED = {"SY", "S-1-5-18", "BA", "S-1-5-32-544", "CO", "S-1-3-0",  # SYSTEM, Administrators, CREATOR OWNER
            "LA"}  # the built-in Administrator account (its own SID renders as this alias)
_WHO = {"WD": "Everyone", "S-1-1-0": "Everyone", "BU": "Users", "S-1-5-32-545": "Users",
        "AU": "Authenticated Users", "S-1-5-11": "Authenticated Users", "IU": "Interactive"}


def decode_sddl(raw: bytes) -> str:
    """`icacls /save` writes UTF-16LE, with or without a BOM."""
    return (raw[2:] if raw.startswith(codecs.BOM_UTF16_LE) else raw).decode("utf-16-le", "replace")


def _system32(tool: str) -> str:
    """``%SystemRoot%\\System32\\<tool>.exe``: the doctor reads ACLs, so a same-named file in the working
    directory or on a user-writable PATH entry must never stand in for it (SEC1-04). The bare name
    only when SystemRoot is unset."""
    root = os.environ.get("SystemRoot")
    return str(Path(root) / "System32" / f"{tool}.exe") if root else tool


def _icacls_save(path: Path) -> str | None:
    fd, tmp = tempfile.mkstemp(suffix=".acl")
    os.close(fd)
    try:
        cp = subprocess.run([_system32("icacls"), str(path), "/save", tmp], capture_output=True, timeout=20, check=False)
        return decode_sddl(Path(tmp).read_bytes()) if cp.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _user_sid() -> str:
    try:
        out = subprocess.run([_system32("whoami"), "/user", "/fo", "csv", "/nh"], capture_output=True,
                             encoding="utf-8", errors="replace", timeout=10, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    sid = out.strip().rsplit(",", 1)[-1].strip().strip('"')
    return sid if sid.startswith("S-1-") else ""


def _mask(rights: str) -> int:
    if rights.lower().startswith("0x"):
        try:
            return int(rights, 16)
        except ValueError:
            return _CAN_READ  # unreadable mask: say so rather than pass
    mask = 0
    for i in range(0, len(rights), 2):
        mask |= _RIGHTS.get(rights[i:i + 2], _CAN_READ)  # an unknown token: say so rather than pass
    return mask


def _readers(sddl: str, me: str) -> list[str]:
    """Principals other than the user, SYSTEM and Administrators with an ALLOW ace that can read."""
    trusted = _TRUSTED | {me}
    if "NO_ACCESS_CONTROL" in sddl:  # a NULL DACL: no ACE, and everyone has full access
        return ["Everyone"]
    return sorted({_WHO.get(who, who) for kind, _f, rights, who in _ACE.findall(sddl)
                   if kind == "A" and who not in trusted and _mask(rights) & _CAN_READ})


def _secret_acls(files: list[Path], save: Callable, user_sid: Callable) -> tuple[str, str]:
    me = user_sid()
    if not me:
        return WARN, "could not read the current user SID (whoami /user): ACLs not checked"
    loose, unreadable = {}, []
    for p in files:
        text = save(p)
        if text is None:
            unreadable.append(p.name)
        elif who := _readers(text, me):
            loose[p.name] = who
    if not loose and not unreadable:
        return PASS, f"{len(files)} secret-adjacent file(s), read access only for the user, SYSTEM, Administrators"
    parts = []
    if loose:
        parts.append("readable by other principals: " + "; ".join(f"{n} -> {', '.join(w)}" for n, w in loose.items())
                     + f' (fix: icacls "<file>" /inheritance:r /grant:r "*S-1-5-18:F" "*S-1-5-32-544:F" "*{me}:F";'
                     " the doctor never changes ACLs)")
    if unreadable:
        parts.append(f"could not read ACL: {unreadable}")
    return WARN, "; ".join(parts)


def check_secret_perms(root: Path, *, is_windows: bool | None = None, icacls_save: Callable = _icacls_save,
                       user_sid: Callable = _user_sid, home: Path | None = None) -> tuple[str, str]:
    """Secret-adjacent files of ``root`` plus ``~/.claude.json`` (MCP ``env`` holds API keys).
    ``is_windows`` defaults to ``platform.IS_WINDOWS``; the runners are injectable."""
    claude_json = (Path(home) if home else Path.home()) / ".claude.json"
    seen = sorted({p for g in SECRET_GLOBS for p in Path(root).glob(g) if p.is_file()}
                  | ({claude_json} if claude_json.is_file() else set()))
    if not seen:  # nothing checked is not a pass (a fresh profile, a CI runner)
        return SKIP, "no secret files found"
    if plat.IS_WINDOWS if is_windows is None else is_windows:
        return _secret_acls(seen, icacls_save, user_sid)
    loose = [p for p in seen if p.stat().st_mode & 0o077]
    if not loose:
        return PASS, f"{len(seen)} secret-adjacent file(s), none group/world readable"
    names = " ".join(str(p) for p in loose)
    return WARN, f"group/world readable: {[p.name for p in loose]} -> chmod 600 {names}"
