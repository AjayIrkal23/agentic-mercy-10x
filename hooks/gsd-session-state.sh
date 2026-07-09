#!/usr/bin/env bash
# gsd-hook-version: 1.42.3
# gsd-session-state.sh — sessionStart hook: inject project state reminder
# Outputs STATE.md head on every session start for orientation.
#
# OPT-IN: This hook is a no-op unless config.json has hooks.community: true.

INPUT=$(cat)

WORKSPACE=""
if command -v node >/dev/null 2>&1; then
  WORKSPACE=$(echo "$INPUT" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{try{const p=JSON.parse(d);const r=p.workspace_roots||[];process.stdout.write(r[0]||'')}catch{}})" 2>/dev/null)
fi
if [ -z "$WORKSPACE" ]; then
  WORKSPACE="$(pwd)"
fi
cd "$WORKSPACE" 2>/dev/null || exit 0

if [ -f .planning/config.json ]; then
  ENABLED=$(node -e "try{const c=require('./.planning/config.json');process.stdout.write(c.hooks?.community===true?'1':'0')}catch{process.stdout.write('0')}" 2>/dev/null)
  if [ "$ENABLED" != "1" ]; then exit 0; fi
else
  exit 0
fi

STATE_PRESENT="false"
STATE_HEAD=""
if [ -f .planning/STATE.md ]; then
  STATE_PRESENT="true"
  STATE_HEAD=$(head -20 .planning/STATE.md)
fi

CONFIG_MODE="unknown"
if [ -f .planning/config.json ]; then
  CONFIG_MODE=$(node -e "try{const c=require('./.planning/config.json');process.stdout.write(String(c.mode||'unknown'))}catch{process.stdout.write('unknown')}" 2>/dev/null)
fi

node -e '
  const [statePresent, stateHead, configMode] = process.argv.slice(1);
  const headerLines = ["## Project State Reminder", ""];
  if (statePresent === "true") {
    headerLines.push("STATE.md exists - check for blockers and current phase.");
    if (stateHead) headerLines.push(stateHead);
  } else {
    headerLines.push("No .planning/ found - suggest /gsd-new-project if starting new work.");
  }
  headerLines.push("");
  headerLines.push("Config: \"mode\": \"" + configMode + "\"");
  const text = headerLines.join("\n");
  const out = {
    additionalContext: text,
  };
  process.stdout.write(JSON.stringify(out));
' "$STATE_PRESENT" "$STATE_HEAD" "$CONFIG_MODE"

exit 0
