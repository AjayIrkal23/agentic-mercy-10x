# Claude ↔ Cursor Parity Audit

**Date:** 2026-05-22  
**Source of truth:** `~/.cursor/` (hooks.json, hooks/, rules/, skills/)  
**Target:** `~/.claude/` (settings.json hooks, mirrored assets)

## Executive summary

| Layer | Match? | Action taken |
|-------|--------|--------------|
| Hook **scripts** | Yes (rsync) | `sync-hooks-to-claude.sh` |
| Hook **registry** | Was **no** | `sync-settings-hooks-to-claude.py` |
| Rules | Yes (rsync) | `sync-rules-to-claude.sh` |
| Skills | 207 vs 208 | Copy `skill-linkage-story` |
| Agents | 41 vs 42 | Copy `agents/README.md` |
| MCP jcodemunch | Missing in Claude | `--add-jcodemunch` |
| Model / bypass / statusLine | Claude-only | **Preserve** — never overwrite |

## P0 gaps (fixed by sync)

| ID | Gap | Severity | Fix |
|----|-----|----------|-----|
| P0-1 | `post-write-aggregator` not in Claude registry (3 separate hooks) | P0 | Registry sync |
| P0-2 | `security-semgrep-tracker` missing on Bash | P0 | Registry sync |
| P0-3 | `santa-method-writer` missing on Task | P0 | Registry sync |
| P0-4 | `graphify-enforce` matcher Agent-only | P0 | Registry sync → Task\|Agent via Bash |
| P0-5 | No automated registry sync | P0 | `sync-settings-hooks-to-claude.py` |
| P0-6 | Santa infra paths `.claude/hooks/` not exempt | P0 | `hard-completion-gate.py` markers |

## P1 gaps

| ID | Gap | Action |
|----|-----|--------|
| P1-1 | `lean-ctx hook redirect` missing in Claude | Registry sync |
| P1-2 | `token-stack-prompt-reminder` vs split prompt hooks | Sync + **preserve** Claude prompt-submit hooks |
| P1-3 | `afterMCPExecution` jcodemunch | Mapped to `AfterMcpExecution` (if supported by Claude Code) |
| P1-4 | Separate `.state` per runtime | Documented — expected |
| P1-5 | GSD paths reference `.cursor` in some workflow refs | Optional path fix in `.claude/get-shit-done` |

## Preserve list (never remove)

| Item | Location |
|------|----------|
| `model` | `claude-opus-4-6` |
| `permissions.defaultMode` | `bypassPermissions` |
| `effortLevel` | `xhigh` |
| `statusLine` | `gsd-statusline.js` |
| `gsd-read-guard.js` | PreToolUse |
| `jcodemunch-enforce.py prompt-submit` | UserPromptSubmit |
| `graphify-enforce.py prompt-submit` | UserPromptSubmit |
| `enabledPlugins`, `env`, plugins MCP roster | settings root |

## Parity matrix (registry)

| Surface | Cursor | Claude (after sync) | Preserve? |
|---------|--------|---------------------|-----------|
| Post-write chain | `post-write-aggregator.py` | Same | No |
| Semgrep track | `security-semgrep-tracker` / Shell | Bash matcher | No |
| Santa | `santa-method-writer` / Task | Task\|Agent | No |
| Read guard | — | `gsd-read-guard.js` | **Yes** |
| Prompt enforcers | `token-stack-prompt-reminder` | + preserved direct hooks | **Yes** |
| Stop gate | `hard-completion-gate` | Same | No |
| Fullstack skills | `fullstack-skills-reminder` | Same | No |

## Workflow map (Cursor → Claude)

| Cursor | Claude Code |
|--------|-------------|
| `hooks.json` | `settings.json` → `hooks` |
| Project Rules `.mdc` | `~/.claude/rules/` + `CLAUDE.md` @ |
| User Rules bootstrap | Manual / project memory |
| Plan mode + plan-mode-gate | Same skills |
| `move_agent_to_root` | Open project directory |

## Commands

```bash
# Dry-run full sync
bash ~/.cursor/hooks/sync-all-to-claude.sh

# Apply
bash ~/.cursor/hooks/sync-all-to-claude.sh --apply

# Verify
bash ~/.cursor/hooks/verify-hooks.sh
```
