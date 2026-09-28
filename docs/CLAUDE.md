# `docs/` — local rules

Repo-level documentation for `~/.claude`: changelog, ADRs, the directory index, skill
precedence, project rule templates, and an archive of superseded docs.

## Conventions

- `CHANGELOG.md`: one dated section per upgrade — what changed and why.
- `adr/NNNN-<slug>.md`: only decisions that are hard to reverse + surprising + a real trade-off.
- `archive/<period>/`: superseded docs kept verbatim for history. Never "fix" them; they
  legitimately name deleted scripts. Exclude `archive/` from stale-name greps.
- `project-templates/`: rule files meant to be copied into other repos.

## Key files

| File | Role |
|------|------|
| `INDEX.md` | index of every local `CLAUDE.md` in `~/.claude` |
| `CHANGELOG.md` | upgrade history |
| `adr/0001-2026-09-28-upgrade-decisions.md` | D1–D18 consolidated |
| `SKILL-HARMONIZATION.md` | which canonical skill wins in overlapping clusters |

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md) · Index: [`INDEX.md`](INDEX.md)
