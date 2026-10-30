// Pure rules for the shared resume lock `state/resume-lock/<sid>`: the mod's auto-resume and
// scripts/restore_sessions.py (the OOM guard's restore) must never both resume one session.
// Python takes the lock with O_EXCL and treats it as stale after 600 s; both write
// `{"owner", "ts"}` with `ts` in SECONDS.

export const LOCK_STALE_MS = 600_000

export type LockDecision = { take: boolean; reason: 'free' | 'stale' | 'own' | 'unreadable' | `held:${string}` }

/** Free, stale, unreadable or our own lock → take it; a fresh foreign lock → yield. */
export function decideResumeLock(existing: string | undefined, nowMs: number, owner = 'mod'): LockDecision {
  if (existing === undefined) return { take: true, reason: 'free' }
  let d: unknown
  try {
    d = JSON.parse(existing)
  } catch {
    return { take: true, reason: 'unreadable' }
  }
  if (typeof d !== 'object' || d === null || Array.isArray(d)) return { take: true, reason: 'unreadable' }
  const o = d as Record<string, unknown>
  const ts = typeof o['ts'] === 'number' && Number.isFinite(o['ts']) ? o['ts'] * 1000 : 0
  if (ts <= 0 || nowMs - ts > LOCK_STALE_MS) return { take: true, reason: 'stale' }
  const holder = typeof o['owner'] === 'string' && o['owner'] ? o['owner'] : 'unknown'
  if (holder === owner) return { take: true, reason: 'own' }
  return { take: false, reason: `held:${holder}` }
}

/** The lock body this side writes. */
export function lockBody(nowMs: number, owner = 'mod'): string {
  return JSON.stringify({ owner, ts: Math.floor(nowMs / 1000) })
}

/** The mod flag body (`state/mercy-mod.active.d/<sid>.json`): Python readers use `sid` and `ts` only; a mod has no pid. */
export function flagBody(sessionId: string, nowMs: number, ended = false): string {
  return JSON.stringify({ sid: sessionId, pid: null, ts: ended ? 0 : Math.floor(nowMs / 1000) })
}
