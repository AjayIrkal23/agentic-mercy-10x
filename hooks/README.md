# Hooks workflow

**Source of truth:** `~/.claude/hooks/` and `~/.claude/hooks.json`

After editing hooks:

1. Run `bash ~/.claude/hooks/verify-hooks.sh`
2. Run `bash ~/.claude/hooks/sync-hooks-to-claude.sh` (keeps `~/.claude/hooks` identical)
3. Restart Cursor (Hooks reload on save; restart if hooks do not fire)

**Stacks:** jcodemunch (index + enforce), graphify (graph + enforce), lean-ctx (Shell rewrite/observe/redirect).

**Sync:** Cursor registry is `hooks.json`; Claude Code registry remains in `~/.claude/settings.json`.
