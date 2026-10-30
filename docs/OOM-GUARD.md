# OOM guard

Keeps Claude Code sessions alive when the machine runs out of memory, and acts on memory pressure before the kernel does.

## Why

The kernel OOM killer takes one process. systemd's default `DefaultOOMPolicy=stop` then stops the whole unit that process lived in. A terminal tab is one unit (`ptyxis-spawn-<uuid>.scope`, `gnome-terminal-*.scope`), so one runaway `vitest` or browser tab took every Claude session, MCP server and tmux server in that tab with it. Recorded losses: 2026-10-18, 10-20, 10-24, 10-26, 10-27.

tmux 3.6 puts each pane in its own `tmux-spawn-*.scope`, so wrapping the tmux server does nothing for the panes. The protective scope has to be created inside the pane, by the command that starts `claude`.

## Layers

| Layer | What | Where |
|---|---|---|
| L0 | `DefaultOOMPolicy=continue` for every new user scope | `~/.config/systemd/user.conf.d/10-oom.conf` (template `hooks/tools/oomguard/10-oom.conf`) |
| L1 | every interactive `claude` in its own `claude-<pid>.scope` with `OOMPolicy=continue`, `ManagedOOMPreference=avoid`, `MemoryHigh` = MemTotal minus 4 GiB, never below 50 % (`bin/claude-tmux` gives the tmux server the same); RAM-derived agent caps | `bin/claude`, `bin/claude-tmux`, PATH block in `~/.zshrc` / `~/.bashrc` / `~/.profile` (bash login shells); the launcher also passes the tier's main model (`docs/MODEL-ROUTING.md` §6) |
| L2 | machine-wide tool memory cap (ONE cgroup, `app.slice/claude-code-bash`, shared by every session's Bash/tool commands) and default agent caps | `settings.template.json` `env` sets the floors (`CLAUDE_CODE_TOOL_MEMORY_LIMIT=6G`, 5 subagents, 4 workflow agents) for every launch; on Linux the installer sizes all three per machine in `settings.user.json` (`seed_machine_overlay`): the tool cap by the memory rule, the agent floors by RAM |
| L3 | the sentinel: tiers, kill ladder, journal readers, announcements | `hooks/tools/memwatch.py` as `claude-memwatch.service` |
| L4 | session ledger and restore after a crash | `hooks/session-ledger.py`, `scripts/restore_sessions.py`, `claude-restore.service` |
| L5 | brake gate, statusline segment, once-per-session notice, mod relay | `hooks/memwatch-brake.py`, `scripts/statusline.py`, `hooks/lib/session_notices.py` |
| L6 | doctor rows and self-heal | `installer/doctor_oomguard.py`, `installer/oomguard_setup.py` |

### L1: the launcher

`bin/claude` finds the real binary (`CLAUDE_REAL_BIN`, else the next `claude` on PATH that is not a copy of the launcher) and runs it through `systemd-run --user --scope`. It passes straight through, with no scope and no caps, when:

- `$1` is a subcommand (`plugin`, `mcp`, `update`, … the list that also skips the tier model): a
  management command is not a session, and `--settings` in front of one made `claude plugin test` refuse;
- the call is `-p` / `--print` (it also exports `CLAUDE_WORKBENCH_UNATTENDED=1`) or `--bare` (hook helpers);
- `CLAUDECODE` is set or `CLAUDE_WORKBENCH_SCOPE=1` (nested launch: no scope inside a scope);
- there is no `$XDG_RUNTIME_DIR/bus` or no `systemd-run`.

Launch caps from `MemAvailable` (GiB, rounded down), exported only when the shell did not set them:

- `CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS` = clamp(⌊GiB/3⌋, 1, 8)
- `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` = clamp(⌊GiB/2⌋, 2, 6)
- `workflowSizeGuideline` (passed with `--settings state/launch-settings-<pid>.json` unless the caller gave `--settings`): `small` under 8 GiB, `medium` under 16, else `large`.

Settings `env` beats the process environment, so the two caps also go into the launch-settings file's `env` block (it outranks the user settings file). `settings.template.json` sets a floor of 5 subagents and 4 workflow agents for launches that skip `bin/claude` (`-p`, `--bare`, nested, no user bus, the desktop app, Windows); on Linux the installer sizes that floor per machine in `settings.user.json` (3 / 2 on a 16 GB box, 5 / 4 on 30 GB), and the launcher still sizes each interactive launch from MemAvailable. When you pass your own `--settings`, the caps stay env-only and a user settings `env` value wins. The numbers land in `state/launch-caps/<pid>.json`. The scope's `MemoryHigh` is `CLAUDE_SCOPE_MEMORY_HIGH`, else `oomguard.local.json` `memory_high`, else MemTotal minus 4 GiB, never below half of MemTotal (11554M on a 16 GB laptop, 26573M on 30 GB). `bin/claude-tmux` puts the tmux server in its own continue-scope with the same `MemoryHigh`; the panes are covered by `bin/claude`.

### L3: the sentinel

`claude-memwatch.service` (`MemoryMax=200M`, `Nice=10`, `Restart=always`) samples `/proc/meminfo`, `/proc/pressure/memory` and the process table every 5 s, sooner when a PSI trigger fires.

| Tier | Enters when | Leaves when |
|---|---|---|
| warn | MemAvailable < 15 % of MemTotal, or PSI some avg10 > 10, or swap free < 5 % with MemAvailable < 22.5 % of MemTotal | MemAvailable ≥ the warn line + 1024 MB and PSI < 5, and 60 s since the last change |
| crit | MemAvailable < 8 % of MemTotal, or PSI > 25 | MemAvailable ≥ the crit line + 1024 MB and PSI < 12.5, and 60 s since the last change |

Rising is immediate; falling waits. Thresholds live in `hooks/memwatch.config.json` (percent; the MB lines per machine are in "Small or headless machine").

Two journal readers report kills the sentinel did not make:

- kernel: `Out of memory: Killed process <pid> (<name>) total-vm:…kB, anon-rss:…kB, …` (and `Memory cgroup out of memory: …` for a capped scope). The name may hold spaces and parentheses: `node (vitest 4)`.
- systemd-oomd: `Killed /user.slice/user-1000.slice/user@1000.service/app.slice/<unit> due to memory pressure for … being 91.07% > 50.00% for > 20s with reclaim activity`.
- the user manager (`journalctl --user`): `<unit>: The kernel OOM killer killed some processes in this unit.` and `Stopped <unit>.` A `Stopped` line within 60 s of a kill for that scope records the scope's death; each kill is matched once, and a unit-less kernel kill only matches the scope its pid was last seen in.

Units named `claude-test-*` are test scopes and never become kill rows.

Each tier change and each kill is announced once: `notify-send` (warn `normal`, crit and kills `critical`); a live mod (any `state/mercy-mod.active.d/<sid>.json` younger than 60 s) toasts in-pane as well; the desktop notification is always memwatch's, one per machine. `notify.quiet_hours` (`"23:00-07:00"`) silences warn only.

### The kill ladder

| Stage | Trigger | Action | Never |
|---|---|---|---|
| 0 | ok / warn | nothing | |
| 1 | crit | `systemctl --user stop` our own `claude-index-*` scopes (`shed_mode: known-heavy` also kills headless chrome and vitest under claude) | any scope we did not start |
| 2 | crit for 20 s, or MemAvailable < 4 % of MemTotal (emergency) | SIGTERM (SIGKILL after 3 s) to the biggest browser renderer (`Isolated Web Co`, `Web Content`, `chrome --type=renderer`, …) or stray build (`tsserver`, `vitest`, `cargo`, …) outside every claude tree and owned by your uid; one victim per 10 s | browser parents, anything under a `claude` process or in a `claude-*` scope, a process with a `claude` below it (VS Code pty host), other users' processes, the protected list (`tmux`, `gnome-shell`, `sshd`, `systemd`, `pipewire`, `ollama`, …) |
| 3 | stage 2 active for 40 s, or an emergency with no stage-2 victim | SIGTERM the most idle ledger session (idle ≥ 10 min, not the foreground one, no Bash call still running), stop its scope 5 s later only when it is a `claude-*` scope; the restore brings it back | the foreground session or the one under the focused tmux pane, a session with a pending Bash call, a terminal or editor scope |

A Claude session is recognised by command line, not only by the process name `claude`: the native installer's binary shows its version (`2.1.312`) as the name and the npm cli runs as `node`, so `kill_policy.claude_cmd_re` in `hooks/memwatch.config.json` (`/claude/versions/<n>`, `claude bg-pty-host`, `@anthropic-ai/claude-code/`, …) decides for those. A `--dry-run` pass writes `dry_run: true` rows and a `DRY-RUN would kill` journal line, never a desktop toast.

Stages 2 and 3 act on the current sample: when MemAvailable climbs back above the crit enter line, the tier can stay crit (hysteresis) but nothing more is killed, and the stage-3 clock restarts. A refused SIGTERM (EPERM) is logged with `"ok": false`, is not announced, and frees the kill slot. A browser parent kill closes every window, while a killed renderer reloads its tab. Children of claude belong to the machine-wide tool cap (L2). Stage 3 only stops a session the restore can bring back. memwatch debounces restore spawns with `state/restore.spawned`; `state/restore.lock` belongs to `restore_sessions.py`.

### L5: what you see

- Brake (`PreToolUse` on Agent, Task, Workflow, heavy Bash/PowerShell, `mcp__playwright__browser_navigate`): warn adds one advisory per tier per session; crit asks `permissionDecision: ask` with the numbers, or adds an advisory when the session is unattended (see the ask-or-advise rule).
- Statusline: `mem 11G sw99% wf4` (green, yellow at warn, red at crit; hidden when the state is older than 30 s), a plan tier suffix (`20x`) and `↓` while the usage guard is active.
- SessionStart: `OOM guard since last session: 2 kills (node 3.9 GB, kernel; Isolated Web Co 2.4 GB, memwatch stage 2), 1 session restored`, said once per event.

## Files

```text
state/mem-pressure.json  {"schema":1,"ts":<epoch>,"level":"ok|warn|crit","mem_available_mb":11210,"swap_free_pct":1.2,
                          "psi_some_avg10":3.4,"top":[{"name":"tsserver","rss_mb":3800,"unit":"ptyxis-spawn-....scope"}],
                          "stuck":[{"sid":"...","since":<epoch>}],"shed":[],"notify_owner":"memwatch|mod",
                          "kill_policy":{"stage":0,"crit_since":null,"stage2_since":null,"last_kill_ts":null},
                          "restore_pending":false,"unsupported":false}
state/oomguard.events    one JSON per line:
   {"ts","kind":"tier","from":"ok","to":"warn","mem_available_mb","psi_some_avg10","swap_free_pct"}
   {"ts","kind":"kill","victim":"node","pid":123,"rss_mb":3900,"unit":"x.scope","source":"kernel|oomd|user-manager|memwatch","stage":2,"cmd":"...","dry_run":false}
   {"ts","kind":"shed","unit":"claude-index-graphify-ab12cd34.scope","dry_run":false}
   {"ts","kind":"restore","sid":"...","ok":true}
state/oomguard.cursor    {"reported_until": <ts>}
state/mercy-mod.active.d/<sid>.json  {"sid","pid","ts"}  one per live mod session
state/live-sessions/<sid>.json  {"sid","pid","cwd","transcript","tmux","scope","started","seen","ended":null,"restored":false}
state/session-bridge/<sid>.json {"context_pct","cost_usd","five_hour_pct","five_hour_resets_at","ts"}
state/launch-caps/<pid>.json {"mem_available_mb","workflow_agents","subagents","size_guideline","ts"}
~/.claude/oomguard.local.json  {"restore_enabled":true,"shed_mode":"own-builders","memory_high":"8G",
                               "kill_policy":{"enabled":true},"protected_extra":[],"victims_extra":[],
                               "linger":true,"tiers":{"warn":{"mem_available_mb":5000}}}   (every key optional)
```

A missing or stale (> 30 s) state file reads as `ok` everywhere.

## Runbook

```sh
systemctl --user status claude-memwatch
journalctl --user -u claude-memwatch -n 50
cat ~/.claude/state/mem-pressure.json
tail ~/.claude/state/oomguard.events
# dry-run the ladder against a fixture (nothing is signalled; fixture pids are never signalled anyway)
python3 hooks/tools/memwatch.py --once --dry-run --proc-root hooks/tests/fixtures/proc-kill \
  --state /tmp/mw.json --events /tmp/mw.jsonl
# (re)install: drop-in, units, PATH block, attach running sessions
python3 installer/oomguard_setup.py --apply
# is this shell's scope protected?
systemctl --user show "$(basename "$(cut -d: -f3 /proc/self/cgroup)")" -p OOMPolicy
```

Move one running session into a continue-scope by hand (what `attach_live` does): list the session's pids (the `claude` pid and its descendants), then

```sh
busctl --user call org.freedesktop.systemd1 /org/freedesktop/systemd1 org.freedesktop.systemd1.Manager \
  StartTransientUnit 'ssa(sv)a(sa(sv))' claude-safe-<pid>.scope fail 3 \
  PIDs au <n> <pid> <child pids…> OOMPolicy s continue ManagedOOMPreference s avoid 0
```

Restore sessions by hand when `scripts/restore_sessions.py` cannot: one tmux session `claude`, one window per session, each started with `bin/claude --resume <id> "<continue prompt>"`, 15 s apart. Strip `CLAUDECODE CLAUDE_* LEAN_CTX_* BASH_ENV MCP_TIMEOUT NoDefaultCurrentDirectoryInExePath` from the environment first. Never `pgrep -f` a pattern that also appears in your own command line.

## Opt-out

`~/.claude/oomguard.local.json` (gitignored; absent means defaults):

| Key | Effect |
|---|---|
| `restore_enabled: false` | no restore spawn, `claude-restore` disabled |
| `shed_mode` | `none` (no stage 1), `own-builders` (default), `known-heavy` |
| `memory_high` | scope `MemoryHigh` for `bin/claude` (`8G`, `16384M`); unset = MemTotal minus 4 GiB, never below 50 % (`bin/claude`, `bin/claude-tmux`) |
| `linger: false` | the installer does not run `loginctl enable-linger` (the doctor row then PASSes as opted out) |
| `tiers.warn` / `tiers.crit` | absolute MemAvailable / swap / psi numbers (MB) that replace the percent lines |
| `kill_policy.enabled: false` | crit stays at stage 0: no shed, no kill |
| `kill_policy.stage_holdoff_s`, `emergency_mb`, `idle_min` | stage timings |
| `protected_extra` | process names never touched (wins over `victims_extra`) |
| `victims_extra` | process names stage 2 may kill |

To drop the launcher from PATH, remove the `# >>> claude-workbench >>>` block from `.zshrc`,
`.bashrc` and `.profile` (the installer only appends it to files that exist; it never creates
`~/.bash_profile` or `~/.zprofile`, so `zsh -l` without an interactive shell keeps `~/.local/bin/claude`).

## Small or headless machine

Every memory line follows MemTotal, so a 16 GB laptop and a 30 GB desktop get the same headroom in
proportion (2026-10-30). Two rules:

- **Caps** (each session's scope `MemoryHigh`, and the machine-wide `CLAUDE_CODE_TOOL_MEMORY_LIMIT`):
  MemTotal minus 4 GiB for the desktop, never below half of MemTotal
  (`hooks/lib/oomguard_config.memory_cap_mb`).
- **memwatch lines**: percent of MemTotal; hysteresis stays 1024 MB and 60 s.

| Knob | Rule | 16 GB laptop (MemTotal 15650 MB) | 30 GB desktop (MemTotal 30669 MB) |
|---|---|---|---|
| scope `MemoryHigh` (per session, also the tmux server) | MemTotal − 4096 MB, ≥ 50 % | 11554M | 26573M |
| `CLAUDE_CODE_TOOL_MEMORY_LIMIT` (one cgroup, all sessions) | same | 11554M | 26573M |
| warn `mem_available_mb` | 15 % | 2347 | 4600 |
| warn swap rule (swap free < 5 %) | 22.5 % (1.5 × warn) | 3521 | 6900 |
| crit `mem_available_mb` | 8 % | 1252 | 2453 |
| `kill_policy.emergency_mb` | 4 % | 626 | 1226 |
| subagents / workflow agents floor (`settings.user.json`) | ⌊MemTotal / 5120⌋ in 2..6, workflow one less | 3 / 2 | 5 / 4 |
| index-lifecycle `fallback_min_avail_mb` | 12288 × min(1, MemTotal / 30000), floor 6000 | 6410 | 12288 |

A "16 GB" laptop reports about 15.3 GiB (firmware and graphics keep the rest), so its caps are 11.3 GiB;
`"memory_high": "12G"` in `oomguard.local.json` and `env.CLAUDE_CODE_TOOL_MEMORY_LIMIT` in
`settings.user.json` pin other values. A local `tiers` number stays absolute and wins.

- **Tool cap:** not per session: every session's tool commands share that one cgroup, so one type-check
  plus another session's vitest must fit in it. A tool killed by it shows as rc 137 / signal 9; the
  doctor's mods-runtime row reports that as WARN "killed: memory cap". A value already in
  `settings.user.json` is yours and is kept.
- **Launch caps:** on 15 GiB free they come out at 4 workflow agents, 6 subagents, `medium`.
- **Linger:** the installer runs `loginctl enable-linger <you>` (no sudo; polkit allows it for
  yourself). The user manager then starts at boot, so `claude-memwatch` runs from boot,
  `claude-restore` runs at boot (it restores sessions killed in the last 2 h into a detached
  tmux), and scopes and the tmux server survive logout. Opt out with `"linger": false`; the doctor
  row `linger` FAILs when the guard is installed without it.
- **tmux:** session restore relaunches into tmux. Without it the doctor's `restore-unit` row
  WARNs and stage 3 says `(not restorable: tmux missing)` instead of `(restored later)`; the kill
  still happens (it saves the machine). `sudo apt-get install -y tmux`.
- **zram:** when swap is under half of RAM and no zram is active, the end-of-run checklist prints
  a one-time `systemd-zram-generator` command (`zram-size = min(ram / 2, 8192)`, zstd). The
  installer never runs it.
- **No desktop:** `notify-send`, `canberra-gtk-play` and `pw-play` are skipped on a server (no
  toasts there); the OOM guard reports through the journal and the SessionStart notice line.
- **No user manager** (container, SSH without a bus): the PATH block is still written; the
  `oomguard` post step reports `SKIP`, never `FAIL`.

## Ask-or-advise rule (directive 31)

An `ask` from any gate becomes a logged advisory when nobody is there to answer it: a subagent payload (`agent_id` / `agent_type`), a ledger entry with `restored: true`, `CLAUDE_WORKBENCH_UNATTENDED=1` (set by `bin/claude` for `-p`), or a Workflow call (`workflow_id`). The decision lives in `hooks/lib/gate_mode.decide()`; each downgrade writes a telemetry row with `decision: "ask_downgraded"` and the reason. `deny` is never downgraded. Interactive sessions still get the prompt.

## Windows

Every probe in `hooks/lib/platform.py` returns `None` there. The sentinel prints `unsupported` and writes `{"level":"ok","unsupported":true}`; the brake and statusline stay silent; the installer and doctor print SKIP rows; `bin/claude` is never on a PowerShell PATH. Ideas for later, not built: `GlobalMemoryStatusEx` for the probe, job objects for the scope. The template's floors stand there (`CLAUDE_CODE_TOOL_MEMORY_LIMIT=6G`, 5 subagents, 4 workflow agents): the installer sizes them from `/proc/meminfo`, which Windows lacks.

## Not doing

- Killing browser parents or any user-launched process outside the victim classes.
- A second kill daemon next to systemd-oomd.
- Anything that needs sudo (system-wide `DefaultOOMPolicy`, swap size): that lives in the go-live plan.
