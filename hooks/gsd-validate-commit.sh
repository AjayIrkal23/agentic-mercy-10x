#!/usr/bin/env bash
# gsd-hook-version: 1.42.3
# gsd-validate-commit.sh — preToolUse(Shell) hook: enforce Conventional Commits
#
# OPT-IN: This hook is a no-op unless config.json has hooks.community: true.

if [ -f .planning/config.json ]; then
  ENABLED=$(node -e "try{const c=require('./.planning/config.json');process.stdout.write(c.hooks?.community===true?'1':'0')}catch{process.stdout.write('0')}" 2>/dev/null)
  if [ "$ENABLED" != "1" ]; then exit 0; fi
else
  exit 0
fi

INPUT=$(cat)

# Cursor uses Shell; Claude Code uses Bash — accept both.
TOOL=$(echo "$INPUT" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{try{const p=JSON.parse(d);process.stdout.write(p.tool_name||p.tool||'')}catch{}})" 2>/dev/null)
if [ "$TOOL" != "Shell" ] && [ "$TOOL" != "Bash" ]; then
  exit 0
fi

CMD=$(echo "$INPUT" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{try{process.stdout.write(JSON.parse(d).tool_input?.command||'')}catch{}})" 2>/dev/null)

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
if GIT_CMD_LIB="$HOOK_DIR/lib/git-cmd.js" node -e "
  const {isGitSubcommand}=require(process.env.GIT_CMD_LIB);
  process.exit(isGitSubcommand(process.argv[1],'commit')?0:1);
" "$CMD" 2>/dev/null; then
  MSG=""
  if [[ "$CMD" =~ -m[[:space:]]+\"([^\"]+)\" ]]; then
    MSG="${BASH_REMATCH[1]}"
  elif [[ "$CMD" =~ -m[[:space:]]+\'([^\']+)\' ]]; then
    MSG="${BASH_REMATCH[1]}"
  fi

  if [ -n "$MSG" ]; then
    SUBJECT=$(echo "$MSG" | head -1)
    if ! [[ "$SUBJECT" =~ ^(feat|fix|docs|style|refactor|perf|test|build|ci|chore)(\(.+\))?:[[:space:]].+ ]]; then
      REASON="Commit message must follow Conventional Commits: <type>(<scope>): <subject>. Valid types: feat, fix, docs, style, refactor, perf, test, build, ci, chore. Subject must be <=72 chars, lowercase, imperative mood, no trailing period."
      node -e "const r=process.argv[1];process.stdout.write(JSON.stringify({permissionDecision:'deny',permissionDecisionReason:r}))" "$REASON"
      exit 2
    fi
    if [ ${#SUBJECT} -gt 72 ]; then
      REASON="Commit subject must be 72 characters or less."
      node -e "const r=process.argv[1];process.stdout.write(JSON.stringify({permissionDecision:'deny',permissionDecisionReason:r}))" "$REASON"
      exit 2
    fi
  fi
fi

exit 0
