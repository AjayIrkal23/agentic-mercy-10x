<!-- dox:root v1 -->
# <Project Name> — Agent Guide (dox root)

> Root of the dox documentation tree. Read this first, then walk down to the
> `CLAUDE.md` in the directory you are about to touch. Update the local `CLAUDE.md`
> after you change files there (Phase 7).

## What this is

<One-paragraph overview: what the project does, who uses it, the runtime surfaces.>

## Stack & entry points

| Surface | Root dir | Boot entry |
|---------|----------|------------|
| <e.g. Web> | `<dir>/` | `<entry file>` |
| <e.g. API> | `<dir>/` | `<entry file>` |

Commands: `<dev>` · `<build>` · `<test>` · `<lint>`

## Non-negotiables (project-wide)

1. <e.g. file-size / tenancy / error-envelope rules — link to the deeper doc that owns each>
2. <…>

## dox index (children)

<!-- dox:index:start -->
<!-- dox auto-syncs this block from the tree on disk; edit directories, not these lines.
     One nested line per directory that has a local CLAUDE.md. -->
- [`<dir>/`](<dir>/CLAUDE.md)
  - [`<dir>/<subdir>/`](<dir>/<subdir>/CLAUDE.md)
<!-- dox:index:end -->

## Related docs (link, don't duplicate)

- Working decisions & known pitfalls → `CODEX.md`
- Repo docs → `<frontend_docs/ | server_docs/ | docs/>`
- Knowledge graph / symbol map → jcodemunch / graphify
