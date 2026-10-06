<#
  install.ps1 - Windows entry of the ~/.claude workbench. Use install.cmd (double-click, or
  `install.cmd -Headless` / `-Ci` in a console): it runs this file with ExecutionPolicy Bypass.

  This script only gets Python >= 3.10 (reusing yours, else the pinned per-user python.org
  installer from installer\manifest.json: SHA-256 + Authenticode checked, no admin), then hands
  off to install.py. git, node, Claude Code, uv, gh and ollama are installed by Python afterwards
  (installer\wintools.py), each pinned and SHA-256 checked.
#>
#requires -Version 5
param([switch]$Headless, [switch]$Ci, [Parameter(ValueFromRemainingArguments = $true)]$Rest)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Repo = $PSScriptRoot

function Say($m)  { Write-Host "==> $m" -ForegroundColor Cyan }
function Warn($m) { Write-Host "  !! $m" -ForegroundColor Yellow }
function Stop-Install($m) { Write-Host "  xx $m" -ForegroundColor Red; exit 1 }

# before anything runs or installs: with no Python, `/ci` reached the python.org installer (SANTA2B-02)
$Unknown = @(@($Rest) | Where-Object { $_ -and $_ -notin @('--ci', '--headless') })
if ($Unknown.Count) { Stop-Install "unknown argument(s): $($Unknown -join ' ') - use -Headless or -Ci (nothing was changed)" }
if ($Repo.Length -gt 120) { Warn "this folder path is $($Repo.Length) characters long; if the install hits path errors, move the clone closer to the drive root" }
if (-not (Test-Path -LiteralPath (Join-Path $Repo 'installer\manifest.json'))) { Stop-Install 'installer\manifest.json is not next to install.ps1: run install.cmd from the repository root (nothing was changed)' }
# a zip downloaded in a browser carries Mark-of-the-Web on every file (only once this is known to be the workbench folder)
Get-ChildItem -LiteralPath $Repo -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notlike '*\.git\*' } | Unblock-File -ErrorAction SilentlyContinue

$env:NoDefaultCurrentDirectoryInExePath = '1'  # python.exe and every child skip the current directory
# -LiteralPath everywhere: a clone under `claude [work]` must not be read as a wildcard (A5v2-01)
$Pin = (Get-Content -LiteralPath (Join-Path $Repo 'installer\manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json).user_space.windows.python
# a sandboxed run (AGENTIC_MERCY_SANDBOX=1) derives the tools dir from the redirected USERPROFILE, never the real LOCALAPPDATA
$Tools = if ($env:AGENTIC_MERCY_TOOLS_DIR) { $env:AGENTIC_MERCY_TOOLS_DIR } elseif ($env:AGENTIC_MERCY_SANDBOX -eq '1') { Join-Path $env:USERPROFILE 'AppData\Local\Programs\agentic-mercy' } else { Join-Path $env:LOCALAPPDATA 'Programs\agentic-mercy' }
$InProfile = @($env:USERPROFILE, $env:LOCALAPPDATA) | Where-Object { $_ -and $Tools.TrimEnd('\').StartsWith($_.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase) }
if (-not $InProfile) { Warn "AGENTIC_MERCY_TOOLS_DIR is outside your profile ($Tools): other local users may be able to replace the tools there, and they go first on your PATH" }
$Probe = 'import sys;print(sys.version_info[0]*100+sys.version_info[1])'
$IsCi = $Ci -or (@($Rest) -contains '--ci')

function Find-Python {  # py -3, a PATH python, our own: runs, >= 3.10, never the Microsoft Store stub
    $ErrorActionPreference = 'Continue'  # Windows PowerShell 5.1 makes native stderr a terminating error under 'Stop'; judge by exit code
    foreach ($n in @('py', 'python', 'python3', (Join-Path $Tools 'python\python.exe'))) {
        $exe = if ($n -like '*\*') { if (Test-Path -LiteralPath $n -PathType Leaf) { $n } } else { (Get-Command $n -ErrorAction SilentlyContinue | Select-Object -First 1).Source }
        if (-not $exe -or $exe -like '*\WindowsApps\*') { continue }
        $pre = @(if ($n -eq 'py') { '-3' })
        try { $v = [int]("$(& $exe @pre -c $Probe 2>$null)".Trim()) } catch { continue }
        if ($LASTEXITCODE -eq 0 -and $v -ge 310) { return @{ Exe = $exe; Pre = $pre } }
    }
    return $null
}

function Install-Python {  # the pinned python.org installer: SHA-256 + Authenticode, per user, no admin
    if ($env:AGENTIC_MERCY_SANDBOX -eq '1') {  # that installer writes the real user PATH
        Stop-Install 'AGENTIC_MERCY_SANDBOX=1 and no usable Python: the python.org installer is not run in a sandbox'
    }
    $url =$Pin.url.Replace('{version}', $Pin.version).Replace('{arch}', $Pin.arch.x64)
    $exe = Join-Path $Tools ('cache\' + $url.Split('/')[-1])
    New-Item -ItemType Directory -Force -Path (Split-Path -LiteralPath $exe) | Out-Null
    Say "downloading Python $($Pin.version) (per user, no admin)"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $exe
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $exe).Hash -ne $Pin.sha256.x64) {
        Remove-Item -LiteralPath $exe -Force; Stop-Install 'Python installer SHA-256 mismatch - refused'
    }
    $sig = Get-AuthenticodeSignature -LiteralPath $exe
    if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.GetNameInfo('SimpleName', $false) -ne $Pin.signer) {
        Remove-Item -LiteralPath $exe -Force; Stop-Install "Python installer is not validly signed by $($Pin.signer) - refused"
    }
    $opts = @('/quiet', 'InstallAllUsers=0', 'PrependPath=1', 'Include_launcher=1', 'InstallLauncherAllUsers=0',
              'Include_test=0', 'Include_doc=0', 'Shortcuts=0', "TargetDir=`"$Tools\python`"")
    # PassThru + WaitForExit, not the wait switch: that one waits for the whole process tree
    $p = Start-Process -FilePath $exe -ArgumentList $opts -PassThru
    $p.WaitForExit()
    Remove-Item -LiteralPath $exe -Force -ErrorAction SilentlyContinue
    if ($p.ExitCode -ne 0) { Stop-Install "Python installer exited with code $($p.ExitCode)" }
}

Say 'claude-workflow installer (Windows)'
$Py = Find-Python
if (-not $Py -and $IsCi) { Stop-Install '-Ci plans only and never installs: no usable Python >= 3.10 here. Install Python 3.10+ yourself, or run install.cmd without -Ci' }
if (-not $Py) { Install-Python; $Py = Find-Python }
if (-not $Py) { Stop-Install 'Python >= 3.10 is still not usable; open a new terminal and run install.cmd again' }

$extra = @()
if ($Headless) { $extra += '--headless' }
if ($Ci) { $extra += '--ci' }
$extra = @($extra + @($Rest) | Where-Object { $_ } | Select-Object -Unique)
$env:PYTHONUTF8 = '1'
# install.cmd's `-ExecutionPolicy Bypass` makes PowerShell export this to every child: Python and the powershell.exe it starts keep their own policy
[Environment]::SetEnvironmentVariable('PSExecutionPolicyPreference', $null, 'Process')
& $Py.Exe @($Py.Pre) (Join-Path $Repo 'install.py') @extra
exit $LASTEXITCODE
