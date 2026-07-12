#!/usr/bin/env node
// gsd-hook-version: 1.42.3
// gsd-session-state.js — sessionStart hook: inject project state reminder.
//
// Portable 1:1 port of gsd-session-state.sh (P6-T2). Byte-identical behaviour:
// same opt-in gate, same workspace resolution (payload.workspace_roots[0] then
// cwd), same STATE.md head + config-mode emission via {additionalContext}.
// The .sh is retained only as the 30-day flip-back path.
//
// OPT-IN: a no-op unless .planning/config.json has hooks.community === true.
'use strict';

const fs = require('fs');
const path = require('path');

function readStdin() {
  return new Promise((resolve) => {
    let d = '';
    process.stdin.on('data', (c) => (d += c));
    process.stdin.on('end', () => resolve(d));
  });
}

function readConfigField(cfgPath, pick) {
  try {
    const c = JSON.parse(fs.readFileSync(cfgPath, 'utf8'));
    return pick(c);
  } catch {
    return undefined;
  }
}

async function main() {
  const raw = await readStdin();
  let workspace = '';
  try {
    const p = JSON.parse(raw);
    const r = p.workspace_roots || [];
    workspace = r[0] || '';
  } catch {
    workspace = '';
  }
  if (!workspace) workspace = process.cwd();

  // cd "$WORKSPACE" 2>/dev/null || exit 0
  try {
    process.chdir(workspace);
  } catch {
    process.exit(0);
  }

  const cfgPath = path.join(process.cwd(), '.planning', 'config.json');
  if (!fs.existsSync(cfgPath)) {
    process.exit(0);
  }
  const enabled = readConfigField(cfgPath, (c) => (c.hooks && c.hooks.community === true ? '1' : '0'));
  if (enabled !== '1') {
    process.exit(0);
  }

  const statePath = path.join(process.cwd(), '.planning', 'STATE.md');
  let statePresent = false;
  let stateHead = '';
  if (fs.existsSync(statePath)) {
    statePresent = true;
    try {
      // head -20, then strip trailing newlines exactly like bash $(...) does.
      stateHead = fs
        .readFileSync(statePath, 'utf8')
        .split('\n')
        .slice(0, 20)
        .join('\n')
        .replace(/\n+$/, '');
    } catch {
      stateHead = '';
    }
  }

  let configMode = 'unknown';
  const m = readConfigField(cfgPath, (c) => (c.mode != null ? String(c.mode) : 'unknown'));
  if (m !== undefined) configMode = m;

  const headerLines = ['## Project State Reminder', ''];
  if (statePresent) {
    headerLines.push('STATE.md exists - check for blockers and current phase.');
    if (stateHead) headerLines.push(stateHead);
  } else {
    headerLines.push('No .planning/ found - suggest /gsd-new-project if starting new work.');
  }
  headerLines.push('');
  headerLines.push('Config: "mode": "' + configMode + '"');

  process.stdout.write(JSON.stringify({ additionalContext: headerLines.join('\n') }));
  process.exit(0);
}

main();
