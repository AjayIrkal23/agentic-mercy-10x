# Hooks -> rules -> skills, end to end

SessionStart + UserPromptSubmit hooks classify the prompt and inject the ranked skill pushes (post-overhaul: one prompt router, priority-budgeted). Rules in `~/.claude/rules` are always-in-context directives; skills are on-demand method bodies surfaced by the router. A skill fires when its triggers (keywords/paths/intents in the index) match; aliases keep every historic name firing. See `skill-linkage-story` for the full trace.
