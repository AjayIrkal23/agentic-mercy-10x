#!/usr/bin/env node
// gsd-hook-version: 1.42.3
// GSD Workflow Guard — PreToolUse hook
// Detects direct file edits outside a GSD workflow context and injects advisory warning.
//
// Enable via config: hooks.workflow_guard: true (default: false)
// Only triggers on Write/Edit/StrReplace tool calls to non-.planning/ files.

const fs = require('fs');
const path = require('path');
const { toolName, isWriteTool, emitPreContext } = require('./lib/gsd-hook-io');

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

    if (data.tool_input?.is_subagent || data.session_type === 'task') {
      process.exit(0);
    }

    const filePath = data.tool_input?.file_path || data.tool_input?.path || '';

    if (filePath.includes('.planning/') || filePath.includes('.planning\\')) {
      process.exit(0);
    }

    const allowedPatterns = [
      /\.gitignore$/,
      /\.env/,
      /CLAUDE\.md$/,
      /AGENTS\.md$/,
      /GEMINI\.md$/,
      /CURSOR\.md$/,
      /settings\.json$/,
    ];
    if (allowedPatterns.some(p => p.test(filePath))) {
      process.exit(0);
    }

    const cwd = data.cwd || process.cwd();
    const configPath = path.join(cwd, '.planning', 'config.json');
    if (fs.existsSync(configPath)) {
      try {
        const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
        if (!config.hooks?.workflow_guard) {
          process.exit(0);
        }
      } catch (e) {
        process.exit(0);
      }
    } else {
      process.exit(0);
    }

    emitPreContext(
      `⚠️ WORKFLOW ADVISORY: You're editing ${path.basename(filePath)} directly without a GSD command. ` +
      'This edit will not be tracked in STATE.md or produce a SUMMARY.md. ' +
      'Consider using /gsd:fast for trivial fixes or /gsd:quick for larger changes ' +
      'to maintain project state tracking. ' +
      'If this is intentional (e.g., user explicitly asked for a direct edit), proceed normally.'
    );
  } catch (e) {
    process.exit(0);
  }
});
