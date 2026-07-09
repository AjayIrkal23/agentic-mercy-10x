'use strict';

/**
 * Shared GSD hook I/O helpers for Cursor + Claude Code runtimes.
 * Cursor tool names: Shell, StrReplace, Task, Write
 * Claude tool names: Bash, Edit, Agent, Write, MultiEdit
 */

const os = require('os');
const path = require('path');

const WRITE_TOOLS = new Set(['Write', 'Edit', 'StrReplace', 'MultiEdit', 'TabWrite']);
const SHELL_TOOLS = new Set(['Shell', 'Bash']);
const AGENT_TOOLS = new Set(['Task', 'Agent']);
const READ_TOOLS = new Set(['Read', 'TabRead']);

function toolName(data) {
  return data?.tool_name || data?.tool || '';
}

function isWriteTool(name) {
  return WRITE_TOOLS.has(name);
}

function isShellTool(name) {
  return SHELL_TOOLS.has(name);
}

function isAgentTool(name) {
  return AGENT_TOOLS.has(name);
}

function isReadTool(name) {
  return READ_TOOLS.has(name);
}

/**
 * Cursor and Claude Code enforce read-before-edit natively.
 */
function isNativeReadBeforeEdit(data) {
  const runtime = (process.env.CURSOR_CONFIG_DIR || process.env.CLAUDE_CONFIG_DIR || '').toLowerCase();
  if (runtime.includes('.claude')) {
    return true;
  }
  if (process.env.CURSOR_AGENT === '1' || process.env.CLAUDE_CODE === '1') {
    return true;
  }
  const hookEvent = data?.hook_event_name || data?.hookEventName || '';
  if (/cursor|claude/i.test(String(data?.agent || ''))) {
    return true;
  }
  // Default: assume native enforcement on modern harnesses unless OpenCode/Gemini env set.
  if (process.env.GEMINI_API_KEY || process.env.OPENCODE === '1') {
    return false;
  }
  return true;
}

function sessionId(data) {
  return data?.conversation_id || data?.session_id || '';
}

/** Bridge file written by gsd-statusline.js for gsd-context-monitor.js */
function ctxBridgePath(sid) {
  const safe = String(sid || '').replace(/[/\\]/g, '_');
  return path.join(os.tmpdir(), `gsd-ctx-${safe}.json`);
}

function emitHookContext(eventName, message) {
  const out = {
    continue: true,
    additional_context: message,
    hookSpecificOutput: {
      hookEventName: eventName,
      additionalContext: message,
    },
  };
  process.stdout.write(JSON.stringify(out));
}

function emitPreContext(message) {
  emitHookContext('PreToolUse', message);
}

function emitPostContext(message) {
  const event = process.env.GEMINI_API_KEY ? 'AfterTool' : 'PostToolUse';
  emitHookContext(event, message);
}

module.exports = {
  toolName,
  isWriteTool,
  isShellTool,
  isAgentTool,
  isReadTool,
  isNativeReadBeforeEdit,
  sessionId,
  ctxBridgePath,
  emitPreContext,
  emitPostContext,
  emitHookContext,
  WRITE_TOOLS,
  SHELL_TOOLS,
  AGENT_TOOLS,
};
