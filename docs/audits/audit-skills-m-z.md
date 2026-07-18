# Skills audit — slice m–z (63 dirs) — 2026-07-18

All 63 dirs have SKILL.md with valid frontmatter (name + description). Playwright browsers installed (`~/.cache/ms-playwright`: chromium-1208/1228 + headless shells). All 12 MCP servers present in `~/.claude.json` (browser-tools-mcp, context7, fetch, gbrain, graphify, jcodemunch, jdocmunch, lean-ctx, markdownify, memory, playwright, sequential-thinking). gstack host repo intact at `~/.claude/skills/gstack/` (v1.60.1.0): full `bin/` (75 binaries), `hosts/claude/hooks/` question-log-hook + question-preference-hook (compiled, registered in settings.json), browse daemon `browse/dist/browse`, make-pdf `dist/pdf` (97 MB compiled), extension/, docs/askuserquestion-*.md, scripts/jargon-list.json, `~/.gstack/` state present. bun, node, npx, gh, jq, gbrain, semgrep, gstack CLI, tdd-guard all on PATH. Missing CLIs confirmed: mmx, higgsfield, firecrawl, codex, tdd-guard-go, tdd-guard-vitest, pandoc, marp, system chrome/chromium.

Legend: gstack-family refs like `docs/askuserquestion-*.md`, `scripts/jargon-list.json`, `qa/references/...` resolve inside the gstack host repo — verified present.

