#!/usr/bin/env python3
"""verify.py — the ~/.claude WORKFLOW TESTER (Windows + Ubuntu/macOS).

Answers "is my whole workflow installed and active?" in one report:
  · PREREQUISITES   python3 / node / git / claude (+ versions)
  · PRIVILEGES      ~/.claude user-owned + npm -g prefix writable (the sudo trap)
  · DEPENDENCIES    lean-ctx, tdd-guard, semgrep, jcodemunch-mcp, jdocmunch-mcp, graphify
  · MCP SERVERS     every manifest server vs `claude mcp list` (+ claude.ai connectors)
  · PLUGINS         superpowers / ponytail / karpathy / mermaid vs `claude plugin list`
  · WIRING          settings.json -> UserPromptSubmit=router.py (LIVE) + PreToolUse=dispatch.py
  · PALETTE         skill + command counts vs the manifest

`collect()` returns the report as STRUCTURED data (JSON-able) so both the CLI
(`python check.py`) and the visual installer (installer/ui.py) render the same
truth. Every gap carries an exact `fix` command. Read-only. Exit 0 = all green.

Run:  python install.py verify   ·   python check.py   ·   python install.py ui
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from lib import platform as plat  # noqa: E402

MANIFEST = _ROOT / "installer" / "manifest.json"

# semantic status tokens (JSON-safe); the CLI maps them to ASCII markers.
OK, MISS, WARN, CONN = "ok", "miss", "warn", "conn"
_MARK = {OK: "[OK]  ", MISS: "[MISS]", WARN: "[WARN]", CONN: "[conn]"}


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _ver(binary: str) -> str:
    for flag in ("--version", "version", "-V"):
        cp = plat.run([binary, flag], timeout=15)
        if cp.returncode == 0 and (cp.stdout or cp.stderr):
            return (cp.stdout or cp.stderr).strip().splitlines()[0][:44]
    return ""


def _claude_list(kind: list[str]) -> tuple[bool, str]:
    """(claude_present, listing_text). kind e.g. ['mcp','list'] / ['plugin','list']."""
    if not shutil.which("claude"):
        return False, ""
    cp = plat.run(["claude", *kind], timeout=40)
    return True, ((cp.stdout or "") if cp.returncode == 0 else "")


def _registered_mcps() -> tuple[set, str]:
    """Registered MCP server names — read AUTHORITATIVELY from the claude config
    file (instant, no network). `claude mcp list` runs a per-server health check
    that network-probes each server and can exceed our timeout, so it is only the
    fallback. Returns (names, source_label)."""
    for cand in (os.environ.get("CLAUDE_CONFIG_DIR"), str(Path.home())):
        if not cand:
            continue
        f = Path(cand) / ".claude.json"
        if not f.is_file():
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        names = set((d.get("mcpServers") or {}).keys())
        for pv in (d.get("projects") or {}).values():
            names |= set(((pv or {}).get("mcpServers") or {}).keys())
        if names:
            return names, f.name  # ".claude.json"
    ok, txt = _claude_list(["mcp", "list"])  # fallback (slow: health-checks each server)
    if ok and txt:
        return ({ln.split(":", 1)[0].strip() for ln in txt.splitlines() if ":" in ln},
                "claude mcp list")
    return set(), ("claude mcp list" if ok else "")


def _row(rows, mark, name, detail="", fix=""):
    rows.append({"mark": mark, "name": name, "detail": detail, "fix": fix})


def _present(root: Path, pat: str) -> bool:
    """True if a path (glob or literal) exists under root — used to detect local
    installs (e.g. GSD's engine dir + materialized gsd-* agents/skills)."""
    if any(c in pat for c in "*?["):
        return any(root.glob(pat))
    return (root / pat).exists()


def collect(env, target: Path | None = None) -> tuple[list, int]:
    """Return (sections, hard_gap_count). sections = [{title, subtitle, rows:[...]}]."""
    man = _manifest()
    os_name = env.os_name
    root = Path(target) if target else _ROOT
    sections: list[dict] = []

    # --- prerequisites ---
    rows = []
    for p in man.get("prereqs", []):
        w = p.get("which", p["id"])
        if shutil.which(w):
            _row(rows, OK, p["id"], _ver(w))
        else:
            hint = p.get(f"install_{os_name}") or p.get("install_posix") or ""
            _row(rows, MISS if p.get("required") else WARN, p["id"], "not found", hint)
    sections.append({"title": "Prerequisites", "subtitle": "you install these", "rows": rows})

    # --- privileges (no root/sudo needed anywhere except a system-npm -g) ---
    rows = []
    home = str(Path.home())
    cdir = str(root)
    _row(rows, OK if cdir.startswith(home) else WARN, ".claude location",
         f"{cdir}  (user home — no root/sudo/admin)")
    if shutil.which("npm"):
        cp = plat.run(["npm", "root", "-g"], timeout=15)
        gdir = (cp.stdout or "").strip()
        probe = gdir if os.path.isdir(gdir) else os.path.dirname(gdir or "/")
        if probe and os.access(probe, os.W_OK):
            _row(rows, OK, "npm -g prefix", f"{gdir}  (user-writable — no sudo)")
        else:
            _row(rows, WARN, "npm -g prefix", f"{gdir}  (system-owned)",
                 "install Node via nvm, OR: npm config set prefix ~/.npm-global  (+ add ~/.npm-global/bin to PATH)")
    sections.append({"title": "Privileges", "subtitle": "no root/sudo/admin", "rows": rows})

    # --- dependency binaries ---
    rows = []
    for d in man.get("deps", []):
        w = d.get("which")
        if not w:  # import-only (pyyaml)
            imp = d.get("import")
            ok = bool(imp) and plat.run([env.python.split()[0], "-c", f"import {imp}"], timeout=20).returncode == 0
            _row(rows, OK if ok else (WARN if d.get("optional") else MISS), d["id"], "python lib")
            continue
        if shutil.which(w):
            _row(rows, OK, d["id"], _ver(w))
        else:
            hint = d.get(f"install_{os_name}") or d.get("install") or ""
            hint = " ".join(hint) if isinstance(hint, list) else str(hint)
            _row(rows, WARN if d.get("optional") else MISS, d["id"], "not found", hint)
    sections.append({"title": "Dependency binaries", "subtitle": "installer auto-installs these", "rows": rows})

    # --- MCP servers ---
    rows = []
    reg, src = _registered_mcps()
    if not reg and not shutil.which("claude"):
        _row(rows, MISS, "claude CLI", "not found",
             "npm install -g @anthropic-ai/claude-code  (needed to register MCP servers)")
    else:
        for s in man.get("mcp_servers", []):
            nm = s["name"]
            if nm in reg:
                _row(rows, OK, nm, "registered")
            else:
                _row(rows, MISS, nm, "not registered", " ".join(str(x) for x in s["add"]))
    for c in man.get("connectors", []):
        _row(rows, CONN, c["id"], "claude.ai Connectors UI (not CLI)")
    sections.append({"title": "MCP servers", "subtitle": f"registered · {src or 'claude mcp list'}", "rows": rows})

    # --- plugins ---
    rows = []
    claude_ok, pl_txt = _claude_list(["plugin", "list"])
    if claude_ok:
        for pl in man.get("plugins", {}).get("install", []):
            _row(rows, OK if pl["id"] in pl_txt else WARN, pl["id"],
                 "installed" if pl["id"] in pl_txt else "not installed",
                 "" if pl["id"] in pl_txt else " ".join(pl["add"]))
    else:
        _row(rows, WARN, "marketplace plugins", "claude CLI absent — cannot check")
    # "manual" installs are LOCAL (a directory + materialized agents/skills), not
    # marketplace plugins — detect them on disk so a present one shows OK, not WARN.
    for m in man.get("plugins", {}).get("manual", []):
        found = any(_present(root, p) for p in m.get("detect_paths", []))
        ver = ""
        vf = m.get("version_file")
        if found and vf and (root / vf).is_file():
            try:
                ver = "v" + (root / vf).read_text(encoding="utf-8").strip()
            except Exception:
                ver = ""
        if found:
            _row(rows, OK, m["id"], (ver + " installed (local)").strip())
        else:
            _row(rows, WARN, m["id"], "not installed", m.get("note", "")[:90])
    sections.append({"title": "Plugins", "subtitle": "marketplace + local", "rows": rows})

    # --- workflow wiring ---
    rows = []
    try:
        sj = json.loads((root / "settings.json").read_text(encoding="utf-8")).get("hooks", {})
    except Exception:
        sj = {}
    def _cmds(ev):
        return " ".join(h.get("command", "") for g in sj.get(ev, []) for h in g.get("hooks", []))
    _row(rows, OK if "prompt_router/router.py" in _cmds("UserPromptSubmit") else MISS, "router LIVE",
         "UserPromptSubmit -> prompt_router/router.py",
         "" if "prompt_router/router.py" in _cmds("UserPromptSubmit") else "python install.py install  (re-renders settings.json)")
    n_disp = sum(1 for ev in ("SessionStart", "PreToolUse", "PostToolUse", "Stop",
                              "SubagentStop", "PreCompact", "SessionEnd") if "dispatch.py" in _cmds(ev))
    _row(rows, OK if n_disp >= 7 else MISS, "dispatch chains", f"{n_disp}/7 events -> dispatch.py")
    _row(rows, OK if (root / "hooks/prompt_router/router.py").is_file() else MISS,
         "router file", "hooks/prompt_router/router.py")
    sections.append({"title": "Workflow wiring", "subtitle": "router live + dispatch", "rows": rows})

    # --- palette ---
    rows = []
    pal = man.get("palette", {})
    n_sk = len(list((root / "skills").glob("*/SKILL.md"))) if (root / "skills").is_dir() else 0
    n_cmd = len(list((root / "commands").glob("*.md"))) if (root / "commands").is_dir() else 0
    _row(rows, OK if n_sk >= pal.get("skill_bodies", 0) else WARN, "skills", f"{n_sk} SKILL.md (want >= {pal.get('skill_bodies')})")
    _row(rows, OK if n_cmd == pal.get("command_files") else WARN, "commands", f"{n_cmd} files (want {pal.get('command_files')})")
    sections.append({"title": "Palette", "subtitle": "skills + commands", "rows": rows})

    hard = sum(1 for s in sections for r in s["rows"] if r["mark"] == MISS)
    return sections, hard


def main(argv: list[str] | None = None) -> int:
    from detect import detect  # type: ignore
    env = detect()
    print("=" * 60)
    print(f" ~/.claude WORKFLOW STATUS   os={env.os_name}  python={env.python}")
    print("=" * 60)
    sections, hard = collect(env)
    for s in sections:
        sub = f"  ({s['subtitle']})" if s.get("subtitle") else ""
        print(f"\n{s['title'].upper()}{sub}")
        for r in s["rows"]:
            tail = r["detail"] or ""
            if r["mark"] in (MISS, WARN) and r["fix"]:
                tail = (tail + "  -> " + r["fix"]).strip(" ->")
            print(f"  {_MARK[r['mark']]} {r['name']:20s} {tail}".rstrip())
    print("\n" + "-" * 60)
    if hard == 0:
        print("SUMMARY: WORKFLOW ACTIVE — all required checks green. [WARN]=optional, [conn]=claude.ai UI.")
    else:
        print(f"SUMMARY: {hard} required gap(s) [MISS] above — run the fix command on each, then re-run. "
              "(Or `python install.py install` to auto-install, or `python install.py ui` for the visual installer.)")
    return 1 if hard else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
