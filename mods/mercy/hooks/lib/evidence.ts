// Pure: which segments of a Bash command decide its exit status. A test run counts as
// verification evidence only when its failure would fail the whole command (audit H-02,
// santa P1). Shell grammar: `|` binds tighter than `&&`/`||`, which bind tighter than
// `;`, `&` and newlines. `set -o pipefail` makes a pipeline fail when any stage fails;
// `set -e` exits on a failed list, except inside an `&&`/`||` chain before its last item.

import type { RawSegment } from './shell'
import { words } from './shell'
import { isExitForwarder } from './winshell'

type Options = { errexit: boolean; pipefail: boolean }

/** Applies one `set` command's flags (`-e`, `-eo pipefail`, `+o pipefail`, `-o errexit`). */
function applySet(argv: readonly string[], o: Options): void {
  for (let i = 1; i < argv.length; i++) {
    const m = /^([-+])([A-Za-z]+)$/.exec(argv[i] as string)
    if (!m) continue
    const on = m[1] === '-'
    for (const ch of m[2] as string) {
      if (ch === 'e') o.errexit = on
      if (ch !== 'o') continue
      const name = argv[++i]
      if (name === 'pipefail') o.pipefail = on
      if (name === 'errexit') o.errexit = on
    }
  }
}

/** The shell options in force at each segment (set by earlier `set` segments only, never by quoted text). */
function optionsAt(raw: readonly RawSegment[]): Options[] {
  const o: Options = { errexit: false, pipefail: false }
  return raw.map(seg => {
    const now = { ...o }
    const argv = words(seg.text)
    if (argv[0] === 'set') applySet(argv, o)
    return now
  })
}

// PowerShell statements that set no native exit status: cmdlets (Verb-Noun), their common
// aliases and the control-flow keywords. The ones that run something else (`iex`, jobs,
// `Start-Process`) are not here: what they run may set, hide or never report a status.
const PS_RUNS = /^(?:invoke-expression|iex|invoke-command|icm|start-process|saps|start-job|start-threadjob|invoke-item)$/i
// Verbs, not any `a-b` word: `vue-tsc`, `svelte-check` and `start-storybook` are native tools
const PS_NEUTRAL = new RegExp('^(?:(?:get|set|write|out|select|sort|where|foreach|format|tee|measure|test|new|remove|add|clear|copy|move|rename|read|' +
  'convert|convertto|convertfrom|compare|group|join|split|import|export|wait|receive|resolve|update|push|pop|enable|disable)-[a-z]+' +
  '|%|\\?|if|else|elseif|try|catch|finally|foreach|for|while|switch|select|sort|where|group|measure|tee|ft|fl|fw|echo|write|cat|gc|ls|dir|gci|sleep|cd|sl|pwd)$', 'i')

/**
 * The PowerShell tool reports the last native command's `$LASTEXITCODE`, whatever pipes or
 * cmdlets follow it (A1v2-05, measured): trailing neutral segments (`| Select-Object -Last 20`,
 * `; Write-Host done`) do not mask it, so they are left out and the segment before them is last.
 */
function nativeTail(raw: readonly RawSegment[]): RawSegment[] {
  let end = raw.length
  for (; end > 0; end--) {
    const first = /^\s*([^\s({]+)/.exec(raw[end - 1]?.text ?? '')?.[1] ?? ''
    if (PS_RUNS.test(first) || !PS_NEUTRAL.test(first)) break
  }
  return raw.slice(0, end).map((s, i) => (i === end - 1 ? { ...s, sep: '' } : s))
}

/**
 * owns[i]: a failure of segment i makes the whole command exit non-zero. A trailing
 * PowerShell `if ($LASTEXITCODE …) { exit … }` / `exit $LASTEXITCODE` forwards the status of
 * the segment before it: that segment is the last one. `powershell`: the PowerShell tool's
 * status rules (`nativeTail`); a segment past the tail owns nothing.
 */
export function exitOwners(all: readonly RawSegment[], powershell = false): boolean[] {
  const raw = powershell ? nativeTail(all) : all
  return ownersOf(raw, optionsAt(raw)).concat(all.slice(raw.length).map(() => false))
}

function ownersOf(raw: readonly RawSegment[], opts: readonly Options[]): boolean[] {
  const n = raw.length
  const forwarded = n >= 2 && raw[n - 2]?.sep === ';' && isExitForwarder(raw[n - 1]?.text ?? '')
  const sep = (k: number): string => (forwarded && k === n - 2 ? '' : raw[k]?.sep ?? '')
  return raw.map((_, i) => {
    let p = i
    while (sep(p) === '|') p++
    if (p !== i && !opts[i]?.pipefail) return false
    // the rest of i's `&&`/`||` chain: any `||` after it runs something else on failure
    let k = p
    while (sep(k) === '&&' || sep(k) === '||') {
      if (sep(k) === '||') return false
      k++
      while (sep(k) === '|') k++
    }
    if (sep(k) === '') return true
    return sep(k) === ';' && k === p && Boolean(opts[i]?.errexit)
  })
}
