#!/usr/bin/env node
/**
 * Plan Mode Gate — Auto Context Extraction
 *
 * Accepts a task description and points at the jcodemunch MCP server for
 * codebase context. NOTE: jcodemunch is an MCP server, not a shell CLI — there
 * is no `jcodemunch-mcp` binary. Use the MCP tools directly:
 *   mcp__jcodemunch__plan_turn / assemble_task_context / get_context_bundle.
 * The symbol index is kept fresh by the SessionStart index-lifecycle guard.
 *
 * Usage: node auto-context.js "<task description>"
 * Output: JSON with the MCP tool plan to run for this task
 */

const path = require('path');

// jcodemunch has no CLI; return the MCP invocation plan instead of shelling out
// to a nonexistent binary (fail-open, honest).
function jcodemunchPlan(task) {
  return {
    via: 'mcp',
    note: 'jcodemunch is an MCP server (no CLI). Run these tools for this task:',
    tools: [
      { tool: 'mcp__jcodemunch__plan_turn', arg: task },
      { tool: 'mcp__jcodemunch__assemble_task_context', arg: task },
      { tool: 'mcp__jcodemunch__get_repo_health' }
    ]
  };
}

function main() {
  const task = process.argv[2] || '';
  const cwd = process.cwd();

  if (!task) {
    console.log(JSON.stringify({ error: 'Usage: node auto-context.js "<task description>"' }, null, 2));
    process.exit(1);
  }

  const result = {
    task,
    cwd,
    jcodemunch: jcodemunchPlan(task),
    recommendations: {
      use_assemble_task_context: true,
      use_sequential_thinking: true,
      note: 'jcodemunch runs via MCP tools, not a CLI. The SessionStart '
        + 'index-lifecycle guard keeps the symbol index fresh for the active repo.'
    }
  };

  console.log(JSON.stringify(result, null, 2));
}

main();
