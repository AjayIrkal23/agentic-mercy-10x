# Skills audit — slice `_`..`l` (164 dirs) — 2026-07-18

All 164 have SKILL.md with valid frontmatter (name+description). No alias points at a missing target. All gsd-* references into ~/.claude/get-shit-done/ resolve. gstack host infra (skills/gstack bin+hosts+node_modules, /usr/bin/gstack, ~/.gstack) intact.

| skill | status | missing deps | fix |
|---|---|---|---|
| _gstack-command | OK | gstack CLI /usr/bin/gstack executable; hosts/claude/hooks + bin complete; ~/.gstack present | - |
| agent-development | OK | - | - |
| api-and-interface-design | OK | - | - |
| api-contract-standards | OK | - | - |
| architect-system-design | OK | - | - |
| autoplan | OK | - | - |
| backend-api-standards | OK | - | - |
| backend-code-review | OK | - | - |
| backend-error-handling | OK | - | - |
| backend-performance-standards | OK | - | - |
| backend-standards-always-follow | OK | - | - |
| benchmark | OK | - | - |
| benchmark-models | OK | - | - |
| browse | OK | gstack CLI OK; daemon bin/chrome-cdp executable; playwright chromium cached | - |
| browser-testing-with-devtools | OK | - | - |
| canary | OK | - | - |
| canary-playwright | OK | - | - |
| careful | OK | - | - |
| caveman | OK | - | - |
| ci-cd-and-automation | OK | - | - |
| code-execution-standard | OK | - | - |
| code-review-and-quality | OK | - | - |
| code-simplification | OK | - | - |
| codebase-intel-first | OK | - | - |
| codebase-start-point-guide | OK | - | - |
| codex | BROKEN | codex CLI not on PATH | npm install -g @openai/codex && codex login |
| command-development | OK | - | - |
| connect-chrome | OK | - | - |
| context-engineering | OK | - | - |
| context-restore | OK | - | - |
| context-save | OK | - | - |
| cso | OK | - | - |
| dead-code-and-change-audit | OK | - | - |
| debug-investigation | OK | - | - |
| debugging-and-error-recovery | OK | - | - |
| deprecation-and-migration | OK | - | - |
| design-consultation | OK | - | - |
| design-extract | OK | SKILL.md-only by design; no external deps | - |
| design-html | OK | - | - |
| design-review | OK | - | - |
| design-review-playwright | OK | - | - |
| design-shotgun | OK | - | - |
| devex-review | OK | - | - |
| diagnose | OK | - | - |
| diagram | OK | renders offline via browse daemon bundle; no mmdc needed | - |
| document-generate | OK | - | - |
| document-release | OK | - | - |
| documentation-and-adrs | OK | - | - |
| domain-scaffold-patterns | OK | - | - |
| doubt-driven-development | DEGRADED | fresh-context reviewer CLIs (gemini, codex) missing; documented subagent fallback exists | npm i -g @openai/codex or gemini CLI for true fresh-context review |
| dox-doc-tree | OK | all dox hooks present in ~/.claude/hooks/ | - |
| eval-harness | OK | - | - |
| find-skills | OK | uses npx skills (on-demand); npx present | - |
| fix-lint-format | OK | - | - |
| forensic-change-coupling | OK | - | - |
| forensic-complexity-trends | OK | - | - |
| forensic-debt-quantification | OK | - | - |
| forensic-hotspot-finder | OK | - | - |
| freeze | OK | - | - |
| frontend-api-standards | OK | - | - |
| frontend-code-review | OK | - | - |
| frontend-response-handling | OK | - | - |
| frontend-server-data-patterns | OK | - | - |
| frontend-standards-always-follow | OK | - | - |
| frontend-structure-standards | OK | - | - |
| frontend-ui-engineering | OK | SKILL.md-only by design; no external deps | - |
| git-workflow-and-versioning | OK | - | - |
| golang-patterns | OK | - | - |
| golang-testing | OK | - | - |
| graphify | OK | graphify CLI (~/.local/bin) + graphify MCP both present | - |
| grill-with-docs | OK | - | - |
| gsd-add-tests | OK | - | - |
| gsd-ai-integration-phase | OK | - | - |
| gsd-audit-fix | OK | - | - |
| gsd-audit-milestone | OK | - | - |
| gsd-audit-uat | OK | - | - |
| gsd-autonomous | OK | - | - |
| gsd-capture | OK | - | - |
| gsd-cleanup | OK | - | - |
| gsd-code-review | OK | - | - |
| gsd-complete-milestone | OK | - | - |
| gsd-config | OK | - | - |
| gsd-debug | OK | - | - |
| gsd-discuss-phase | OK | - | - |
| gsd-docs-update | OK | - | - |
| gsd-eval-review | OK | - | - |
| gsd-execute-phase | OK | - | - |
| gsd-explore | OK | - | - |
| gsd-extract-learnings | OK | - | - |
| gsd-fast | OK | - | - |
| gsd-forensics | OK | - | - |
| gsd-graphify | OK | - | - |
| gsd-health | OK | - | - |
| gsd-help | OK | - | - |
| gsd-import | OK | - | - |
| gsd-inbox | OK | - | - |
| gsd-ingest-docs | OK | - | - |
| gsd-manager | OK | - | - |
| gsd-map-codebase | OK | - | - |
| gsd-milestone-summary | OK | - | - |
| gsd-mvp-phase | OK | - | - |
| gsd-new-milestone | OK | - | - |
| gsd-new-project | OK | - | - |
| gsd-ns-context | OK | - | - |
| gsd-ns-ideate | OK | - | - |
| gsd-ns-manage | OK | - | - |
| gsd-ns-project | OK | - | - |
| gsd-ns-review | OK | - | - |
| gsd-ns-workflow | OK | - | - |
| gsd-pause-work | OK | - | - |
| gsd-phase | OK | - | - |
| gsd-plan-phase | OK | - | - |
| gsd-plan-review-convergence | DEGRADED | depends on gsd-review external CLIs (gemini/codex/... all missing) | same installs as gsd-review |
| gsd-pr-branch | OK | - | - |
| gsd-profile-user | OK | - | - |
| gsd-progress | OK | - | - |
| gsd-quick | OK | - | - |
| gsd-resume-work | OK | - | - |
| gsd-review | DEGRADED | external reviewer CLIs all missing: gemini, codex, qwen, opencode, cursor-agent (only `claude` present) | install desired reviewer CLIs (e.g. npm i -g @openai/codex, @google/gemini-cli) |
| gsd-review-backlog | OK | - | - |
| gsd-secure-phase | OK | - | - |
| gsd-settings | OK | - | - |
| gsd-ship | OK | - | - |
| gsd-sketch | OK | - | - |
| gsd-spec-phase | OK | - | - |
| gsd-spike | OK | - | - |
| gsd-stats | OK | - | - |
| gsd-surface | OK | bin/lib/surface.cjs present; ~/.claude/commands/gsd absent but skill re-stages it | - |
| gsd-thread | OK | - | - |
| gsd-ui-phase | OK | - | - |
| gsd-ui-review | OK | - | - |
| gsd-ultraplan-phase | OK | - | - |
| gsd-undo | OK | - | - |
| gsd-update | OK | - | - |
| gsd-validate-phase | OK | - | - |
| gsd-verify-work | OK | - | - |
| gsd-workspace | OK | - | - |
| gsd-workstreams | OK | - | - |
| gstack | OK | - | - |
| gstack-upgrade | OK | - | - |
| guard | OK | - | - |
| health | OK | - | - |
| higgsfield-generate | BROKEN | higgsfield CLI not on PATH (all commands shell to it); claude.ai higgsfield MCP connector present as partial fallback | install higgsfield CLI + higgsfield auth login |
| higgsfield-marketplace-cards | BROKEN | higgsfield CLI not on PATH (skill only routes to CLI) | install higgsfield CLI + auth login |
| higgsfield-product-photoshoot | BROKEN | higgsfield CLI not on PATH (skill only routes to CLI) | install higgsfield CLI + auth login |
| higgsfield-soul-id | BROKEN | higgsfield CLI not on PATH | install higgsfield CLI + auth login |
| higgsfield-websites | BROKEN | higgsfield CLI not on PATH (entire create/clone/deploy loop is `higgsfield website ...`); MCP connector website tools partial fallback | install higgsfield CLI + auth login |
| huashu-design | DEGRADED | node deps not installed (playwright, pptxgenjs, sharp, pdf-lib — package.json present, no node_modules); export/PDF/PPTX/thumbnail scripts need them. All files present; verify.py + all 15 scripts syntax-OK | cd ~/.claude/skills/huashu-design && npm install |
| idea-refine | OK | - | - |
| impeccable | OK | all 38 reference command docs + full scripts tree present; context/load-context/detect.mjs syntax-OK | - |
| improve-codebase-architecture | OK | - | - |
| incremental-implementation | OK | - | - |
| investigate | OK | - | - |
| ios-clean | DEGRADED | xcodebuild/Xcode missing — Linux host | run on macOS |
| ios-design-review | DEGRADED | iOS-on-device pipeline; macOS/Xcode toolchain absent on this Linux host | run on macOS |
| ios-fix | DEGRADED | xcodebuild/Xcode missing — Linux host | run on macOS |
| ios-qa | DEGRADED | xcodebuild/Xcode missing — Linux host; needs real iOS device + gstack ios daemon | run on macOS |
| ios-sync | DEGRADED | xcodebuild/Xcode missing — Linux host | run on macOS |
| iterative-retrieval | OK | - | - |
| jcodemunch-token-saver | OK | - | - |
| land-and-deploy | OK | - | - |
| landing-report | OK | - | - |
| lean-ctx | OK | lean-ctx MCP live (v3.9.12) | - |
| learn | OK | - | - |

