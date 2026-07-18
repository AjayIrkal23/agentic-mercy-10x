#!/usr/bin/env node
// gsd-hook-version: 1.43.0
// GSD Prompt Injection Guard — PreToolUse hook
// Scans file content being written to .planning/ for prompt injection patterns.
// Defense-in-depth: hard-blocks injection on first attempt; allows on second (ack).
// Exception: 'act as' pattern stays advisory due to false-positive risk.
//
// Triggers on: Write/Edit/StrReplace tool calls targeting .planning/ files
// Action: permissionDecision: "deny" on first match; advisory on second match

const fs = require('fs');
const path = require('path');
const { toolName, isWriteTool, emitPreContext } = require('./lib/gsd-hook-io');
// Shared injection-pattern lib (P6-T4) — single source of truth, no drift.
// HARD_BLOCK_PATTERNS = the strict deny set (unchanged 13). Advisory tier now
// also covers SUMMARISATION_PATTERNS (strictly stronger; advisory, never a block).
const {
  HARD_BLOCK_PATTERNS: INJECTION_PATTERNS,
  ADVISORY_PATTERNS: _ROLE_ADVISORY,
  SUMMARISATION_PATTERNS,
} = require('./lib/injection-patterns');

const STATE_DIR = path.join(__dirname, '.state');

// Advisory-only patterns (role-assignment + summarisation-persistence) —
// emitPreContext, never deny (false-positive risk too high for a hard block).
const ADVISORY_PATTERNS = [..._ROLE_ADVISORY, ...SUMMARISATION_PATTERNS];

function _safeCid(cid) {
  return cid.replace(/[^a-zA-Z0-9_-]/g, '_');
}

function _stateFile(cid) {
  return path.join(STATE_DIR, `${_safeCid(cid)}.prompt-guard.json`);
}

function _loadState(cid) {
  try {
    const raw = fs.readFileSync(_stateFile(cid), 'utf8');
    return JSON.parse(raw);
  } catch {
    return { acked_injections: [] };
  }
}

function _saveState(cid, state) {
  try {
    fs.mkdirSync(STATE_DIR, { recursive: true });
    fs.writeFileSync(_stateFile(cid), JSON.stringify(state), 'utf8');
  } catch {
    // Non-fatal — state loss means next attempt will block again (safe degradation)
  }
}

function _emitDeny(filePath, findings) {
  const basename = path.basename(filePath);
  process.stdout.write(JSON.stringify({
    hookSpecificOutput: {
      hookEventName: 'PreToolUse',
      permissionDecision: 'deny',
      permissionDecisionReason:
        `INJECTION GUARD: Content written to ${basename} triggered ` +
        `${findings.length} injection detection pattern(s): [${findings.join(', ')}]. ` +
        'This content may manipulate agent context if written to .planning/. ' +
        'If content is legitimate (e.g., documentation about prompt injection), ' +
        're-run the write — the second attempt within this conversation will be allowed.',
    },
  }));
}

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

    const filePath = data.tool_input?.file_path || '';

    if (!filePath.includes('.planning/') && !filePath.includes('.planning\\')) {
      process.exit(0);
    }

    const content = data.tool_input?.content || data.tool_input?.new_string || '';
    if (!content) {
      process.exit(0);
    }

    const cid = data.conversation_id || '';
    const state = _loadState(cid);
    const ackedSet = new Set(state.acked_injections || []);

    const findings = [];
    for (const pattern of INJECTION_PATTERNS) {
      if (pattern.test(content)) {
        findings.push(pattern.source);
      }
    }

    if (/[\u200B-\u200F\u2028-\u202F\uFEFF\u00AD]/.test(content)) {
      findings.push('invisible-unicode-characters');
    }

    // Advisory-only patterns (act as) \u2014 emitPreContext, never deny
    const advisoryFindings = [];
    for (const pattern of ADVISORY_PATTERNS) {
      if (pattern.test(content)) {
        advisoryFindings.push(pattern.source);
      }
    }

    if (findings.length === 0) {
      if (advisoryFindings.length > 0) {
        emitPreContext(
          `\u26a0\ufe0f PROMPT GUARD (advisory): Content written to ${path.basename(filePath)} ` +
          `matched advisory pattern(s): ${advisoryFindings.join(', ')}. ` +
          'Review for unintended role-assignment instructions if this is not documentation.'
        );
      }
      process.exit(0);
    }

    // Check if ALL detected patterns have been acked in this conversation
    const unackedFindings = findings.filter(f => !ackedSet.has(f));

    if (unackedFindings.length === 0) {
      // All patterns previously acked \u2014 allow with advisory only
      emitPreContext(
        `\u26a0\ufe0f PROMPT GUARD (override active): Re-detected ${findings.length} pattern(s) in ` +
        `${path.basename(filePath)} but conversation ack found \u2014 proceeding. ` +
        'Patterns: ' + findings.join(', ')
      );
      process.exit(0);
    }

    // First occurrence of unacked patterns \u2014 hard block and record ack
    if (cid) {
      const newAcked = [...ackedSet, ...unackedFindings];
      _saveState(cid, { acked_injections: newAcked });
    }

    _emitDeny(filePath, unackedFindings);
  } catch {
    process.exit(0);
  }
});
