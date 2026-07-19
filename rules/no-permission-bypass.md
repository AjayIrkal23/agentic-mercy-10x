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

## Every tool works. Nothing is denied. That is deliberate.

**`permissions.deny` is `[]`** in `settings.template.json` (the tracked source of
truth that `installer/render.py` renders into `settings.json`). `Read`, `Grep`, and
`Glob` all work, so **`Edit` and `Write` work everywhere**, including outside the
project root.

This changed on 2026-07-19. It is the correction to the incident above, not a
relaxation of it. `Read` had been denied to force jcodemunch-first discovery — but
`Edit` requires a prior `Read`, and `Write` requires one to overwrite an existing
file, so denying `Read` silently killed *both* native write paths on every file.
`ctx_patch` is path-jailed to the project root, so outside it there was **no
sanctioned editor at all**. Agents did not shell out to be clever; they shelled out
because nothing else could write. Removing the deny removes the motive.

Discovery discipline did not depend on that deny anyway: the `jcm-gate-read`
dispatch link gates `Read`/`Grep`/`Glob` until a jcodemunch call happens in the
conversation, then fails open. The hook does the steering; the blanket deny only
added collateral damage.

## Write through the editor, never through the shell

**This is trusted to you, not enforced.** No hook blocks these by default (see
Enforcement) — the ban is real regardless.

| Do not | Why |
|---|---|
| `sed -i` / `perl -i -pe` | in-place edit, no reviewable diff, invisible to every write gate |
| `python3 -c "...open(...,'w')..."` | interpreter-mediated write |
| `python3 - <<'EOF'` / `node -e` / `ruby -e` | heredoc into an interpreter's **stdin** — no `>` at all |
| `cat <<EOF > file` / `tee file` / `echo … > file` | redirect write |
| `awk … > file && mv` | write-then-swap |
| `grep -r` / `find` / `ls -R` **to discover code** | that is jcodemunch/graphify's job |

Use instead: **`Edit`** (existing file, after reading it), **`Write`** (new file, or
whole-file replacement outside the project root), **`ctx_patch`** (inside the project
root; `op="replace_all"` for a unique literal, or `ctx_read(mode="anchored")` →
`op="replace_lines"` when the text is not unique).

**Read before you write.** Never edit a file you have not read — `Edit` enforces this
structurally, and it is the reason the deny was harmful rather than merely strict.

**Convenience is never a reason.** The failure mode is not "I was blocked and had no
choice" — it is "the editor needed N calls and the shell needed one." Take the N
calls. Batching edits into one `python3`/`sed` invocation is the banned shortcut, not
an optimization.

Bash remains correct for what it is actually for: builds, tests, linters, `git`,
package managers, and read-only inspection — `grep`, `sed` *without* `-i`, and
`python3 -c` that only prints.

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

**Nothing blocks shell writes by default. This rule is carried by instruction.**

`hooks/bash-write-gate.py` (PreToolUse on `Bash`) can detect every pattern above —
the detection is implemented and tested — but **Layer 1 is opt-in and OFF**. Arm it
with `BASH_WRITE_GATE_DENY_SHELL_WRITES=1`.

It is off because static string-scanning cannot tell a command being *run* from one
being *quoted*. Within minutes of being armed it denied, in order: a `git commit`
whose message mentioned `` `sed -i` `` in markdown backticks; an `echo` containing
`=>` (parsed as a redirect, with `the` as the target filename); and its own test
harness. Anchoring patterns to command positions fixed the common cases and is
retained, but the class is unfixable without parsing shell rather than scanning it.
A guard that blocks real work teaches you to disable it, which is worse than no
guard.

What carries the rule instead:
- **This file**, always in context.
- **`hooks/opus-guard.py`** appends a read-then-write protocol to every subagent
  prompt via the `updatedInput` it already returned. Subagents start fresh and
  inherit none of these rules — as of 2026-07-19, 0 of 58 agent definitions
  mentioned `ctx_patch`, so they found `Edit` broken and improvised. Injecting at
  the one call site every `Agent` invocation passes through beats 58 copies that
  drift.
- **A working editor.** The strongest enforcement is that `Edit`/`Write`/`ctx_patch`
  all function, so shelling out buys nothing.

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
