// Pure side of the autonomous jobs (features/auto.tsx): which listening ports are dev
// servers and what changed, the local day key for the daily standup, the session summary
// saved after each turn, the auto-compact decision, and the ports/deps pane rows.

import type { Card, DepsState, Ledger, LastSession, PortRow } from '../../types'
import type { Row } from './deckviews'
import { ago, clip, usd } from './format'
import { unverified } from './ledger'

const DEV_PROCS = /^(?:node|bun|deno|python[\d.]*|uvicorn|gunicorn|next-server|vite|esbuild|php|ruby|java|go|air|cargo|dotnet)$/
const DEV_LABELS = new Set(['dev', 'vite', 'vite preview', 'expo', 'node inspect'])

/** A dev server the user runs: a known dev port, or a dev runtime on a non-system port. */
export function isDevPort(p: PortRow): boolean {
  return (p.label !== undefined && DEV_LABELS.has(p.label)) || (p.port >= 1024 && p.process !== undefined && DEV_PROCS.test(p.process) && p.process !== 'claude')
}

/** `▲ :5173 vite (node)` / `▼ :3000 dev` lines for dev servers that came up or went down. */
export function portChanges(before: readonly PortRow[] | undefined, now: readonly PortRow[]): string[] {
  if (before === undefined) return []
  const was = new Map(before.filter(isDevPort).map(p => [p.port, p]))
  const is = new Map(now.filter(isDevPort).map(p => [p.port, p]))
  const name = (p: PortRow): string => `:${p.port}${p.label ? ` ${p.label}` : ''}${p.process ? ` (${p.process})` : ''}`
  return [
    ...[...is.values()].filter(p => !was.has(p.port)).map(p => `▲ ${name(p)} is up`),
    ...[...was.values()].filter(p => !is.has(p.port)).map(p => `▼ ${name(p)} stopped`),
  ]
}

/** `2026-10-05` in the host's local time. */
export function dayKey(now: number, offsetMinutes: number): string {
  return new Date(now + offsetMinutes * 60_000).toISOString().slice(0, 10)
}

/** How far back a standup looks: the last workday (Monday → Friday, Sunday → Friday). */
export function standupDays(now: number, offsetMinutes: number): number {
  const dow = new Date(now + offsetMinutes * 60_000).getUTCDay()
  return dow === 1 ? 3 : dow === 0 ? 2 : 1
}

/** The cards map with `card` added, keeping the newest 30. */
export function withCard(all: Record<string, Card> | undefined, card: Card): Record<string, Card> {
  const kept = Object.values(all ?? {}).filter(c => c.id !== card.id).sort((a, b) => b.id - a.id).slice(0, 29)
  return Object.fromEntries([card, ...kept].map(c => [String(c.id), c]))
}

export function sessionSummary(l: Ledger, now: number, costUsd: number): LastSession {
  return {
    at: now, minutes: Math.round((now - l.startedAt) / 60_000), turns: l.turn, files: Object.keys(l.files).length,
    unverified: unverified(l).length, commands: l.commands.length, failed: l.commands.filter(c => !c.ok).length, costUsd,
  }
}

export function lastSessionLine(s: LastSession | undefined, now: number): string | undefined {
  if (!s || s.turns === 0) return undefined
  return `Previous session (${ago(now, s.at)}): ${s.minutes} min · ${s.turns} turns · ${s.files} files${s.unverified ? ` (${s.unverified} left unverified)` : ''} · ${s.commands} commands (${s.failed} failed) · ${usd(s.costUsd) || '$0.00'}`
}

/** Compact between turns: interactive, past the threshold, not again within ten minutes. */
export function shouldCompact(f: { threshold: number; contextPct: number; now: number; lastAt: number; interactive: boolean }): boolean {
  return f.interactive && f.threshold > 0 && f.contextPct >= f.threshold && f.now - f.lastAt > 600_000
}

export function portsRows(ports: readonly PortRow[] | undefined, width: number): Row[] {
  const fit = (t: string): string => clip(t, Math.max(30, width))
  if (!ports) return [{ text: 'Not scanned yet (every minute, `ss -ltnpH`).', dim: true }]
  if (!ports.length) return [{ text: 'Nothing is listening on TCP.', dim: true }]
  return ports.map(p => ({
    text: fit(`${String(p.port).padStart(5)}  ${p.address.padEnd(15)} ${(p.process ?? '-').padEnd(14)} ${p.label ?? ''}`),
    color: isDevPort(p) ? 'green' : undefined,
    dim: !isDevPort(p),
  }))
}

export function depsRows(deps: DepsState | undefined, now: number, width: number): Row[] {
  const fit = (t: string): string => clip(t, Math.max(30, width))
  if (!deps) return [{ text: 'Not checked yet (npm outdated runs once a day per package folder).', dim: true }]
  const rows: Row[] = []
  for (const d of deps.dirs) {
    const majors = d.rows.filter(r => r.bump === 'major').length
    rows.push({ text: fit(`${d.dir}: ${d.rows.length ? `${d.rows.length} outdated, ${majors} major` : 'all current'}`), bold: true, color: d.rows.length ? undefined : 'green' })
    for (const r of d.rows.slice(0, 15)) rows.push({ text: fit(`  ${r.name.padEnd(28)} ${r.current} → ${r.latest}${r.bump === 'major' ? '  major' : ''}`), color: r.bump === 'major' ? 'yellow' : undefined, dim: r.bump !== 'major' })
    if (d.rows.length > 15) rows.push({ text: `  … ${d.rows.length - 15} more`, dim: true })
  }
  rows.push({ text: `checked ${ago(now, deps.at)}`, dim: true })
  return rows
}
