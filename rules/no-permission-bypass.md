# No permission bypass — a denied tool is a ROUTE, not an obstacle

> Always-on rule. Written 2026-07-19 after a real incident. `Edit` returned
> "File is covered by a Read deny rule"; instead of using the sanctioned editor
> the agent rewrote three project source files with `python3 - <<'EOF'` heredocs
> and `sed -i`. Nothing was blocking it — `ctx_patch` was available and had
> already worked on another file in the same task. It switched to shell writes
> because batching them in one Python script was faster. That is circumventing
> a control the user installed on purpose.

## The one rule

**When a tool is denied, blocked, or gated — STOP and switch to the sanctioned
tool for that job. NEVER reimplement the denied tool's job in Bash.**

A deny is the user's routing decision. Reaching the same end state through a
different mechanism defeats the control completely, and is worse than failing,
because it looks like success.

**Convenience is never a reason.** The failure mode is not "I was blocked and had
no choice" — it is "the sanctioned tool needed N calls and the shell needed one."
Take the N calls.

## `Edit` does not work on this machine. Ever. Anywhere.

`~/.claude/settings.json` sets `permissions.deny = ["Read", "Grep", "Glob"]`.
`Edit` requires a prior native `Read` of its target, so **`Edit` is unusable on
every file, including files in the current project.**

`File is covered by a Read deny rule and cannot be edited` is the expected,
designed message — not a malfunction, not a path problem, not something to
retry or work around.

**→ The editor on this machine is `ctx_patch`. Reach for it FIRST; do not
discover it by failing `Edit` first.**

`ctx_patch` needs no native `Read` — that is the entire point of it:

- `ctx_patch(op="replace_all", path, find, replace)` — unique literal, one call.
- `ctx_read(path, mode="anchored")` → `ctx_patch(op="replace_lines"|"set_line", …)`
  with the returned `line:hash` anchors, when the text is not unique.
- `ctx_patch(op="create", …)` or the `Write` tool for new files.

Multiple edits are still multiple `ctx_patch` calls. Batching them into one
`python3`/`sed` invocation is the banned shortcut, not an optimization.

## Banned bypasses (hard — no exceptions, no "just this once")

| Bypass | Why it's banned |
|---|---|
| `sed -i` / `perl -i -pe` | in-place edit, invisible to every write gate |
| `python3 -c "...write_text()/open(...,'w')..."` | interpreter-mediated write |
| `python3 - <<'EOF'` / `node -e` / `ruby -e` | heredoc into an interpreter's **stdin** — no `>` redirect, so redirect-matching gates miss it |
| `cat <<EOF > file` / `tee file` / `echo … > file` | redirect write |
| `awk … > file && mv` | write-then-swap |
| `grep -r` / `find` / `ls -R` **to discover code** | reimplements a denied Grep/Glob |

Bash remains correct for what it is actually for: builds, tests, linters, `git`,
package managers, and read-only inspection of command output.

## Sanctioned matrix

| Job | Inside the project root | Outside it (`~/.claude`, `~/.config`) |
|---|---|---|
| Read source | `jcodemunch` `get_symbol_source` / `get_file_outline` / `get_file_content` | same, with `repo:"<display_name>"` from `list_repos` (NOT an abs path) |
| Read non-code | `ctx_read` | `jcodemunch get_file_content`, else ask |
| Search | `ctx_search`, `jcodemunch search_text` | `jcodemunch search_text` |
| **Edit a file** | **`ctx_patch`** | `Write` (whole-file) — `ctx_patch` is path-jailed |
| New file | `Write` / `ctx_patch(op="create")` | `Write` |
| Run things | `ctx_shell` / `Bash` | same |

### PathJail (a separate, much rarer issue — do not confuse the two)

lean-ctx confines `ctx_read`/`ctx_patch` to the current project root
("path escapes project root"). This affects `~/.claude` and other out-of-tree
config **only**. It has nothing to do with editing project files, and it is
still not a cue to shell out — use `Write`, or ask.

