# lean-ctx — Context Engineering Layer
<!-- lean-ctx-rules-v9 -->

Scope (see `codebase-intel-first.md` for the full precedence): lean-ctx owns
**residual non-code** files (single small configs, .env, lockfiles), shell
output, dir trees, and edit fallback. **Source code** is jcodemunch's job
end-to-end — discovery AND reading
(`search_symbols`/`get_symbol_source`/`get_file_outline`/`get_file_content`).
**Documentation SETS** (md/rst/adoc trees, docs/ folders, READMEs) are
jdocmunch's job end-to-end — discovery AND reading
(`search_sections`/`get_toc`/`get_section`), indexed at `~/.doc-index`.
Don't `ctx_read` a source file jcodemunch already returned, or a doc file
jdocmunch has indexed; that's a redundant second hop. Within its scope:
ALWAYS use lean-ctx tools instead of native equivalents. This is NOT optional.

## Tool Mapping
| MUST USE | NEVER USE | Why |
|----------|-----------|-----|
| `ctx_read(path, mode)` — **non-code files only** | `Read` / `cat` / `head` / `tail` on docs/config/env | Cached, 10 read modes, re-reads ~13 tokens |
| `ctx_search(pattern, path)` — **non-code only** | `Grep` / `rg` on docs/config | Compact, token-efficient results |
| `ctx_shell(command)` | `Shell` / `bash` / terminal | Pattern compression for git/npm/cargo output |
| `ctx_tree(path, depth)` | `ls` / `find` | Compact directory maps |
| `ctx_edit(path, old_string, new_string)` | `Edit` (when Read unavailable) | Search-and-replace without native Read |

For source code, skip this table — use jcodemunch's own read tools
(`get_symbol_source`, `get_file_outline`, `get_file_content`) instead of `ctx_read`.

## ctx_read modes:
- `auto` — auto-select optimal mode (recommended default)
- `full` — cached read (files you edit)
- `map` — deps + exports (context-only files)
- `signatures` — API surface only
- `diff` — changed lines after edits
- `aggressive` — maximum compression (context only)
- `entropy` — highlight high-entropy fragments
- `task` — IB-filtered (task relevant)
- `reference` — quote-friendly minimal excerpts
- `lines:N-M` — specific range

## Mode selection:
1. Editing the file? → `full` first, then `diff` for re-reads
2. Need API surface only? → `map` or `signatures`
3. Large file, context only? → `entropy` or `aggressive`
4. Specific lines? → `lines:N-M`
5. Active task set? → `task`
6. Unsure? → `auto` (system selects optimal mode)

Anti-pattern: NEVER use `full` for files you won't edit — use `map` or `signatures`.

## File editing:
Use native Edit/StrReplace if available. If Edit requires Read and Read is unavailable, use ctx_edit.
Write, Delete, Glob → use normally. NEVER loop on Edit failures — switch to ctx_edit immediately.

## Proactive (use without being asked):
- `ctx_overview(task)` at session start
- `ctx_compress` when context grows large

Fallback only if a lean-ctx tool is unavailable: use native equivalents.
REMINDER: You MUST use lean-ctx tools. NEVER use native Read, Grep, or Shell directly.
<!-- /lean-ctx -->