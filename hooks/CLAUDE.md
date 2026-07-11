<!-- dox:child v1 -->
# `hooks/` — local rules (dox)

> Local doc for this directory only. Read after the root `CLAUDE.md`. Update this
> file whenever you add, remove, or rename files here, or change a local convention.

## What lives here

<One or two lines: the responsibility of this directory. What kind of files belong,
what does NOT belong here.>

## Local conventions

- <e.g. naming pattern, file-size cap, import boundaries specific to this folder>
- <e.g. "every X must register in Y" / "do not import from Z">

## Key files

| File | Role |
|------|------|
| `jdocmunch-index-guard.py` | SessionStart guard: doc index (`~/.doc-index/local/<name>.json`) missing/stale check — docs twin of `jcodemunch-index-guard.py`; wired in `session-start-aggregator.py` |
| `jdocmunch-index-guard.config.json` | Informational roots + settings for the jdocmunch guard |
| `jdocmunch-reindex-hook.py` | PostToolUse wrapper → `jdocmunch-mcp hook-posttooluse` (throttled background doc reindex after Edit/Write); chained in `post-write-aggregator.py` |

## Gotchas / fragile spots

- <non-obvious thing that breaks if you're not careful>

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children: <links to deeper `*/CLAUDE.md`, or "none">
- Related repo docs: <link to the numbered doc / CODEX.md section — link, don't restate>
