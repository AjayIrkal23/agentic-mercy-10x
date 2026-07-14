<#
  install.ps1 — Windows installer for the ~/.claude workbench.

  Mirrors install.sh on Windows: copies the workspace into %USERPROFILE%\.claude
  (non-destructive, add/update only), then runs the CROSS-PLATFORM install.py
  (prereq check -> deps -> MCP servers -> plugins -> settings.json -> doctor).

  Usage (from the repo root):
      powershell -ExecutionPolicy Bypass -File .\install.ps1

  Prereqs you must install first (install.py will also report any that are missing):
      Python >= 3.10   winget install Python.Python.3.12
      Node LTS         winget install OpenJS.NodeJS.LTS
      Git              winget install Git.Git
      Claude Code CLI  npm install -g @anthropic-ai/claude-code
#>
#requires -Version 5
$ErrorActionPreference = 'Stop'

$RepoDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Target  = if ($env:CLAUDE_HOME) { $env:CLAUDE_HOME } else { Join-Path $env:USERPROFILE '.claude' }

function Say  ($m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Warn ($m) { Write-Host "  !! $m" -ForegroundColor Yellow }
function Note ($m) { Write-Host "      $m"  -ForegroundColor DarkGray }

Say "claude-workflow installer (Windows)"
Note "repo:   $RepoDir"
Note "target: $Target"

# --- resolve a Python invocation (prefer the 'py -3' launcher) ---
$Py = $null
foreach ($cand in @('py -3', 'python3', 'python')) {
    $exe = $cand.Split(' ')[0]
    if (Get-Command $exe -ErrorAction SilentlyContinue) { $Py = $cand; break }
}
if (-not $Py) {
    Warn "Python >= 3.10 not found. Install it (winget install Python.Python.3.12), reopen the shell, and re-run."
    exit 1
}
$PyParts = $Py.Split(' ')
$PyExe   = $PyParts[0]
$PyArgs0 = if ($PyParts.Length -gt 1) { $PyParts[1..($PyParts.Length - 1)] } else { @() }

# --- STEP 1: copy workspace into $Target (merge; nothing deleted) ---
$sameTarget = $false
try { $sameTarget = ((Resolve-Path $RepoDir).Path -eq (Resolve-Path $Target).Path) } catch { }
if ($sameTarget) {
    Say "workspace already at $Target (cloned in place) — nothing to copy"
} else {
    Say "copying workspace into $Target (add/update only — your extra files stay)"
    New-Item -ItemType Directory -Force -Path $Target | Out-Null
    # robocopy: /E all subdirs, /XO skip files that are older in source, quiet.
    robocopy $RepoDir $Target /E /XO /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed (exit $LASTEXITCODE)" }
    $global:LASTEXITCODE = 0
}

# --- STEP 2: run the cross-platform installer ---
Say "running install.py install"
Push-Location $Target
try {
    & $PyExe @($PyArgs0 + @('install.py', 'install'))
} finally {
    Pop-Location
}

Write-Host ""
Say "done."
Note "VISUAL installer (pick folder, live status, step-by-step):  $PyExe $($PyArgs0 -join ' ') install.py ui"
Note "check status any time:  $PyExe $($PyArgs0 -join ' ') check.py   (or: install.py verify)"
Note "claude.ai connectors (higgsfield, penpot) are added in the claude.ai Connectors UI, not the CLI."
