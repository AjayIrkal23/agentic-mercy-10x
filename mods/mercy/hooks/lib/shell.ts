// Pure shell parsing for Bash tool commands: segments, words, and the real command
// past env assignments, wrappers and runners. No `$` here: the validator follows `$`
// only within one file, and pure code runs in the plugin tests without stubs.

/** `sep` is the operator that ended the segment (`&&`, `||`, `;`, `|`, `&`; '' last). */
export type RawSegment = { text: string; background: boolean; sep: string }

type Heredoc = { delim: string; strip: boolean; end: number }

/** At `<<WORD` / `<<-'WORD'` (not `<<<`): the terminator, whether tabs are stripped, where the word ends. */
function heredocAt(s: string, i: number): Heredoc | undefined {
  if (s[i + 1] !== '<' || s[i + 2] === '<' || s[i - 1] === '<') return undefined
  let j = i + 2
  const strip = s[j] === '-'
  if (strip) j++
  while (s[j] === ' ' || s[j] === '\t') j++
  const m = /^(?:'([^'\n]*)'|"([^"\n]*)"|\\?([^\s;&|<>()'"]+))/.exec(s.slice(j))
  if (!m) return undefined
  return { delim: m[1] ?? m[2] ?? m[3] ?? '', strip, end: j + m[0].length }
}

/** The index just past the heredoc bodies that start at `from` (the line after `<<WORD`). */
function skipBodies(s: string, from: number, docs: readonly Heredoc[]): number {
  let i = from
  for (const d of docs) {
    while (i < s.length) {
      const nl = s.indexOf('\n', i)
      const line = s.slice(i, nl < 0 ? s.length : nl)
      i = nl < 0 ? s.length : nl + 1
      if ((d.strip ? line.replace(/^\t+/, '') : line) === d.delim) break
    }
  }
  return i
}

/**
 * Splits on `&&`, `||`, `;`, `|`, `&` and newlines outside quotes and `( )`. Heredoc
 * bodies are data, not commands: they are dropped (a `git commit` line inside
 * `cat > f <<'EOF'` is no commit, santa P9).
 */
export function splitSegments(command: string): RawSegment[] {
  const out: RawSegment[] = []
  let cur = ''
  let quote: '"' | "'" | null = null
  let depth = 0
  let docs: Heredoc[] = []
  const push = (background: boolean, sep: string): void => {
    const text = cur.trim()
    if (text) out.push({ text, background, sep })
    cur = ''
  }
  for (let i = 0; i < command.length; i++) {
    const c = command[i] as string
    const n = command[i + 1]
    if (quote) {
      if (c === '\\' && quote === '"' && n !== undefined) {
        cur += c + n
        i++
        continue
      }
      if (c === quote) quote = null
      cur += c
      continue
    }
    if (c === '\\' && n !== undefined) {
      cur += c + n
      i++
      continue
    }
    const doc = c === '<' ? heredocAt(command, i) : undefined
    if (doc) {
      cur += command.slice(i, doc.end)
      docs.push(doc)
      i = doc.end - 1
      continue
    }
    if (c === '\n' && docs.length) {
      const end = skipBodies(command, i + 1, docs)
      docs = []
      if (depth > 0) cur += c
      else push(false, ';')
      i = end - 1
      continue
    }
    if (c === '"' || c === "'") {
      quote = c
      cur += c
      continue
    }
    if (c === '(') depth++
    if (c === ')' && depth > 0) depth--
    if (depth > 0) {
      cur += c
      continue
    }
    if ((c === '&' && n === '&') || (c === '|' && n === '|')) {
      push(false, c + n)
      i++
      continue
    }
    // `&>file`, `2>&1`, `>&2` are redirections, not background markers
    if (c === '&' && (n === '>' || command[i - 1] === '>')) {
      cur += c
      continue
    }
    if (c === ';' || c === '\n' || c === '|') {
      push(false, c === '|' ? '|' : ';')
      continue
    }
    if (c === '&') {
      push(true, '&')
      continue
    }
    cur += c
  }
  push(false, '')
  return out
}

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

const ASSIGN = /^[A-Za-z_][A-Za-z0-9_]*=/
const WRAPPERS = new Set(['sudo', 'env', 'time', 'nice', 'nohup', 'exec', 'command', 'stdbuf', 'ionice'])
const WRAPPER_VALUE_FLAGS = new Set(['-n', '-u', '-o', '-e', '-c'])
const RUNNERS = new Set(['uv', 'poetry', 'pipenv', 'hatch', 'pdm'])

export function basename(word: string): string {
  const cut = Math.max(word.lastIndexOf('/'), word.lastIndexOf('\\'))
  return cut >= 0 ? word.slice(cut + 1) : word
}

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
  while (i < argv.length && (ASSIGN.test(argv[i] as string) || WRAPPERS.has(basename(argv[i] as string)))) i++
  if (basename(argv[i] ?? '') !== 'timeout') return undefined
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
  if (!SHELLS.has(a[0] ?? '')) return undefined
  for (let i = 1; i < a.length && (a[i] as string).startsWith('-'); i++) {
    if (/^-[a-z]*c[a-z]*$/i.test(a[i] as string)) return a[i + 1]
  }
  return undefined
}

/** Drops env assignments, wrappers (`sudo`, `timeout 30`) and runners (`npx`, `uv run`, `python -m`). */
export function realCommand(argv: readonly string[]): string[] {
  let a = argv.slice()
  for (let guard = 0; guard < 8 && a.length > 0; guard++) {
    const before = a.join('\u0000')
    while (a.length > 0 && ASSIGN.test(a[0] as string)) a = a.slice(1)
    const t0 = basename(a[0] ?? '')
    if (WRAPPERS.has(t0)) {
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
    } else if (/^python(\d(\.\d+)?)?$/.test(t0) || t0 === 'py') {
      let i = 1
      while (i < a.length && /^-[0-9A-Za-z]$/.test(a[i] as string) && a[i] !== '-m') i++
      if (a[i] === '-m' && a[i + 1] !== undefined) a = a.slice(i + 1)
    }
    if (a.join('\u0000') === before) break
  }
  if (a.length > 0) a[0] = basename(a[0] as string)
  return a
}