## Environment facts
- Present: gstack, graphify, gbrain, jq, gh, semgrep, bun, node/npx/npm, tdd-guard, tmux, docker, ffmpeg, sqlite3, uv, claude; playwright browsers cached (~/.cache/ms-playwright).
- Missing: higgsfield, mmx, firecrawl, codex, tdd-guard-go, tdd-guard-vitest, gemini, qwen, opencode, cursor-agent, mmdc, pandoc, xcodebuild, typst, weasyprint, deno.
- tdd-guard-go / tdd-guard-vitest: no a-l skill hard-requires them (they belong to tdd-auto-init / tdd doctrine, m-z slice).
- mmx / firecrawl: no a-l skill dir requires them (mmx-cli and firecrawl plugin skills are outside this slice).
- MCP servers required by a-l skills (graphify, jcodemunch, jdocmunch, lean-ctx, memory, sequential-thinking, playwright, gbrain, context7) all in configured list.

## Design-stack deep check (owner-named)
- huashu-design: SKILL.md 53KB; scripts/ 15 files incl. verify.py (compiles), export_deck_pptx.mjs, gen_deck_thumbs.mjs, html2pptx.js; references/ 26 docs; assets/ full (sfx library, showcases, bgm, frames). Only gap: npm install not run.
- impeccable: reference/ has every command doc (audit, critique, polish, animate, load-context via init/context); scripts/ full incl. detector engine tree + live-edit suite; node syntax checks pass.
- ui-ux-pro-max (m-z slice, verified per owner request): data/ complete — styles/colors/typography/google-fonts/ux-guidelines/charts CSVs + 16 stack CSVs; scripts core.py/search.py/design_system.py compile.
- taste-skill, design-extract, frontend-ui-engineering: SKILL.md-only, intact, no external deps.
- shadcn (m-z slice, verified per owner request): full tree (agents/assets/evals/rules + cli/mcp/registry docs); uses npx shadcn on demand.
