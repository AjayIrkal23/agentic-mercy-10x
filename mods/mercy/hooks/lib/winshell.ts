// Pure: Windows launchers and PowerShell idioms for the command classifier. Parsed on
// every OS (the spellings are inert on Linux). `a` is a segment's argv after
// `realCommand`, so its head has no directory and no `.exe`/`.cmd`.

const PS_SWITCHES = new Set(['-noprofile', '-noninteractive', '-nologo', '-noexit', '-mta', '-sta'])
const PS_VALUED = new Set(['-executionpolicy', '-ep', '-windowstyle'])
// `/b` and, as Git Bash needs to spell it so the path rewrite leaves it alone, `//b`
const SP_SWITCHES = /^(?:\/{1,2}(?:b|wait|min|max)|-(?:nonewwindow|wait|passthru|usenewenvironment))$/
const SP_VALUED = new Set(['-workingdirectory', '-verb', '-windowstyle'])
// Only status-preserving forms (SANTA1-02): `exit $LASTEXITCODE`, or a failure test that exits non-zero.
// `{ exit 0 }`, `-eq 0 { exit 1 }` and `if ($?) { … }` swallow or invert the failure. No `.*`: linear (SEC1-07).
const FORWARDER = /^(?:if\s*\(\s*(?:\$LASTEXITCODE\s+-ne\s+0|-not\s+\$\?|!\s*\$\?)\s*\)\s*\{\s*exit\s+(?:-?[1-9]\d*|\$LASTEXITCODE)\s*\}|exit\s+\$LASTEXITCODE)$/i
const FORWARDER_MAX = 400

/** `powershell [-NoProfile -ExecutionPolicy X] -c <script>`: the script (PowerShell joins what follows). */
function psScript(a: readonly string[]): string | undefined {
  for (let i = 1; i < a.length; i++) {
    const f = (a[i] as string).toLowerCase()
    if (PS_SWITCHES.has(f)) continue
    if (PS_VALUED.has(f)) i++
    else if (f === '-c' || f === '-command') return a.slice(i + 1).join(' ')
    else if (f.startsWith('-')) return undefined // -File, -EncodedCommand, ...
    else return a.slice(i).join(' ') // -Command is the default parameter
  }
  return undefined
}

/** `Start-Process [-FilePath] f [-ArgumentList a,b]` and cmd's `start [/b] f args`: `f a b`. */
function startScript(a: readonly string[]): string {
  let file: string | undefined
  const args: string[] = []
  for (let i = 1; i < a.length; i++) {
    const w = a[i] as string
    const f = w.toLowerCase()
    if (f === '-filepath') file = a[++i]
    else if (f === '-argumentlist') {
      let v = a[++i] ?? ''
      while (v.endsWith(',') && i + 1 < a.length) v += a[++i]
      args.push(...v.split(',').filter(Boolean))
    } else if (SP_VALUED.has(f)) i++
    else if (SP_SWITCHES.test(f)) continue
    else if (file === undefined) file = w
    else args.push(w)
  }
  return [file ?? '', ...args].join(' ')
}

const LAUNCHERS = new Set(['start-process', 'start', 'saps'])

/** `Start-Process`, `saps`, cmd's `start`: the command runs detached, its status never reaches the tool (A1v2-01). */
export function isLauncher(a: readonly string[]): boolean {
  return LAUNCHERS.has((a[0] ?? '').toLowerCase())
}

/** The script a Windows wrapper runs (`cmd /c`, `powershell -c`, `Start-Process`, `iex`), else undefined. */
export function winInner(a: readonly string[]): string | undefined {
  const t0 = (a[0] ?? '').toLowerCase()
  if (t0 === 'cmd') {
    // `//c` is how Git Bash passes `/c` (it would rewrite a lone `/c` into a drive path)
    const i = a.findIndex((x, j) => j > 0 && /^\/{1,2}[ck]$/i.test(x))
    return i < 0 ? undefined : a.slice(i + 1).join(' ')
  }
  if (t0 === 'iex' || t0 === 'invoke-expression') return a.slice(1).join(' ')
  if (t0 === 'powershell' || t0 === 'pwsh') return psScript(a)
  if (isLauncher(a)) return startScript(a)
  return undefined
}

/** `if ($LASTEXITCODE -ne 0) { exit 1 }` or `exit $LASTEXITCODE`: passes on the status of the command before it. */
export function isExitForwarder(text: string): boolean {
  return text.length <= FORWARDER_MAX && FORWARDER.test(text.trim())
}

const WSL_VALUED = new Set(['-d', '--distribution', '-u', '--user', '--cd'])

/** `wsl [-d distro] [-u user] [--cd dir] [-e|--exec|--] cmd args`: the Linux command (`-e`, `--exec`, `--` end the options). */
export function wslCommand(a: readonly string[]): string[] {
  for (let i = 1; i < a.length; i++) {
    const w = a[i] as string
    if (w === '-e' || w === '--exec' || w === '--') return a.slice(i + 1)
    if (!w.startsWith('-')) return a.slice(i)
    if (WSL_VALUED.has(w)) i++
  }
  return []
}
