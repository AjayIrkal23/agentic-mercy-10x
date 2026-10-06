// Pure shell parsing for Bash and PowerShell tool commands: words, and the real command
// past env assignments, wrappers and runners (segments: `scan.ts`). No `$` here: the
// validator follows `$` only within one file, and pure code runs in the plugin tests
// without stubs.

import { winInner, wslCommand } from './winshell'

export { splitAlternatives, splitSegments } from './scan'
export type { RawSegment } from './scan'

/** Shell-ish word split honouring quotes; the quotes are dropped from the words. */
export function words(segment: string): string[] {
  const out: string[] = []
  let cur = ''
  let has = false
  let quote: '"' | "'" | null = null
  for (const c of segment) {
    if (quote) {
      if (c === quote) quote = null
      else cur += c
      continue
    }
    if (c === '"' || c === "'") {
      quote = c
      has = true
      continue
    }
    if (/\s/.test(c)) {
      if (has || cur) out.push(cur)
      cur = ''
      has = false
      continue
    }
    cur += c
    has = true
  }
  if (has || cur) out.push(cur)
  return out
}

const ASSIGN = /^(?:\$env:)?[A-Za-z_][A-Za-z0-9_]*=/i
// `wsl` stays here for `timeoutSeconds`; `realCommand` parses its options itself (winshell.ts `wslCommand`)
const WRAPPERS = new Set(['sudo', 'env', 'time', 'nice', 'nohup', 'exec', 'command', 'stdbuf', 'ionice', 'wsl'])
const WRAPPER_VALUE_FLAGS = new Set(['-n', '-u', '-o', '-e', '-c'])
const RUNNERS = new Set(['uv', 'poetry', 'pipenv', 'hatch', 'pdm'])
// `python`, `python3.12`, `python313`, `pythonw`; and the launcher's `-3`, `-3.12`, `-3.12-32`, `-V:3.12`, `-u`
const PYTHON = /^python\d*(?:\.\d+)?w?$/
const PY_FLAG = /^-(?:\d+(?:\.\d+)?(?:-\d+)?|V:\S+|[0-9A-Za-z])$/

export function basename(word: string): string {
  const cut = Math.max(word.lastIndexOf('/'), word.lastIndexOf('\\'))
  return (cut >= 0 ? word.slice(cut + 1) : word).replace(/\.(exe|cmd|bat|com|ps1)$/i, '')
}

/** The command name as the shell finds it: no directory, no `.exe`/`.cmd`, case folded (Windows lookup ignores case). */
const head = (word: string): string => basename(word).toLowerCase()

function dropFlags(a: string[]): string[] {
  let i = 0
  while (i < a.length && (a[i] as string).startsWith('-')) i++
  return a.slice(i)
}

const SHELLS = new Set(['bash', 'sh', 'zsh', 'dash', 'ksh'])
const UNIT_S: Record<string, number> = { '': 1, s: 1, m: 60, h: 3600, d: 86400 }

/** `timeout 30 <cmd>` in front of the command (past env and wrappers): its limit in seconds. */
export function timeoutSeconds(argv: readonly string[]): number | undefined {
  let i = 0
  while (i < argv.length && (ASSIGN.test(argv[i] as string) || WRAPPERS.has(head(argv[i] as string)))) i++
  if (head(argv[i] ?? '') !== 'timeout') return undefined
  for (i++; i < argv.length && (argv[i] as string).startsWith('-'); i++) if (argv[i] === '-k' || argv[i] === '-s') i++
  const m = /^(\d+(?:\.\d+)?)([smhd]?)$/.exec(argv[i] ?? '')
  return m ? Number(m[1]) * (UNIT_S[m[2] as string] ?? 1) : undefined
}

/** The script a wrapper runs (`bash -c '<s>'`, `eval <s>`, a `( <s> )` subshell), else undefined (H-10). */
export function innerScript(text: string, argv: readonly string[]): string | undefined {
  const group = /^\(([\s\S]*)\)[^()]*$/.exec(text.trim())
  if (group) return group[1]
  const a = realCommand(argv)
  if (a[0] === 'eval') return a.slice(1).join(' ')
  const win = winInner(a)
  if (win !== undefined) return win
  if (!SHELLS.has(a[0] ?? '')) return undefined
  for (let i = 1; i < a.length && (a[i] as string).startsWith('-'); i++) {
    if (/^-[a-z]*c[a-z]*$/i.test(a[i] as string)) return a[i + 1]
  }
  return undefined
}

/** Drops env assignments, wrappers (`sudo`, `timeout 30`) and runners (`npx`, `uv run`, `python -m`); the head comes back lower-case. */
export function realCommand(argv: readonly string[]): string[] {
  let a = argv.slice()
  for (let guard = 0; guard < 8 && a.length > 0; guard++) {
    const before = a.join('\u0000')
    while (a.length > 0 && ASSIGN.test(a[0] as string)) a = a.slice(1)
    const t0 = head(a[0] ?? '')
    if (t0 === 'wsl') a = wslCommand(a)
    else if (WRAPPERS.has(t0)) {
      a = a.slice(1)
      while (a.length > 0 && ((a[0] as string).startsWith('-') || ASSIGN.test(a[0] as string))) {
        const flag = a[0] as string
        a = a.slice(1)
        if (WRAPPER_VALUE_FLAGS.has(flag) && a.length > 0) a = a.slice(1)
      }
    } else if (t0 === 'timeout') {
      a = a.slice(1)
      while (a.length > 0 && (a[0] as string).startsWith('-')) {
        const flag = a[0] as string
        a = a.slice(1)
        if ((flag === '-k' || flag === '-s') && a.length > 0) a = a.slice(1)
      }
      if (a.length > 0 && /^\d+(\.\d+)?[smhd]?$/.test(a[0] as string)) a = a.slice(1)
    } else if (t0 === 'npx' || t0 === 'bunx' || t0 === 'pnpx') {
      a = dropFlags(a.slice(1))
    } else if ((t0 === 'pnpm' || t0 === 'yarn' || t0 === 'npm') && (a[1] === 'exec' || a[1] === 'dlx')) {
      a = dropFlags(a.slice(2))
    } else if (t0 === 'bun' && a[1] === 'x') {
      a = a.slice(2)
    } else if (RUNNERS.has(t0) && a[1] === 'run') {
      a = dropFlags(a.slice(2))
    } else if (PYTHON.test(t0) || t0 === 'py') {
      let i = 1
      while (i < a.length && PY_FLAG.test(a[i] as string) && a[i] !== '-m') i++
      if (a[i] === '-m' && a[i + 1] !== undefined) a = a.slice(i + 1)
    }
    if (a.join('\u0000') === before) break
  }
  if (a.length > 0) a[0] = head(a[0] as string)
  return a
}
