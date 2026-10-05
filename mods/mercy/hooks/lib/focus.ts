// Pure skill-listing focus. The engine lists every enabled skill on every request
// (~134k chars, ~33k tokens here), including ~140 claude.ai business-plugin skills that
// are noise inside a code repo. Hidden families stay invocable by name or slash command.

export type FocusResult = { text: string; hidden: number }

const SKILL_LINE = /^- ([A-Za-z0-9_.-]+):([A-Za-z0-9_.:-]+): /

export function focusListing(text: string, hideFamilies: readonly string[]): FocusResult {
  if (hideFamilies.length === 0) return { text, hidden: 0 }
  const hide = new Set(hideFamilies)
  const kept: string[] = []
  const families = new Map<string, number>()
  let hidden = 0
  let skipping = false
  for (const line of text.split('\n')) {
    const m = SKILL_LINE.exec(line)
    if (m) {
      const family = m[1] as string
      skipping = hide.has(family)
      if (skipping) {
        hidden++
        families.set(family, (families.get(family) ?? 0) + 1)
        continue
      }
    } else if (skipping && line.startsWith('- ')) {
      skipping = false
    } else if (skipping) {
      continue
    }
    kept.push(line)
  }
  if (hidden === 0) return { text, hidden: 0 }
  const names = [...families.entries()].map(([f, n]) => `${f} (${n})`).join(', ')
  const note = `\n(mercy focus: ${hidden} business-plugin skills are left out of this list inside a code repo: ${names}. They still run by exact name or slash command, e.g. /${[...families.keys()][0]}:<skill>.)`
  return { text: kept.join('\n').replace(/\s+$/, '') + note, hidden }
}
