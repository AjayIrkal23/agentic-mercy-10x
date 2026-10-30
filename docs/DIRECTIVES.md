# Standing directives (checklist; tests/test_directives.py keeps every row loaded)

Strength: TEXT = the sentence is the only carrier; SOFT = a hook injects the text (the key
must still sit in an always-on file); HOOK = code enforces it (the mechanism path must exist).
Keys are exact substrings after whitespace, backticks and asterisks are stripped; several
keys in one cell are joined with ` || `. Always-on files: `CLAUDE.md`, the imported part of
`CLAUDE.machines.local.md`, `rules/0*.md`, `output-styles/caveman.md`, the session-start
aggregator sample. `docs/**` is never searched.

| # | directive | sentence_key | source | mechanism | strength |
|---|---|---|---|---|---|
| 1 | Agent and Workflow are pre-authorized; small tasks stay inline | `pre-authorized` | CLAUDE.md §1 | text | TEXT |
| 2 | Omit `model`; the plan tier and the agent role pick it | `Omit model on Agent calls` | CLAUDE.md §2, rules/04 | `hooks/opus-guard.py`, `hooks/workflow-model-guard.py`, `hooks/model-policy.json` | HOOK |
| 3 | `name` only for teammates | `name only for teammates` | CLAUDE.md §2 | `agents/team-lead.md`, `hooks/teammate-idle-gate.py` | SOFT |
| 4 | Subagents never commit, never start servers | `never git commit and never start servers` | CLAUDE.md §2 | `hooks/subagent-context.py`; mod guard | SOFT |
| 5 | Per-project model mode phrases | `use opus for this project` | CLAUDE.md §2 | `hooks/prompt_router/router.py`, `hooks/lib/model_mode.py` | HOOK |
| 6 | No shell writes | `never writes files` | rules/01 | `hooks/bash-write-gate.py` (advisory; deny off) | TEXT |
| 7 | FIND with jcodemunch → READ → Edit | `FIND with jcodemunch` | CLAUDE.md §3, rules/00 | `hooks/jcodemunch-enforce.py` | HOOK |
| 8 | Ask before deleting files or removing features | `Ask before deleting files or removing features` | CLAUDE.md §3 | `hooks/dangerous-bash-gate.py` (shell forms only) | TEXT |
| 9 | Commit only when asked | `Commit only when asked` | CLAUDE.md §3 | `hooks/blocking-doc-enforcer.py` (docs gate only) | TEXT |
| 10 | MCPs are mandatory | `MCPs are mandatory` | CLAUDE.md §4, rules/00, rules/03 | router routes, `hooks/graphify-enforce.py`, `hooks/jdocmunch-enforce.py` | SOFT |
| 11 | Verify without servers; evidence before done | `Never start dev servers` | CLAUDE.md §5 | mod verify gate; `hooks/mcp-post-hints.py` | SOFT |
| 12 | dox: read root → dir CLAUDE.md; update the local one after | `update the local one after` | CLAUDE.md §6 | `hooks/dox-write-gate.py`, `hooks/hard-completion-gate.py` | HOOK |
| 13 | Memory: search at project start, save on "remember" | `at the start of project work` | CLAUDE.md §7, rules/00 | `hooks/memory-load-on-start.py`, `hooks/lib/memory_gate.py` | HOOK |
| 14 | scroll-craft before scroll code | `before writing scroll code` | CLAUDE.md §8 | router route | SOFT |
| 15 | Higgsfield for assets, never placeholders | `never placeholders or stock URLs` | CLAUDE.md §8, rules/frontend | router UI line | SOFT |
| 16 | Every new app and website is a PWA | `Every new app and every new website is a PWA` | CLAUDE.md §8, rules/frontend | text | TEXT |
| 17 | Style: caveman + no-ai-slop + ponytail reply shape | `full technical accuracy || smallest complete change || no banned words` | CLAUDE.md §9, output-styles/caveman.md | `hooks/session-start-aggregator.py` STYLE_DIRECTIVE; output style | SOFT |
| 18 | Machines file is private, never committed | `never commit it` | CLAUDE.md §10 | `.gitignore`, `scripts/grep_gates.py` G6/G7 | HOOK |
| 19 | Autonomy: the user only prompts and develops | `I only prompt and develop || Never end a turn with "run X" || Ask me only for human-only steps` | CLAUDE.md §11 | `hooks/tools/selfheal-daily.py`, `tests/test_autonomy_wpd.py` | SOFT |
| 20 | Run sudo yourself, never ask the user (owner machines only) | `never ask me to run sudo` | machines | `scripts/sudo-askpass.sh` (gitignored) | TEXT |
| 21 | Dev PC #2 never sleeps; full performance (owner machines only) | `NEVER let the laptop sleep || Full performance always` | machines | text | TEXT |
| 22 | Ubuntu + Windows parity | — | memory `cross-platform-ubuntu-windows` | `hooks/lib/platform.py`, `scripts/grep_gates.py`, CI | HOOK |
| 23 | Zero `lean-ctx` strings in settings.json/CLAUDE.md | — | memory `lean-ctx-shadow-mode-deny-incident` | `installer/render.py` FORBIDDEN_SUBSTRING, `installer/doctor_checks.py` | HOOK |
| 24 | `permissions.deny` stays `[]` | — | template | `hooks/settings-permissions-selfheal.py` (SessionStart exec and the ConfigChange link `permissions-deny-guard`, same file with arg `config-change`), `tests/test_template_contract.py` | HOOK |
| 25 | Hooks fail open; Stop gates block once per turn; no daemons in hooks | — | hooks/CLAUDE.md | `hooks/dispatch.py`, `hooks/lib/turns.py`, `tests/test_timeout_ladder.py` | HOOK |
| 26 | Subagents Read before Edit | — | subagent-context | `hooks/subagent-context.py`; native | HOOK |
| 27 | Index/graph freshness event-driven; ollama remote, no local fallback | `falls back to a local ollama` | machines | `hooks/index-lifecycle.py`, `installer/ollama_setup.py` | TEXT |
| 28 | Auto-resume after a usage limit | — | memory `auto-resume-after-limit` | `mods/mercy/hooks/features/lifecycle.ts`, `scripts/restore_sessions.py` | HOOK |
| 29 | Sessions survive an OOM kill | — | memory `oom-kills-terminal-scope` | `hooks/memwatch-ensure.py`, `hooks/memwatch-brake.py`, `installer/oomguard_setup.py` | HOOK |
| 30 | Production safety (owner machines only): never touch Contabo/GCP prod, cutover or rollback without the user's word; GCP VM read-only; servers run IST | `without my explicit word || GCP VM is read-only || Servers run IST || Read-only unless the user asks` | machines (prod-safety block written by `scripts/split_machines_file.py`) | text | TEXT |
| 31 | ask-or-advise: every gate `ask` becomes a logged advisory when unattended (subagent, restored session, `-p`, Workflow); `.blast-bypass` never covers secret material; git hook bypass denied; GitHub write tools denied for subagents | — | gates, oom-sentinel | `hooks/lib/gate_mode.py`, `hooks/gateguard-write-gate.py`, `hooks/dangerous-bash-gate.py`, `hooks/connector-ask-gate.py` | HOOK |
| 32 | Plan ceilings are hard: pro never Opus/Fable; max5 Opus only when asked that turn; Fable only when asked | `pro never Opus` | rules/04 | `hooks/opus-guard.py` (`hooks/tests/test_opus_guard.py::test_tier_matrix_per_role`) | HOOK |

## How to add a row

Append the next id; pick the strength by what actually carries the rule (code beats text).
TEXT/SOFT rows name a key that is a verbatim substring of an always-on file; HOOK rows name
the enforcing file first in `mechanism`. Change a key and its sentence in the same edit.

## Rows that moved in the 2026-10 merge

- Row 1: CLAUDE.md §1 now pre-authorizes `Workflow` beside `Agent` (one sentence).
- Row 2: the model choice follows the plan tier (`rules/04-model-routing.md`), not fixed labels.
- Row 17: the caveman rules ride in the `caveman` output style, no longer a full skill body
  injected at session start.
- Row 30: the production-safety block is appended to the imported machines file by
  `scripts/split_machines_file.py`, so it survives the split; the GCP VM bullet's
  `Read-only unless the user asks` is lifted back the same way.
- Row 31: new (gates + oom-sentinel). Row 32: new (model-routing tier ceilings).