Note: `lean-ctx config set root.allow_paths …` currently reports success without
persisting to `~/.config/lean-ctx/config.toml`. Do not trust it silently; verify
the file, and if it did not persist, report that rather than hand-editing the
user's security config to force it.

## When there is genuinely no sanctioned path

**Stop and say so.** Name the blocker, offer the options, let the user choose.
Being blocked and reporting it is a correct, complete outcome. Improvising
around it is not.

## Enforcement

`hooks/bash-write-gate.py` (PreToolUse on `Bash`) detects these patterns.

**History — this rule described enforcement that did not exist (2026-07-18 → 2026-07-19).**
The hook originally carried only three redirect-based regexes (`cat <<EOF > path`,
`tee path`, `echo > path`). An interpreter heredoc pipes to **stdin** and has no `>`
at all; `sed -i` has no redirect either. So every interpreter write and every
in-place edit returned `{}` — allowed. `cat > path <<EOF` also passed, because the
regex hardcoded the opposite argument order from its own docstring. This file
nonetheless claimed the hook "now also matches ... and **denies** them", which was
never true of the code. Two more layers were silently inert alongside it: the hook's
`HARD_BLOCK` flag defaults **off** (so even a match only advised), and it acted only
above a 5-importer blast-radius threshold on a fixed source-extension list.
Net effect: the gate fired ~1700×/day and denied nothing.

**Actual behavior since 2026-07-19** — Layer 1 of the hook hard-denies, before any
other check, on every extension, ignoring both the blast-radius threshold and
`HARD_BLOCK`:

| Pattern | Verdict |
|---|---|
| `python3\|node\|ruby\|perl - <<EOF` (stdin heredoc) with a write in the body | deny |
| `python3 -c` / `node -e` with a write in the body | deny |
| `sed -i`, `perl -i`, `ruby -i`, `--in-place` | deny |
| `cat <<EOF > path` **and** `cat > path <<EOF` | deny |
| `tee path`, `echo\|printf > path` | deny |

Deliberately still allowed, so builds and tests keep working: read-only interpreter
invocations (no write indicator in the body), `sed` without `-i`, and any write whose
targets are all under `/tmp`, a scratchpad, `/dev/*`, `*.log`, `node_modules`, or
`dist`/`build`. Patterns are anchored to a **command position**, so a banned pattern
quoted inside a legitimate command (e.g. `git commit -m "switch from sed -i to
ctx_patch"`) is not denied. Escape hatch for debugging the gate itself:
`BASH_WRITE_GATE_ALLOW_SHELL_WRITES=1`.

`hooks/opus-guard.py` (PreToolUse on `Agent`) appends the read-then-write protocol to
every subagent prompt via `updatedInput`. Subagents start in a fresh context and
inherit none of these rules — as of 2026-07-19, 0 of 58 agent definitions mentioned
`ctx_patch`, so they discovered the write path by trial and error and fell back to
shell writes. Injecting at the one call site every Agent invocation passes through
avoids 58 copies that would drift.

> **Prerequisite — do not re-add `Read` to `permissions.deny`.** `Edit` requires a
> prior native `Read`, and `Write` requires one to overwrite an existing file. Denying
> `Read` therefore kills *both* native write paths everywhere, and `ctx_patch` is
> path-jailed to the project root — leaving no sanctioned editor at all outside it.
> That vacuum is what pushed agents to shell writes in the first place. Discovery
> discipline is already enforced by the `jcm-gate-read` dispatch link, which gates
> `Read`/`Grep`/`Glob` until a jcodemunch call happens in the conversation and then
> fails open. The blanket deny duplicated that steering at the cost of the write path.
>
> Note: `permissions.deny` is held in memory per session. A second concurrent
> `claude` process will re-serialize its own stale copy over yours — if a deny rule
> keeps reappearing after `/permissions` deletes it, check `ps aux | grep claude`
> for another session and quit it.

See also [[lean-ctx]], [[codebase-intel-first]].
