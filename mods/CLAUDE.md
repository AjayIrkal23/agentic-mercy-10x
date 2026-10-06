# `mods/` — local rules (dox)

> Local doc for `mods/` and the `mercy` mod (a plugin root may not carry its own
> `CLAUDE.md`: `claude plugin validate --strict` refuses it). Read after the root
> `CLAUDE.md`. Update it when you add, remove, or rename a file here or change a
> feature's contract.

## What lives here

Claude Code mods (hooks modules, Claude Code ≥ 2.1.288, early access), one folder per
plugin. A mod runs inside the claude process next to the Python hooks in `../hooks/`. It
never replaces them: Python stays the truth for every gate.

## How a mod loads

1. `../installer/manifest.json` → `mods.enabled` names the folders.
2. `../installer/render.py` writes their absolute paths into `settings.json` →
   `env.CLAUDE_CODE_PLUGIN_DIRS`, joined with `os.pathsep` (`:` on Ubuntu, `;` on
   Windows). The template token is `{{MOD_DIRS}}`; an empty list drops the key.
3. Claude Code loads each folder at session start. Mods sit behind a remote rollout
   switch (`tengu_plugin_hooks_modules` in `~/.claude.json` → `cachedGrowthBookFeatures`)
   that each session reads at start and refreshes near its start. On 2026-10-05 about
   one refresh in three came back off, at random per session (any model). A session that
   starts while it is off runs without the mod, and `dispatch.py` runs every link (no
   `MERCY_MOD_*` env), which is the pre-mod behaviour. `claude plugin test` then says
   "hooks modules are turned off" (`validate_mods.py` warns, never fails). There is no
   supported override; never edit the cached flag.

## Conventions (every mod)

- Check: `python3 scripts/validate_mods.py` (static M1–M6, then `claude plugin validate
  --strict` and `claude plugin test`); doctor row `mods` runs the same minus tests.
- Type-check: `tsc -p mods/<name>` once the engine has laid `.claude-plugin/types/`
  there. That folder is engine output, gitignored; never commit it (M6).
- No `setTimeout`, `setInterval`, `console`, `import()` or `require` in a module: the mod
  environment has none of them (M3). Timers are `$.clock.after` / `$.clock.sleep`.
- Validator rules that shape every file: `$` may only be passed to functions declared
  in the same file; a plugin registers each event at most once without a matcher
  (matchers take arrays and RegExp); `register` calls each `registerX(on)` by name.
- New mod: add the folder, add its name to `mods.enabled`, run `installer/render.py`.

## mercy: what it does, per workflow step

One plugin; each feature has a `userConfig` toggle in `mercy/.claude-plugin/plugin.json`.

