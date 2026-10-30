#!/usr/bin/env python3
"""Print the live MCP inventory as a markdown table.

Sources (D13: ~/.claude.json is the only live MCP store):
  - ~/.claude.json            mcpServers (user scope) + projects.*.mcpServers
  - plugins/installed_plugins.json -> each plugin's .mcp.json (plugin-provided servers)

Used to regenerate skills/mcp-usage-standards/references/mcp-inventory.md and by the doctor:
  python3 scripts/mcp_inventory.py --md > skills/mcp-usage-standards/references/mcp-inventory.md
  python3 scripts/mcp_inventory.py            # markdown (same as --md)
  python3 scripts/mcp_inventory.py --json     # machine-readable
Output is UTF-8 with LF line endings on every OS and ends with exactly one newline.
"""
import argparse
import json
import sys
from pathlib import Path

HOME = Path.home()
PURPOSE = {
    "jcodemunch": "code symbols, callers, blast radius, reading source (FIRST for code)",
    "jdocmunch": "section-level search/read over indexed doc sets (FIRST for docs)",
    "graphify": "architecture graph: god nodes, neighbors, paths (FIRST for architecture; needs graphify-out/)",
    "lean-ctx": "optional compressed ctx_read/ctx_shell/ctx_patch",
    "context7": "current library/framework/SDK/CLI docs",
    "semgrep": "security scanning (THE security path; satisfies Gate 3)",
    "playwright": "drive a real browser: flows, clicks, a11y snapshots",
    "browser-tools-mcp": "DevTools console/network/audits of the user's open tab",
    "reticle": "in-app state/network truth of the user's running dev app (attach only)",
    "memory": "durable cross-session facts (pattern::/decision::/fragile::)",
    "sequential-thinking": "MUST for non-trivial reasoning: plan/spec/audit/design/debug/decide",
    "github": "GitHub issues/PRs/files via API (gh CLI is often simpler)",
    "markdownify": "convert pdf/docx/pptx/xlsx/web/youtube to markdown",
    "higgsfield": "DEFAULT asset engine: image/video/3D/audio generation",
    "openart": "secondary asset engine (only where a project says so)",
}


def transport(cfg):
    t = cfg.get("type") or ("http" if "url" in cfg else "stdio")
    if t in ("http", "sse"):
        return t, cfg.get("url", "")
    return t, " ".join([cfg.get("command", "")] + list(cfg.get("args", []))).strip()


def load_json(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def collect():
    rows = []
    cj = load_json(HOME / ".claude.json")
    for name, cfg in sorted(cj.get("mcpServers", {}).items()):
        rows.append(("user", name, *transport(cfg)))
    for proj, pv in sorted(cj.get("projects", {}).items()):
        for name, cfg in sorted((pv.get("mcpServers") or {}).items()):
            rows.append((f"project:{proj}", name, *transport(cfg)))
    ip = load_json(HOME / ".claude/plugins/installed_plugins.json")
    for plug, installs in sorted(ip.get("plugins", {}).items()):
        for inst in installs:
            mcp = load_json(Path(inst.get("installPath", "")) / ".mcp.json")
            servers = mcp.get("mcpServers", mcp) if isinstance(mcp, dict) else {}
            for name, cfg in sorted(servers.items()):
                if isinstance(cfg, dict):
                    rows.append((f"plugin:{plug}", name, *transport(cfg)))
    return rows


def render_md(rows) -> str:
    out = ["| Server | Scope | Transport | Target | Reach for it when |", "|---|---|---|---|---|"]
    for scope, name, t, target in rows:
        out.append(f"| `{name}` | {scope} | {t} | `{target}` | {PURPOSE.get(name, '—')} |")
    n_user = sum(1 for r in rows if r[0] == "user")
    out.append(f"\n{n_user} user-scope, {len(rows) - n_user} project/plugin-scope servers.")
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="live MCP inventory")
    fmt = ap.add_mutually_exclusive_group()
    fmt.add_argument("--md", action="store_true", help="markdown table (default)")
    fmt.add_argument("--json", action="store_true", help="machine-readable list")
    a = ap.parse_args(argv)
    try:  # LF even when a Windows console or redirect would write CRLF
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    except (AttributeError, ValueError, OSError):
        pass
    rows = collect()
    if a.json:
        text = json.dumps([dict(zip(("scope", "name", "transport", "target"), r)) for r in rows], indent=1) + "\n"
    else:
        text = render_md(rows)
    sys.stdout.write(text)


if __name__ == "__main__":
    main()
