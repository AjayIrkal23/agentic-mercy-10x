#!/usr/bin/env node
/**
 * Plan Mode Gate — Plan Mode Entry Check
 *
 * Validates that pre-flight gates are complete before
 * entering plan mode. Called by SessionStart / PreToolUse hook.
 */

const fs = require('fs');
const path = require('path');

function checkRepoIndexed(cwd) {
  // Check for jcodemunch index indicator
  const homeDir = require('os').homedir();
  const indexDir = path.join(homeDir, '.code-index');
  // We can't easily check indexed state from JS, so we check for git
  try {
    const { execSync } = require('child_process');
    execSync('git rev-parse --git-dir', { cwd, stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
}

function detectExternalLibraries(cwd) {
  const pkgPaths = [
    path.join(cwd, 'package.json'),
    path.join(cwd, 'client', 'package.json'),
    path.join(cwd, 'server', 'package.json')
  ];

  const deps = [];
  for (const pkgPath of pkgPaths) {
    if (fs.existsSync(pkgPath)) {
      try {
        const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf-8'));
        deps.push(...Object.keys({ ...pkg.dependencies, ...pkg.devDependencies }));
      } catch { /* ignore */ }
    }
  }

  return [...new Set(deps)].filter(d => !d.startsWith('@types/') && !d.includes('eslint'));
}

function main() {
  const cwd = process.cwd();
  const hasGit = checkRepoIndexed(cwd);
  const libs = detectExternalLibraries(cwd);
  const isComplex = libs.length > 5;

  const reminder = {
    plan_mode_gate: true,
    repo_status: hasGit ? 'git_repo_detected' : 'no_git_repo',
    external_libraries: libs.length,
    complexity: isComplex ? 'complex' : 'simple',
    checklist: {
      superpowers: 'REQUIRED - Invoke using-superpowers skill (plugin) or read workflow-orchestrator',
      jcodemunch: hasGit ? 'OPTIONAL on Cursor - Enable only if jcodemunch MCP is installed and indexed' : 'OPTIONAL - Not a git repo',
      sequential: isComplex ? 'REQUIRED - Use sequentialthinking for complex task' : 'OPTIONAL - Task appears simple',
      context7: libs.length > 0 ? `REQUIRED - Query Context7 for ${libs.slice(0, 5).join(', ')}${libs.length > 5 ? '...' : ''}` : 'OPTIONAL - No external libraries detected'
    },
    reminder: `[PLAN MODE GATE ACTIVE]
Before entering plan mode or implementing, complete the pre-flight checklist:
1. Invoke using-superpowers skill or follow workflow-orchestrator
2. (Optional) If using jcodemunch MCP: plan_turn and assemble_task_context
3. Use sequentialthinking if task is complex
4. Use Context7 for external libraries

Announce: PLAN_GATE: superpowers=pass jcodemunch=skip|pass sequential=pass context7=pass mutation=open`
  };

  console.log(JSON.stringify(reminder, null, 2));
}

main();
