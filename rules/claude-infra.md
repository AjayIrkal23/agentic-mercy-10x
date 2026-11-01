---
paths:
  - "**/.claude/hooks/**"
  - "**/.claude/rules/**"
  - "**/.claude/agents/**"
  - "**/.claude/skills/**"
  - "**/.claude/installer/**"
  - "**/.claude/scripts/**"
  - "**/.claude/mods/**"
  - "**/hooks/*.py"
  - "**/dispatch.config.json"
  - "**/settings.template.json"
  - "**/model-policy.json"
---
# ~/.claude infrastructure (loads on hook / rule / agent / skill / installer files)

**Editing order:** FIND (jcodemunch) → READ → EDIT. `Edit` needs a prior `Read` of that
exact file; `ctx_patch` does not. Never shell-write.

**Rendered vs source:** `settings.template.json` → `python3 installer/render.py` →
`settings.json`. Never hand-edit `settings.json` for anything durable; edit the template
and re-render. `hooks/model-policy.json` is the model truth →
`python3 hooks/gen-invoke-skills.py` regenerates the `/invoke` delegators.
`hooks/dispatch.config.json` declares every hook link (types `exec`, `gate`, `advisory`,
`mutator`, `async`); each link is isolated and fail-open. Tests:
`python3 -m pytest hooks/tests -q`; health: `python3 installer/doctor.py`.
OOM guard files: `hooks/memwatch-brake.py`, `hooks/memwatch-ensure.py`,
`hooks/memwatch.config.json`, `hooks/tools/memwatch.py`, `hooks/lib/memwatch_state.py`,
state `state/mem-pressure.json`; runbook `docs/OOM-GUARD.md`.

**Gate reference (what each refusal actually says):**

| Gate | Fires on | Message prefix | Behavior |
|---|---|---|---|
| `dangerous-bash-gate` | Bash / PowerShell | `DANGEROUS COMMAND BLOCKED:` | deny; `rm` targets held in the command's own `R=/tmp/...` variable count as temp |
| `jcodemunch-enforce` (jcm-gate-read, jcm-gate-shell) | Read/Grep/Glob/`ctx_read`, and Bash/PowerShell `grep/rg/cat/sed -n/head/tail/find`, `Get-Content/Select-String/findstr`, on source | `BLOCKED (once per agent per turn): call mcp__jcodemunch__…(repo="<id>", …)` | one deny per agent per user turn, then allows with an advisory |
| `jdocmunch-enforce` (jdoc-doc-steer) | whole Read of an indexed doc ≥ 2,000 bytes | `BLOCKED (once per agent per turn): call mcp__jdocmunch__search_sections(repo="local/<name>", …)` | one deny per agent per user turn, then advisory |
| `first-write-skill-gate` | first Write/Edit of code | `SKILL GATE: First code write to …` | advisory once per session: load the named skills |
| `dox-write-gate` | Write/Edit in a repo with no root `CLAUDE.md` | `DOX GATE: no root CLAUDE.md …` | deny once per repo |
| `gateguard-write-gate` | Write/Edit with high blast radius | `GATEGUARD — high-blast-radius write to …` | `ask`, not deny |
| `tdd-guard-gate` | Write/Edit in a project with a test runner | `⚠️ TDD GUARD (advisory — not blocking):` | advisory, 15 s cap; never in `$HOME` / non-git |
| `bash-write-gate` | Bash / PowerShell shell-write patterns (`sed -i`, `>`, `tee`, `Set-Content`, `Out-File`, …) | `BASH-WRITE-GATE (advisory)`, once per kind per session; deny when `BASH_WRITE_GATE_DENY_SHELL_WRITES=1` | rule carried by `01-no-shell-writes.md` |
| `memwatch-brake` | Agent/Task/Workflow + heavy shell commands | `memory warn:` / `memory crit:` | warn: advisory once per tier per session; crit: `ask`, advisory when unattended |
| `config-protection-gate` | Write/Edit on lint/format config | — | `ask` unless the prompt asked for it |
| `settings-protection-gate` | Write/Edit, and Bash/PowerShell writes, on `.claude/settings*.json`, `hooks/model-policy.json`, `~/.claude.json` (new files too) | — | `ask`, never an auto-deny (2026-10-31: subagent / unattended / headless `-p` get the ask too and the session's permission mode decides); escape = the prompt names the file (`.claude/settings…` path for the settings files; basename for `.claude.json` / `model-policy.json`) or a permission-rule phrase (`permission rule`, `allow rule`, `permissions.allow`, ...) |
| `hookify-gate` | repo `.claude/hookify.*.local.md` rules | — | gate on tools; advisory on prompt/stop |
| `connector-ask-gate` | claude.ai connector, plugin and GitHub write tools | — | `ask` (subagents too; never an advisory, never an auto-deny) |
| `hard-completion-gate` | Stop | `Gate 2 (docs)` … `Gate 5 (dead code)` | ≤1 block per turn |
| `blocking-doc-enforcer` | `git commit` | `BLOCKED: Cannot commit without documentation updates.` | only when doc trees exist |
| mercy mod guard | Bash / PowerShell dev server / watcher, subagent commit/push, live secret in a write | `mercy guard:` | deny; userConfig `guard` |
| mercy mod verify gate | Stop after unverified code edits | `mercy verify gate:` | ≤1 block per turn; userConfig `verifyGate` |

jcm-gate-read: non-code paths and `~/.claude` are exempt. Index freshness is event-driven (active
repo only); a session-start STALE/MISSING line → `mcp__jcodemunch__index_folder({path, incremental:true})`
and `graphify update <root>`.

Mods (`mods/<name>`, loaded via rendered `env.CLAUDE_CODE_PLUGIN_DIRS`) run in-process
beside the Python hooks; check them with `python3 scripts/validate_mods.py`.

**Misdiagnosis order when an edit or read is refused** (stop at the first hit):
1. No jcodemunch call yet by this agent this turn → make the call the refusal names. 2. No `Read` of that file before
`Edit` → `Read` it and retry immediately (or use `ctx_patch`). 3. The message is a named
gate above → follow it. 4. Only then look at `settings.json` `permissions.deny` (should
be `[]`) or another running session. `Error editing file` is native, not a hook. Never
open with "settings drift".

**Conventions:** one concern per rule file; rules cost context every turn, so anything
not needed on every turn goes into a skill's `references/`. `rules/**` is never written
by dox. Hooks print nothing on success, return `{}` on doubt, and never block on an
exception.
