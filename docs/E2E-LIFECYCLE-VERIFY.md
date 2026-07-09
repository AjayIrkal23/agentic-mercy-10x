# E2E Lifecycle Verification Checklist

Run after config changes. All critical hook checks: `~/.cursor/hooks/verify-hooks.sh`.

## Automated

- [ ] `verify-hooks.sh` — all PASS
- [ ] `sync-hooks-to-claude.sh` — no drift after sync
- [ ] `sync-rules-to-claude.sh` — rules mirrored to `~/.claude/rules`
- [ ] `python3 -m py_compile ~/.cursor/hooks/fullstack-skills-reminder.py ~/.cursor/hooks/post-write-aggregator.py`
- [ ] `node ~/.cursor/skills/plan-mode-gate/scripts/plan-mode-check.js`
- [ ] `python3 ~/.cursor/hooks/skill_router.py src/components/App.tsx frontend 1` — path-ranked skills + cross_cut

## Manual session flow

1. **Phase 0** — New chat: sessionStart injects plan gate + lifecycle routing path
2. **Phase 1** — Ask to plan a feature: agent reads `workflow-orchestrator` then `plan-mode-gate`
3. **Plan mode** — Read/Grep `.tsx`/`.go` for exploration without jcodemunch deny
4. **First Write** — Edit a `.tsx` file: `_post` injects FE path-ranked skills + manifest pending list
5. **Multi-file FE** — Later writes surface additional FE skills from session manifest (batch of 4)
6. **First Write BE** — Edit a `.go` service: BE skills include `api-contract-standards` on contract files
7. **UI prompt** — "design a dashboard": six-skill stack once (checklist + paths, not triple SKILL.md dump)
8. **Stop** — Re-verify lists all FE/BE slugs for surfaces touched
9. **3+ writes + stop** — Without code-reviewer Task: Gate 4 Santa denies once
10. **Task code-reviewer** — `.santa.json` written; stop passes Gate 4
11. **Auth file write + stop** — Gate 3 denies until `semgrep scan` Shell runs (post-tracker)
12. **Infra-only** — Edit only `~/.cursor/hooks/*`: Santa + doc Gate 2 skipped
13. **Repo without server_docs/** — BE code + stop: Gate 2 does not require missing tree
14. **git commit** without docs in repo with doc trees — `blocking-doc-enforcer` denies

## User Rules (Phase 0)

Paste bootstrap per `~/.cursor/docs/USER-RULES-SETUP.md` — cannot be automated via file edit.

## Claude Code parity

After `bash ~/.cursor/hooks/sync-all-to-claude.sh --apply`:

- [ ] `settings.json` includes `post-write-aggregator`, `santa-method-writer`, `security-semgrep-tracker post-tool-use`
- [ ] `gsd-read-guard.js` still on PreToolUse (preserve)
- [ ] `model` still `claude-opus-4-6`, `permissions.defaultMode` still `bypassPermissions`
- [ ] `mcpServers.jcodemunch` present
- [ ] New Claude session: SessionStart plan gate; Write skill injection; Stop advisories once (`pass_advisories_sent`)
- [ ] Restart Claude Code after sync

See [`CLAUDE-CURSOR-PARITY-AUDIT.md`](CLAUDE-CURSOR-PARITY-AUDIT.md).
