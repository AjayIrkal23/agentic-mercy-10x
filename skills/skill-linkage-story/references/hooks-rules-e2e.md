# Hook -> rule -> skill lifecycle (Claude Code)

Post-overhaul architecture: a single UserPromptSubmit prompt router classifies once, ranks skills from the index, applies substrate precedence, and emits a priority-budgeted injection; PreToolUse/Stop gates stay wired per link. (The former Cursor sessionStart/beforeSubmit/preToolUse/postToolUse/stop model is superseded — see rules/agent-lifecycle-routing.md.)
