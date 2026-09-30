#!/usr/bin/env python3
"""Print the live MCP inventory as a markdown table.

Sources (D13: ~/.claude.json is the only live MCP store):
  - ~/.claude.json            mcpServers (user scope) + projects.*.mcpServers
  - plugins/installed_plugins.json -> each plugin's .mcp.json (plugin-provided servers)

Used to regenerate skills/mcp-usage-standards/references/mcp-inventory.md and by the doctor.
  python3 scripts/mcp_inventory.py            # markdown
  python3 scripts/mcp_inventory.py --json     # machine-readable
"""
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


def main():
    rows = collect()
    if "--json" in sys.argv:
        print(json.dumps([dict(zip(("scope", "name", "transport", "target"), r)) for r in rows], indent=1))
        return
    print("| Server | Scope | Transport | Target | Reach for it when |")
    print("|---|---|---|---|---|")
    for scope, name, t, target in rows:
        print(f"| `{name}` | {scope} | {t} | `{target}` | {PURPOSE.get(name, '—')} |")
    n_user = sum(1 for r in rows if r[0] == "user")
    print(f"\n{n_user} user-scope, {len(rows) - n_user} project/plugin-scope servers.")


if __name__ == "__main__":
    main()
