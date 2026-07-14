#!/usr/bin/env bash
# ============================================================================
#  claude-workflow — one-command installer
#  Integrates this workspace into ~/.claude on a fresh or existing machine,
#  WITHOUT deleting anything you already have.
#
#  Usage:
#     git clone https://github.com/<you>/claude-workflow ~/.claude-repo
#     ~/.claude-repo/install.sh
#
#  Or, if you cloned straight to ~/.claude, just run: ~/.claude/install.sh
#
#  Ubuntu-focused. Idempotent — safe to re-run.
#  Requires: git, python3.   Optional: bun (gstack build), gh, rsync, uv.
# ============================================================================
set -euo pipefail

# --- locate the repo (this script's own directory) and the target ----------
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${CLAUDE_HOME:-$HOME/.claude}"
TS="$(date +%Y%m%d-%H%M%S)"

# --- pretty output ---------------------------------------------------------
c_bold=$'\033[1m'; c_grn=$'\033[32m'; c_ylw=$'\033[33m'; c_red=$'\033[31m'; c_dim=$'\033[2m'; c_off=$'\033[0m'
say()  { printf '%s\n' "${c_bold}==>${c_off} $*"; }
ok()   { printf '%s\n' "  ${c_grn}ok${c_off}  $*"; }
warn() { printf '%s\n' "  ${c_ylw}!!${c_off}  $*"; }
err()  { printf '%s\n' "  ${c_red}xx${c_off}  $*" >&2; }
note() { printf '%s\n' "      ${c_dim}$*${c_off}"; }

# --- consent helper: default YES on a TTY, auto-SKIP when non-interactive ---
ask() {
  local prompt="$1" reply
  if [ ! -t 0 ]; then note "non-interactive: skipping ($prompt) — run it manually later"; return 1; fi
  read -r -p "  ${c_bold}?${c_off} ${prompt} [Y/n] " reply || true
  case "${reply:-y}" in [nN]*) return 1;; *) return 0;; esac
}

require() { command -v "$1" >/dev/null 2>&1; }

# --- preflight -------------------------------------------------------------
say "claude-workflow installer"
note "repo:   $REPO_DIR"
note "target: $TARGET"

for bin in git python3; do
  require "$bin" || { err "missing required dependency: $bin"; exit 1; }
done
ok "git + python3 present"
require bun || warn "bun not found — the gstack skill won't be built (optional)"
require gh  || warn "gh not found — you'll configure GitHub/plugins manually (optional)"

# --- STEP 1: put the workspace into $TARGET --------------------------------
same_path() { [ "$(cd "$1" 2>/dev/null && pwd)" = "$(cd "$2" 2>/dev/null && pwd)" ]; }

if same_path "$REPO_DIR" "$TARGET"; then
  say "workspace is already at $TARGET (cloned in place) — nothing to copy"
elif [ ! -e "$TARGET" ]; then
  say "fresh machine: copying workspace into $TARGET"
  mkdir -p "$TARGET"
  if require rsync; then
    rsync -a "$REPO_DIR"/ "$TARGET"/
  else
    cp -a "$REPO_DIR"/. "$TARGET"/
  fi
  ok "workspace installed to $TARGET"
else
  say "existing $TARGET found — backing up before merge (nothing is deleted)"
  BACKUP="$HOME/.claude-backup-$TS.tgz"
  tar czf "$BACKUP" -C "$(dirname "$TARGET")" "$(basename "$TARGET")"
  ok "backup written: $BACKUP"
  say "merging workspace into $TARGET (add/update only — your extra files stay)"
  if require rsync; then
    # NO --delete: files you have that the repo doesn't are preserved.
    rsync -a "$REPO_DIR"/ "$TARGET"/
  else
    cp -a "$REPO_DIR"/. "$TARGET"/
  fi
  ok "workspace merged into $TARGET"
fi

cd "$TARGET"

# --- STEP 2: re-installable externals (gitignored; fetched here) -----------
say "optional externals (not shipped in the repo — cloned on consent)"

# gstack — the /ship, /qa, /browse, /health, design-* skill suite
if [ -d "$TARGET/skills/gstack/.git" ]; then
  ok "gstack already present (skills/gstack)"
elif ask "clone gstack suite -> skills/gstack (github.com/garrytan/gstack)?"; then
  rm -rf "$TARGET/skills/gstack"
  git clone --depth 1 https://github.com/garrytan/gstack.git "$TARGET/skills/gstack" \
    && ok "gstack cloned" || warn "gstack clone failed — clone it manually later"
  if [ -d "$TARGET/skills/gstack" ]; then
    if [ -x "$TARGET/skills/gstack/setup" ]; then
      ( cd "$TARGET/skills/gstack" && ./setup ) && ok "gstack setup ran" || warn "gstack ./setup failed"
    elif require bun && [ -f "$TARGET/skills/gstack/package.json" ]; then
      ( cd "$TARGET/skills/gstack" && bun install && (bun run build 2>/dev/null || true) ) \
        && ok "gstack built with bun" || warn "gstack bun build failed — run it manually"
    else
      note "install bun and run 'bun install && bun run build' in skills/gstack to finish gstack"
    fi
  fi
