# jcodemunch-token-saver

> Absorbed into `codebase-intel-first` (P5 consolidation). Method content preserved verbatim below.

---

# jCodeMunch Token Saver — Mandatory Code Retrieval Standard

## Why this exists

`Read`-ing entire source files is the single largest token-waste pattern in this account. The user has installed [jcodemunch-mcp](https://github.com/jgravelle/jcodemunch-mcp), a tree-sitter-backed symbol index that returns **exact functions / classes / methods with byte-precision offsets** instead of full files. Benchmarks: **~95% retrieval-token reduction**, **~45% wire-size reduction**, **80% vs 72% agent success rate** at lower cost.

**Using it is mandatory for code retrieval on this machine.** It is not a preference.

## Decision rule (apply BEFORE every Read / Grep / Glob on source code)

```
Is the target a code symbol (function, class, method, type, interface) ?
├── YES → use jcodemunch (mcp__jcodemunch__*) — DO NOT Read the whole file
└── NO  → Is it markdown / config / lock / env / data ?
         ├── YES → use Read normally
         └── NO  → still try jcodemunch search first; fall back to Read only if it has no answer
```

## Required tool mappings

Replace the LEFT-hand habit with the RIGHT-hand call. If a tool name below is not yet visible in your tool list, the index has not been built for this repo — run `mcp__jcodemunch__index_project` first (or ask the user to).

| If you would normally… | Use instead |
| --- | --- |
| `Read` a whole file to find one function | `mcp__jcodemunch__search_symbols` → `mcp__jcodemunch__get_symbol_source` |
| `Grep` for a function name across the repo | `mcp__jcodemunch__search_symbols` (name + kind filter) |
| `Grep` for a code pattern (e.g. `await fetch(`) | `mcp__jcodemunch__search_ast` |
| Trace "who calls X" / "what does X call" | `mcp__jcodemunch__get_call_hierarchy` |
| Estimate impact of changing X | `mcp__jcodemunch__get_blast_radius` |
| Find unused exports / dead code | `mcp__jcodemunch__find_dead_code` |
| Read a file just to see its structure | `mcp__jcodemunch__list_symbols` (file-level outline) |
| First touch on a new repo | `mcp__jcodemunch__index_project` then `list_symbols` on key files |

(Tool names follow the `mcp__<server>__<tool>` convention used by Claude Code; the server name is whatever `claude mcp add` registered it as — by default `jcodemunch`.)

## Hard rules

1. **Never `Read` a source file over ~200 lines without first attempting `search_symbols` / `get_symbol_source`.** If you do, you are wasting the user's tokens — they explicitly flagged this as mandatory.
2. **Never `Grep` for a symbol name** when `search_symbols` would answer it — `search_symbols` returns kind, path, line, and offsets in one structured response.
3. **Index once per repo.** Before the first jcodemunch call in a new working directory, run `mcp__jcodemunch__index_project` (idempotent, cached at `~/.code-index/`).
4. **Compact wire format on.** Trust the server's `compact_schemas` / MUNCH encoding — don't request raw dumps.
5. **Fallback only with reason.** If you fall back to `Read` / `Grep`, state the reason in one sentence (e.g. "jcodemunch returned no match for symbol — falling back to grep").

## When jCodeMunch is the wrong tool

- Non-code text: README, CHANGELOG, ADRs, prose docs → `Read`.
- Configuration / data: `package.json`, `tsconfig`, `.env`, YAML, lockfiles, SQL fixtures → `Read`.
- File system / git operations: `ls`, `git log`, `git diff` → `Bash`.
- Brand-new file you are about to create → no retrieval needed.
- Binary / image / PDF → existing tools.

## Failure modes & recovery

- **Tool missing from list** → MCP isn't registered for this session. Tell the user: `claude mcp add -s user jcodemunch jcodemunch-mcp` and restart Claude Code.
- **`index not found` error** → run `mcp__jcodemunch__index_project` with the repo root.
- **Symbol not found** → broaden with `search_ast` (regex / pattern) before falling back to `Grep`.
- **Stale index after big edits** → `mcp__jcodemunch__reindex` (or `index_project` again — it's incremental).

## Self-check before answering any code question

Ask yourself: *"Did I read a whole file when a symbol fetch would have answered it?"* If yes, redo the retrieval the right way next time and note it in your response so the pattern doesn't recur.

## References

- Repo: https://github.com/jgravelle/jcodemunch-mcp
- Config: `~/.code-index/config.jsonc` (`jcodemunch-mcp config --init`, `--check`)
- Tool profiles: `core` (16) / `standard` (51) / `full` (62) — default `core` is enough for retrieval; bump to `standard` for analytics queries.
