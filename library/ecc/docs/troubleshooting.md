<!-- ecc:TROUBLESHOOTING.md@25278e7d7b6cf6e6a4e7a6c8e10f14ff22f0eb5b -->
# Troubleshooting (merged from ECC)


## Source: TROUBLESHOOTING.md

## Troubleshooting Guide

Common issues and solutions for ECC plugin.

### Table of Contents

- [Memory & Context Issues](#memory--context-issues)
- [Agent Harness Failures](#agent-harness-failures)
- [Hook & Workflow Errors](#hook--workflow-errors)
- [Installation & Setup](#installation--setup)
- [Performance Issues](#performance-issues)
- [Common Error Messages](#common-error-messages)
- [Getting Help](#getting-help)

---

### Memory & Context Issues

#### Context Window Overflow

**Symptom:** "Context too long" errors or incomplete responses

**Causes:**
- Large file uploads exceeding token limits
- Accumulated conversation history
- Multiple large tool outputs in single session

**Solutions:**
```bash
# 1. Clear conversation history and start fresh
# Use Claude Code: "New Chat" or Cmd/Ctrl+Shift+N

# 2. Reduce file size before analysis
head -n 100 large-file.log > sample.log

# 3. Use streaming for large outputs
head -n 50 large-file.txt

# 4. Split tasks into smaller chunks
# Instead of: "Analyze all 50 files"
# Use: "Analyze files in src/components/ directory"
```

#### Memory Persistence Failures

**Symptom:** Agent doesn't remember previous context or observations

**Causes:**
- Disabled continuous-learning hooks
- Corrupted observation files
- Project detection failures

**Solutions:**
```bash
# Check if observations are being recorded
ls <learning-state-dir>/projects/*/observations.jsonl

# Find the current project's hash id
python3 - <<'PY'
import json, os
registry_path = os.path.expanduser("<learning-state-dir>/projects.json")
with open(registry_path) as f:
    registry = json.load(f)
for project_id, meta in registry.items():
    if meta.get("root") == os.getcwd():
        print(project_id)
        break
else:
    raise SystemExit("Project hash not found in <learning-state-dir>/projects.json")
PY

# View recent observations for that project
tail -20 <learning-state-dir>/projects/<project-hash>/observations.jsonl

# Back up a corrupted observations file before recreating it
mv <learning-state-dir>/projects/<project-hash>/observations.jsonl \
  <learning-state-dir>/projects/<project-hash>/observations.jsonl.bak.$(date +%Y%m%d-%H%M%S)

# Verify hooks are enabled
grep -r "observe" ~/.claude/settings.json
```

---

### Agent Harness Failures

#### Agent Not Found

**Symptom:** "Agent not loaded" or "Unknown agent" errors

**Causes:**
- Plugin not installed correctly
- Agent path misconfiguration
- Marketplace vs manual install mismatch

**Solutions:**
```bash
# Check plugin installation
ls ~/.claude/plugins/cache/

# Verify agent exists (marketplace install)
ls ~/.claude/plugins/cache/*/agents/

# For manual install, agents should be in:
ls ~/.claude/agents/  # Custom agents only

# Reload plugin
# Claude Code → Settings → Extensions → Reload
```

#### Workflow Execution Hangs

**Symptom:** Agent starts but never completes

**Causes:**
- Infinite loops in agent logic
- Blocked on user input
- Network timeout waiting for API

**Solutions:**
```bash
# 1. Check for stuck processes
ps aux | grep claude

# 2. Enable debug mode
export CLAUDE_DEBUG=1

# 3. Set shorter timeouts
export CLAUDE_TIMEOUT=30

# 4. Check network connectivity
curl -I https://api.anthropic.com
```

#### Tool Use Errors

**Symptom:** "Tool execution failed" or permission denied

**Causes:**
- Missing dependencies (npm, python, etc.)
- Insufficient file permissions
- Path not found

**Solutions:**
```bash
# Verify required tools are installed
which node python3 npm git

# Fix permissions on hook scripts
chmod +x ~/.claude/plugins/cache/*/hooks/*.sh
chmod +x ~/.claude/plugins/cache/*/skills/*/hooks/*.sh

# Check PATH includes necessary binaries
echo $PATH
```

---

### Hook & Workflow Errors

#### Hooks Not Firing

**Symptom:** Pre/post hooks don't execute

**Causes:**
- Hooks not registered in settings.json
- Invalid hook syntax
- Hook script not executable

**Solutions:**
```bash
# Check hooks are registered
grep -A 10 '"hooks"' ~/.claude/settings.json

# Verify hook files exist and are executable
ls -la ~/.claude/plugins/cache/*/hooks/

# Test hook manually
bash ~/.claude/plugins/cache/*/hooks/pre-bash.sh <<< '{"command":"echo test"}'

# Re-register hooks (if using plugin)
# Disable and re-enable plugin in Claude Code settings
```

#### Python/Node Version Mismatches

**Symptom:** "python3 not found" or "node: command not found"

**Causes:**
- Missing Python/Node installation
- PATH not configured
- Wrong Python version (Windows)

**Solutions:**
```bash
# Install Python 3 (if missing)
# macOS: brew install python3
# Ubuntu: sudo apt install python3
# Windows: Download from python.org

# Install Node.js (if missing)
# macOS: brew install node
# Ubuntu: sudo apt install nodejs npm
# Windows: Download from nodejs.org

# Verify installations
python3 --version
node --version
npm --version

# Windows: Ensure python (not python3) works
python --version
```

#### Dev Server Blocker False Positives

**Symptom:** Hook blocks legitimate commands mentioning "dev"

**Causes:**
- Heredoc content triggering pattern match
- Non-dev commands with "dev" in arguments

**Solutions:**
```bash
# This is fixed in v1.8.0+ (PR #371)
# Upgrade plugin to latest version

# Workaround: Wrap dev servers in tmux
<!-- ecc-conflict: server -->
tmux new-session -d -s dev "npm run dev"
tmux attach -t dev

# Disable hook temporarily if needed
# Edit ~/.claude/settings.json and remove pre-bash hook
```

---

### Installation & Setup

#### Plugin Not Loading

**Symptom:** Plugin features unavailable after install

**Causes:**
- Marketplace cache not updated
- Claude Code version incompatibility
- Corrupted plugin files
- Local Claude setup was wiped or reset

**Solutions:**
```bash
# First inspect what ECC still knows about this machine
ecc list-installed
ecc doctor
ecc repair

# Only reinstall if doctor/repair cannot restore the missing files

# Inspect the plugin cache before changing it
ls -la ~/.claude/plugins/cache/

# Back up the plugin cache instead of deleting it in place
mv ~/.claude/plugins/cache ~/.claude/plugins/cache.backup.$(date +%Y%m%d-%H%M%S)
mkdir -p ~/.claude/plugins/cache

# Reinstall from marketplace
# Claude Code → Extensions → ECC → Uninstall
# Then reinstall from marketplace

# If the issue is marketplace/account access, use ECC Tools billing/account recovery separately; do not use reinstall as a proxy for account recovery

# Check Claude Code version
claude --version
# Requires Claude Code 2.0+

# Manual install (if marketplace fails)
git clone https://github.com/affaan-m/ECC.git
cp -r ECC ~/.claude/plugins/ecc
```

#### Package Manager Detection Fails

**Symptom:** Wrong package manager used (npm instead of pnpm)

**Causes:**
- No lock file present
- CLAUDE_PACKAGE_MANAGER not set
- Multiple lock files confusing detection

**Solutions:**
```bash
# Set preferred package manager globally
export CLAUDE_PACKAGE_MANAGER=pnpm
# Add to ~/.bashrc or ~/.zshrc

# Or set per-project
<!-- ecc-conflict: shell-write -->
echo '{"packageManager": "pnpm"}' > .claude/package-manager.json

# Or use package.json field
npm pkg set packageManager="pnpm@8.15.0"

# Warning: removing lock files can change installed dependency versions.
# Commit or back up the lock file first, then run a fresh install and re-run CI.
# Only do this when intentionally switching package managers.
rm package-lock.json  # If using pnpm/yarn/bun
```

#### OpenCode Fails to Start on Termux/Android

**Symptom:** Changed-files tracking silently stops working (a one-time
`[ECC] changed-files tracking disabled` warning appears in the OpenCode
logs), or (on older versions) `opencode` crashes on startup entirely with a
Bun `ResolveMessage`, e.g.:

```
ResolveMessage: Cannot find module '../plugins/lib/changed-files-store.js' from '.../.opencode/tools/changed-files.ts'
```

**Causes:**
- The `~/.opencode` install is missing or incomplete for this machine —
  usually `tools/` and `plugins/` are present but `plugins/lib/` never
  finished copying (an interrupted install, or a storage/permission hiccup
  that's more common on Android's filesystem). Both the `changed-files` tool
  and the `ecc-hooks` plugin depend on `plugins/lib/changed-files-store.js`;
  since `ecc-hooks.ts` is OpenCode's plugin entry point (loaded once at
  session startup, before `tools/index.ts`'s barrel file), a missing
  dependency there used to crash the entire OpenCode session before any
  hooks could load — not just the one tool.

**Solutions:**
```bash
# From the ECC repo, check for and repair missing/incomplete managed files
ecc doctor --target opencode
ecc repair --target opencode

# If that reports no drift but plugins/ is still missing on the device,
# re-run the ECC installer for the opencode target
```

**Note:** If you're also seeing `ProviderModelNotFoundError: Model not found: openai/gpt-5.5`
referencing `~/.config/opencode/oh-my-opencode-slim.json`, that file belongs to the
third-party [`oh-my-opencode-slim`](https://github.com/alvinunreal/oh-my-opencode-slim)
plugin, not ECC — ECC never writes to `~/.config/opencode/`. Fix the model prefix
(`opencode/...` instead of `openai/...`) there, or file it against that project.

---

### Performance Issues

#### Slow Response Times

**Symptom:** Agent takes 30+ seconds to respond

**Causes:**
- Large observation files
- Too many active hooks
- Network latency to API

**Solutions:**
```bash
# Archive large observations instead of deleting them
archive_dir="<learning-state-dir>/archive/$(date +%Y%m%d)"
mkdir -p "$archive_dir"
find <learning-state-dir>/projects -name "observations.jsonl" -size +10M -exec sh -c '
  for file do
    base=$(basename "$(dirname "$file")")
    gzip -c "$file" > "'"$archive_dir"'/${base}-observations.jsonl.gz"
    : > "$file"
  done
' sh {} +

# Disable unused hooks temporarily
# Edit ~/.claude/settings.json

# Keep active observation files small
# Large archives should live under <learning-state-dir>/archive/
```

#### High CPU Usage

**Symptom:** Claude Code consuming 100% CPU

**Causes:**
- Infinite observation loops
- File watching on large directories
- Memory leaks in hooks

**Solutions:**
```bash
# Check for runaway processes
top -o cpu | grep claude

# Disable continuous learning temporarily
touch <learning-state-dir>/disabled

# Restart Claude Code
# Cmd/Ctrl+Q then reopen

# Check observation file size
du -sh <learning-state-dir>/*/
```

---

### Common Error Messages

#### "EACCES: permission denied"

```bash
# Fix hook permissions
find ~/.claude/plugins -name "*.sh" -exec chmod +x {} \;

# Fix observation directory permissions
chmod -R u+rwX,go+rX <learning-state-dir>
```

#### "MODULE_NOT_FOUND"

```bash
# Install plugin dependencies
# Replace <version> with the version from `claude plugin list`, for example 2.2.3
cd "$HOME/.claude/plugins/cache/ecc/ecc/<version>"
npm install

# Or for manual install
cd ~/.claude/plugins/ecc
npm install
```

#### "spawn UNKNOWN"

```bash
# Windows-specific: Ensure scripts use correct line endings
# Convert CRLF to LF
find ~/.claude/plugins -name "*.sh" -exec dos2unix {} \;

# Or install dos2unix
# macOS: brew install dos2unix
# Ubuntu: sudo apt install dos2unix
```

---

### Getting Help

 If you're still experiencing issues:

1. **Check GitHub Issues**: [github.com/affaan-m/ECC/issues](https://github.com/affaan-m/ECC/issues)
2. **Enable Debug Logging**:
   ```bash
   export CLAUDE_DEBUG=1
   export CLAUDE_LOG_LEVEL=debug
   ```
3. **Collect Diagnostic Info**:
   ```bash
   claude --version
   node --version
   python3 --version
   echo $CLAUDE_PACKAGE_MANAGER
   ls -la ~/.claude/plugins/cache/
   ```
4. **Open an Issue**: Include debug logs, error messages, and diagnostic info

---

### Related Documentation

- [README.md](./README.md) - Installation and features
- [CONTRIBUTING.md](./CONTRIBUTING.md) - Development guidelines
- [docs/](./docs/) - Detailed documentation
- [examples/](./examples/) - Usage examples


## Source: docs/TROUBLESHOOTING.md

## Troubleshooting

Community-reported workarounds for current Claude Code bugs that can affect ECC users.

These are upstream Claude Code behaviors, not ECC bugs. The entries below summarize the production-tested workarounds collected in [issue #644](https://github.com/affaan-m/ECC/issues/644) on Claude Code `v2.1.79` (macOS, heavy hook usage, MCP connectors enabled). Treat them as pragmatic stopgaps until upstream fixes land.

### Community Workarounds For Open Claude Code Bugs

#### False "Hook Error" labels on otherwise successful hooks

**Symptoms:** Hook runs successfully, but Claude Code still shows `Hook Error` in the transcript.

**What helps:**

- Consume stdin at the start of the hook (`input=$(cat)` in shell hooks) so the parent process does not see an unconsumed pipe.
- For simple allow/block hooks, send human-readable diagnostics to stderr and keep stdout quiet unless your hook implementation explicitly requires structured stdout.
- Redirect noisy child-process stderr when it is not actionable.
- Use the correct exit codes: `0` allows, `2` blocks, other non-zero exits are treated as errors.

**Example:**

```bash
# Good: block with stderr message and exit 2
input=$(cat)
echo "[BLOCKED] Reason here" >&2
exit 2
```

#### Earlier-than-expected compaction with `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`

**Symptoms:** Lowering `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` causes compaction to happen sooner, not later.

**What helps:**

- On some current Claude Code builds, lower values may reduce the compaction threshold instead of extending it.
- If you want more working room, remove `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` and prefer manual `/compact` at logical task boundaries.
- Use ECC's `strategic-compact` guidance instead of forcing a lower auto-compact threshold.

#### MCP connectors look connected but fail after compaction

**Symptoms:** Gmail or Google Drive MCP tools fail after compaction even though the connector still looks authenticated in the UI.

**What helps:**

- Toggle the affected connector off and back on after compaction.
- If your Claude Code build supports it, add a `PostCompact` reminder hook that warns you to re-check connector auth after compaction.
- Treat this as an auth-state recovery step, not a permanent fix.

#### Hook edits do not hot-reload

**Symptoms:** Changes to `settings.json` hooks do not take effect until the session is restarted.

**What helps:**

- Restart the Claude Code session after changing hooks.
- Advanced users sometimes script a local `/reload` command around `kill -HUP $PPID`, but ECC does not ship that because it is shell-dependent and not universally reliable.

#### Repeated `529 Overloaded` responses

**Symptoms:** Claude Code starts failing under high hook/tool/context pressure.

**What helps:**

- Reduce tool-definition pressure with `ENABLE_TOOL_SEARCH=auto:5` if your setup supports it.
- Lower the supported effort level (for example, `/effort low`) for routine work on adaptive-reasoning models. `MAX_THINKING_TOKENS=0` disables thinking; nonzero values cap fixed-budget thinking only when adaptive thinking is disabled.
- Route subagent work to a cheaper model such as `CLAUDE_CODE_SUBAGENT_MODEL=haiku` if your setup exposes that knob.
- Disable unused MCP servers per project.
- Compact manually at natural breakpoints instead of waiting for auto-compaction.

### ECC Dashboard Does Not Start

**Symptoms:** `npm run dashboard` or `python3 ecc_dashboard.py` fails, often with `ModuleNotFoundError: No module named 'tkinter'`.

**What helps:**

- The GUI dashboard needs Tkinter, which many Python installs omit:
  - Debian/Ubuntu: `sudo apt-get install python3-tk`
  - Fedora: `sudo dnf install python3-tkinter`
  - macOS (Homebrew): `brew install python-tk`
  - Windows: re-run the python.org installer and enable "tcl/tk and IDLE"
- Or use the browser dashboard, which only needs Node: `npm run dashboard:web`, then open the printed localhost URL.
- Both commands must be run from a full clone of the ECC repo (`git clone https://github.com/affaan-m/ECC`), not from inside the Claude Code plugin directory — plugin installs do not ship `package.json` scripts.

### Anthropic Cyber Safeguards Block Security Audits Of Your Own Code

**Symptoms:** Running security reviews/audits (e.g. `ecc:security-reviewer`) fails with an API error citing the Usage Policy and "cyber-related safeguards", even though you are auditing your own codebase.

**What helps:**

- This is an upstream Anthropic model-level safeguard, not GateGuard and not an ECC block. No ECC configuration can bypass it.
- Apply to Anthropic's [Cyber Verification Program](https://claude.com/form/cyber-use-case) — the error message includes a tokenized link for your account. Approved accounts get legitimate security workflows unblocked.
- Until approved, structure prompts defensively: state up front that you own the code and the goal is remediation ("review this module I own for vulnerabilities and propose fixes"), keep scope to one module at a time, and avoid exploit-generation phrasing ("write a PoC", "craft a payload").
- Prefer remediation-oriented skills (`security-review`, `security-scan`) over offensive framing, and run static tooling (semgrep, bandit, `npm audit`) yourself, then ask the model to interpret results.

### Related ECC Docs

- [hook-bug-workarounds.md](./hook-bug-workarounds.md) for the shorter hook/compaction/MCP recovery checklist.
- [hooks/README.md](../hooks/README.md) for ECC's documented hook lifecycle and exit-code behavior.
- [token-optimization.md](./token-optimization.md) for cost and context management settings.
- [issue #644](https://github.com/affaan-m/ECC/issues/644) for the original report and tested environment.


## Source: docs/fixes


<!-- file: docs/fixes/HOOK-FIX-20260421.md -->

## ECC Hook Fix — 2026-04-21

### Summary

Claude Code CLI v2.1.116 on Windows was failing all Bash tool hook invocations with:

```
PreToolUse:Bash hook error
Failed with non-blocking status code:
C:\Program Files\Git\bin\bash.exe: C:\Program Files\Git\bin\bash.exe:
cannot execute binary file

PostToolUse:Bash hook error  (同上)
```

Result: `observations.jsonl` stopped updating after `2026-04-20T23:03:38Z`
(last entry was a `parse_error` from an earlier BOM-on-stdin issue).

### Root Cause

`%USERPROFILE%\.claude\settings.local.json` had two defects:

#### Defect 1 — UTF-8 BOM + CRLF line endings

The file started with `EF BB BF` (UTF-8 BOM) and used `CRLF` line terminators.
This is the PowerShell `ConvertTo-Json | Out-File` default behavior, and it is
what `patch_settings_cl_v2_simple.ps1` leaves behind when it rewrites the file.

```
00000000: efbb bf7b 0d0a 2020 2020 2268 6f6f 6b73  ...{..    "hooks
```

#### Defect 2 — Double-wrapped bash.exe invocation

The command string explicitly re-invoked bash.exe:

```json
"command": "\"C:\\Program Files\\Git\\bin\\bash.exe\" \"%USERPROFILE%\\.claude\\skills\\continuous-learning\\hooks\\observe-wrapper.sh\""
```

When Claude Code spawns this on Windows, argument splitting does not preserve
the quoted `"C:\Program Files\..."` token correctly. The embedded space in
`Program Files` splits `argv[0]`, and `bash.exe` ends up being passed to
itself as a script file, producing:

```
bash.exe: bash.exe: cannot execute binary file
```

#### Prior working shape (for reference)

Before `patch_settings_cl_v2_simple.ps1` ran, the command was simply:

```json
"command": "%USERPROFILE%\\.claude\\skills\\continuous-learning\\hooks\\observe.sh"
```

Claude Code on Windows detects `.sh` and invokes it via Git Bash itself — no
manual `bash.exe` wrapping needed.

### Fix

`%USERPROFILE%\.claude\settings.local.json` rewritten as UTF-8 (no BOM), LF
line endings, with the command pointing directly at the wrapper `.sh` and
passing the hook phase as a plain argument:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "%USERPROFILE%/.claude/skills/continuous-learning/hooks/observe-wrapper.sh pre"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "%USERPROFILE%/.claude/skills/continuous-learning/hooks/observe-wrapper.sh post"
          }
        ]
      }
    ]
  }
}
```

Side benefit: the `pre` / `post` argument is now routed to `observe.sh`'s
`HOOK_PHASE` variable so events are correctly logged as `tool_start` vs
`tool_complete` (previously everything was recorded as `tool_complete`).

### Verification

Direct invocation of the new command format, emulating both hook phases:

```bash
# PostToolUse path
echo '{"tool_name":"Bash","tool_input":{"command":"pwd"},"session_id":"post-fix-verify-001","cwd":"...","hook_event_name":"PostToolUse"}' \
  | "%USERPROFILE%/.claude/skills/continuous-learning/hooks/observe-wrapper.sh" post
# exit=0

# PreToolUse path
echo '{"tool_name":"Bash","tool_input":{"command":"ls"},"session_id":"post-fix-verify-pre-001","cwd":"...","hook_event_name":"PreToolUse"}' \
  | "%USERPROFILE%/.claude/skills/continuous-learning/hooks/observe-wrapper.sh" pre
# exit=0
```

`observations.jsonl` gained:

```
{"timestamp":"2026-04-21T05:57:54Z","event":"tool_complete","tool":"Bash","session":"post-fix-verify-001",...}
{"timestamp":"2026-04-21T05:57:55Z","event":"tool_start","tool":"Bash","session":"post-fix-verify-pre-001","input":"{\"command\":\"ls\"}",...}
```

Both phases now produce correctly typed events.

**Note on live CLI verification:** settings changes take effect on the next
`claude` CLI session launch. Restart the CLI and run a Bash tool call to
confirm new rows appear in `observations.jsonl` from the actual CLI session.

### Files Touched

- `%USERPROFILE%\.claude\settings.local.json` — rewritten
- `%USERPROFILE%\.claude\settings.local.json.bak-hookfix-20260421-145718` — pre-fix backup

### Known Upstream Bugs (not fixed here)

- `install_hook_wrapper.ps1` — halts at step [3/4], never reaches [4/4].
- `patch_settings_cl_v2_simple.ps1` — overwrites `settings.local.json` with
  UTF-8-BOM + CRLF and re-introduces the double-wrapped `bash.exe` command.
  Should be replaced with a patcher that emits UTF-8 (no BOM), LF, and a
  direct `.sh` path.

### Branch

`claude/hook-fix-20260421`


Scripts not vendored: docs/fixes/apply-hook-fix.sh, docs/fixes/install_hook_wrapper.ps1, docs/fixes/patch_settings_cl_v2_simple.ps1


## Source: docs/hook-bug-workarounds.md

## Hook Bug Workarounds

Community-tested workarounds for current Claude Code bugs that can affect ECC hook-heavy setups.

This page is intentionally narrow: it collects the highest-signal operational fixes from the longer troubleshooting surface without repeating speculative or unsupported configuration advice. These are upstream Claude Code behaviors, not ECC bugs.

### When To Use This Page

Use this page when you are specifically debugging:

- false `Hook Error` labels on otherwise successful hook runs
- earlier-than-expected compaction
- MCP connectors that look authenticated but fail after compaction
- hook edits that do not hot-reload
- repeated `529 Overloaded` responses under heavy hook/tool pressure

For the fuller ECC troubleshooting surface, use [TROUBLESHOOTING.md](./TROUBLESHOOTING.md).

### High-Signal Workarounds

#### False `Hook Error` labels

What helps:

- Consume stdin at the start of shell hooks (`input=$(cat)`).
- Keep stdout quiet for simple allow/block hooks unless your hook explicitly requires structured stdout.
- Send human-readable diagnostics to stderr.
- Use the correct exit codes: `0` allow, `2` block, other non-zero values are treated as errors.

```bash
input=$(cat)
echo "[BLOCKED] Reason here" >&2
exit 2
```

#### Earlier-than-expected compaction

What helps:

- Remove `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` if lowering it causes earlier compaction in your build.
- Prefer manual `/compact` at natural task boundaries.
- Use ECC's `strategic-compact` guidance instead of forcing a lower threshold.

#### MCP auth looks live but fails after compaction

What helps:

- Toggle the affected connector off and back on after compaction.
- If your Claude Code build supports it, add a lightweight `PostCompact` reminder hook that tells you to re-check connector auth.
- Treat this as a recovery reminder, not a permanent fix.

#### Hook edits do not hot-reload

What helps:

- Restart the Claude Code session after changing hooks.
- Advanced users sometimes use shell-local reload helpers, but ECC does not ship one because those approaches are shell- and platform-dependent.

#### Repeated `529 Overloaded`

What helps:

- Reduce tool-definition pressure with `ENABLE_TOOL_SEARCH=auto:5` if your setup supports it.
- Lower the supported effort level (for example, `/effort low`) for routine work on adaptive-reasoning models. `MAX_THINKING_TOKENS=0` disables thinking; nonzero values cap fixed-budget thinking only when adaptive thinking is disabled.
- Route subagent work to a cheaper model such as `CLAUDE_CODE_SUBAGENT_MODEL=haiku` if your setup exposes that knob.
- Disable unused MCP servers per project.
- Compact manually at natural breakpoints instead of waiting for auto-compaction.

### Related ECC Docs

- [TROUBLESHOOTING.md](./TROUBLESHOOTING.md)
- [token-optimization.md](./token-optimization.md)
- [hooks/README.md](../hooks/README.md)
- [issue #644](https://github.com/affaan-m/ECC/issues/644)