else
  note "skipped gstack"
fi

# ast-grep-mcp — powers the ast-grep MCP server referenced in settings.json
if [ -d "$TARGET/ast-grep-mcp/.git" ]; then
  ok "ast-grep-mcp already present"
elif ask "clone ast-grep-mcp -> ast-grep-mcp/ (github.com/ast-grep/ast-grep-mcp)?"; then
  git clone --depth 1 https://github.com/ast-grep/ast-grep-mcp.git "$TARGET/ast-grep-mcp" \
    && ok "ast-grep-mcp cloned" || warn "clone failed — the ast-grep MCP server is optional"
  note "run 'uv sync' (or pip install) inside ast-grep-mcp/ if you use the ast-grep MCP server"
else
  note "skipped ast-grep-mcp"
fi

# get-shit-done (GSD) — the gsd-* command + agent system.
# Canonical distribution is uncertain (npm 'get-shit-done-cc' / a GSD installer);
# not auto-cloned to avoid fetching the wrong source. Install manually:
if [ -d "$TARGET/get-shit-done" ]; then
  ok "get-shit-done (GSD) already present"
else
  warn "get-shit-done (GSD) not present — install it manually"
  note "GSD ships the gsd-* skills/agents. Best-effort: 'npx get-shit-done-cc' or the"
  note "GSD installer, then '/gsd-update'. Replace this with the exact command once known."
fi

# --- STEP 2.5: code/doc intelligence stack (claude-native MCP servers) ------
say "code/doc intelligence stack (graphify + jdocmunch — claude-native)"
if [ -f "$TARGET/scripts/install-graphify.sh" ] && ask "install/refresh graphify (dependency-graph MCP, claude-owned venv)?"; then
  bash "$TARGET/scripts/install-graphify.sh" || warn "graphify install had issues — re-run scripts/install-graphify.sh"
else
  note "skipped graphify — run scripts/install-graphify.sh later"
fi
if [ -f "$TARGET/scripts/install-jdocmunch.sh" ] && ask "install/refresh jdocmunch (docs-index MCP)?"; then
  bash "$TARGET/scripts/install-jdocmunch.sh" --no-index || warn "jdocmunch install had issues — re-run scripts/install-jdocmunch.sh"
else
  note "skipped jdocmunch — run scripts/install-jdocmunch.sh later"
fi
note "jcodemunch stays a separate external tool — install jcodemunch-mcp yourself (uv/pipx)."

# --- STEP 3: post-install notes (things the repo deliberately excludes) ----
say "${c_bold}post-install — finish these yourself${c_off}"

cat <<'NOTES'

  1) PLUGINS  (re-installable; manifests are per-machine and NOT in the repo)
     Add the marketplaces, then install the plugins:

       claude plugin marketplace add anthropics/claude-plugins-official
       claude plugin marketplace add veelenga/claude-mermaid
       claude plugin marketplace add obra/superpowers-marketplace
       claude plugin marketplace add forrestchang/andrej-karpathy-skills
       claude plugin marketplace add DietrichGebert/ponytail

     Plugins used by this workspace (install the ones you want):
       superpowers, ponytail, andrej-karpathy-skills, claude-mermaid,
       frontend-design, context7, supabase, firecrawl, playwright,
       clickhouse, gopls-lsp, typescript-lsp, claude-session-driver,
       double-shot-latte, elements-of-style, superpowers-lab
     e.g.:  claude plugin install superpowers@superpowers-marketplace

  2) MCP SERVERS  (live in ~/.claude.json, which is NOT in this repo)
     The hooks/agents expect these servers configured on your machine:
       jcodemunch, graphify, jdocmunch, lean-ctx, memory, sequential-thinking, context7
     Also referenced in settings.json mcpServers (edit/remove as you like):
       ast-grep, semgrep, playwright, browser-tools-mcp, fetch, markdownify, github
     graphify + jdocmunch are wired by STEP 2.5 above (scripts/install-graphify.sh,
     scripts/install-jdocmunch.sh — claude-native, no cursor coupling). jcodemunch is
     a separate external tool (jcodemunch-mcp). Configure your own creds — none shipped.

  3) SECRETS  are never in this repo:
       .credentials.json, tokens, API keys, and ~/.claude.json stay on YOUR
       machine only. settings.json references env vars (e.g. ${GITHUB_TOKEN}) —
       export them in your shell profile.

  4) OPTIONAL TOOLS the workflow leans on: bun, gh, ripgrep, semgrep, uv,
     golangci-lint (Go TDD). Index freshness is event-driven (index-lifecycle.py,
     active-repo only) — no watch daemons.

NOTES

say "${c_grn}done.${c_off} Start a new Claude Code session in any repo to pick up the workflow."
