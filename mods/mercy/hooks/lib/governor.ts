// Pure governor for the Python prompt router's per-prompt context. The router cannot see
// the session (A3 H5): it re-pushes skills already loaded, MCP lines for tools already
// used, first-write directives after the first write, and "/model opus" on Opus. The
// governor drops those, then de-duplicates what repeats inside a window of turns.

import { hash } from './dedupe'
import type { SeenBlocks } from './dedupe'

export const ROUTER_MARK = '<!-- prompt-router'

export type GovernorFacts = {
  turn: number
  window: number
  loadedSkills: ReadonlySet<string>
  mcpUsed: ReadonlySet<string>
  wroteCode: boolean
  onOpus: boolean
}

export type GovernorSeen = { blocks: SeenBlocks; skills: Record<string, number> }

export type GovernorResult = { text: string; seen: GovernorSeen; dropped: number; kept: number }

type Section = { header: string; lines: string[] }

/** The router's deep-inject item (router.py `[inlined skill: <name>]` + the skill body): the rest of its section. */
const INLINED = /^\[inlined skill:\s*([^\]]+)\]\s*$/i
/** router.py `_SECTION_TITLE`: inside an inlined body only these end it (the body may hold `[...]` lines of its own). */
const ROUTER_HEADER = /^\[(Critical directives|Tool precedence|Indexed symbols|Skills for this task|Suggested routing|Model)\]\s*$/

function sections(text: string): Section[] {
  const out: Section[] = []
  let cur: Section = { header: '', lines: [] }
  let inlined = false
  for (const line of text.split('\n')) {
    const t = line.trim()
    if (INLINED.test(t)) inlined = true
    else if (inlined ? ROUTER_HEADER.test(t) : /^\[[^\]]{2,60}\]\s*$/.test(t)) {
      inlined = false
      if (cur.header || cur.lines.some(l => l.trim())) out.push(cur)
      cur = { header: line.trim(), lines: [] }
      continue
    }
    cur.lines.push(line)
  }
  if (cur.header || cur.lines.some(l => l.trim())) out.push(cur)
  return out
}

type Item = { name: string; lines: string[]; must: boolean }

/**
 * Skill items: `- **name** (...)` plus the indented lines under it; lines before the first
 * item form a preamble (name ''). An inlined body is one item (`inline:<name>`) to the end,
 * blank lines and `- **bold**` lines included.
 */
function skillItems(lines: readonly string[]): Item[] {
  const items: Item[] = [{ name: '', lines: [], must: false }]
  let inlined = false
  for (const line of lines) {
    const deep = INLINED.exec(line.trim())
    const m = inlined ? null : /^\s*-\s+\*\*([^*]+)\*\*(.*)$/.exec(line)
    if (deep) inlined = true
    if (deep) items.push({ name: `inline:${(deep[1] as string).trim()}`, lines: [line], must: false })
    else if (m) items.push({ name: (m[1] as string).trim(), lines: [line], must: /\(MUST-READ\)/.test(m[2] ?? '') })
    else if (inlined || line.trim()) (items[items.length - 1] as Item).lines.push(line)
  }
  return items
}

function lineIsStale(line: string, f: GovernorFacts): boolean {
  if (f.wroteCode && /First substantive change this session/i.test(line)) return true
  if (f.mcpUsed.has('sequential-thinking') && /mcp__sequential-thinking__sequentialthinking now/.test(line)) return true
  if (f.onOpus && /consider \/model opus/i.test(line)) return true
  return false
}

/** Filters one router context string; returns '' when nothing is left worth sending. */
export function govern(text: string, f: GovernorFacts, seen: GovernorSeen): GovernorResult {
  const next: GovernorSeen = { blocks: { ...seen.blocks }, skills: { ...seen.skills } }
  let dropped = 0
  let kept = 0
  const outSections: string[] = []
  for (const s of sections(text)) {
    if (s.header === '' && s.lines.every(l => l.trim() === '' || l.trim().startsWith(ROUTER_MARK))) continue
    let body: string[]
    // Python records this turn's rank-1 MUST-READ as a hard push the Stop gate enforces:
    // never drop it as a repeat (only once the skill is loaded), nor its section (C-15)
    let mustKeep = false
    if (/Skills for this task/i.test(s.header)) {
      body = []
      for (const item of skillItems(s.lines)) {
        if (item.name === '') {
          body.push(...item.lines)
          continue
        }
        const last = next.skills[item.name]
        const recent = last !== undefined && f.turn - last < f.window && !item.must
        if (f.loadedSkills.has(item.name.replace(/^inline:/, '')) || recent) {
          dropped++
          continue
        }
        next.skills[item.name] = f.turn
        mustKeep ||= item.must
        body.push(...item.lines)
      }
    } else {
      body = s.lines.filter(l => {
        if (!lineIsStale(l, f)) return true
        dropped++
        return false
      })
    }
    const content = body.join('\n').trim()
    if (!content) continue
    const block = s.header ? `${s.header}\n${content}` : content
    const h = hash(block)
    const last = next.blocks[h]
    if (last !== undefined && f.turn - last < f.window && !mustKeep) {
      dropped++
      continue
    }
    next.blocks[h] = f.turn
    kept++
    outSections.push(block)
  }
  const head = text.trimStart().startsWith(ROUTER_MARK) ? `${text.trimStart().split('\n')[0]}\n` : ''
  return { text: outSections.length ? head + outSections.join('\n\n') : '', seen: next, dropped, kept }
}

/** Applies the governor to the router's entry of a UserPromptSubmit additionalContext list. */
export function governAll(entries: readonly string[], f: GovernorFacts, seen: GovernorSeen): { entries: string[]; seen: GovernorSeen; dropped: number } {
  let state = seen
  let dropped = 0
  const out: string[] = []
  for (const entry of entries) {
    if (!entry.includes(ROUTER_MARK)) {
      out.push(entry)
      continue
    }
    const r = govern(entry, f, state)
    state = r.seen
    dropped += r.dropped
    if (r.text.trim()) out.push(r.text)
  }
  return { entries: out, seen: state, dropped }
}
