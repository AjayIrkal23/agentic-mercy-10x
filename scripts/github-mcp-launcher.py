#!/usr/bin/env python3
"""github-mcp-launcher.py — launch the GitHub MCP server with the `gh` token.

POSIX registers (installer/manifest.json ``add``):
    sh -c 'GITHUB_PERSONAL_ACCESS_TOKEN=$(gh auth token) exec npx -y @modelcontextprotocol/server-github'
Windows has no ``sh`` and Claude Code spawns MCP commands without a shell, so the
manifest's ``windows_add`` runs this script instead: it reads ``gh auth token`` at
launch (never stored) and starts the same server with the MCP stdio pipes inherited
(through ``cmd /c`` on Windows, where ``npx`` is a ``.cmd`` shim).
"""
import os
import subprocess
import sys

try:
    token = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=20,
                           stdin=subprocess.DEVNULL).stdout.strip()  # keep the MCP stdin pipe for the server
except (OSError, subprocess.TimeoutExpired):
    token = ""
env = dict(os.environ)
if token:
    env["GITHUB_PERSONAL_ACCESS_TOKEN"] = token
npx = ["cmd", "/c", "npx"] if os.name == "nt" else ["npx"]
sys.exit(subprocess.call([*npx, "-y", "@modelcontextprotocol/server-github"], env=env))
