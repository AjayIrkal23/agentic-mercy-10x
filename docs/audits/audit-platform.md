# PLATFORM AUDIT — restored ~/.claude (2026-07-18)

Audit-only. Scope: plugins, MCP servers, indexers/watchers, commands, rules, agents, GSD, memory, misc infra.

---

## WORKING

### Plugins (installed_plugins.json v2, 16 entries; marketplaces: claude-plugins-official, superpowers-marketplace, ponytail, karpathy-skills, claude-mermaid — all 5 marketplace clones present)
| Plugin | Version | Install path | State |
|---|---|---|---|
| superpowers@superpowers-marketplace | 6.1.1 | cache/superpowers-marketplace/superpowers/6.1.1 | OK (15 entries) |
| ponytail | 4.8.4 | cache/ponytail/ponytail/4.8.4 | OK |
| andrej-karpathy-skills | 1.0.0 | cache/karpathy-skills/... | OK |
| claude-mermaid | 1.2.0 | OK | OK |
| claude-session-driver | 4.0.0 | OK | OK |
| clickhouse | 1.0.0 | OK | OK |
| double-shot-latte | 1.2.0 | OK (plugin cache) | OK |
| elements-of-style | 1.0.0 | OK | OK |
| firecrawl | 1.0.9 | OK | OK |
| frontend-design | unknown | OK (3 entries) | OK |
| gopls-lsp / typescript-lsp | 1.0.0 | OK | OK |
| superpowers-lab | 0.5.0 | OK | OK (yes, superpowers-lab exists and is installed) |

