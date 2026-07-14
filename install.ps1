<#
  install.ps1 — Windows launcher for the ~/.claude workbench. UI-ONLY, AUTOMATIC.

  Just finds Python and runs install-ui.py. That auto-detects ~/.claude,
  auto-relocates this clone into it, and opens the visual installer, which
  installs + repairs + re-checks in a loop until 100%. You do nothing.

  Usage (from the repo root):
      powershell -ExecutionPolicy Bypass -File .\install.ps1

  Prereqs (the installer also reports any that are missing):
      Python >= 3.10   winget install Python.Python.3.12
      Node LTS         winget install OpenJS.NodeJS.LTS
      Git              winget install Git.Git
      Claude Code CLI  npm install -g @anthropic-ai/claude-code
#>
#requires -Version 5
$ErrorActionPreference = 'Stop'

$RepoDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Say  ($m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Warn ($m) { Write-Host "  !! $m" -ForegroundColor Yellow }

Say "claude-workflow installer (Windows) — automatic, visual"

# resolve a Python invocation (prefer the 'py -3' launcher)
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

# launch the one automatic installer — it relocates into ~/.claude itself.
& $PyExe @($PyArgs0 + @((Join-Path $RepoDir 'install-ui.py')))
