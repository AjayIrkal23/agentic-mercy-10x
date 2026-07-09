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

const STATE_DIR = path.join(__dirname, '.state');

// Patterns that HARD-BLOCK on first attempt.
// Rationale: these are unambiguous adversarial tokens with no legitimate use
// in .planning/ phase files or GSD plan documents.
const INJECTION_PATTERNS = [
  /ignore\s+(all\s+)?previous\s+instructions/i,
  /ignore\s+(all\s+)?above\s+instructions/i,
  /disregard\s+(all\s+)?previous/i,
  /forget\s+(all\s+)?(your\s+)?instructions/i,
  /override\s+(system|previous)\s+(prompt|instructions)/i,
  /you\s+are\s+now\s+(?:a|an|the)\s+/i,
  /pretend\s+(?:you(?:'re| are)\s+|to\s+be\s+)/i,
  /from\s+now\s+on,?\s+you\s+(?:are|will|should|must)/i,
  /(?:print|output|reveal|show|display|repeat)\s+(?:your\s+)?(?:system\s+)?(?:prompt|instructions)/i,
  /<\/?(?:system|assistant|human)>/i,
  /\[SYSTEM\]/i,
  /\[INST\]/i,
  /<<\s*SYS\s*>>/i,
];

// Advisory-only pattern — false-positive risk too high for hard block.
// "act as a reviewer" in documentation would be incorrectly blocked.
const ADVISORY_PATTERNS = [
  /act\s+as\s+(?:a|an|the)\s+(?!plan|phase|wave)/i,
];

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
