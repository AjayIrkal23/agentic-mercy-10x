// Pure model of the deck UI: modes, sound rules, the git and GitHub CI parsers, usage
// marks, the Raster sparkline and the model's task list. No `$`: features/deck.tsx runs
// the processes and draws; this file decides and is unit-tested (tests/deck.test.ts).

import type { CheckState, CiCheck, CiState, GitFile, GitState, Todo, UiMode, UiPrefs } from '../../types'
import { duration } from './format'
import { clockLabel } from './resume'
import type { AlertKind, Cmd } from './winalerts'
import { windowsPlayers } from './winalerts'

export type Flags = { status: boolean; band: boolean; paneAuto: boolean; toasts: 'all' | 'failures' | 'none'; sound: boolean; notify: boolean; restyle: boolean }

/** What each UI mode turns on; a `/ui` toggle (prefs) wins over the userConfig default (o). */
export function flags(mode: UiMode, prefs: UiPrefs, o: { sound: boolean; notify: boolean; paneAuto: boolean }): Flags {
  const loud = mode === 'full' || mode === 'focus'
  return {
    status: mode !== 'off',
    band: loud,
    paneAuto: mode === 'full' && (prefs.pane ?? o.paneAuto),
    toasts: mode === 'full' ? 'all' : mode === 'focus' ? 'failures' : 'none',
    sound: loud && (prefs.sound ?? o.sound),
    notify: loud && (prefs.notify ?? o.notify),
    restyle: mode === 'full',
  }
}

/** `22-07` or `22:30-07:00`, wrapping past midnight; anything else is never quiet. */
export function inQuietHours(spec: string, minuteOfDay: number): boolean {
  const m = /^(\d{1,2})(?::(\d{2}))?-(\d{1,2})(?::(\d{2}))?$/.exec(spec.trim())
  if (!m) return false
  const from = Number(m[1]) * 60 + Number(m[2] ?? 0)
  const to = Number(m[3]) * 60 + Number(m[4] ?? 0)
  return from <= to ? minuteOfDay >= from && minuteOfDay < to : minuteOfDay >= from || minuteOfDay < to
}

export type SoundKind = AlertKind
const SOUNDS: Record<SoundKind, { id: string; file: string }> = {
  done: { id: 'complete', file: 'complete.oga' },
  error: { id: 'dialog-error', file: 'dialog-error.oga' },
  input: { id: 'message-new-instant', file: 'message-new-instant.oga' },
}

export function shouldSound(kind: SoundKind, f: Flags, s: { now: number; lastAt: number; quiet: boolean; afterMs: number; turnMs?: number }): boolean {
  if (!f.sound || s.quiet || s.now - s.lastAt < 3000) return false
  return kind !== 'done' || (s.turnMs ?? 0) >= s.afterMs
}

/** Players to try in order. Windows: PowerShell with a Media wav, then the user's SystemSounds. Elsewhere: the desktop sound theme (respects GNOME volume), file players, macOS. */
export function playerCmds(kind: SoundKind, windows: boolean, root?: string): Cmd[] {
  if (windows) return windowsPlayers(kind, root)
  const { id, file } = SOUNDS[kind]
  const path = `/usr/share/sounds/freedesktop/stereo/${file}`
  return [['canberra-gtk-play', '-i', id, '-d', 'claude-code'], ['pw-play', path], ['paplay', path], ['afplay', '/System/Library/Sounds/Glass.aiff']].map(argv => ({ argv }))
}

// ---- git -----------------------------------------------------------------------------

