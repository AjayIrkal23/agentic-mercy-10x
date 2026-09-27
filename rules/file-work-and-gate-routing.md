# File work & gate routing — how reads/writes really flow (don't misdiagnose)

> Always-on rule. Written 2026-07-21 after a real incident: an agent went straight
> to `Edit` on a source file, hit a bare `Error editing file`, and then invented a
> "Read deny rule / settings drift / another session" story — burning three turns
> chasing `settings.json` and `ps aux` when the cause was simply *no read happened
> first*. This file is the single place that ties the file-work ORDER to the GATE
> reality so that mistake never repeats.

## 1. The one correct order for touching any file

**FIND → READ → EDIT. Never jump straight to Edit/Read on source.**

1. **FIND with jcodemunch** — `search_symbols` / `get_file_outline` /
   `assemble_task_context` / `get_context_bundle`. This is also what *unlocks the
   read gate for the whole session* (see §2).
2. **READ the located file** — lean-ctx `ctx_read` (inside project root) or
   jcodemunch `get_symbol_source` / `get_file_content`. Once you know the exact
   file, `ctx_read` is the easy path.
3. **EDIT** — `Edit` (needs a prior Read of that file), `ctx_patch` (inside project
   root, needs NO prior Read), or `Write` (new file / whole-file replace).

Non-code (md/config/env/lockfiles) skips jcodemunch → `ctx_read` directly. Docs
SETS → jdocmunch. See [[codebase-intel-first]] and [[lean-ctx]] for the full
precedence.

## 2. What the gates actually do (PreToolUse hooks, via `dispatch.py pre-tool-use`)

These run as links in `hooks/dispatch.config.json`. Each emits its OWN reason
string — memorize which is which so a block is never mystifying:

| Hook | Matches | Behavior & its real message |
|---|---|---|
| `jcodemunch-enforce.py` | `Read` `Grep` `Glob` `ctx_read` `ctx_search` `ctx_multi_read` — **NOT Edit/Write** (returns 0 for them) | Denies a **source read** until ≥1 jcodemunch call this conversation, then FAILS OPEN after a small budget. Message: `BLOCKED: use jcodemunch to FIND '<file>' first…`. One jcodemunch call unlocks all reads/edits for the session. |
| `first-write-skill-gate.py` | `Write` `Edit` `MultiEdit` | Blocks the **first** code write until mandatory skills are surfaced. Message: `SKILL GATE: First code write to <file> blocked…`. Fires at most once per conversation; loading the named skills clears it. |
| `dox-write-gate.py` | `Write` `Edit` `MultiEdit` `Bash` | Blocks code writes when the repo has **no root `CLAUDE.md`**. Repos that already have one pass instantly. |
| `tdd-guard-gate.py` | `Write` `Edit` `MultiEdit` `TodoWrite` | **WARN mode** — downgrades blocks to a `⚠️ TDD GUARD` advisory; never actually stops you. |
| `gateguard-write-gate.py` | `Write` `Edit` | Blast-radius awareness; uses `permissionDecision:"ask"` (prompt), not a hard deny. |
| `bash-write-gate.py` | `Bash` | Detects shell writes (`sed -i`, heredocs, `>` redirects). Hard-deny path is OFF by default; the ban is carried by [[no-permission-bypass]]. |

## 3. "Error editing file" / "Read deny" — the anti-misdiagnosis checklist

