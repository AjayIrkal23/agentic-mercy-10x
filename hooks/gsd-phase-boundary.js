#!/usr/bin/env node
// gsd-hook-version: 1.42.3
// gsd-phase-boundary.js — postToolUse hook: detect .planning/ file writes.
//
// Portable 1:1 port of gsd-phase-boundary.sh (P6-T2): zero bash in the live
// hook path. Behaviour is byte-identical to the .sh — same opt-in gate, same
// file-path detection, same {additional_context, planning_modified, file_path}
// JSON emission. The .sh is retained only as the 30-day flip-back path.
//
// OPT-IN: a no-op unless .planning/config.json has hooks.community === true.
'use strict';

const fs = require('fs');
const path = require('path');

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
    // If nothing is piped, resolve empty after the stream ends.
  });
}

async function main() {
  if (!communityEnabled()) {
    process.exit(0);
  }
  const raw = await readStdin();
  let file = '';
  try {
    const p = JSON.parse(raw);
    file = (p.tool_input && p.tool_input.file_path) || '';
  } catch {
    file = '';
  }

  const planningModified = file.includes('.planning/') || file.startsWith('.planning/');
  if (planningModified) {
    const text =
      '.planning/ file modified: ' + file + '\n' +
      'Check: Should STATE.md be updated to reflect this change?';
    process.stdout.write(
      JSON.stringify({
        additional_context: text,
        planning_modified: true,
        file_path: file,
      })
    );
  }
  process.exit(0);
}

main();
