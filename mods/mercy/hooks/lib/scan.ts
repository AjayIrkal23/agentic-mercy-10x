// Pure: splits a shell command into segments (`&&`, `||`, `;`, `|`, `&`, newlines, and the
// braces of PowerShell script blocks) outside quotes, `( )`, heredoc bodies and PowerShell
// here-strings. No `$` here: the validator follows `$` only within one file.

import { isExitForwarder } from './winshell'

/**
 * `sep` is the operator that ended the segment (`&&`, `||`, `;`, `|`, `&`; '' last).
 * `block`: inside a PowerShell `{ }` (script block, `if`/`try` body): scanned for servers,
 * watchers and commits, but never verify evidence (it may be detached or conditional).
 */
export type RawSegment = { text: string; background: boolean; sep: string; block?: boolean }

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
 * At `@'` / `@"` ending its line (a PowerShell here-string): the index just past the closing
 * `'@` / `"@` that starts a line, or the text end (unterminated: PowerShell refuses to run it).
 */
function hereStringEnd(s: string, i: number): number | undefined {
  const q = s[i + 1]
  if (s[i] !== '@' || (q !== "'" && q !== '"')) return undefined
  let j = i + 2
  while (s[j] === ' ' || s[j] === '\t') j++
  if (s[j] === '\r') j++
  if (s[j] !== '\n') return undefined
  for (let k = j + 1; k < s.length; ) {
    if (s[k] === q && s[k + 1] === '@') return k + 2
    const nl = s.indexOf('\n', k)
    if (nl < 0) break
    k = nl + 1
  }
  return s.length
}

const FORWARDER_SPAN = 400

/** `{` at `i` opens the body of an exit forwarder (`if ($LASTEXITCODE -ne 0) { exit 1 }`): the index of its `}`. */
function forwarderEnd(s: string, i: number, cur: string): number | undefined {
  if (cur.length > FORWARDER_SPAN || !/^\s*if\b/i.test(cur)) return undefined
  const close = s.slice(i, i + FORWARDER_SPAN).indexOf('}')
  return close >= 0 && isExitForwarder(cur + s.slice(i, i + close + 1)) ? i + close : undefined
}

/**
 * Splits on `&&`, `||`, `;`, `|`, `&` and newlines outside quotes and `( )`. Heredoc
 * bodies and here-strings are data, not commands: they are dropped (a `git commit` line
 * inside `cat > f <<'EOF'` is no commit, santa P9; an apostrophe in a `@'` body opens no
 * quote, A1v2-06). PowerShell's `"D:\p\"` (a `\"` before the end, a space or `;|&)` closes
 * the quote) is read first; if that leaves a quote open the text was bash with an escaped
 * quote, and it is split again the bash way. That first reading also splits at the braces of
 * script blocks (A1v2-02). Test-only entry (REAP-1 A1): `splitAlternatives(command)[0]`.
 */
export const splitSegments = (command: string): RawSegment[] => splitAlternatives(command)[0] as RawSegment[]

/** The `splitSegments` result, plus the strict bash split when the two quote rules disagree (two `\"` early closes can cancel out, santa P2). */
export function splitAlternatives(command: string): RawSegment[][] {
  const win = scan(command, true)
  const bash = scan(command, false).out
  return win.open || JSON.stringify(win.out) === JSON.stringify(bash) ? [win.open ? bash : win.out] : [win.out, bash]
}

function scan(command: string, winQuote: boolean): { out: RawSegment[]; open: boolean } {
  const out: RawSegment[] = []
  let cur = ''
  let quote: '"' | "'" | null = null
  let depth = 0
  let braces = 0
  let docs: Heredoc[] = []
  const push = (background: boolean, sep: string): void => {
    const text = cur.trim()
    if (text) out.push(braces > 0 ? { text, background, sep, block: true } : { text, background, sep })
    cur = ''
  }
  for (let i = 0; i < command.length; i++) {
    const c = command[i] as string
    const n = command[i + 1]
    if (quote) {
      const closes = winQuote && n === '"' && /^(?:[\s;|&)]|$)/.test(command[i + 2] ?? '')
      if (c === '\\' && quote === '"' && n !== undefined && !closes) {
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
    const here = c === '@' ? hereStringEnd(command, i) : undefined
    if (here !== undefined) {
      cur += `@${n}${n}@`
      i = here - 1
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
    if (winQuote && c === '{' && (cur === '' || /[\s)]/.test(cur.slice(-1)))) {
      const end = forwarderEnd(command, i, cur)
      if (end !== undefined) {
        cur += command.slice(i, end + 1)
        i = end
        continue
      }
      push(false, ';')
      braces++
      continue
    }
    if (winQuote && c === '}' && braces > 0) {
      push(false, ';')
      braces--
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
  return { out, open: quote !== null }
}
