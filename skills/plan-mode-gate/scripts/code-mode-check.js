#!/usr/bin/env node
/**
 * Plan Mode Gate — Code Mode Entry Check
 *
 * Validates that pre-flight gates are complete before
 * first code edit in a session. Called by PreToolUse hook.
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

function getModifiedFiles(cwd) {
  try {
    let output;
    try {
      output = execSync('git diff --name-only HEAD', {
        cwd,
        encoding: 'utf-8',
        stdio: ['pipe', 'pipe', 'pipe']
      });
    } catch {
      output = execSync('git diff --name-only', {
        cwd,
        encoding: 'utf-8',
        stdio: ['pipe', 'pipe', 'pipe']
      });
    }
    return output.trim().split('\n').filter(Boolean);
  } catch {
    return [];
  }
}

function detectCodeFiles(files) {
  const codeExts = ['.js', '.jsx', '.ts', '.tsx', '.py', '.go', '.java', '.rs', '.php'];
  return files.filter(f => codeExts.includes(path.extname(f)));
}

function main() {
  const cwd = process.cwd();
  const modified = getModifiedFiles(cwd);
  const codeFiles = detectCodeFiles(modified);

  if (codeFiles.length === 0) {
    // No code changes yet, silent exit
    process.exit(0);
  }

  const reminder = {
    code_mode_gate: true,
    modified_code_files: codeFiles,
    reminder: `[CODE MODE GATE CHECK]
Code files have been modified in this session:
${codeFiles.map(f => `  - ${f}`).join('\n')}

Ensure the PLAN_GATE pre-flight checklist was completed:
1. Superpowers / workflow-orchestrator discipline (using-superpowers plugin or workflow-orchestrator)
2. (Optional) jcodemunch plan_turn if that MCP is enabled
3. Blast radius / symbol impact if modifying core paths (use your normal search + skills)
4. Relevant domain skills loaded

If gates were skipped, stop and complete them before further edits.`
  };

  console.log(JSON.stringify(reminder, null, 2));
}

main();