> **FAST FIX — do this FIRST, it resolves almost every case in one step:** if `Edit`/`Write`
> fails with **"File is covered by a Read deny rule …"** or a bare **"Error editing file"**,
> **`Read` that EXACT file again and then IMMEDIATELY retry the edit — with nothing in between.**
> No other `Read`, `grep`, or tool call may sit between the `Read` and the `Edit`; reading a
> *different* file in between does NOT count — it must be the same file you are about to edit.
> Cause — ROOT CAUSE FOUND 2026-08-05: lean-ctx ≤3.9.12 in shadow mode wrote
> `permissions.deny: ["Read","Grep","Glob"]` into settings.json on EVERY MCP server start
> (~once per session start, 100–200×/day for weeks). Fixed by updating to v3.9.17 and
> setting `shadow_mode = false` (verified: fresh serve init no longer touches deny). If
> deny EVER reappears, check `lean-ctx config | grep shadow` and `lean-ctx --version`
> FIRST — a concurrent Claude session flushing stale in-memory deny on exit is only the
> secondary carrier, not the source. The `settings-permissions-selfheal` hook reconciles
> the file back to
> `deny: []` within a turn, and the re-read-then-retry simply gives it that turn. It is **not**
> a hard permission block and **not** a reason to shell out — `sed -i` / `python` writes stay
> banned (see [[no-permission-bypass]]). Only if a clean read-then-immediate-retry STILL fails,
> walk the diagnostic checklist below.

**`Error editing file` is a NATIVE Claude Code message. NO hook emits it.**
(Grep of `~/.claude/hooks/` returns zero matches; the string lives only in
conversation logs.) The most common native cause: **`Edit` was called on a file
that was never `Read` this session** — `Edit` requires a prior read, and if the
implicit read is also gated by `jcodemunch-enforce` (no jcodemunch call yet), the
edit fails.

`File is covered by a Read deny rule in your permission settings` is likewise the
**native permission system's** wording — it is documented as an *example* in these
rules; do NOT quote it as if a tool returned it unless a tool literally did.

When an edit/read is refused, diagnose in THIS order — stop at the first hit:

1. **Did I make a jcodemunch call yet?** If no → that's it. Call
   `get_file_outline`/`search_symbols` once, then read/edit. (Covers the vast
   majority of cases.)
2. **Did I Read the file before Edit?** If no → Read it (or use `ctx_patch`, which
   needs no prior read), then edit.
3. **Is the reason string a named hook gate?** (`SKILL GATE`, `BLOCKED: use
   jcodemunch`, `⚠️ TDD GUARD`, dox root missing) → follow that hook's instruction.
4. **Only if 1–3 are all clean:** check `settings.json` `permissions.deny` and
   concurrent sessions. This is LAST and almost never the cause —
   `settings.json` normally has `deny: []` and `defaultMode: bypassPermissions`.

**Never** open with "settings drift / another session is running" — that was the
exact wrong move. Verify with evidence (`ps`, the settings file) before ever
claiming it, and only after steps 1–3.

## 4. The whole `.claude` workflow, in one map (details live in the linked rules)

- **Session start** — indexes/graph auto-refresh; memory + dox load. Orient with
  jcodemunch/graphify, not blind `ls -R`. → [[codebase-intel-first]]
- **Reason** — externalize non-trivial thinking via sequential-thinking BEFORE
  deciding/planning. → [[sequential-thinking-doctrine]]
- **Plan** — plan-gate + Phase-0/1 lifecycle. → [[mandatory-skill-protocol]],
  [[plan-exec-unified-stack]]
- **Code** — FIND→READ→EDIT (§1); mandatory FE/BE skills surface on first write;
  writes go through `Edit`/`ctx_patch`/`Write`, **never the shell**. →
  [[no-permission-bypass]], [[lean-ctx]]
- **Subagents** — `[sonnet]` default; `[opus]` only for UI/UX or genuinely heavy
  work; `[fable]` only on explicit request. Model in both `description` and `name`.
  → root `CLAUDE.md` "Agent tool" section, [[invoke-impl-opus]]
- **Post-code** — dead-code audit → lint/security → Santa review → docs. →
  [[agent-lifecycle-routing]], [[tdd-doctrine]]
- **Docs** — every dir carries a `CLAUDE.md`; read root→target before editing,
  update after. → [[dox-doc-tree]]
- **Memory** — persist durable feedback/decisions; a recalled memory is background
  context, verify file/flag names still exist before acting. → [[memory-protocol]]

## 5. Standing lesson

The gate system is deliberate and self-healing (blocks are budgeted and fail
open). When something refuses, the fix is almost always **satisfy the workflow**
(one jcodemunch call, a Read before Edit), not **edit config or kill processes**.
Read fully, diagnose in order, then act.
