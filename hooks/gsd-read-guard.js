#!/usr/bin/env node
// gsd-hook-version: 1.42.3
// GSD Read Guard — PreToolUse hook
// Injects advisory guidance when Write/Edit/StrReplace targets an existing file,
// reminding the model to Read the file first.
//
// Cursor and Claude Code natively enforce read-before-edit — this hook no-ops
// on those runtimes. It remains useful for OpenCode/Gemini/Kilo where the loop
// can occur.

const fs = require('fs');
const path = require('path');
const { toolName, isWriteTool, isNativeReadBeforeEdit, emitPreContext } = require('./lib/gsd-hook-io');

let input = '';
const stdinTimeout = setTimeout(() => process.exit(0), 3000);
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => input += chunk);
process.stdin.on('end', () => {
  clearTimeout(stdinTimeout);
  try {
    const data = JSON.parse(input);
    const name = toolName(data);

    if (!isWriteTool(name)) {
      process.exit(0);
    }

    if (isNativeReadBeforeEdit(data)) {
      process.exit(0);
    }

    const filePath = data.tool_input?.file_path || '';
    if (!filePath) {
      process.exit(0);
    }

    let fileExists = false;
    try {
      fs.accessSync(filePath, fs.constants.F_OK);
      fileExists = true;
    } catch {
      // File does not exist — no guidance needed
    }

    if (!fileExists) {
      process.exit(0);
    }

    const fileName = path.basename(filePath);

    emitPreContext(
      `READ-BEFORE-EDIT REMINDER: You are about to modify "${fileName}" which already exists. ` +
      'If you have not already used the Read tool to read this file in the current session, ' +
      'you MUST Read it first before editing. The runtime will reject edits to files that ' +
      'have not been read. Use the Read tool on this file path, then retry your edit.'
    );
  } catch {
    process.exit(0);
  }
});