/** `git status --porcelain=v2 --branch` + `git diff --numstat HEAD` + `git log --format=%h%x1f%s%x1f%ct`. */
export function gitState(status: string, numstat: string, log: string, now: number): GitState {
  const g: GitState = { branch: '?', ahead: 0, behind: 0, staged: 0, modified: 0, untracked: 0, conflicts: 0, total: 0, files: [], commits: [], at: now }
  let oid = ''
  const changed: Array<{ path: string; state: string }> = []
  for (const line of status.split('\n')) {
    const f = line.split(' ')
    if (line.startsWith('# branch.oid ')) oid = f[2] ?? ''
    else if (line.startsWith('# branch.head ')) g.branch = f.slice(2).join(' ')
    else if (line.startsWith('# branch.upstream ')) g.upstream = f[2]
    else if (line.startsWith('# branch.ab ')) {
      g.ahead = Math.abs(Number(f[2]) || 0)
      g.behind = Math.abs(Number(f[3]) || 0)
    } else if (f[0] === '1' || f[0] === '2') {
      const xy = f[1] ?? '..'
      if (xy[0] !== '.') g.staged += 1
      if (xy[1] !== '.') g.modified += 1
      const path = (f[0] === '1' ? f.slice(8) : f.slice(9)).join(' ').split('\t')[0] ?? ''
      changed.push({ path, state: f[0] === '2' ? 'R' : xy[0] !== '.' ? (xy[0] ?? 'M') : (xy[1] ?? 'M') })
    } else if (f[0] === 'u') {
      g.conflicts += 1
      changed.push({ path: f.slice(10).join(' '), state: 'U' })
    } else if (f[0] === '?') {
      g.untracked += 1
      changed.push({ path: f.slice(1).join(' '), state: '?' })
    }
  }
  if (g.branch === '(detached)') g.branch = oid.slice(0, 7)
  if (/^[0-9a-f]{7,}$/.test(oid)) g.head = oid
  const counts = new Map<string, [number, number]>()
  for (const line of numstat.split('\n')) {
    const [a, d, ...rest] = line.split('\t')
    if (rest.length) counts.set(rest.join('\t'), [Number(a) || 0, Number(d) || 0])
  }
  g.total = changed.length
  g.files = changed.slice(0, 40).map((c): GitFile => ({ ...c, add: counts.get(c.path)?.[0] ?? 0, del: counts.get(c.path)?.[1] ?? 0 }))
  for (const line of log.split('\n')) {
    const [sha, subject, ct] = line.split('\x1f')
    if (sha && subject !== undefined) g.commits.push({ sha, subject, at: (Number(ct) || 0) * 1000 })
  }
  return g
}

// ---- CI (gh) -------------------------------------------------------------------------

type Rollup = { name?: string; context?: string; workflowName?: string; status?: string; conclusion?: string; state?: string; detailsUrl?: string; targetUrl?: string; url?: string }

function checkState(r: Rollup): CheckState {
  const status = (r.status ?? '').toUpperCase()
  if (status && status !== 'COMPLETED') return 'pending'
  const s = (r.conclusion || r.state || '').toUpperCase()
  if (s === 'SUCCESS') return 'pass'
  if (s === 'NEUTRAL' || s === 'SKIPPED' || s === 'STALE') return 'skip'
  if (s === '' || s === 'PENDING' || s === 'EXPECTED') return 'pending'
  return 'fail'
}

export function overall(checks: readonly CiCheck[]): CiState['overall'] {
  if (!checks.length) return 'none'
  if (checks.some(c => c.state === 'fail')) return 'fail'
  if (checks.some(c => c.state === 'pending')) return 'pending'
  return 'pass'
}

/** `gh pr view --json number,title,state,url,isDraft,reviewDecision,statusCheckRollup`. */
export function parsePr(json: string, now: number): CiState {
  try {
    const p = JSON.parse(json) as { number: number; title: string; state: string; url: string; isDraft?: boolean; reviewDecision?: string; statusCheckRollup?: Rollup[] }
    const checks = (p.statusCheckRollup ?? []).map(r => ({ name: r.name || r.context || r.workflowName || '?', state: checkState(r), url: r.detailsUrl || r.targetUrl || undefined }))
    const pr = { number: p.number, title: p.title, url: p.url, state: p.state, draft: p.isDraft === true, review: p.reviewDecision || undefined }
    return { source: 'pr', overall: overall(checks), pr, checks, at: now }
  } catch (err) {
    return { source: 'error', overall: 'none', checks: [], error: err instanceof Error ? err.message : String(err), at: now }
  }
}

/** `gh run list --branch <b> -L 5 --json workflowName,status,conclusion,url`: latest run per workflow. */
export function parseRuns(json: string, now: number): CiState {
  try {
    const seen = new Set<string>()
    const checks: CiCheck[] = []
    for (const r of JSON.parse(json) as Rollup[]) {
      const name = r.workflowName || r.name || '?'
      if (seen.has(name)) continue
      seen.add(name)
      checks.push({ name, state: checkState(r), url: r.url })
    }
    return { source: checks.length ? 'runs' : 'none', overall: overall(checks), checks, at: now }
  } catch (err) {
    return { source: 'error', overall: 'none', checks: [], error: err instanceof Error ? err.message : String(err), at: now }
  }
}

