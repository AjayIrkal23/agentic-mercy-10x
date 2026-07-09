#!/usr/bin/env bash
# gsd-hook-version: 1.42.3
# gsd-phase-boundary.sh — postToolUse hook: detect .planning/ file writes
#
# OPT-IN: This hook is a no-op unless config.json has hooks.community: true.

if [ -f .planning/config.json ]; then
  ENABLED=$(node -e "try{const c=require('./.planning/config.json');process.stdout.write(c.hooks?.community===true?'1':'0')}catch{process.stdout.write('0')}" 2>/dev/null)
  if [ "$ENABLED" != "1" ]; then exit 0; fi
else
  exit 0
fi

INPUT=$(cat)

FILE=$(echo "$INPUT" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{try{const p=JSON.parse(d);process.stdout.write(p.tool_input?.file_path||'')}catch{}})" 2>/dev/null)

PLANNING_MODIFIED="false"
if [[ "$FILE" == *.planning/* ]] || [[ "$FILE" == .planning/* ]]; then
  PLANNING_MODIFIED="true"
fi

if [ "$PLANNING_MODIFIED" = "true" ]; then
  node -e '
    const file = process.argv[1];
    const text = ".planning/ file modified: " + file + "\n" +
      "Check: Should STATE.md be updated to reflect this change?";
    process.stdout.write(JSON.stringify({
      additional_context: text,
      planning_modified: true,
      file_path: file,
    }));
  ' "$FILE"
fi

exit 0
