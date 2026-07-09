# Attic Manifest — 2026-07-09

Everything moved here is recoverable forever. Format:

| file | original path | reason | restore command |
|---|---|---|---|
| rules/lean-ctx.mdc | ~/.claude/rules/lean-ctx.mdc | Stale Cursor-era duplicate contradicting live lean-ctx.md (claimed ctx_* MCP tools don't exist; they do). Not imported by CLAUDE.md. | `mv ~/.claude/attic/2026-07-09/rules/lean-ctx.mdc ~/.claude/rules/` |
| rules/global-operating-rules.mdc | ~/.claude/rules/global-operating-rules.mdc | Inert Cursor-only stub; its own text redirects Claude Code to mandatory-skill-protocol.mdc. Not imported by CLAUDE.md. | `mv ~/.claude/attic/2026-07-09/rules/global-operating-rules.mdc ~/.claude/rules/` |
| hooks/design-quality-gate.py | ~/.claude/hooks/design-quality-gate.py | Dormant — logic merged into ui-ux-stack-orchestrator.py (comment-confirmed at its lines 44/378/430). Not wired in settings.json; no hook invokes it. | `mv ~/.claude/attic/2026-07-09/hooks/design-quality-gate.py ~/.claude/hooks/` |
| hooks/design-quality-gate.config.json | ~/.claude/hooks/design-quality-gate.config.json | Config sidecar of the dormant hook; orchestrator reads constants inline, not this file. | `mv ~/.claude/attic/2026-07-09/hooks/design-quality-gate.config.json ~/.claude/hooks/` |
| skills-pre-update/{impeccable,huashu-design,ui-ux-pro-max,taste-skill} | ~/.claude/skills/<name>/ | Pre-hard-reset snapshots taken by Phase P1 before fetching fresh upstream (user chose hard reset over merge). | `rm -rf ~/.claude/skills/<name> && cp -r ~/.claude/attic/2026-07-09/skills-pre-update/<name> ~/.claude/skills/<name>` |
| dox-stubs/{agents,commands,plugins}/** (364 files) | ~/.claude/agents/, ~/.claude/commands/, ~/.claude/plugins/** | Dox auto-scaffold stubs (CLAUDE.md/AGENTS.md) created inside roster-scanned dirs; Claude Code misparsed them as phantom skills ("AGENTS", "CLAUDE") and phantom agents ("supabase:AGENTS" etc.). dox now skips these paths via `skipPaths` in hooks/dox-tree-guard.config.json. 2 in agents/, 2 in commands/, 360 under plugins/; skills/ had none (its AGENTS.md/CLAUDE.md files are legit upstream content, untouched). | `cd ~/.claude/attic/2026-07-09/dox-stubs && find . -type f -name '*.md' -exec sh -c 'mkdir -p ~/.claude/$(dirname {}) && cp {} ~/.claude/{}' \;` (only if skipPaths is also removed) |
