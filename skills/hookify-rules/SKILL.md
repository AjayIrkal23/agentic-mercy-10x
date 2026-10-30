---
name: hookify-rules
description: 'Write a repo-local hookify rule (`.claude/hookify.<name>.local.md`) when the user says "never do X in this repo", "always warn when Y" or asks for a repo guard: declarative bash/file/prompt/stop patterns the hookify gate enforces without hook code.'
when_to_use: 'Use when the user wants a repo-specific never/always rule, a hookify rule, or a pattern guardrail (block a command shape, warn on a file edit, remind at stop); not for global policy, which lives in rules/.'
disable-model-invocation: false
metadata:
  schema: 1
  category: claude-infra
  surfaces:
  - claude-infra
  - codebase
  platforms:
  - linux
  - darwin
  - windows
  token-cost: 764
  triggers:
    keywords:
    - hookify
    - never do
    - always warn
    - repo rule
    - block this command
    - local rule
---

# hookify-rules

## When

The user states a never/always that belongs to ONE repo ("never push to main here", "warn me when
someone adds console.log to src/"). Write the rule file yourself, tell the user the one-line summary,
done. No command to run: the `hookify-gate` link reads the file on the next tool call. Policy for every
repo goes to `~/.claude/rules/` instead.

## File

`<repo>/.claude/hookify.<kebab-name>.local.md`. The gate reads only UNTRUSTED-safe files: untracked,
not a symlink, at most 64 KB. A git-tracked rule is ignored with a diagnostic, so add
`.claude/*.local.md` to the repo's `.gitignore` when it is absent (same turn).

## Format

Frontmatter, then the message body (markdown; shown to the model when the rule fires).

| Key | Value |
|---|---|
| `name` | kebab-case, verb first: `block-*`, `warn-*`, `require-*` |
| `enabled` | `true` (default) or `false` |
| `event` | `bash`, `file`, `prompt`, `stop` or `all` (default) |
| `action` | `warn` (default) or `block` |
| `pattern` | one regex, case-insensitive, at most 400 chars |
| `conditions` | instead of `pattern`: a list of `field` / `operator` / `pattern`, all must hold |
| `tool_matcher` | optional regex the tool name must fully match (`Bash`, `Edit\|Write`) |

Operators: `regex_match`, `contains`, `equals`, `not_contains`, `starts_with`, `ends_with`.
Fields: bash `command`; file `file_path`, `new_text`, `old_text`, `content`; prompt `user_prompt`;
stop `last_assistant_message`. A plain `pattern` is searched in every field of the event.
Use plain scalars or quoted strings: flow lists (`[a, b]`) and block scalars (`|`) are refused.

## Limits

A cloned repo cannot turn rules into a weapon: symlinks, files over 64 KB and tracked files are
refused; 100 rules at most; fields are judged on their first 64 KB; 1 s per event in total; no
backreferences, lookbehind, nested quantifiers (`(a+)+`), quantified alternation (`(a|b)*`) or
`.*x.*`. Every message is prefixed `[untrusted local rule <name>]`, clipped to 2,000 chars, and at
most 5 rules are shown. `block` denies Bash, PowerShell, Write and Edit calls; on prompt and stop
events every rule is advisory (the message says the block was requested).

## Examples

Block a push to main in this repo:

```markdown
---
name: block-push-main
event: bash
action: block
pattern: (?:^|[;&|]\s*)git\s+push\b[^;&|]*\bmain\b
---
Do not push to main in this repo; open a PR from a branch.
```

Warn when `console.log` lands in `src/`:

```markdown
---
name: warn-console-log
event: file
conditions:
  - field: file_path
    operator: regex_match
    pattern: '[\\/]src[\\/].*\.tsx?$'
  - field: new_text
    operator: contains
    pattern: console.log
---
Remove the console.log before finishing; use the logger.
```

Remind at stop (shown as a system message at Stop; it never blocks the stop):

```markdown
---
name: require-e2e
event: stop
pattern: .*
---
Run the e2e suite before saying done.
```

## Change or remove

Edit the file; set `enabled: false` to pause it; delete the file to remove it. Test a pattern on any
platform with `python3 -c "import re; print(re.search(r'<pattern>', '<text>'))"`.
