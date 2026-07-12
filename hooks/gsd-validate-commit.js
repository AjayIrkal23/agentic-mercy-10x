#!/usr/bin/env node
// gsd-hook-version: 1.42.3
// gsd-validate-commit.js — preToolUse(Bash|Shell) hook: enforce Conventional Commits.
//
// Portable 1:1 port of gsd-validate-commit.sh (P6-T2). Byte-identical behaviour:
// same opt-in gate, same git-commit detection via lib/git-cmd.js, same -m message
// extraction, same Conventional-Commits subject rules, same
// {permissionDecision:'deny', permissionDecisionReason} + exit 2 on violation.
// The .sh is retained only as the 30-day flip-back path.
//
// OPT-IN: a no-op unless .planning/config.json has hooks.community === true.
'use strict';

const fs = require('fs');
const path = require('path');
const { isGitSubcommand } = require(path.join(__dirname, 'lib', 'git-cmd.js'));

const VALID_TYPES = /^(feat|fix|docs|style|refactor|perf|test|build|ci|chore)(\(.+\))?:\s.+/;

function communityEnabled() {
  const cfgPath = path.join(process.cwd(), '.planning', 'config.json');
  if (!fs.existsSync(cfgPath)) return false;
  try {
    const c = JSON.parse(fs.readFileSync(cfgPath, 'utf8'));
    return c && c.hooks && c.hooks.community === true;
  } catch {
    return false;
  }
}

function readStdin() {
  return new Promise((resolve) => {
    let d = '';
    process.stdin.on('data', (c) => (d += c));
    process.stdin.on('end', () => resolve(d));
  });
}

function deny(reason) {
  process.stdout.write(JSON.stringify({ permissionDecision: 'deny', permissionDecisionReason: reason }));
  process.exit(2);
}

async function main() {
  if (!communityEnabled()) process.exit(0);

  const raw = await readStdin();
  let payload = {};
  try {
    payload = JSON.parse(raw);
  } catch {
    process.exit(0);
  }

  // Cursor uses Shell; Claude Code uses Bash — accept both.
  const tool = payload.tool_name || payload.tool || '';
  if (tool !== 'Shell' && tool !== 'Bash') process.exit(0);

  const cmd = (payload.tool_input && payload.tool_input.command) || '';
  if (!cmd) process.exit(0);

  if (!isGitSubcommand(cmd, 'commit')) process.exit(0);

  // Extract -m "..." or -m '...'
  let msg = '';
  let m = cmd.match(/-m\s+"([^"]+)"/);
  if (m) {
    msg = m[1];
  } else {
    m = cmd.match(/-m\s+'([^']+)'/);
    if (m) msg = m[1];
  }
  if (!msg) process.exit(0);

  const subject = msg.split('\n')[0];
  if (!VALID_TYPES.test(subject)) {
    deny(
      'Commit message must follow Conventional Commits: <type>(<scope>): <subject>. ' +
        'Valid types: feat, fix, docs, style, refactor, perf, test, build, ci, chore. ' +
        'Subject must be <=72 chars, lowercase, imperative mood, no trailing period.'
    );
  }
  if (subject.length > 72) {
    deny('Commit subject must be 72 characters or less.');
  }
  process.exit(0);
}

main();