| skill | status | missing deps | exact fix |
|---|---|---|---|
| make-pdf | OK | — (host dist/pdf binary + fonts note only) | optional: `apt install fonts-liberation` |
| mcp-usage-standards | DEGRADED | stale link `~/.claude/rules/user-mcp-inventory.md` (file is `.mdc`); all 12 MCPs configured | edit SKILL.md link to `user-mcp-inventory.mdc` |
| mmx-cli | BROKEN | `mmx` CLI not installed | install MiniMax mmx CLI (`npm i -g @minimax/mmx` or per vendor docs) + API key |
| office-hours | OK | — (codex CLI optional mode unavailable) | optional: install codex CLI |
| open-gstack-browser | OK | — (extension/ + bin/chrome-cdp + playwright chromium present) | — |
| owasp-security | OK | — | — |
| pair-agent | OK | — (gstack infra verified) | — |
| performance-optimization | OK | — | — |
| plan-ceo-review | OK | — (codex optional) | — |
| plan-design-review | OK | — (codex optional) | — |
| plan-devex-review | OK | — (codex optional) | — |
| plan-eng-review | OK | — (codex optional) | — |
| plan-exec-stack-guide | OK | — (alias; workflow-orchestrator/references/stack-ordering.md exists) | — |
| plan-mode-gate | OK | — (scripts/*.js present, node present; hooks/session-plan-gate-hint.py exists in ~/.claude/hooks) | — |
| plan-tune | OK | — (gstack docs/designs/PLAN_TUNING_V0/V1.md exist) | — |
| planning-and-task-breakdown | DEGRADED | `~/.claude/rules/plan-root-save.md` missing (rule renamed/lost in restore) | recreate the rule file or point link at plan-exec-unified-stack.md |
| postgres-patterns | OK | — | — |
| project-reference-linkage | OK | — | — |
| project-structure-map | OK | — (alias; codebase-intel-first/references/structure-map.md exists) | — |
| prototype | OK | — (LOGIC.md, UI.md present) | — |
| qa | OK | — (gstack/qa/references + templates exist; browse daemon present) | — |
| qa-only | OK | — (same host files) | — |
| qa-playwright | OK | — (playwright MCP configured, chromium binaries installed) | — |
| react-hooks-patterns | OK | — | — |
| retro | OK | — (codex optional) | — |
| review | OK | — (gstack/review/checklist.md, greptile-triage.md, design-checklist.md, agents/openai.yaml exist; codex optional) | — |
| santa-review | OK | — (agents/santa-reviewer.md, hooks/hard-completion-gate.py, hooks/santa-method-writer.py all exist) | — |
| scaffold-standards | OK | — (core/*.py refs are illustrative example paths) | — |
| scrape | OK | — (browse daemon present) | — |
| security-and-hardening | OK | — (alias; owasp-security/references/hardening.md exists) | — |
| service-layer-standards | OK | — | — |
| setup-browser-cookies | DEGRADED | no real Chrome/Chromium user browser installed to import cookies FROM (playwright chromium has no user profile) | install Chrome/Chromium, or use CDP mode via connect-chrome |
| setup-deploy | OK | — | — |
| setup-gbrain | OK | — (gbrain CLI at ~/.local/bin/gbrain; host memory.md exists; ~/.gstack configured) | — |
| shadcn | OK | — (uses `npx shadcn@latest`, npx present; no MCP required; all rules/assets/evals files exist) | — |
| ship | OK | — (gstack/review/TODOS-format.md exists; gh present) | — |
| shipping-and-launch | OK | — | — |
| skill-linkage-story | OK | — (~/.claude/rules/agent-lifecycle-routing.md exists) | — |
| skillify | OK | — (fixture path in body is an example artifact) | — |
| source-driven-development | OK | — | — |
| spec | OK | — (missing-ref hits are illustrative example paths) | — |
| spec-driven-development | OK | — | — |
| strategic-compact | OK | — (alias; context-engineering/references/compaction.md exists) | — |
| sync-gbrain | OK | — (gbrain CLI + gstack-gbrain-sync bin + ~/.gstack state present) | — |
| tailwind-design-system | OK | — | — |
| taste-skill | OK | — (guidance-only; shadcn via npx per-project) | — |
| tdd | DEGRADED | alias files fine; loop depends on `tdd-guard-go` reporter — NOT installed (tdd-guard binary IS installed) | `go install github.com/nizos/tdd-guard/reporters/go/cmd/tdd-guard-go@latest` |
| tdd-auto-init | DEGRADED | `tdd-guard-go` + `tdd-guard-vitest` reporters missing (tdd-guard core present at ~/.nvm/.../bin/tdd-guard) | install tdd-guard-go (go install, above) + `npm i -g tdd-guard-vitest` |
| tech-debt-audit | OK | — (self-ref resolves; references/deepening.md exists) | — |
| test-driven-development | OK | — (references/loop.md, testing-patterns.md exist) | — |
| to-issues | OK | — | — |
| to-prd | OK | — | — |
| tool-and-doc-selection | OK | — | — |
| triage | OK | — (AGENT-BRIEF.md, OUT-OF-SCOPE.md present) | — |
| ui-ux-pro-max | OK | — datasets verified: styles.csv 84 rows (50+ ✓), colors.csv 160 palettes (~161 ✓), typography.csv 73 pairings (57+ ✓), products.csv 161, ux-guidelines 98, charts 25, stacks/ 16 CSVs (10+ ✓); scripts core.py/design_system.py/search.py present | — |
| unfreeze | OK | — | — |
| update-docs | OK | — (references/examples/ + upstream-nextjs/ dirs non-empty; missing-ref hits are example paths) | — |
| using-agent-skills | DEGRADED | stale links: `~/.claude/rules/plan-exec-superpowers-stack.md` and `agent-ecosystem-skills.md` don't exist (renamed to plan-exec-unified-stack.md) | update the two links in SKILL.md |
| verification-loop | OK | — (uses per-project npx tsc etc.) | — |
| vite-react-best-practices | OK | — (all 11 rules/*.md exist) | — |
| webapp-testing | OK | — (scripts/with_server.py exists; playwright MCP + chromium installed) | — |
| workflow-orchestrator | DEGRADED | `~/.claude/rules/plan-root-save.md` missing | recreate rule file or drop the link (convention is restated inline) |
| zoom-out | OK | — (alias; codebase-intel-first/references/zoom-out.md exists) | — |

## gstack host infra (item 6)
- Location: `~/.claude/skills/gstack/` — full repo, VERSION 1.60.1.0, node_modules present, bun on PATH.
- `bin/`: 75 executables incl. gstack-config, gstack-question-log, gstack-question-preference, gstack-update-check, chrome-cdp — present.
- `hosts/claude/hooks/`: question-log-hook, question-preference-hook, auq-error-fallback-hook (compiled + .ts) — the two named hooks ARE registered in settings.json.
- Browse daemon: `browse/dist/browse`, `dist/find-browse`, server-node.mjs — present (not executed; lean-ctx allowlist blocks direct run).
- make-pdf engine: `make-pdf/dist/pdf` 97 MB compiled binary — present.
- `~/.gstack/`: config.yaml, gbrain-detection.json, projects/ — present.
- Shared docs referenced by every gstack skill (docs/askuserquestion-cjk.md, askuserquestion-split.md, gbrain-write-surfaces.md, scripts/jargon-list.json) — all present.

## Known-missing CLIs attributed
- mmx → mmx-cli (BROKEN)
- tdd-guard-go / tdd-guard-vitest → tdd, tdd-auto-init (DEGRADED)
- codex → optional cross-AI mode in review / retro / plan-*-review / office-hours (kept OK; core flows don't need it — the dedicated `codex` skill is in the a–l slice)
- higgsfield / firecrawl → no skill in the m–z slice depends on them (higgsfield-* and firecrawl skills are a–l slice)
