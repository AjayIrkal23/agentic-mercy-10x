#!/usr/bin/env node
/**
 * Plan Mode Gate — Auto Context Extraction
 *
 * Accepts a task description and auto-extracts codebase context
 * using jcodemunch CLI tools.
 *
 * Usage: node auto-context.js "<task description>"
 * Output: JSON with plan_turn results, task context, and repo health
 */

const { execSync } = require('child_process');
const path = require('path');

function runJcodemunch(args) {
  try {
    const output = execSync(`jcodemunch-mcp ${args}`, {
      encoding: 'utf-8',
      timeout: 30000,
      stdio: ['pipe', 'pipe', 'ignore']
    });
    return JSON.parse(output);
  } catch (err) {
    return { error: err.message, stderr: err.stderr };
  }
}

function resolveRepo(cwd) {
  try {
    const output = execSync(`jcodemunch-mcp index "${cwd}" --no-ai-summaries 2>&1`, {
      encoding: 'utf-8',
      timeout: 60000
    });
    return JSON.parse(output);
  } catch (err) {
    return { error: err.message };
  }
}

function main() {
  const task = process.argv[2] || '';
  const cwd = process.cwd();

  if (!task) {
    console.log(JSON.stringify({ error: 'Usage: node auto-context.js "<task description>"' }, null, 2));
    process.exit(1);
  }

  // Step 1: Resolve repo
  const repoInfo = resolveRepo(cwd);
  const repo = repoInfo.repo || 'unknown';

  // Step 2: Run plan_turn
  const planTurn = runJcodemunch(`plan_turn "${task.replace(/"/g, '\\"')}" --repo "${repo}"`);

  // Step 3: Run get_repo_health
  const health = runJcodemunch(`health --repo "${repo}"`);

  const result = {
    task,
    repo,
    indexed: !repoInfo.error,
    plan_turn: planTurn,
    repo_health: health,
    recommendations: {
      use_assemble_task_context: true,
      use_sequential_thinking: (planTurn.recommended_symbols || []).length > 5,
      check_hotspots: health.hotspots && health.hotspots.length > 0
    }
  };

  console.log(JSON.stringify(result, null, 2));
}

main();
