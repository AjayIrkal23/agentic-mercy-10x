---
paths:
  - "**/.claude/hooks/**"
  - "**/.claude/rules/**"
  - "**/.claude/agents/**"
  - "**/.claude/skills/**"
  - "**/.claude/installer/**"
  - "**/.claude/scripts/**"
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

**Gate reference (what each refusal actually says):**

| Gate | Fires on | Message prefix | Behavior |
|---|---|---|---|
| `dangerous-bash-gate` | Bash | `DANGEROUS COMMAND BLOCKED:` | deny |
| `jcodemunch-enforce` (jcm-gate-read) | Read/Grep/Glob/`ctx_read` on source | `BLOCKED: Use mcp__jcodemunch__…` | budget 2, then fails open |
| `first-write-skill-gate` | first Write/Edit of code | `SKILL GATE: First code write to …` | once per session; load the named skills |
| `dox-write-gate` | Write/Edit in a repo with no root `CLAUDE.md` | `DOX GATE: no root CLAUDE.md …` | deny once; `DOX FIRST —` is advisory |
| `gateguard-write-gate` | Write/Edit with high blast radius | `GATEGUARD — high-blast-radius write to …` | `ask`, not deny |
| `tdd-guard-gate` | Write/Edit in a project with a test runner | `⚠️ TDD GUARD (advisory — not blocking):` | advisory, 15 s cap; never in `$HOME` / non-git |
| `bash-write-gate` | Bash shell-write patterns | advisory unless `BASH_WRITE_GATE_DENY_SHELL_WRITES=1` | rule carried by `01-no-shell-writes.md` |
| `hard-completion-gate` | Stop | `Gate 2 (docs)` … `Gate 5 (dead code)` | ≤1 block per turn |
| `blocking-doc-enforcer` | `git commit` | `BLOCKED: Cannot commit without documentation updates.` | only when doc trees exist |

**Misdiagnosis order when an edit or read is refused** (stop at the first hit):
1. No jcodemunch call yet this session → make one. 2. No `Read` of that file before
`Edit` → `Read` it and retry immediately (or use `ctx_patch`). 3. The message is a named
gate above → follow it. 4. Only then look at `settings.json` `permissions.deny` (should
be `[]`) or another running session. `Error editing file` is native, not a hook. Never
open with "settings drift".

**Conventions:** one concern per rule file; rules cost context every turn, so anything
not needed on every turn goes into a skill's `references/`. `rules/**` is never written
by dox. Hooks print nothing on success, return `{}` on doubt, and never block on an
exception.