// ---- usage, todos --------------------------------------------------------------------

/** The highest mark the value passed between two readings, if any. */
export function crossed(prev: number, now: number, marks: readonly number[]): number | undefined {
  return [...marks].reverse().find(m => prev < m && now >= m)
}

/** `13:30 (in 1h30m)` from an ISO time or epoch seconds; '' when unknown. */
export function resetLabel(resetsAt: string | undefined, now: number, offsetMinutes: number): string {
  if (!resetsAt) return ''
  const at = /^\d+(\.\d+)?$/.test(resetsAt) ? Number(resetsAt) * 1000 : Date.parse(resetsAt)
  if (!Number.isFinite(at)) return ''
  return `${clockLabel(at, offsetMinutes)} (in ${duration(Math.max(0, at - now))})`
}

const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'

function base64(bytes: Uint8Array): string {
  let out = ''
  for (let i = 0; i < bytes.length; i += 3) {
    const n = ((bytes[i] ?? 0) << 16) | ((bytes[i + 1] ?? 0) << 8) | (bytes[i + 2] ?? 0)
    out += B64[(n >> 18) & 63]! + B64[(n >> 12) & 63]! + (i + 1 < bytes.length ? B64[(n >> 6) & 63]! : '=') + (i + 2 < bytes.length ? B64[n & 63]! : '=')
  }
  return out
}

/** One Raster row of block glyphs (▁..█), green → amber → red by height; the newest value at the right. */
export function sparkCells(values: readonly number[], columns: number): string {
  const tail = values.slice(-columns)
  const max = Math.max(1, ...tail)
  const view = new DataView(new ArrayBuffer(columns * 12))
  for (let c = 0; c < columns; c++) {
    const v = tail[c - (columns - tail.length)]
    const level = v === undefined ? 0 : Math.max(1, Math.round((v / max) * 8))
    const glyph = level === 0 ? 0x20 : 0x2580 + level
    const color = level <= 3 ? 0x4caf50 : level <= 6 ? 0xe0a030 : 0xe5534b
    view.setUint32(c * 12, glyph, true)
    view.setUint32(c * 12 + 4, color, true)
    view.setUint32(c * 12 + 8, 0x01000000, true)
  }
  return base64(new Uint8Array(view.buffer))
}

type TodoInput = { todos?: Array<{ content?: string; status?: string; [k: string]: unknown }>; subject?: string; taskId?: string; status?: string; [k: string]: unknown }

// `git`, `git.exe`, a quoted exe path, and the options before the subcommand (`-C <dir>`, `-c k=v`, A1v2-13)
const GIT = String.raw`\bgit(?:\.exe)?["']?\s+(?:-[cC]\s+(?:"[^"]*"|'[^']*'|\S+)\s+)*`
/** A shell command that changes what the git row shows: refresh it now instead of at the next poll. */
export const GIT_CHANGE = new RegExp(GIT + String.raw`(?:commit|checkout|switch|merge|rebase|pull|reset|stash|add|restore|push|cherry-pick|revert|fetch)\b`, 'i')
/** A push: the CI watch polls soon after. */
export const GIT_PUSH = new RegExp(GIT + String.raw`push\b`, 'i')

/** The model's own task list, from TodoWrite (whole list) or TaskCreate / TaskUpdate (one item). */
export function applyTodo(list: readonly Todo[], tool: string, input: TodoInput, result: unknown): Todo[] {
  const status = (s: string | undefined): Todo['status'] => (s === 'completed' || s === 'in_progress' ? s : 'pending')
  if (tool === 'TodoWrite') return (input.todos ?? []).map((t, i) => ({ id: `w${i}`, text: t.content ?? '', status: status(t.status) }))
  if (tool === 'TaskCreate') {
    const id = (result as { task?: { id?: string } } | undefined)?.task?.id
    return id ? [...list, { id, text: input.subject ?? '', status: 'pending' }] : [...list]
  }
  if (tool === 'TaskUpdate' && input.taskId) {
    if (input.status === 'deleted') return list.filter(t => t.id !== input.taskId)
    return list.map(t => (t.id === input.taskId ? { ...t, text: input.subject ?? t.text, status: input.status ? status(input.status) : t.status } : t))
  }
  return [...list]
}
