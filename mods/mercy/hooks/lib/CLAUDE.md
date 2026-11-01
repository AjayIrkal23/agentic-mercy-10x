<!-- dox:child v1 -->
# `mods/mercy/hooks/lib/` — local rules (dox)

> Local doc for this directory only. Read after the root `CLAUDE.md`. Update this
> file whenever you add, remove, or rename files here, or change a local convention.

## What lives here

<One or two lines: the responsibility of this directory. What kind of files belong,
what does NOT belong here.>

## Local conventions

- <e.g. naming pattern, file-size cap, import boundaries specific to this folder>
- <e.g. "every X must register in Y" / "do not import from Z">

## Key files

Pure modules unless noted (no `$`): what each exports, and who imports it (`features/` unless `lib/`).

| File | Exports | Imported by |
|------|---------|-------------|
| `auto.ts` | dev-port changes, day key, standup days, session summary for the autonomous jobs | cmds, auto, pulse |
| `brain.ts` | the per-repo brain: `learnCommands`, `learnFixes`, `mergeFacts`, `addNote` | pulse, mtools, lifecycle, prompts |
| `bridgeplan.ts` | which dispatch links the mod owns and how to run them (`ownedLinks`, `Plan`) | bridge, lifecycle |
| `commands.ts` | Bash/PowerShell command classification (`analyze`, `classifyArgv`, `commandKey`) | deck, toolflow, lib/guard |
| `consent.ts` | `isConsent`: did the last prompt tell the agent to stop (mirrors `hard-completion-gate.py`) | prompts |
| `deck.ts` | deck UI model: modes, sound rules, git/CI parsers, quiet hours (`flags`, `shouldSound`) | deck, alerts, pulse, lib/deckviews, lib/runtime |
| `deckviews.ts` | pane view rows: usage, git, CI, todo, memory (`memRows`, `memBand`, `gb`) | cmds, deck, auto, pulse, memwatch, lib/auto, lib/views |
| `dedupe.ts` | de-duplication of hook context blocks across turns | prompts, lib/governor |
| `dispatch.ts` | reader of `hooks/dispatch.config.json` (`parseConfig`, `toolMatches`) | lifecycle, lib/bridgeplan, lib/runtime |
| `evidence.ts` | `exitOwners`: which segments decide a command's exit status | lib/commands |
| `focus.ts` | skill-listing focus (`focusListing`) | prompts |
| `format.ts` | display helpers (`duration`, `ago`, `usd`, `meter`, `clip`) | most features and lib views |
| `governor.ts` | governor for the router's per-prompt context (`govern`, `ROUTER_MARK`) | prompts, lib/runtime |
| `guard.ts` | guard decisions: `bashDeny`, `secretDeny`, loop/thrash nudges, `bestVerifyCommand` | stop, toolflow, lib/snap |
| `hostconfig.ts` | readers of rendered settings and skills-index (`hooksDirFrom`, `pythonFrom`, `hiddenFrom`) | lifecycle |
| `ledger.ts` | the session ledger (`emptyLedger`, `recordTool`, `recordEdit`, `recordCommand`) | bridge, restyle, lifecycle, stop, toolflow, lib views |
| `modelcaps.ts` | subagent model cap (`capModel`, `Policy`) mirroring `hooks/opus-guard.py` | model-caps |
| `os.ts` | the one OS switch (`isWindowsEnv`, `defaultPython`, `system32`) | lifecycle, lib/winalerts, lib/probes |
| `nothuman.ts` | `isNotHuman`: harness text (task notification, interrupt, peer message, subagent hand-back, `<agent-message from=`) is not a human prompt; same rule as `hooks/lib/turns.py` and `hooks/prompt_router/classify.py` | prompts |
| `paths.ts` | path classification and `statePathFrom`, `join`, `shortPath` | most features, lib/guard, lib/ledger, lib views |
| `probes.ts` | port/tasklist parsers and `parseMemPressure` | auto, memwatch, lib/deckviews |
| `queue.ts` | background job lanes `fast` / `slow` (`enqueue`, `take`, `busy`) | bridge, lifecycle, stop, lib/snap |
| `resume.ts` | auto-resume timing (`resumeAt`, `parseResetText`, `RESUME_PROMPT`) | lifecycle, lib/snap, lib/deck |
| `resumelock.ts` | shared resume lock rules and the per-session mod flag body (`decideResumeLock`, `lockBody`, `flagBody`) | lifecycle |
| `runtime.ts` | the in-memory runtime `rt`, options, timers (`keepTimer`, `noteError`, `ui`); not pure | every feature, lib/snap, register.ts |
| `scan.ts` | shell segment splitter (`splitSegments`) | lib/shell |
| `secrets.ts` | live-looking secret detection for Write/Edit (`findSecret`) | mtools, toolflow, lib/guard |
| `shell.ts` | shell words and the real command past wrappers (`realCommand`) | lib/evidence, lib/commands |
| `snap.ts` | runtime snapshot for views and `session_state` | cmds, auto, pulse, mtools, lifecycle, toolflow, prompts |
| `specs.ts` | tool and slash-command declarations (`TOOL_SPECS`, `COMMAND_SPECS`, `PANE_ID`) | cmds, deck, alerts, auto, pulse, lifecycle, memwatch |
| `storekeys.ts` | `$.store` housekeeping (`sweepStore`) | lifecycle |
| `toolkinds.ts` | toolchain / framework CLI subcommand kinds | lib/commands |
| `tools.ts` | shell tool set (`SHELL_TOOLS`, `isShellTool`) | deck, toolflow, lib/commands |
| `views.ts` | status line, band and pane rows (`statusText`, `bandModel`) | pulse, lifecycle, toolflow, prompts, lib/deckviews, lib/snap |
| `winalerts.ts` | sound players and the desktop notification command per OS (`toastCmd`) | alerts, lib/deck |
| `winshell.ts` | Windows launchers and PowerShell idioms for the classifier | lib/shell, lib/scan, lib/evidence, lib/commands |

## Gotchas / fragile spots

- <non-obvious thing that breaks if you're not careful>

## Up / down

- Parent: [`../../../CLAUDE.md`](../../../CLAUDE.md)
- Children: <links to deeper `*/CLAUDE.md`, or "none">
- Related repo docs: <link to the numbered doc / CODEX.md section — link, don't restate>
