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
| `build_skills_index.py` | the one skills-index generator (shim `hooks/build-skills-index.py`) |
| `validate_skills.py` | skill validator R1..R12 (installer post-step; fails the install on a broken catalog) |
| `skills_lib.py` | shared front-matter / trigger-token / hashing primitives |
| `migrate_frontmatter.py` | one-shot native-frontmatter migration (2026-09-27), idempotent |
| `model-mode.py` | per-repo subagent model mode: `opus|sonnet|fable|clear|status` |
| `add-db-mcp.py` | add read-only Supabase/MongoDB MCP to a repo's `.mcp.json` from `templates/mcp/` |
| `mcp_inventory.py` | print the live MCP inventory (user + project scope + plugins) |
| `dox_cleanup.py` | one-shot removal of untouched dox stubs under `~` |
| `grep_gates.py` | portability grep-gates (wrapped by `tests/test_portability_gate.py`) |
| `install-graphify.sh` | graphify MCP install helper |
| `github-mcp-launcher.py` | GitHub MCP launcher for Windows (manifest `windows_add`): reads `gh auth token` at launch, runs the server via `cmd /c npx` |

## Gotchas / fragile spots

- `add-db-mcp.py` writes project scope only and never literal secrets (`${VAR}` only).
- `model-mode.py` is per repo; the global `state/*-only-mode` flags affect every project.

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children: none
