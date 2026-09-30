# Changelog

## v3.1.1 — 2026-09-30 Ubuntu end-to-end run fixes

Why: a full end-to-end run on Ubuntu (three headless sessions plus replays) found
features that looked wired but did nothing.

- SessionStart was 33k chars. Claude Code saves any hook context over 8,000 chars to a
  file and shows a 2 KB preview, so core skills and the memory directive were lost. The
  aggregator now fits 5,500 chars (pointers first, full bodies only if they fit); every
  dispatch `budgets.chars` is 7,800.
- `paths:`-scoped skills failed `Skill()` with "Unknown skill". The router and the
  suite gate now say Read `SKILL.md` for them; agent bodies get a generated
  `<!-- path-skills -->` Read block, because `skills:` preload skips them too.
- tdd-guard advisories were dropped: Sonnet takes 4-7.3 s and the gate cut off at 7 s.
  The cap is now 15 s (Haiku is faster but let a test-less edit through).
- Hook-run jcodemunch indexing lost its AI summaries: the CLI never got the MCP's
  `OPENAI_API_BASE` and jcodemunch 1.108.319 refuses api.openai.com. index-lifecycle now
  passes `mcpServers.jcodemunch.env`, and the lost ollama-down guard (DEFER plus an
  ACTION NEEDED line) is back.
- A jcodemunch index rooted at `$HOME` captured every repo without its own index. The
  installer's `jcodemunch-config` repair now deletes such indexes; `graphify-out/` is
  ignored.
- The workbench checkout is never indexed or dox-swept, even under a sandbox HOME, and
  doctor mode no longer spawns writers. CI had been red since 2026-07-14: tests are now
  hermetic, and a dox fallback stub without its placeholder is no longer indexed.
- playwright MCP registers with `--browser chromium`, plus a post-step that installs it.
- graphify skill refreshed to 0.9.70 (a shell-injection fix and manifest data-loss
  fixes), keeping the local frontmatter.

## v3.1.0 — 2026-09-30 Sonnet 5.5 routing + Windows parity

Why: Sonnet 5.5 matches Opus 5.5 on agentic execution at half the price, while Opus 5.5
leads on review and judgment (plan `plan-2026-09-29-sonnet55-model-routing.md`). An
end-to-end test of the Windows replica then found gaps that the installer never covered.

### Models
- Roles flipped: Opus judges (santa, uiux, plan, spec, debug, team-lead); Sonnet executes.
  Executors escalate to Opus on a failed previous attempt or large unplanned work
  (`escalation` in `hooks/model-policy.json`). Every opus-guard decision is logged to
  `hooks/.telemetry/<sid>.model-routing.jsonl`.
- Doctrine: omit `model` on `Agent` calls; opus-guard sets it and the `[label]`.
  `/invoke` no longer passes `model=`.
- Effort: executors `high`, `max` banned. The `CLAUDE_CODE_SUBAGENT_EFFORT` env key was
  removed: Claude Code never reads it, so agent `effort:` frontmatter is the only lever.
  `TDD_GUARD_MODEL_VERSION=claude-sonnet-5-5`. New `test_model_policy_consistency.py`
  keeps frontmatter, template env and escalation in line with the policy.
- Doctor `model-routing` checks the new invariant (judges on Opus, no executor pinned).

### Installer and Windows
- `installer/jcodemunch_config.py` + doctor row `jcodemunch-config`: the installer keeps
  `~/.code-index/config.jsonc` at `tool_surface: full`, AI summaries and a trusted home
  (a copied Windows install exposed 6 of 90 jcodemunch tools).
- `check.py` no longer hangs on Windows: version probes close stdin.
- Windows `CLAUDE_DIR` render token names the checkout being rendered, so the doctor
  test passes in a sandboxed HOME.
- `switchModelsOnFlag` is Claude-managed (carried over, never compared); the ollama probe
  also wants `qwen2.5-coder:3b` for jcodemunch summaries.
- Private per-machine doctrine moved to the gitignored `CLAUDE.machines.local.md`,
  imported from `CLAUDE.md` §10 (this repo is public).

