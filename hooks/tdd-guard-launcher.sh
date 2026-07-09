#!/usr/bin/env bash
# tdd-guard-launcher.sh — gate tdd-guard to ACTIVE projects only.
#
# tdd-guard is installed globally so the binary is AVAILABLE everywhere, but the
# source defaults to `guardEnabled ?? true` — i.e. it would enforce in EVERY repo
# (incl. test-less ones) if wired directly. This launcher makes enforcement
# strictly opt-in per project:
#
#   A repo is "active" iff it has:  <project>/.claude/tdd-guard/data/config.json
#   with "guardEnabled" not set to false.
#
# Active repo   -> forward the hook payload to tdd-guard (real TDD enforcement).
# Inactive repo -> exit 0 immediately (allow, ZERO validation/LLM cost).
#
# Wired globally on PreToolUse(Write|Edit|MultiEdit|TodoWrite), UserPromptSubmit,
# and SessionStart(startup|resume|clear). Fails OPEN on any error.
set -o pipefail

INPUT="$(cat)"
DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
CFG="$DIR/.claude/tdd-guard/data/config.json"

# Active project? Opt-in marker present and not explicitly disabled.
if [ -f "$CFG" ] && ! grep -Eq '"guardEnabled"[[:space:]]*:[[:space:]]*false' "$CFG"; then
  export CLAUDE_PROJECT_DIR="$DIR"
  # WARN mode + project scoping: the gate runs tdd-guard, allows files outside the
  # project, and downgrades any block to a non-blocking advisory. Never pauses.
  printf '%s' "$INPUT" | python3 "$HOME/.claude/hooks/tdd-guard-gate.py"
  exit 0
fi

# Inactive project -> allow silently.
exit 0
