#!/usr/bin/env python3
"""verify.py — the ~/.claude WORKFLOW TESTER (Windows + Ubuntu/macOS).

Answers "is my whole workflow installed and active?" in one report:
  · PREREQUISITES   python3 / node / npm / git / claude / uv / pipx (+ versions)
  · DEPENDENCIES    lean-ctx, tdd-guard, semgrep, jcodemunch-mcp, jdocmunch-mcp, graphify
  · MCP SERVERS     every server in the manifest, checked against `claude mcp list`
                    (+ the claude.ai connectors, which are UI-added)
  · PLUGINS         superpowers / ponytail / karpathy / mermaid vs `claude plugin list`
  · WIRING          settings.json -> UserPromptSubmit=router.py (LIVE) + PreToolUse=dispatch.py
  · PALETTE         skill + command counts vs the manifest

Every gap prints the EXACT fix command. Read-only. ASCII markers (Windows-safe).
Exit 0 = all required checks green; 1 = one or more required gaps.

Run:  python install.py verify        or:  python check.py
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_ROOT / "installer"), str(_ROOT / "hooks")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from lib import platform as plat  # noqa: E402

MANIFEST = _ROOT / "installer" / "manifest.json"
OK, MISS, WARN, CONN = "[OK]  ", "[MISS]", "[WARN]", "[conn]"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _ver(binary: str) -> str:
    for flag in ("--version", "version", "-V"):
        cp = plat.run([binary, flag], timeout=15)
        if cp.returncode == 0 and (cp.stdout or cp.stderr):
            return (cp.stdout or cp.stderr).strip().splitlines()[0][:40]
    return ""


def _claude_list(kind: list[str]) -> tuple[bool, str]:
    """Return (claude_present, listing_text). kind e.g. ['mcp','list'] / ['plugin','list']."""
    if not shutil.which("claude"):
        return False, ""
    cp = plat.run(["claude", *kind], timeout=40)
    return True, (cp.stdout or "") if cp.returncode == 0 else (True, "")[1]


def _row(rows, mark, name, detail=""):
    rows.append((mark, name, detail))


def _section(title, rows) -> int:
    print(f"\n{title}")
    issues = 0
    for mark, name, detail in rows:
        print(f"  {mark} {name:22s} {detail}".rstrip())
        if mark == MISS:
            issues += 1
    return issues


def check(env, *, os_name: str) -> int:
    man = _manifest()
    total_issues = 0

    # --- prerequisites ---
    rows = []
    for p in man.get("prereqs", []):
        w = p.get("which", p["id"])
        if shutil.which(w):
            _row(rows, OK, p["id"], _ver(w))
        else:
            hint = p.get(f"install_{os_name}") or p.get("install_posix") or ""
            _row(rows, MISS if p.get("required") else WARN, p["id"], f"-> {hint}")
    total_issues += _section("PREREQUISITES (you install these)", rows)

    # --- dependency binaries ---
    rows = []
    for d in man.get("deps", []):
        w = d.get("which")
        if not w:  # import-only dep (pyyaml) — check import
            imp = d.get("import")
            ok = imp and plat.run([env.python.split()[0], "-c", f"import {imp}"], timeout=20).returncode == 0
            _row(rows, OK if ok else (WARN if d.get("optional") else MISS), d["id"], "" if ok else "(python lib)")
            continue
        if shutil.which(w):
            _row(rows, OK, d["id"])
        else:
            hint = d.get(f"install_{os_name}") or d.get("install") or ""
            hint = " ".join(hint) if isinstance(hint, list) else str(hint)
            _row(rows, WARN if d.get("optional") else MISS, d["id"], f"-> {hint}")
    total_issues += _section("DEPENDENCY BINARIES", rows)

    # --- MCP servers ---
    rows = []
    claude_ok, mcp_txt = _claude_list(["mcp", "list"])
    if not claude_ok:
        _row(rows, MISS, "claude CLI", "-> install @anthropic-ai/claude-code (can't check MCP roster)")
    else:
        for s in man.get("mcp_servers", []):
            nm = s["name"]
            if nm in mcp_txt:
                _row(rows, OK, nm)
            else:
                add = " ".join(str(x) for x in s["add"])
                _row(rows, MISS, nm, f"-> {add}")
    for c in man.get("connectors", []):
        _row(rows, CONN, c["id"], "(claude.ai Connectors UI — not CLI)")
    total_issues += _section("MCP SERVERS (claude mcp list)", rows)

    # --- plugins ---
    rows = []
    claude_ok, pl_txt = _claude_list(["plugin", "list"])
    if claude_ok:
        for pl in man.get("plugins", {}).get("install", []):
            if pl["id"] in pl_txt:
                _row(rows, OK, pl["id"])
            else:
                _row(rows, WARN, pl["id"], f"-> {' '.join(pl['add'])}")
        for m in man.get("plugins", {}).get("manual", []):
            _row(rows, WARN, m["id"], "-> manual (see manifest note)")
    else:
        _row(rows, WARN, "plugins", "claude CLI absent — cannot check")
    _section("PLUGINS (claude plugin list)", rows)  # plugins are advisory, not counted as hard issues

    # --- workflow wiring ---
    rows = []
    settings = _ROOT / "settings.json"
    try:
        sj = json.loads(settings.read_text(encoding="utf-8")).get("hooks", {})
    except Exception:
        sj = {}
    def _cmds(ev):
        return " ".join(h.get("command", "") for g in sj.get(ev, []) for h in g.get("hooks", []))
    ups = _cmds("UserPromptSubmit")
    if "prompt_router/router.py" in ups:
        _row(rows, OK, "router LIVE", "UserPromptSubmit -> prompt_router/router.py")
    else:
        _row(rows, MISS, "router", "-> settings.json UserPromptSubmit must call prompt_router/router.py")
    n_dispatch = sum(1 for ev in ("SessionStart", "PreToolUse", "PostToolUse", "Stop",
                                  "SubagentStop", "PreCompact", "SessionEnd") if "dispatch.py" in _cmds(ev))
    _row(rows, OK if n_dispatch >= 7 else MISS, "dispatch chains", f"{n_dispatch}/7 events -> dispatch.py")
    _row(rows, OK if (_ROOT / "hooks/prompt_router/router.py").is_file() else MISS,
         "router file", "hooks/prompt_router/router.py")
    total_issues += _section("WORKFLOW WIRING", rows)

    # --- palette ---
    rows = []
    pal = man.get("palette", {})
    n_sk = len(list((_ROOT / "skills").glob("*/SKILL.md"))) if (_ROOT / "skills").is_dir() else 0
    n_cmd = len(list((_ROOT / "commands").glob("*.md"))) if (_ROOT / "commands").is_dir() else 0
    _row(rows, OK if n_sk >= pal.get("skill_bodies", 0) else WARN, "skills", f"{n_sk} SKILL.md (want >= {pal.get('skill_bodies')})")
    _row(rows, OK if n_cmd == pal.get("command_files") else WARN, "commands", f"{n_cmd} files (want {pal.get('command_files')})")
    _section("PALETTE", rows)

    print("\n" + "-" * 60)
    if total_issues == 0:
        print("SUMMARY: WORKFLOW ACTIVE — all required checks green. "
              "[WARN]=optional, [conn]=claude.ai UI.")
    else:
        print(f"SUMMARY: {total_issues} required gap(s) [MISS] above — run the fix command on each, "
              "then re-run `python install.py verify`. (Or `python install.py install` to auto-install.)")
    return 1 if total_issues else 0


def main(argv: list[str] | None = None) -> int:
    from detect import detect  # type: ignore
    env = detect()
    print("=" * 60)
    print(f" ~/.claude WORKFLOW STATUS   os={env.os_name}  python={env.python}")
    print("=" * 60)
    return check(env, os_name=env.os_name)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