## v3.0.0 — 2026-09-28 upgrade

Why: an audit (2026-09-27) found the routing layer largely inert — `dispatch.py` dropped
every `opus-guard` mutation, the prompt router emitted an invalid output shape, tdd-guard
stalled writes with a bad model id, ~45k tokens of always-on context, and an installer
that could `git checkout -- .` over uncommitted work. Decisions D1–D18 are recorded in
[ADR 0001](adr/0001-2026-09-28-upgrade-decisions.md).

### Routing
- Prompt router rewritten: word-boundary matching, stack/cwd-aware surface detection,
  ≤5 skills, availability-aware MCP "call X now" lines, valid `hookSpecificOutput`.
- Native skill `paths:` / `when_to_use:` and path-scoped rules replace hook injection for
  file-bound skills. Alias stub skills deleted; aliases resolve at runtime via
  `hooks/lib/skill_aliases.py`.
- MCP auto-trigger layer: `hooks/mcp-post-hints.py` (PostToolUse), router MCP lines,
  SubagentStart MCP block, memory search directive at session start. MCP mandates
  (jcodemunch, graphify, jdocmunch, sequential-thinking, memory, context7, semgrep) are MUST.
- New events wired: SubagentStart, TeammateIdle, PostToolUseFailure, PostCompact,
  ConfigChange (13 events, 43 links).

### Models, agents, teams
- Model routing = env default + agent frontmatter pins + `opus-guard` label aligner; the
  write protocol moved to a SubagentStart hook. Per-project model mode wired.
- Deliberate teams: `name` is optional; `agents/team-lead.md` + `teammate-idle-gate.py`.
- Removed agents: 4 figma, 3 vercel.

### /invoke
- Slash commands became skills: `skills/invoke` + forked single-act skills, run folders
  `.claude/runs/<ts>-<slug>/`, generated by `hooks/gen-invoke-skills.py` (replaces the
  old command generator). Alias and legacy command files deleted.

### Rules and docs
- `rules/` rewritten as native auto-loaded `.md` (all `.mdc` and `@import`s gone);
  root `CLAUDE.md` is ~4 KB.
- dox: git repos only, HOME-guarded, `~/.claude` hard-refused, per-repo opt-in for
  all-dirs; `scripts/dox_cleanup.py` removed stub sprawl. The session-start dox guard was deleted
  (the sweep now runs from `index-lifecycle.py`).
- Cursor-era docs moved to `docs/archive/`.

### Gates and hooks removed
- The dispatch/router flip-back scripts, the 4 disconnected index guards and the
  jdocmunch reindex hook (freshness is `index-lifecycle.py`), memory writers
  (`session-memory-writer`, `session-learning-extractor`, `memory-bootstrap-guard`),
  `model-mode-phrase.py`, `session-plan-gate-hint.py`, lean-ctx shell hooks.
- Stop gate: ≤1 block per turn, honors `stop_hook_active`. tdd-guard: advisory, never in
  `$HOME`.

### Installer and MCP
- One-click flow (`install.sh` / `install.ps1` / `install.py` → bootstrap → visual
  self-heal loop → doctor 0 FAIL). MCP source of truth = `installer/manifest.json` →
  `~/.claude.json`; template carries no `mcpServers` and no `lean-ctx` string.
- MCP: removed fetch, ast-grep, figma, gbrain; added reticle, higgsfield/openart (HTTP).
  Plugins: removed playwright/context7/clickhouse/mermaid/double-shot-latte duplicates;
  added pyright-lsp. New skill `modern-web-guidance`; `scrollcraft` → `scroll-craft`.
- Vendored skills: one `vendored-git` family in `hooks/skills-sources.json`,
  `scripts/vendor_skill.py`, `/invoke-update`.
- Per-project read-only DB MCP: `templates/mcp/db-readonly.mcp.json` +
  `scripts/add-db-mcp.py`. jdocmunch semantic search via ollama.

Rollback: `git checkout <pre-upgrade tag>` in `~/.claude`, then re-run the installer;
full backup at `~/claude-upgrade-backup-20260927.tgz`.
