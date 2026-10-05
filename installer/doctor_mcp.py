"""Doctor row ``mcp-roster``: the live user-scope MCP registrations vs the manifest.

WARN (a fresh machine registers on the next install) on
  * a manifest server that is not registered;
  * a registered server the manifest does not declare (audit I-09 / G-04, e.g. drawio);
  * an ``npx``/``uvx`` package spec that differs from an exact manifest pin (I-12 / G-06):
    FAIL when the claude CLI is present (``selfheal._repair`` runs
    ``deps.reconcile_mcp_pins``), WARN when no reconcile is possible;
  * a registered server whose manifest entry is marked ``deprecated`` (G-01);
  * servers that still need ``/mcp`` auth.

Reads only ``command`` / ``args`` / ``url`` of each live entry; ``env`` values (tokens)
are never read into a message. Pure stdlib.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"
_SPEC = r"((?:@[\w.-]+/)?[\w.-]+(?:(?:@|==)[\w.^~<>=-]+)?)"
_NPX = re.compile(r"\b(?:npx|uvx)\s+(?:-y\s+|--yes\s+)*" + _SPEC)


def npx_spec(text: str) -> str | None:
    """The package spec an ``npx -y <spec>`` / ``uvx <spec>`` command line runs, or None."""
    m = _NPX.search(text or "")
    return m.group(1) if m else None


def spec_version(spec: str) -> str | None:
    if "==" in spec:
        return spec.split("==", 1)[1]
    at = spec.rfind("@")
    return spec[at + 1:] if at > 0 else None


def _live_text(entry: dict) -> str:
    args = entry.get("args") or []
    return " ".join([str(entry.get("command") or "")] + [str(a) for a in args])


def pin_drift(manifest: dict, live: dict) -> list[tuple[str, str, str]]:
    """[(name, live spec, manifest spec)] for user-scope stdio servers whose package spec
    differs from an EXACT manifest pin (version starts with a digit). OAuth/http servers,
    servers the manifest leaves unpinned and live entries that are not npx/uvx are skipped."""
    out = []
    for srv in manifest.get("mcp_servers", []):
        entry = live.get(srv["name"])
        if not entry or entry.get("url") or entry.get("type") == "http":
            continue
        want = npx_spec(" ".join(srv.get("add") or []))
        have = npx_spec(_live_text(entry))
        if want and have and (spec_version(want) or "")[:1].isdigit() and want != have:
            out.append((srv["name"], have, want))
    return out


def swap_spec(text: str, have: str, want: str) -> str:
    """``text`` with the package spec ``have`` (whole token) replaced by ``want``."""
    return re.sub(r"(?<![\w@/.=-])" + re.escape(have) + r"(?![\w.=-])", lambda _m: want, text, count=1)


def roster_status(manifest: dict, live: dict, auth: set, repairable: bool = False) -> tuple[str, str]:
    """``repairable``: a reconcile can run (claude CLI present), so pin drift is a FAIL the
    self-heal ``_repair`` routes to ``deps.reconcile_mcp_pins``; without it, a WARN."""
    servers = {s["name"]: s for s in manifest.get("mcp_servers", [])}
    expected = manifest.get("doctor_probes", {}).get("mcp_roster") or list(servers)
    issues = []
    missing = [m for m in expected if m not in live]
    if missing:
        issues.append(f"missing: {missing}")
    extras = sorted(n for n in live if n not in servers)
    if extras:
        issues.append(f"not in manifest: {extras}")
    drift = [f"{n} {have} != {want}" for n, have, want in pin_drift(manifest, live)]
    if drift:
        issues.append(f"pin drift ({'selfheal re-registers it' if repairable else 're-register to apply'}): {drift}")
    deprecated = [f"{n}: {s['deprecated']}" for n, s in servers.items() if s.get("deprecated") and n in live]
    if deprecated:
        issues.append(f"deprecated package: {deprecated}")
    needs = sorted(m for m in expected if m in auth)
    if needs:
        issues.append(f"needs /mcp auth: {needs}")
    if not issues:
        return PASS, f"{len(live)} registered, all declared and pinned as the manifest says"
    return (FAIL if drift and repairable else WARN), "; ".join(issues)


def check_mcp_roster(ci: bool, manifest: dict, config_file: Path, auth_file: Path) -> tuple[str, str]:
    if ci:
        return SKIP, "--ci (no ~/.claude.json in CI)"
    try:
        live = json.loads(Path(config_file).read_text(encoding="utf-8")).get("mcpServers") or {}
    except (OSError, ValueError):
        live = {}
    try:
        auth = set(json.loads(Path(auth_file).read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        auth = set()
    status, detail = roster_status(manifest, live, auth, repairable=shutil.which("claude") is not None)
    return status, f"{detail} ({Path(config_file).name})"