| Step | Feature | Behaviour |
|---|---|---|
| Session start | lifecycle | ids and roots, dispatch config, ledger restore, repo brain, bridge claim, tools and commands, re-arms a saved auto-resume; prunes repo brains idle 90 days and scratch roots (`/tmp`, `AppData/Local/Temp`), which get no brain |
| Prompt | governor | drops router blocks repeated within `dedupeWindow` turns, skill pushes already loaded or hidden, the first-write line once code was written, the sequential-thinking line once used, `/model opus` when already on Opus; never drops this turn's rank-1 (MUST-READ) line as a repeat (Python enforces it), only once the skill is loaded; an `[inlined skill: …]` body is one item up to the next router section |
| Prompt | state + advisories | live state line and queued background advisories, appended at the end of the conversation |
| System prompt | brain | one `mercy:brain` section per session: verified commands, fixes and notes learned in this repo. Writes merge with what other sessions stored since this one read it |
| Skill listing | focus | inside a git repo, leaves the `focusHide` plugin families out of the listing (they still run by name) |
| Tool call | guard | applies to Bash AND PowerShell (`isShellTool`); denies dev servers and watchers, subagent commit/push, live-looking secrets in a write git would track. Package-manager options before the subcommand (`npm --prefix server run dev-http`, `pnpm -C`, `yarn --cwd`, `-w`, `--filter`) are read past; bare `vitest` is a watcher unless `run` (anywhere among its positionals), `--run`, `--no-watch`, `CI=` or `--watch=false`; `bash`/`sh`/`zsh -c`, `eval` and `( … )` are unwrapped one level; `timeout` of 1–60 s bounds a server or watcher (`timeout 0` is no limit); heredoc bodies are data; `.env.example`-style templates are not secret homes |
| Tool call | ledger | edits, commands (verify kinds, failure loops), skills, subagents; loop nudge on the 3rd and 6th repeat of one failure, thrash nudge on the 8th edit of one file in a turn |
| Pre/PostToolUse | bridge | below |
| Stop | verify gate | once per turn, blocks a finish when code changed after the last passing test/typecheck/build and a verify command is known; otherwise a toast. Backgrounded runs are no evidence, nor is a run whose exit status a later `|`, `;` or `\|\|` masks (`npm test \| tail`); `set -o pipefail` (any spelling) restores `\|`, and `set -e` makes `;` act like `&&`. A user prompt that is only consent ("stop", "just stop", "skip verification", same clauses as `hard-completion-gate`) turns it off for that human turn; Python's block, the verify gate and the late-advisory block share one block per human turn. A `<task-notification>`, interrupt row or peer `<cross-session-message>` is not a human turn |
| Stop | late advisories | blocks once to deliver advisories that finished after the last tool call; a tdd-guard advisory is dropped on every delivery path once its file passed a test after the edit (it is moot then) |
| Usage-limit stop | auto-resume | main-thread `classic.StopFailure` schedules the resume prompt at the reset time + 90 s, saved per session in `$.store` (`resume:<sid>`), at most 12 in a row, re-armed after a restart only when `autoResume` is on in an interactive session; a typed prompt, a normal answer, `/clear` or switching conversations cancels it |
| UI | pulse | `$.ui.status` workflow line, action band above the prompt (verify, failure loop, resume, context ≥ 80 % Compact, 5-hour ≥ 85 %, failing CI), `/pulse [view]` pane with 10 views and letter hotkeys, `/mercy status\|brain\|forget\|release\|resume-cancel` |
| UI | deck | watches git (every 60 s, and 2.5 s after the last write or git command, debounced; `--no-optional-locks`), GitHub CI via `gh` (every 3 min, 20 s after a push; a timeout keeps polling, only a missing `gh` stops it, `/ci` re-arms), context and rate limits (`session.measure`), the model's TodoWrite/Task list and verify pass/fail flips; toasts on changes; `/ci`, `/ui [full\|focus\|quiet\|off\|sound\|notify\|pane on\|off\|reset]` (prefs in `$.store` `ui:prefs`) |
| UI | alerts | turn end ≥ `soundAfter`: Linux `canberra-gtk-play` → `pw-play` → `paplay`, macOS `afplay` (`$.audio.play` is silent on Linux), Windows `powershell.exe` 5.1 `SoundPlayer.PlaySync` (wav NAME from env, path from `$env:SystemRoot`; `SystemSounds` fallback; `winalerts.ts`); toast (`notify-send` ≥ `notifyAfter`; Windows WinRT toast through `powershell.exe` 5.1, never pwsh, title/body only via env, XML-escaped and control-stripped; permission/question wait = `scenario='reminder'` + Dismiss, error turn = `duration='long'`, `Tag/Group='mercy'`); error turn and waits too; quiet hours, mode, 3 s throttle; 15 s timeout on Windows; a failing player or toast is noted once per kind in `/mercy status`; `/sound [test\|on\|off]` names the players of this OS |
| Autonomy | auto | no command needed (CLAUDE.md §11): ports scanned every minute (Linux `ss`; Windows `netstat -ano -p TCP` + `-p TCPv6` + `tasklist /FO CSV /NH`, listening = foreign `0.0.0.0:0` / `[::]:0`, locale-proof; a failed scan keeps the last rows and shows `port scan failed: <reason>` in pane, card and `/ports`, never "nothing listening"; toast when a dev server comes up or stops; pane tab p), npm outdated once a day per package folder (`$.store` `deps:<root>`; a rejected npm, exit ≥ 2 or `{"error":…}` is never stored as "all current": `/deps` answers `/deps failed: …` and `/mercy status` notes it; pane tab d; toast on majors), today's standup at the first session of the day (`standup:<root>`; pane tab s, copy key y; Monday looks back to Friday), the session recap saved after every main turn (`recap:<root>`; the next session's overview shows it), compaction between turns once context ≥ `autoCompact` (85 %, at most every 10 min, keeps plan/tasks/unverified files); `deck.tsx` re-probes the indexes (`index-lifecycle.py reprobe`) when HEAD moves, terminal commits included |
| UI | cmds | `/wrapup` here, `/ports` `/deps` `/standup` in `auto.tsx`: one `#n` line (all the model reads) + a CommandOutput card drawn from `$.state` `cards` (last 30, clock ids, card must match the row's command), Copy and "Open in pane" buttons |
| UI | restyle | full mode: Spinner suffix (this turn's ✎ edits, ⚒ commands, ⚙ agents), task-notification rows as one line (ctrl+o shows all), SessionMode label for a non-full UI mode |
| Model tools | mtools | `mcp__mercy__session_state`, `repo_facts`, `remember` (never deferred) |

## mercy: the bridge (Python half: `hooks/dispatch.py`)

- Session start always sets `MERCY_MOD_LOADED=1` (Python's "mod off" notice reads it, bridge on
  or off), then claims the links in `mercy/hooks/lib/bridgeplan.ts` `POLICIES` and sets
  `MERCY_MOD_OWNED` (ids), `MERCY_MOD_SESSION` and `MERCY_MOD_BEAT` (ms, refreshed on
  every tool event) with `$.env.set`. Hook subprocesses inherit them.
- `dispatch.py` skips an owned link only for the matching session and a beat younger
  than 120 s, so a mod that unloads mid-session hands every link back.
- The mod runs owned links through `dispatch.py <event> --only <ids>`, which ignores
  ownership. `sync` links run only when a predicate says they can fire (shell write,
  `git commit`, doc path, jcodemunch not used yet, no root `CLAUDE.md`, semgrep, skill
  load); their deny is returned as the gate's own, and an ask still lets the rest of the
  Python chain run (a deny there wins). `async` links queue in two lanes: `fast`
  (post-write advisories, drained before each classic tool event, PreCompact and Stop)
  and `slow` (tdd-guard, coalesced per file). Their output reaches the model on the
  next tool result or prompt. `graphify-enforce` runs in line for Agent/Task; a write
  waits up to 4 s for a running tdd-guard check, whose advisory rides that write.
- The PreToolUse payload is rebuilt from the classic envelope with the live
  `$.session.cwd()` (a shell `cd` moves it); `CLAUDE_PROJECT_DIR` is `$.session.root()`.
- A failed or thrown sync run sets `MERCY_MOD_FAILED=<tool_use_id>:<ids>` before the Python
  chain runs, so `dispatch.py` runs those links itself for that call (ownership stays).
  Three failed runs in a row (sync or background) release every link with a toast; queued
  runs still run. `/mercy release` does it by hand; `bridge: off` claims nothing; `tddGuard: sync`
  leaves tdd-guard to Python; an armed `bash-write-gate` deny layer stays Python's.

## mercy: conventions

- `hooks/lib/` is pure (no `$`) and unit-tested. `hooks/features/` holds the hooks, and
  each `$` helper lives in the file that uses it (validator rule).
- One matcher-less hook per event for the whole plugin: `tool.call` → `toolflow.ts`,
  `classic.PreToolUse`/`PostToolUse` → `bridge.ts`, `classic.Stop` → `stop.ts`,
  `classic.UserPromptSubmit`/`prompt.submit`/`prompt.compose` → `prompts.ts`,
  `session.start`/`turn.*`/`session.end` → `lifecycle.ts`, `session.measure` → `deck.tsx`,
  `classic.Notification` → `alerts.tsx`. Matched hooks share events: `deck.tsx`
  (`session.start{isInteractive}`, `tool.call{tool: RegExp}`, `ui.press{requestId: pane}`:
  the plugin's own `$.state.set` never reaches its own `state.set` hooks, a press does),
  `alerts.tsx` and `auto.tsx` (`turn.complete{isAborted:false}`; `auto.tsx` also
  `session.start{isInteractive}` and `ui.press{requestId: pane}`, registered after `deck.tsx`
  so `rt.deck` is settled first), every `ui.render{component}` and `command.run{command}`.
- UI flags come from `ui()` in `lib/runtime.ts` (mode from `/ui` prefs over the `pulse`
  option); never read `rt.options.pulse` directly. Nothing in the deck reaches the model but
  a command's one-line `{ text }`.
- Classic hooks always call `next(e)` (the Python chain runs beneath them); only a
  gate's own deny from an `--only` run returns without it.
- Stable facts go in the one `prompt.compose` section; per-turn text goes in
  prompt.submit or tool-result `context`, so the cached prefix never changes mid-session.
- Every hook catches its own errors (`noteError`, shown by `/mercy status`); a feature
  whose `register` throws is marked `error` and the rest still load. Files stay under
  250 lines. Test fixtures that look like secrets are built by concatenation, or the
  guard denies rewriting the test file.
- Check: `claude plugin test mods/mercy`, `claude plugin validate --strict mods/mercy`,
  `tsc -p mods/mercy`, or all at once `python3 scripts/validate_mods.py`.

## mercy: key files

| File | Role |
|------|------|
| `mercy/.claude-plugin/plugin.json` | manifest + `userConfig` (bridge, tddGuard, guard, verifyGate, dedupeWindow, brain, focus, focusHide, autoResume, pulse = UI mode, sound, soundAfter, notify, notifyAfter, quietHours, paneAuto, ci, autoCompact) |
| `mercy/tsconfig.json` | extends the engine-laid `.claude-plugin/types/tsconfig.json`; adds the noUnused* checks |
| `mercy/types/index.d.ts` | `$.state` contract (`PluginState.mercy`) and shared types |
| `mercy/hooks/hooks.json`, `mercy/hooks/register.ts` | module list; registers the features in nesting order |
| `mercy/hooks/features/lifecycle.ts` | init, turns, usage, brain persistence, /clear and compact resets, auto-resume |
| `mercy/hooks/features/toolflow.ts` | the `tool.call` hook: guard, ledger, nudges, advisory delivery |
| `mercy/hooks/features/bridge.ts` | classic Pre/PostToolUse: sync `--only` runs, lanes, failure count, release. A background run for a subagent's call keeps its state writes but its advisory is dropped (never delivered into the main loop); `toolflow.ts` hands queued advisories only to main-loop tool results |
| `mercy/hooks/features/stop.ts` | classic Stop: drain, Python gates first, verify gate, late advisories |
| `mercy/hooks/features/prompts.ts` | governor, state line, brain section, skill focus, `tool.describe` |
| `mercy/hooks/features/mtools.ts`, `pulse.tsx` | model tools; band, pane (views, tabs, Raster sparkline, Open PR link), `/pulse`, `/mercy` |
| `mercy/hooks/features/deck.tsx`, `alerts.tsx`, `auto.tsx`, `cmds.tsx`, `restyle.tsx` | UI deck watchers + HEAD re-probe + `/ci` `/ui`; sound, notify-send, turn stats + `/sound`; autonomous jobs (ports, deps, standup, recap, auto-compact) + `/ports` `/deps` `/standup`; `/wrapup` + command cards; engine-row rewrites |
| `mercy/hooks/lib/auto.ts` | pure: dev-port rules and changes, day key, standup look-back, session summary, auto-compact decision, card map, ports/deps pane rows |
| `mercy/hooks/lib/deck.ts`, `probes.ts`, `deckviews.ts` | pure: modes/flags, sound rules, git/gh parsers, Raster cells, task list; ports and npm outdated parsers; pane rows, band rows, toasts, card markdown |
| `mercy/hooks/lib/hostconfig.ts` | rendered-settings interpreter, hidden skills, `hooksDirFrom`, `interpreterFrom` |
| `mercy/hooks/lib/runtime.ts` | options, the `rt` singleton (incl. `deck`), `ui()` flags, feature health, resume helpers |
| `mercy/hooks/lib/bridgeplan.ts`, `dispatch.ts`, `queue.ts` | link policies; config parse and matcher (Python `re.fullmatch`); lanes |
| `mercy/hooks/lib/ledger.ts`, `commands.ts`, `shell.ts` | session ledger; command analysis (verify kinds, servers, watchers, commits) |
| `mercy/hooks/lib/guard.ts`, `secrets.ts`, `paths.ts` | deny and nudge texts, verify decision; secret patterns; path helpers |
| `mercy/hooks/lib/governor.ts`, `dedupe.ts`, `focus.ts` | router governor, block hashing, skill-listing focus |
| `mercy/hooks/lib/brain.ts`, `resume.ts` | repo facts and their section; reset-time parsing |
| `mercy/hooks/lib/consent.ts` | user stop consent (same clauses as `hard-completion-gate`'s `CONSENT_RE`: `just`, `skip (the) verify/verification`, curly apostrophes) |
| `mercy/hooks/lib/storekeys.ts`, `toolkinds.ts` | `$.store` key sweep (brains idle 90 days); command kind tables |
| `mercy/hooks/lib/os.ts`, `tools.ts` | `isWindowsEnv(env.get('OS'))` and `system32(root, rel, bare)` (`process` is undefined in a mod; `rt.windows` / `rt.systemRoot` are set once at session start from `$.env.get`); `SHELL_TOOLS` / `isShellTool` (Bash, PowerShell, …) used by guard, ledger, verify gate and the deck |
| `mercy/hooks/lib/winshell.ts`, `winalerts.ts` | pure Windows wrappers: `cmd /c`, `powershell -c`, `Start-Process`, `iex`, `wsl <opts>` unwrapping, `.exe/.cmd/.bat/.ps1` suffixes, `$env:CI=`, status-preserving `exit` forwarders; WinRT toast and SoundPlayer scripts (`toastCmd`, `windowsPlayers`, `sanitizeXmlText`) |
| `mercy/hooks/lib/hostconfig.ts`, `evidence.ts` | python argv and hidden skills read from host files; exit-status ownership (which segment's status reaches the command) |
| `mercy/hooks/lib/snap.ts`, `views.ts`, `specs.ts`, `format.ts` | snapshots, UI models, tool and command specs, formatting |
| `mercy/tests/*.test.ts(x)` | lib units, bridge policy, prompt context, engine-level hook tests, auto-resume end to end and `/mercy`; `winshell.test.ts` (Windows wrapper table, PowerShell tool through the engine; the engine's tool-name union is generated per machine and has no `PowerShell` off Windows, so the test passes it as `POWERSHELL`, cast once, or `tsc` fails on Linux), `ports.test.ts` (netstat / tasklist fixtures, scan failure, `/deps` failure parsing), `toast.test.ts` (hostile strings never reach argv, sanitising, flags); `deck.test.ts` (pure deck parsers and rules), `ui.test.tsx` (pane views on terminal and desktop, band, alerts, task list, cards, restyles; JSX because the test's own `ui.render` hooks stand for the engine) (an engine test that needs the interactive path raises `$.session.start({ isInteractive: true })`: the test's own import of `lib/runtime` is not the plugin's copy) |

## Gotchas / fragile spots

- `userConfig` defaults live only in `plugin.json` (the engine fills them);
  `lib/runtime.ts` `DEFAULTS` are fallbacks.
- Engine tests: `$.turn.complete` needs the full `TurnComplete` input and a `{ text }` answer
  from the test's hook; test modules cannot import `.json`; the test engine approves an ask.
- `$.env.set` changes the claude process env, so Bash children see `MERCY_MOD_*` too.
  That env is the bridge's transport: rename a variable only together with
  `dispatch.py` `_mod_owned`.
- Each hook has a 10 s own-time budget and `$.clock.sleep` counts against it; lane
  drains cap at 4–6 s.
- Module variables reset on every reload. What must survive goes to `$.state`
  (session) or `$.store` (across sessions, 4 MiB per plugin).
- Windows: engine paths may use `\`. `lib/paths.ts` and the matchers accept both
  separators; `dispatch.py` is spawned by argv with the interpreter read from the
  rendered settings (`python3` or `py -3`). In engine tests on Windows a POSIX fixture
  cwd (`/r`) reaches hooks as `C:\r`, so `fs.*` fixtures must match both spellings.
- Windows system tools (`netstat`, `tasklist`, `powershell.exe`) are spawned by absolute
  path `<SystemRoot>\System32\…` (`rt.systemRoot` from `$.env.get('SystemRoot')`, `lib/os.ts`
  `system32`); without a SystemRoot the bare name stays. The PowerShell exit forwarder
  (`winshell.ts`) accepts only status-preserving forms (`exit $LASTEXITCODE`,
  `if ($LASTEXITCODE -ne 0|-not $?|!$?) { exit <non-zero> }`); `wsl` options are parsed in
  `winshell.ts` `wslCommand`; when the PowerShell and bash quote rules split a command
  differently, `analyze` unions their server/watch/commit hits.
- The secret guard's `git check-ignore` runs with `-c safe.directory=*`: on the Windows
  replica the SSH account does not own the repos, and git's exit 128 for "dubious
  ownership" would otherwise read as "not in a repo" and switch the guard off.
- A session id change on `classic.SessionStart` (`/clear`, an in-process `/resume`)
  resets the ledger and re-claims the bridge links under the new id; without that,
  `dispatch.py` would run every link while the mod ran the owned ones too.

## Up / down

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children: none (the `mercy/` plugin root carries no `CLAUDE.md`)
- Related: [`../scripts/validate_mods.py`](../scripts/validate_mods.py),
  [`../hooks/dispatch.py`](../hooks/dispatch.py), [`../installer/render.py`](../installer/render.py)
