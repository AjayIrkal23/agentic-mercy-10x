// Pure housekeeping of the plugin's $.store (4 MiB per plugin, kept across sessions):
// saved auto-resumes and per-repo brains. Run once at session start (J-10).

const HOUR = 3_600_000
const RESUME_TTL_MS = 6 * HOUR
/** A repo brain not touched for this long is dropped (its next session starts a new one). */
const REPO_TTL_MS = 90 * 24 * HOUR

/** Temp and scratch folders (e2e clones, `mktemp -d` repos): not worth remembering. */
export function isScratchRoot(root: string): boolean {
  const p = root.replace(/\\/g, '/')
  return /^\/(private\/)?(var\/)?tmp(\/|$)|^\/var\/folders\//.test(p) || /\/AppData\/Local\/Temp(\/|$)/i.test(p)
}

export type Sweep = { drop: string[]; rearmAt?: number }

/** Which keys to delete, and the time to re-arm this session's saved auto-resume (when `rearm`). */
export function sweepStore(entries: ReadonlyArray<readonly [string, unknown]>, o: { now: number; resumeKey: string; rearm: boolean }): Sweep {
  const out: Sweep = { drop: [] }
  for (const [key, value] of entries) {
    if (key.startsWith('resume')) {
      const at = (value as { at?: number } | undefined)?.at
      const fresh = at !== undefined && at > o.now - RESUME_TTL_MS
      const mine = key === o.resumeKey
      if (fresh && mine && o.rearm) out.rearmAt = Math.max(at, o.now + 5000)
      else if (!fresh || mine) out.drop.push(key)
    } else if (key.startsWith('repo:')) {
      const v = value as { root?: unknown; updatedAt?: unknown } | undefined
      const root = typeof v?.root === 'string' ? v.root : key.slice(5)
      const at = typeof v?.updatedAt === 'number' ? v.updatedAt : 0
      if (isScratchRoot(root) || at < o.now - REPO_TTL_MS) out.drop.push(key)
    }
  }
  return out
}
