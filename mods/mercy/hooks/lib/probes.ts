// Pure parsers for the on-demand probes the slash commands run: listening ports
// (`ss -ltnpH`) and outdated npm packages (`npm outdated --json`).

import type { DepRow, PortRow } from '../../types'

export type Port = PortRow
const KNOWN: Record<number, string> = {
  3000: 'dev', 3001: 'dev', 4173: 'vite preview', 5000: 'dev', 5173: 'vite', 5432: 'postgres', 6379: 'redis', 8000: 'dev',
  8080: 'dev', 8081: 'expo', 9229: 'node inspect', 11434: 'ollama', 19000: 'expo', 27017: 'mongodb',
}

/** `ss -ltnpH`: one row per port, the one naming its process preferred. */
export function parsePorts(text: string): Port[] {
  const byPort = new Map<number, Port>()
  for (const line of text.split('\n')) {
    const f = line.trim().split(/\s+/)
    const local = f[3]
    if (!local) continue
    const at = local.lastIndexOf(':')
    const port = Number(local.slice(at + 1))
    if (!Number.isInteger(port) || port <= 0) continue
    const proc = /users:\(\("([^"]+)",pid=(\d+)/.exec(line)
    const row: Port = { port, address: local.slice(0, at).replace(/^\[|\]$/g, '') }
    if (proc) {
      row.process = proc[1]
      row.pid = Number(proc[2])
    }
    if (KNOWN[port]) row.label = KNOWN[port]
    const had = byPort.get(port)
    if (!had || (!had.process && row.process)) byPort.set(port, row)
  }
  return [...byPort.values()].sort((a, b) => a.port - b.port)
}

export type Outdated = DepRow
const ORDER = { major: 0, minor: 1, patch: 2, other: 3 }

function bump(current: string | undefined, latest: string): Outdated['bump'] {
  const a = /^(\d+)\.(\d+)\.(\d+)/.exec(current ?? '')
  const b = /^(\d+)\.(\d+)\.(\d+)/.exec(latest)
  if (!a || !b) return 'other'
  return a[1] !== b[1] ? 'major' : a[2] !== b[2] ? 'minor' : 'patch'
}

/** `npm outdated --json` (exit 1 when anything is outdated): majors first, then by name. */
export function parseOutdated(json: string): Outdated[] {
  let data: Record<string, { current?: string; wanted?: string; latest?: string }>
  try {
    data = json.trim() ? JSON.parse(json) : {}
  } catch {
    return []
  }
  return Object.entries(data)
    .map(([name, v]) => ({ name, current: v.current ?? '-', wanted: v.wanted ?? '-', latest: v.latest ?? '-', bump: bump(v.current, v.latest ?? '') }))
    .sort((a, b) => ORDER[a.bump] - ORDER[b.bump] || a.name.localeCompare(b.name))
}
