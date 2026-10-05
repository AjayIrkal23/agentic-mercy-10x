// Pure de-duplication of hook context blocks across turns. A block the model already
// received recently is still in the transcript, so resending it word for word only
// spends tokens. Blocks resurface after `window` turns to keep their salience, and the
// memory resets after compaction or /clear, when earlier copies are gone.

export type SeenBlocks = Record<string, number> // block hash -> turn it was last sent

/** FNV-1a 32-bit over the whitespace-folded text: stable, tiny, no crypto needed. */
export function hash(text: string): string {
  const s = text.replace(/\s+/g, ' ').trim()
  let h = 0x811c9dc5
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 0x01000193) >>> 0
  }
  return h.toString(36)
}

/** Splits a context string into blocks: a `[Header]` line or a blank line starts one. */
export function blocks(text: string): string[] {
  const out: string[] = []
  let cur: string[] = []
  const flush = (): void => {
    const b = cur.join('\n').trim()
    if (b) out.push(b)
    cur = []
  }
  for (const line of text.split('\n')) {
    if (/^\s*$/.test(line)) {
      flush()
      continue
    }
    if (/^\[[^\]]{2,60}\]/.test(line) && cur.length > 0) flush()
    cur.push(line)
  }
  flush()
  return out
}

export type DedupeResult = { text: string; dropped: number; kept: number; seen: SeenBlocks }

/**
 * Drops blocks sent within the last `window` turns. Short blocks (< minChars) are kept:
 * they cost little and often carry the one live instruction.
 */
export function dedupe(text: string, seen: SeenBlocks, turn: number, window = 6, minChars = 120): DedupeResult {
  const next: SeenBlocks = { ...seen }
  const keptBlocks: string[] = []
  let dropped = 0
  for (const b of blocks(text)) {
    const h = hash(b)
    const last = next[h]
    if (b.length >= minChars && last !== undefined && turn - last < window) {
      dropped++
      continue
    }
    next[h] = turn
    keptBlocks.push(b)
  }
  return { text: keptBlocks.join('\n\n'), dropped, kept: keptBlocks.length, seen: next }
}

/** Keeps the memory bounded: forget blocks not sent for `horizon` turns. */
export function prune(seen: SeenBlocks, turn: number, horizon = 40): SeenBlocks {
  const out: SeenBlocks = {}
  for (const [h, t] of Object.entries(seen)) if (turn - t < horizon) out[h] = t
  return out
}
