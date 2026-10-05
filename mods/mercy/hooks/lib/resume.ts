// Pure auto-resume timing. When a turn dies on a usage limit ("You've hit your session
// limit · resets 5:10am (Asia/Kolkata)"), the lifecycle feature schedules a prompt that
// continues the interrupted task once the limit resets, so long tasks finish unattended.

export type RateLimit = { kind: string; percentUsed: number; resetsAt?: string }

const GRACE_MS = 90_000
const TRANSIENT_RETRY_MS = 3 * 60_000
const UNKNOWN_RETRY_MS = 30 * 60_000
const DAY_MS = 86_400_000

export const RESUME_PROMPT =
  'mercy auto-resume: the usage limit that stopped the last turn has reset. Continue the interrupted task exactly where it stopped. ' +
  'Re-read any checkpoint or progress file you were keeping, resume unfinished subagents with SendMessage instead of restarting them, and do not redo finished work.'

/** Minutes east of UTC for an IANA zone at a moment; undefined when the zone or Intl is unavailable. */
function tzOffsetMinutes(tz: string, at: number): number | undefined {
  try {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: tz, hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
    }).formatToParts(new Date(at))
    const get = (type: string): number => Number(parts.find(p => p.type === type)?.value)
    const asUtc = Date.UTC(get('year'), get('month') - 1, get('day'), get('hour'), get('minute'))
    const minutes = Math.round((asUtc - Math.floor(at / 60_000) * 60_000) / 60_000)
    return Number.isFinite(minutes) ? minutes : undefined
  } catch {
    return undefined
  }
}

/** The next moment the wall clock in `tz` (or UTC+offsetFallback) reads h:m after `now`. */
export function nextWallClock(now: number, hour: number, minute: number, offsetMinutes: number): number {
  const wall = new Date(now + offsetMinutes * 60_000)
  let at = Date.UTC(wall.getUTCFullYear(), wall.getUTCMonth(), wall.getUTCDate(), hour, minute) - offsetMinutes * 60_000
  if (at <= now) at += DAY_MS
  return at
}

const DAYS = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']
const MONTHS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
// resets [Mon | Oct 6,] [at] 5:10am [(Asia/Kolkata) | UTC | GMT+5:30]
const RESET = new RegExp(
  '\\bresets?\\s+(?:on\\s+)?(?:(sun|mon|tue|wed|thu|fri|sat)[a-z]*\\.?,?\\s+|' +
  '(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\\.?\\s+(\\d{1,2})(?:st|nd|rd|th)?,?\\s+)?' +
  '(?:at\\s+)?(\\d{1,2})(?::(\\d{2}))?\\s*(am|pm)?(?:\\s*\\(([^)]+)\\)|\\s+((?:UTC|GMT)(?:[+-]\\d{1,2}(?::?\\d{2})?)?)\\b)?', 'i')

/** Minutes east of UTC for `UTC`, `GMT+5:30`, or an IANA zone. */
function zoneOffset(zone: string, now: number): number | undefined {
  const m = /^(?:UTC|GMT|Z)(?:([+-])(\d{1,2})(?::?(\d{2}))?)?$/i.exec(zone.trim())
  if (!m) return tzOffsetMinutes(zone.trim(), now)
  return (m[1] === '-' ? -1 : 1) * (Number(m[2] ?? 0) * 60 + Number(m[3] ?? 0))
}

/** Parses "resets 5:10am (Asia/Kolkata)", "resets at 17:00", "resets Mon 5am", "resets Oct 6, 5am UTC" into an epoch ms (H-09). */
export function parseResetText(text: string, now: number, hostOffsetMinutes: number): number | undefined {
  const m = RESET.exec(text)
  if (!m) return undefined
  let hour = Number(m[4])
  const minute = Number(m[5] ?? 0)
  const ampm = m[6]?.toLowerCase()
  if (ampm === 'pm' && hour < 12) hour += 12
  if (ampm === 'am' && hour === 12) hour = 0
  if (hour > 23 || minute > 59) return undefined
  const zone = m[7] ?? m[8]
  const offset = (zone ? zoneOffset(zone, now) : undefined) ?? hostOffsetMinutes
  const wall = new Date(now + offset * 60_000)
  const today = Date.UTC(wall.getUTCFullYear(), wall.getUTCMonth(), wall.getUTCDate(), hour, minute) - offset * 60_000
  if (m[1]) {
    let at = today + ((DAYS.indexOf(m[1].toLowerCase()) - wall.getUTCDay() + 7) % 7) * DAY_MS
    if (at <= now) at += 7 * DAY_MS
    return at
  }
  if (m[2]) {
    const month = MONTHS.indexOf(m[2].toLowerCase())
    let at = Date.UTC(wall.getUTCFullYear(), month, Number(m[3]), hour, minute) - offset * 60_000
    if (at <= now) at = Date.UTC(wall.getUTCFullYear() + 1, month, Number(m[3]), hour, minute) - offset * 60_000
    // a reset is days away, never most of a year: a date already past is stale text
    return at - now <= 32 * DAY_MS ? at : undefined
  }
  return nextWallClock(now, hour, minute, offset)
}

/** Unreadable reset text is retried this many times in a row, no more (H-09). */
const MAX_GUESSES = 2

/**
 * When to resume after a turn stopped on an API error, or undefined for errors a retry
 * cannot fix. Exhausted rate-limit windows win; then the error text; then a fixed retry,
 * only while `attempts` (auto-resumes in a row) is under MAX_GUESSES.
 */
export function resumeAt(now: number, error: string, limits: readonly RateLimit[], details: string | undefined, hostOffsetMinutes: number, attempts = 0): number | undefined {
  if (error === 'overloaded' || error === 'server_error') return now + TRANSIENT_RETRY_MS
  if (error !== 'rate_limit') return undefined
  const resets = limits
    .filter(l => l.percentUsed >= 99 && l.resetsAt)
    .map(l => Date.parse(l.resetsAt as string))
    .filter(t => Number.isFinite(t) && t > now)
  if (resets.length) return Math.max(...resets) + GRACE_MS
  const parsed = parseResetText(details ?? '', now, hostOffsetMinutes)
  if (parsed !== undefined) return parsed + GRACE_MS
  return attempts < MAX_GUESSES ? now + UNKNOWN_RETRY_MS : undefined
}

export function clockLabel(at: number, offsetMinutes: number): string {
  const d = new Date(at + offsetMinutes * 60_000)
  return `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`
}
