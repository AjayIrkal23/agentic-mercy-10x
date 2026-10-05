// Pure: which segments of a Bash command decide its exit status. A test run counts as
// verification evidence only when its failure would fail the whole command (audit H-02,
// santa P1). Shell grammar: `|` binds tighter than `&&`/`||`, which bind tighter than
// `;`, `&` and newlines. `set -o pipefail` makes a pipeline fail when any stage fails;
// `set -e` exits on a failed list, except inside an `&&`/`||` chain before its last item.

import type { RawSegment } from './shell'
import { words } from './shell'

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

/** owns[i]: a failure of segment i makes the whole command exit non-zero. */
export function exitOwners(raw: readonly RawSegment[]): boolean[] {
  const opts = optionsAt(raw)
  const sep = (k: number): string => raw[k]?.sep ?? ''
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
