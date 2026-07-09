#!/usr/bin/env bash
# lean-ctx PreToolUse hook — rewrites bash commands to lean-ctx equivalents
set -euo pipefail

LEAN_CTX_BIN="lean-ctx"

INPUT=$(cat)
TOOL=$(echo "$INPUT" | grep -oE '"tool_name":"([^"\\]|\\.)*"' | head -1 | sed 's/^"tool_name":"//;s/"$//' | sed 's/\\"/"/g;s/\\\\/\\/g')

case "$TOOL" in
  Bash|bash|PowerShell|powershell) ;;
  *) exit 0 ;;
esac

CMD=$(echo "$INPUT" | grep -oE '"command":"([^"\\]|\\.)*"' | head -1 | sed 's/^"command":"//;s/"$//' | sed 's/\\"/"/g;s/\\\\/\\/g')

if [ -z "$CMD" ] || echo "$CMD" | grep -qE "^(lean-ctx |$LEAN_CTX_BIN )"; then
  exit 0
fi

case "$CMD" in
  git\ *|gh\ *|cargo\ *|npm\ *|pnpm\ *|yarn\ *|bun\ *|bunx\ *|deno\ *|vite\ *|pip\ *|pip3\ *|pytest\ *|mypy\ *|ruff\ *|go\ *|golangci\-lint*|docker\ *|docker\-compose*|kubectl\ *|helm\ *|aws\ *|terraform\ *|tofu\ *|eslint\ *|prettier\ *|tsc\ *|biome\ *|curl\ *|wget\ *|php\ *|composer\ *|dotnet\ *|bundle\ *|rake\ *|mix\ *|swift\ *|zig\ *|cmake\ *|make\ *|rg\ *|ls\ *|find\ *)
    # Shell-escape then JSON-escape (two passes)
    SHELL_ESC=$(printf '%s' "$CMD" | sed 's/\\/\\\\/g;s/"/\\"/g')
    REWRITE="$LEAN_CTX_BIN -c \"$SHELL_ESC\""
    JSON_CMD=$(printf '%s' "$REWRITE" | sed 's/\\/\\\\/g;s/"/\\"/g')
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","updatedInput":{"command":"%s"}}}' "$JSON_CMD"
    ;;
  *) exit 0 ;;
esac
