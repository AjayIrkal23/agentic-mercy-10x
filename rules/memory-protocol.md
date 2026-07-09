# Memory Protocol — When and What to Persist to Memory MCP

> This protocol governs all interactions with the `mcp__memory__*` tool family.
> Hooks `memory-load-on-start.py` and `session-memory-writer.py` implement the
> automated read/write paths. This file defines the rules for manual and agent-driven writes.

---

## WHEN to Write to Memory MCP

Write to Memory MCP when a fact is:
- **Reusable across sessions** — it will still be true in 30+ days
- **Non-obvious** — it overrides a default LLM assumption or framework convention
- **Actionable** — knowing it changes what code you'd write ("use X not Y")
- **Discovered, not stated** — something found by doing, not from a README

Do NOT write to Memory MCP when the fact is:
- Session-scoped state ("currently working on PR #42" → use CODEX.md Session Log instead)
- A PR number, issue number, or ephemeral status
- Derivable from the codebase in < 30 seconds (grep/jcodemunch)
- Already captured in AGENTS.md or CODEX.md with identical wording
- A secret, credential, token, or any value matching a key/password/token pattern

---

## WHAT to Capture — Entity Schema

Use this schema for all `mcp__memory__create_entities` calls:

```json
{
  "name": "<type>::<project>::<slug>",
  "entityType": "project | preference | pattern | decision | fragile_area",
  "observations": ["<observation string 1>", "<observation string 2>"]
}
```

### Entity type guide

| entityType | Use for | Example name |
|---|---|---|
| `project` | Repo-level framework list, stack facts | `repo::site-sync-vista#web::app` |
| `pattern` | "We do X this way" — reusable code patterns | `pattern::site-sync-vista::rtk-query-standard` |
| `decision` | "We chose X over Y" — architectural choice | `decision::site-sync-vista::auth-slice-over-context` |
| `fragile_area` | "This area breaks if..." — gotchas | `fragile::site-sync-vista::bullmq-jobs` |
| `preference` | Developer workflow preferences | `pref::global::prefer-explicit-planning` |
| `session_decision` | Auto-captured by Stop hook (review and promote) | `session::site-sync-vista::YYYY-MM-DD` |

### Observation format

Each observation is a single sentence or short paragraph. Format:
```
[YYYY-MM-DD] <what>. <why>. <what was rejected or what breaks if violated>.
```

Example observations:
```
[2026-05-28] Use RTK Query createApi for all server state. Tag invalidation across features. Raw react-query hooks caused cache fragmentation in LibraryContext.
[2026-05-28] AppError class in server/src/utils/errors.ts is mandatory for route errors. Do not throw raw Error objects — they bypass the centralized error formatter.
[2026-05-28] Mongoose schemas: always { timestamps: true }. Missing timestamps breaks report queries that filter by createdAt/updatedAt.
```

---

## HOW to Write — Manual Agent Protocol

When you (the agent) discover a new pattern or decision during a session:

1. **Check if it's new**: call `mcp__memory__search_nodes("<project-name> <topic>")` first.
   If a matching entity already exists, call `mcp__memory__add_observations` to append.
   If not, call `mcp__memory__create_entities` then `mcp__memory__add_observations`.

2. **Prefer add_observations over create_entities** when the entity might already exist.
   The Stop hook auto-creates `session::*` entities; for project-level knowledge use
   `pattern::*` or `decision::*` entity names.

3. **One call per logical topic** — do not batch unrelated facts into one entity.

4. **Include the date in each observation** — `[YYYY-MM-DD]` prefix.

### Trigger phrases that mean "write to memory"

If the user or you say any of these, it is a signal to call `mcp__memory__add_observations`:
- "remember that..."
- "going forward..."
- "always use... / never use..."
- "we decided..."
- "the pattern is..."
- "[DECISION]:" / "[STYLE]:" / "[PREFER]:"

---

## STALENESS Handling

Memory observations do not have automatic TTL. Handle staleness explicitly:

1. **30-day review signal**: if a `mcp__memory__search_nodes` result has an observation
   older than 30 days AND the observation references a file that no longer exists,
   flag it: "This memory may be stale (references deleted file X). Verify before using."

2. **Contradiction eviction**: if you discover a stored observation is wrong, call
   `mcp__memory__delete_observations` to remove the stale text, then add a corrected observation.

3. **Auto Dream**: the native Claude Code Auto Dream consolidation fires when 24h have elapsed
   AND 5+ sessions completed. It removes contradicted facts and merges duplicates automatically.
   Rely on Auto Dream for bulk cleanup; manual contradiction eviction for critical facts.

4. **Session entity cleanup**: `session::*` entities (auto-captured by Stop hook) accumulate.
   Monthly: call `mcp__memory__search_nodes("session::")` and delete observations older than
   60 days that have not been promoted to a `pattern::` or `decision::` entity.

---

## HOW to Read — Session Start Protocol

The `memory-load-on-start.py` hook handles automatic injection of top-5 entities.
For deeper retrieval during a session:

```
# Find all patterns for a project
mcp__memory__search_nodes("pattern::site-sync-vista")

# Find all decisions
mcp__memory__search_nodes("decision::site-sync-vista")

# Find all fragile areas
mcp__memory__search_nodes("fragile::site-sync-vista")

# Find a specific topic
mcp__memory__search_nodes("site-sync-vista auth")
```

Read the full graph when onboarding to a project or after a long absence:
```
mcp__memory__read_graph  # returns all entities — use sparingly (can be large)
```

---

## What NOT to Store (Anti-patterns)

| Anti-pattern | Why | Alternative |
|---|---|---|
| Task status ("PR #42 is merged") | Ephemeral, becomes noise | Session Log in CODEX.md |
| Codebase structure ("AuthService is in server/src/services/") | Derivable via jcodemunch/graphify | Skip it |
| File contents or code snippets | Too large, goes stale | Add inline comments to code |
| User's personal preferences for THIS session | Not durable | Just follow in this session |
| Secrets, tokens, credentials | Security risk — never store | Never |

---

## CODEX.md vs Memory MCP — When to Use Which

| Scenario | Use |
|---|---|
| Human-readable reference the whole team sees | CODEX.md (tracked in git) |
| Per-developer preferences or workflow quirks | Memory MCP (`pref::` entity) |
| Auto-captured session decisions (review later) | Memory MCP (`session::` entity) → promote to CODEX.md |
| Decisions that must be visible on project clone | CODEX.md |
| Decisions discovered mid-session automatically | Memory MCP first, CODEX.md after human review |
| Known fragile area that affects only you | Memory MCP (`fragile::` entity) |
| Known fragile area that affects all contributors | CODEX.md Known Fragile Areas section |
