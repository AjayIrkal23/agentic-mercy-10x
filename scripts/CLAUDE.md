<!-- dox:child v1 -->
# `scripts/` — local rules (dox)

> Local doc for this directory only. Update it when you add, remove, or rename a script.

## What lives here

Maintenance CLIs run by hand, by the installer's `post_steps`, or by CI. Not hooks —
nothing here is registered in `dispatch.config.json`.

## Local conventions

- Pure stdlib Python ≥ 3.10; `--check` / `--dry-run` modes exit non-zero on drift and
  never write.
- Skill tooling shares primitives through `skills_lib.py`; do not duplicate front-matter
  parsing or R10 hashing.
- Generators that write tracked files pass `newline="\n"` to `write_text` — on Windows the
  default would write CRLF and dirty every generated file on each run.

## Key files

| File | Role |
|------|------|
| `vendor_skill.py` | vendor third-party skills from `hooks/skills-sources.json` (`<name> [--ref]`, `--all`, `--check`); backs `/invoke-update` |
| `build_provenance.py` | R10 provenance registry → `hooks/skills-provenance.json` |
| `build_skills_index.py` | the one skills-index generator (shim `hooks/build-skills-index.py`); skips skills of plugins the template sets to `false` in `enabledPlugins` (NEW-08) |
| `validate_skills.py` | skill validator R1..R13 (installer post-step; fails the install on a broken catalog); R13 only WARNs on inert lowercase `intents` (C-03) |
| `validate_mods.py` | mods contract M1–M6 for `manifest.mods.enabled`, then `claude plugin validate --strict` + `claude plugin test` (`--static`, `--no-tests`; tests only WARN while Claude Code's rollout switch has mods off); installer post-step `validate-mods`, doctor row `mods` |
| `skills_lib.py` | shared front-matter / trigger-token / hashing primitives |
| `model-mode.py` | per-repo subagent model mode: `opus|sonnet|fable|clear|status`; `show` reads the global flags through `lib/model_mode.global_flags` (the files the guards read) |
| `add-db-mcp.py` | add read-only Supabase/MongoDB MCP to a repo's `.mcp.json` from `templates/mcp/` |
| `mcp_inventory.py` | print the live MCP inventory (user + project scope + plugins) |
| `grep_gates.py` | portability grep-gates G1–G7 over hooks, installer, scripts and `mods/`; G5 = no bare `read_text()`; G6 = no `/home/<user>/` or `/Users/<user>/` in any git-tracked `*.md` (the repo is public: write `~`); G7 = `validate_imports.py` over `library/` and `agents/`. Wrapped by `tests/test_portability_gate.py` |
| `validate_imports.py` | import hygiene (grep gate G7): classes U P V W S M (+ E); `--json`; vendored-upstream headers skip the prose-level rules |
| `vendor_library.py` (+ `catalogue.json`) | vendor the ECC library (`--source --sha --out`; `VENDOR.json`; sanitizer; self-validates) |
| `build_library_index.py` | `library/INDEX.json` from `library/ecc` (`--check`, `--ecc`) |
| `secrets_scan.py` | layer 2 of the go-live secrets scan: known values from the env files, never prints a value |
| `replica_sync.py` | Windows replica sync over key-only SSH; PASS/WARN/SKIP rows |
| `golive.py` | the go-live runner: `--plan`, `--yes-automatic`; secrets (gitleaks `dir` + `stdin`, then `secrets_scan.py`) before any git step |
| `build_workflows.py` | renders `workflows/src/*.js.tpl` (`{{model:<role>}}`, `{{model:<role>:up}}`) into `workflows/*.js` + `index.json` + `.rendered.json` for the tier in `state/plan-tier.json` (usage guard applied); `--tier`, `--usage`, `--out`, `--check` (re-renders from the RECORDED tier, exit 1 on drift); never spawns |
| `skill_health.py` | pushed-vs-invoked skill report and the `skillOverrides` map (superset of the deleted weights loop) |
| `measure_context_cost.py` | measured always-on context cost (`docs/TOKEN-BUDGET.md`; `--write`, `--counts`, `--observed`, `--mcp-eager --record N`) |
| `split_machines_file.py` | keep the imported machines file short (budget 650 ch per unit, `--check` limit 5,200 = plan §5 row); journal beside it (gitignored, not imported), exact `--undo` |
| `restore_sessions.py` | gated restore of ledger-matched killed sessions into tmux session `claude`; `--dry-run` writes nothing; exit 0 + one JSON summary |
| `check_ownership.py` | merge-time check: every changed path vs `PACKAGES.json` `owned_paths` (exactly one owner); golive step 01; `--packages` or `CLAUDE_ECC_PACKAGES` |
| `statusline.py` | Claude Code status line (settings `statusLine`, run on every refresh): reads the payload JSON on stdin, prints one line (model+effort │ ctx bar │ $ │ 5h/7d limits │ git │ ⏱ │ ±lines); + `seg_mem` (OOM guard tier), the plan-tier suffix and `↓` (usage guard), the session bridge `state/session-bridge/<sid>.json` and the ledger heartbeat every 10 s. Never raises; one module on purpose (hot path). history: `docs/CHANGELOG.md` v4.3.0 § statusline.py |
| `install-graphify.sh` | graphify MCP install helper |
| `github-mcp-launcher.py` | GitHub MCP launcher for Windows (manifest `windows_add`): reads `gh auth token` at launch, runs the server via `cmd /c npx` at the version pinned in the manifest |

## Gotchas / fragile spots

- `add-db-mcp.py` writes project scope only and never literal secrets (`${VAR}` only).
- `model-mode.py` is per repo; the global `state/*-only-mode` flags affect every project.

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children: none
