# OOM guard

Keeps Claude Code sessions alive when the machine runs out of memory, and acts on memory pressure before the kernel does.

## Why

The kernel OOM killer takes one process. systemd's default `DefaultOOMPolicy=stop` then stops the whole unit that process lived in. A terminal tab is one unit (`ptyxis-spawn-<uuid>.scope`, `gnome-terminal-*.scope`), so one runaway `vitest` or browser tab took every Claude session, MCP server and tmux server in that tab with it. Recorded losses: 2026-10-18, 10-20, 10-24, 10-26, 10-27.

tmux 3.6 puts each pane in its own `tmux-spawn-*.scope`, so wrapping the tmux server does nothing for the panes. The protective scope has to be created inside the pane, by the command that starts `claude`.

## Layers

| Layer | What | Where |
|---|---|---|
| L0 | `DefaultOOMPolicy=continue` for every new user scope | `~/.config/systemd/user.conf.d/10-oom.conf` (template `hooks/tools/oomguard/10-oom.conf`) |
| L1 | every interactive `claude` in its own `claude-<pid>.scope` with `OOMPolicy=continue`, `ManagedOOMPreference=avoid`, `MemoryHigh=12G`; RAM-derived agent caps | `bin/claude`, `bin/claude-tmux`, PATH block in `~/.zshrc` / `~/.bashrc` |
| L2 | per-tool memory cap and default agent caps | `settings.template.json` `env` (`CLAUDE_CODE_TOOL_MEMORY_LIMIT=6G`, …) |
| L3 | the sentinel: tiers, kill ladder, journal readers, announcements | `hooks/tools/memwatch.py` as `claude-memwatch.service` |
| L4 | session ledger and restore after a crash | `hooks/session-ledger.py`, `scripts/restore_sessions.py`, `claude-restore.service` |
| L5 | brake gate, statusline segment, once-per-session notice, mod relay | `hooks/memwatch-brake.py`, `scripts/statusline.py`, `hooks/lib/session_notices.py` |
| L6 | doctor rows and self-heal | `installer/doctor_oomguard.py`, `installer/oomguard_setup.py` |

### L1: the launcher

`bin/claude` finds the real binary (`CLAUDE_REAL_BIN`, else the next `claude` on PATH that is not a copy of the launcher) and runs it through `systemd-run --user --scope`. It passes straight through, with no scope and no caps, when:

- the call is `-p` / `--print` (it also exports `CLAUDE_WORKBENCH_UNATTENDED=1`) or `--bare` (hook helpers);
- `CLAUDECODE` is set or `CLAUDE_WORKBENCH_SCOPE=1` (nested launch: no scope inside a scope);
- there is no `$XDG_RUNTIME_DIR/bus` or no `systemd-run`.

Launch caps from `MemAvailable` (GiB, rounded down), exported only when the shell did not set them:

- `CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS` = clamp(⌊GiB/3⌋, 1, 8)
- `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` = clamp(⌊GiB/2⌋, 2, 6)
- `workflowSizeGuideline` (passed with `--settings state/launch-settings-<pid>.json` unless the caller gave `--settings`): `small` under 8 GiB, `medium` under 16, else `large`.

The numbers land in `state/launch-caps/<pid>.json`. `CLAUDE_SCOPE_MEMORY_HIGH` overrides `MemoryHigh`. `bin/claude-tmux` puts the tmux server in its own continue-scope; the panes are covered by `bin/claude`.

### L3: the sentinel

`claude-memwatch.service` (`MemoryMax=200M`, `Nice=10`, `Restart=always`) samples `/proc/meminfo`, `/proc/pressure/memory` and the process table every 5 s, sooner when a PSI trigger fires.

| Tier | Enters when | Leaves when |
|---|---|---|
| warn | MemAvailable < 8192 MB, or PSI some avg10 > 10, or swap free < 5 % with MemAvailable < 12288 MB | MemAvailable ≥ 8192 + 1024 MB and PSI < 5, and 60 s since the last change |
| crit | MemAvailable < 3072 MB, or PSI > 25 | MemAvailable ≥ 3072 + 1024 MB and PSI < 12.5, and 60 s since the last change |

Rising is immediate; falling waits. Thresholds live in `hooks/memwatch.config.json`.

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
| 2 | crit for 20 s, or MemAvailable < 1500 MB | SIGTERM (SIGKILL after 3 s) to the biggest browser renderer (`Isolated Web Co`, `Web Content`, `chrome --type=renderer`, …) or stray build (`tsserver`, `vitest`, `cargo`, …) outside every claude tree and owned by your uid; one victim per 10 s | browser parents, anything under a `claude` process or in a `claude-*` scope, a process with a `claude` below it (VS Code pty host), other users' processes, the protected list (`tmux`, `gnome-shell`, `sshd`, `systemd`, `pipewire`, `ollama`, …) |
| 3 | stage 2 active for 40 s, or an emergency with no stage-2 victim | SIGTERM the most idle ledger session (idle ≥ 10 min, not the foreground one, no Bash call still running), stop its scope 5 s later only when it is a `claude-*` scope; the restore brings it back | the foreground session or the one under the focused tmux pane, a session with a pending Bash call, a terminal or editor scope |

Stages 2 and 3 act on the current sample: when MemAvailable climbs back above the crit enter line, the tier can stay crit (hysteresis) but nothing more is killed, and the stage-3 clock restarts. A refused SIGTERM (EPERM) is logged with `"ok": false`, is not announced, and frees the kill slot. A browser parent kill closes every window, while a killed renderer reloads its tab. Children of claude belong to the 6G tool cap (L2). Stage 3 only stops a session the restore can bring back. memwatch debounces restore spawns with `state/restore.spawned`; `state/restore.lock` belongs to `restore_sessions.py`.

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
~/.claude/oomguard.local.json  {"restore_enabled":true,"shed_mode":"own-builders","memory_high":"12G",
                               "kill_policy":{"enabled":true},"protected_extra":[],"victims_extra":[]}
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
| `memory_high` | the scope's `MemoryHigh` written by the installer (`12G`) |
| `kill_policy.enabled: false` | crit stays at stage 0: no shed, no kill |
| `kill_policy.stage_holdoff_s`, `emergency_mb`, `idle_min` | stage timings |
| `protected_extra` | process names never touched (wins over `victims_extra`) |
| `victims_extra` | process names stage 2 may kill |

## Ask-or-advise rule (directive 31)

An `ask` from any gate becomes a logged advisory when nobody is there to answer it: a subagent payload (`agent_id` / `agent_type`), a ledger entry with `restored: true`, `CLAUDE_WORKBENCH_UNATTENDED=1` (set by `bin/claude` for `-p`), or a Workflow call (`workflow_id`). The decision lives in `hooks/lib/gate_mode.decide()`; each downgrade writes a telemetry row with `decision: "ask_downgraded"` and the reason. `deny` is never downgraded. Interactive sessions still get the prompt.

## Windows

Every probe in `hooks/lib/platform.py` returns `None` there. The sentinel prints `unsupported` and writes `{"level":"ok","unsupported":true}`; the brake and statusline stay silent; the installer and doctor print SKIP rows; `bin/claude` is never on a PowerShell PATH. Ideas for later, not built: `GlobalMemoryStatusEx` for the probe, job objects for the scope.

## Not doing

- Killing browser parents or any user-launched process outside the victim classes.
- A second kill daemon next to systemd-oomd.
- Anything that needs sudo (system-wide `DefaultOOMPolicy`, swap size): that lives in the go-live plan.