- Everything CLAUDE.md/rules expect is present: superpowers, ponytail, karpathy-skills, claude-mermaid, clickhouse, firecrawl, superpowers-lab.
- **gstack is NOT a plugin** — it is a skills-dir install: ~/.claude/skills/ contains `_gstack-command`, `gstack`, `gstack-upgrade`, `open-gstack-browser` among 227 skill dirs, plus state at `~/.gstack/` (config.yaml, gbrain-detection.json, projects). Consistent with CLAUDE.md's "/browse from gstack" list.
- No plugin referenced anywhere in CLAUDE.md / rules/* / hooks/* is missing from the install list.

### MCP servers — 12/12 configured, all type=stdio, all binaries resolvable
Config lives in **~/.claude.json (root level)** — correct location. A second copy exists at ~/.claude/.claude.json (11 servers, no gbrain, PATH-relative commands) — appears to be a restored/stale duplicate that Claude Code does NOT read; harmless but confusing.

| Server | Command | Binary |
|---|---|---|
| browser-tools-mcp | npx @agentdeskai/browser-tools-mcp@latest | npx on PATH ✓ |
| context7 | npx @upstash/context7-mcp | ✓ |
| fetch | /home/mercy/.local/bin/uvx mcp-server-fetch | EXISTS ✓ |
| gbrain | /home/mercy/.bun/bin/gbrain serve | EXISTS ✓ (also ~/.local/bin/gbrain 0.42.62.0) |
| graphify | python3 ~/.claude/hooks/graphify_launcher.py | launcher EXISTS ✓ |
| jcodemunch | /home/mercy/.local/bin/jcodemunch-mcp | EXISTS ✓ |
| jdocmunch | /home/mercy/.local/bin/jdocmunch-mcp | EXISTS ✓ |
| lean-ctx | /home/mercy/.local/bin/lean-ctx | EXISTS ✓ (3.9.12, live this session) |
| markdownify | npx mcp-markdownify-server | ✓ |
| memory | npx @modelcontextprotocol/server-memory | ✓ (but see BROKEN: storage) |
| playwright | npx @playwright/mcp@latest | ✓ |
| sequential-thinking | npx @modelcontextprotocol/server-sequential-thinking | ✓ |

No server has a missing backing binary. All stdio; none remote.

### Indexer plumbing (hooks)
- All indexer hooks exist: index-lifecycle.py, jcodemunch-index-guard.py, graphify-index-guard.py, graphify_launcher.py, jdocmunch-enforce.py, jcodemunch-enforce.py, graphify-enforce.py.
- dispatch.config.json wires them: session-start-aggregator (carries index-lifecycle session-start), post-write-aggregator (carries index-lifecycle post-write), Stop `index-flush`, SessionEnd `index-session-end`, jdoc-doc-steer PreToolUse. Telemetry live (telemetry/hook-fires-20260718.jsonl).
- graphify venv healthy: ~/.local/share/claude-graphify-venv/bin/python → Python 3.14.4. CLI ~/.local/bin/graphify runs (0.9.18).
- tdd-guard binary OK: ~/.nvm/versions/node/v24.18.0/bin/tdd-guard; launcher + gate + init-guard wired in dispatch (SessionStart advisory + PreToolUse gate on Write|Edit|MultiEdit|TodoWrite).
- gbrain: ~/.gbrain/config.json exists (0600), engine pglite, db ~/.gbrain/brain.pglite, embeddings ollama:nomic-embed-text — ollama installed at /usr/local/bin/ollama and nomic-embed-text model pulled (12h ago). CLI runs (`gbrain 0.42.62.0`).

### Commands (24 files in ~/.claude/commands/)
invoke.md + 21 invoke-* delegators + santa-review.md. Every agent they dispatch exists; no missing hook/config reference found inside any command file. `hooks/model-policy.json` present; **invoke_categories.IMPLEMENT = "opus"** confirmed. gen-invoke-commands.py present. opus-guard.py + workflow-model-guard.py present and wired as dispatch mutators (Agent / Workflow matchers).

### Rules / imports
All 12 @imports in ~/.claude/CLAUDE.md resolve. Also present: mandatory-skill-protocol.mdc, token-optimization-stack.mdc, ui-ux-playbook.mdc, user-mcp-inventory.mdc, docs/PRESERVE-AND-STRENGTHEN.md, agents/README.md, rules/invoke-impl-opus.md, agent-lifecycle-routing.md, plan-exec-unified-stack.md. hooks/skills-provenance.json EXISTS. memory-load-on-start.py and session-memory-writer.py EXIST and are wired in dispatch (SessionStart advisory _reg 5; Stop exec _reg 54). All hooks named in rules that were probed exist (dox trio, tdd-guard-init-guard, prompt_router/router.py, aggregators, hard-completion-gate, fullstack-skills-reminder, skill_router).

### Agents (55 .md + README.md in ~/.claude/agents/)
All 12 invoke specialists present: audit-specialist, spec-architect, planning-director, implementation-engineer, deadcode-reaper, debug-detective, docs-sync-agent, qa-verifier, refactor-specialist, santa-reviewer, security-sentinel, test-author. Plus frontend-uiux-designer, memory-codex, 33 gsd-*, 4 figma-*, 3 vercel-*. Frontmatter scan: 0 issues (names match filenames, models valid).

### GSD (get-shit-done)
~/.claude/get-shit-done/ complete: VERSION=1.42.3, manifest gsd-file-manifest.json (v1.42.3, full mode, 398 files) — **full existence scan: 0 missing; 20-file random checksum spot-check: 0 mismatches**. gsd-install-state.json: 2 migrations applied (latest 2026-07-17). Node for its .cjs hooks available via ~/.nvm (v24.18.0). No update pending indicator locally (installed same version as manifest).

### State flags (~/.claude/state/)
caveman-active + ponytail-active present (both modes indeed active this session). No sonnet-only/opus-only/fable-only flag → smart routing, as intended. Router manifests per session accumulating normally.

### Other infra
- ~/.claude/scripts/ present (apply_merge, attic, build_provenance, build_skills_index, grep_gates, install-graphify.sh, **flip-dispatch.py, flip-router.py** — note: flip scripts live in scripts/, not hooks/; rules reference them by bare name so no breakage).
- ~/.claude/installer/ present (bootstrap.py, doctor.py, manifest.json, ...).
- ~/.claude/telemetry/ live.

---

## BROKEN

1. **Memory MCP has no persistent storage path.** `memory` server config has `env: {}` — @modelcontextprotocol/server-memory then writes memory.json inside its npx cache package dir, which is wiped/re-created on version bumps and was NOT restored from backup (no memory.json found anywhere under ~/.npm/_npx, ~/.claude, ~). **All pre-crash Memory-MCP knowledge (pattern::/decision::/session:: entities) is gone**, and new writes will be ephemeral.
   FIX: in ~/.claude.json → mcpServers.memory add `"env": {"MEMORY_FILE_PATH": "/home/mercy/.claude/memory/memory.jsonl"}` (create dir), restart session. Restore old file from git-backup if it was ever committed (search backup repo for memory.json).

2. **graphify skill/package version drift**: CLI is 0.9.18 but installed skill is 0.7.16 — graphify itself warns. FIX: `graphify install`.

3. **gbrain CLI ↔ pglite lock contention**: `gbrain sources list` times out ("Timed out waiting for PGLite lock") while the MCP `gbrain serve` holds the DB. Server itself is alive; sources (gstack-code-*, gstack-brain-*) unverifiable from CLI while a session runs. FIX: verify via MCP tools (mcp__gbrain__sources_list) or run CLI when no session is open; if sources really absent, re-run `/sync-gbrain --full`.

## MISSING

4. **jcodemunch index for /home/mercy/Desktop** — ~/.code-index contains only config.jsonc + last_seen_version; zero project indexes (all pre-crash indexes lost). Also note config.jsonc defaults to trusted-folders whitelist mode with an empty (commented) list. FIX: `mcp__jcodemunch__index_folder({"path": "/home/mercy/Desktop", "incremental": true})` (and each active repo); add roots to `trusted_folders` in ~/.code-index/config.jsonc if indexing is refused.

5. **jdocmunch doc index** — ~/.doc-index has only `_hooks` (debounce/lock), no indexes. FIX: `mcp__jdocmunch__index_local` on doc-bearing repos, or let the SessionStart guard rebuild on first real repo session.

6. **/home/mercy/Desktop/graphify-out/** — Desktop CLAUDE.md mandates `graphify query` when graphify-out/graph.json exists; it doesn't exist at all. FIX: `graphify update /home/mercy/Desktop` (AST-only) — or accept absent since Desktop is not a git repo and the graph guard only serves git repos.

7. **tdd-guard reporters (all 3)** — confirmed missing: tdd-guard-go, tdd-guard-vitest, tdd-guard-pytest not on PATH (checked PATH, ~/go/bin, ~/.bun/bin, nvm bin). tdd-guard core binary is fine. Install commands per skills/tdd-auto-init/SKILL.md:
   - Go: `go install github.com/nizos/tdd-guard/reporters/go/cmd/tdd-guard-go@latest`
   - Vitest: `npm i -D tdd-guard-vitest` (per project; `-jest` variant for Jest)
   - pytest: `pip install tdd-guard-pytest`
   Without reporters, tdd-guard has no red/green test.json state in any project (GO_UDP's `make tdd` pipeline is dead until tdd-guard-go is installed).

## ORPHANED / SUSPECT

8. **Duplicate superpowers plugin** — installed from BOTH superpowers-marketplace (6.1.1) and claude-plugins-official (6.1.1). Same version today, but two update channels will eventually skew and both register skills. FIX: `claude plugin uninstall superpowers@claude-plugins-official` (keep the obra marketplace one that autoUpdates).

9. **Empty plugin caches: context7@claude-plugins-official and playwright@claude-plugins-official** — version "unknown", install dirs contain 0 files. Both duplicate standalone MCP servers already configured in ~/.claude.json. FIX: reinstall (`claude plugin install context7@claude-plugins-official` / playwright) or uninstall the plugin entries and rely on the standalone servers (recommended — avoids duplicate playwright toolsets: mcp__playwright__* vs mcp__plugin_playwright_playwright__*).

10. **~/.claude/.claude.json** — stale near-duplicate of root ~/.claude.json (11 servers, PATH-relative, no gbrain). Not read by Claude Code. FIX: delete or archive to avoid future confusion.

11. **~/.claude/double-shot-latte/ is an empty directory**, yet the dox root index in CLAUDE.md links `double-shot-latte/CLAUDE.md`. Plugin content actually lives in plugins/cache. FIX: remove the empty dir + let dox re-sync the index (or leave; harmless).

12. **~/.code-index/config.jsonc whitelist mode** — with all defaults commented, `trusted_folders_whitelist_mode` default true + empty trusted list may refuse indexing new roots after restore. FIX: uncomment/set `"trusted_folders": ["/home/mercy/Desktop", ...your repos]` (verify actual behavior on first index_folder call).

---

## Verification notes
- Commands scanned for subagent references and hooks/ paths: no dangling refs.
- settings.json registers only the 8 dispatch.py event chains + prompt_router/router.py; all rule-named hooks resolve through dispatch.config.json links — matches the "100x overhaul" description in the rules.
- gbrain config field "mode: local-stdio" per Desktop CLAUDE.md is realized as engine=pglite + `gbrain serve` stdio MCP; config file mode 0600 ✓.
