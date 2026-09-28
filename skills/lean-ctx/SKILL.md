---
name: lean-ctx
description: Local context tooling for AI agents. Use it to select, shape, reuse, recover, and inspect context before inference when reading files, running shell commands, searching code, or exploring directories.
---

# lean-ctx — Local Context SDK for AI Agents

## Setup

```bash
which lean-ctx || curl -fsSL https://raw.githubusercontent.com/yvgude/lean-ctx/main/skills/lean-ctx/scripts/install.sh | bash
lean-ctx setup
```

## Tool Visibility Profiles

| Profile | Tools advertised |
|---------|------------------|
| Lean (default, unpinned) | `ctx_read`, `ctx_shell`, `shell`, `ctx_search`, `ctx_glob`, `ctx_tree`, `ctx_session`, `ctx_compose`, `ctx_callgraph`, `ctx_patch`*, `ctx_call`, `ctx_expand` |
| `minimal` | `ctx_read`, `ctx_shell`, `ctx_search`, `ctx_glob`, `ctx_tree`; `ctx_call` is also advertised as the fallback invoker |
| `standard` | Minimal + `ctx_compose`, `ctx_explore`, `ctx_knowledge`, `ctx_session`, `ctx_callgraph`, `ctx_graph`, `ctx_delta`, `ctx_execute`, `ctx_expand`, `ctx_overview`, `ctx_url_read`, `ctx_patch`; `ctx_call` is also advertised as the fallback invoker |
| `power` | Full public tool registry |

\* Lean hides `ctx_patch` for clients with a reliable native editor. Disabled
tools, role policy, and client compatibility can further narrow every profile.

## Shell Hook (use instead of raw exec)

```bash
lean-ctx -c "git status"
lean-ctx -c "cargo test"
lean-ctx -c "npm install"
lean-ctx ls src/
```

## ctx_read Modes

| Mode | When |
|------|------|
| `anchored` | Files you will edit (full text + `N:hh\|` anchors for ctx_patch) |
| `full` | Verbatim cached read |
| `map` | Context-only (deps + exports) |
| `signatures` | API surface only |
| `diff` | After edits (changed lines) |
| `aggressive` | Large files, syntax-stripped; JSON arrays row-deduped (lossless) |
| `entropy` | Shannon filtering |
| `task` | Task-relevant lines |
| `lines:N-M` | Specific range |
| `auto` | System selects optimal |

Re-reads may use the local cache. Set `fresh=true` to bypass it.
Redundant JSON (arrays of like objects) is crushed losslessly into a compact
`_defaults` + per-row form; if a slice was dropped, recover it with
`ctx_expand(id, json_path=… | search=…)`.

## File Editing

Anchored editing keeps an exact, source-addressable view: `ctx_read(mode="anchored")` → `ctx_patch(path, op, line, hash, new_text)`.
Never reproduce old text byte-for-byte; batch via `ops:[…]`; `op=create` writes new files.
Stale anchor → CONFLICT with fresh anchors (retry once). Native Edit/StrReplace stay fine;
`ctx_edit` (str_replace) is the legacy fallback via ctx_call/power profile.

## More Tools (via ctx_call or ctx_load_tools)

Architecture: ctx_symbol, ctx_callgraph, ctx_impact, ctx_architecture, ctx_routes, ctx_smells, ctx_quality
  ↳ "What breaks if I change this file/class/type?" → ctx_impact (file-level blast radius; resolves same-package/namespace type usage with no import for C#, Java, Go and Kotlin). "Who calls this function?" → ctx_callgraph (symbol-level). "How navigable / how much is complexity costing me?" → ctx_quality (navigability score + token quality tax).
Experimental local collaboration (explicit opt-in only): ctx_agent, ctx_share, ctx_task, ctx_handoff, ctx_workflow
Verify: ctx_benchmark, ctx_verify, ctx_proof, ctx_review
Batch: ctx_fill, ctx_execute, ctx_expand, ctx_pack

Full docs: https://leanctx.com/docs
