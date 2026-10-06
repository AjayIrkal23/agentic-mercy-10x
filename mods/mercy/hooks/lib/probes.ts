// Pure parsers for the on-demand probes the slash commands run: listening ports
// (`ss -ltnpH` on Linux; `netstat -ano` + `tasklist` on Windows) and outdated npm packages
// (`npm outdated --json`).

import type { DepRow, PortRow } from '../../types'
import { system32 } from './os'

export type Port = PortRow
export const KNOWN: Record<number, string> = {
  3000: 'dev', 3001: 'dev', 4173: 'vite preview', 5000: 'dev', 5173: 'vite', 5432: 'postgres', 6379: 'redis', 8000: 'dev',
  8080: 'dev', 8081: 'expo', 9229: 'node inspect', 11434: 'ollama', 19000: 'expo', 27017: 'mongodb',
}

/** What to run to list listening TCP ports: ss, or both netstat tables and tasklist (pid → image name), by System32 path when `root` (SystemRoot) is known. */
export function portCmds(windows: boolean, root?: string): string[][] {
  if (!windows) return [['ss', '-ltnpH']]
  const netstat = system32(root, 'netstat.exe', 'netstat')
  return [[netstat, '-ano', '-p', 'TCP'], [netstat, '-ano', '-p', 'TCPv6'], [system32(root, 'tasklist.exe', 'tasklist'), '/FO', 'CSV', '/NH']]
}

/** One row per port, the one naming its process preferred. */
function keep(rows: Map<number, Port>, row: Port): void {
  if (KNOWN[row.port]) row.label = KNOWN[row.port]
  const had = rows.get(row.port)
  if (!had || (!had.process && row.process)) rows.set(row.port, row)
}

const sorted = (rows: Map<number, Port>): Port[] => [...rows.values()].sort((a, b) => a.port - b.port)

/** `ss -ltnpH`: one row per port, the one naming its process preferred. */
export function parsePorts(text: string): Port[] {
  const rows = new Map<number, Port>()
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
    keep(rows, row)
  }
  return sorted(rows)
}

/**
 * `netstat -ano -p TCP|TCPv6`: the listeners. Locale-proof: a row listens when its foreign address
 * is the wildcard and its last field is a PID; the state word ("LISTENING", "ABHÖREN") is never read.
 */
export function netstatRows(text: string): Array<{ port: number; address: string; pid: number }> {
  const rows: Array<{ port: number; address: string; pid: number }> = []
  for (const line of text.split(/\r?\n/)) {
    const f = line.trim().split(/\s+/)
    if (f.length < 5 || (f[2] !== '0.0.0.0:0' && f[2] !== '[::]:0')) continue
    const pid = Number(f[f.length - 1])
    const local = /^(.*):(\d+)$/.exec(f[1] ?? '')
    if (local && Number.isInteger(pid)) rows.push({ port: Number(local[2]), address: (local[1] ?? '').replace(/^\[|\]$/g, ''), pid })
  }
  return rows
}

/** `tasklist /FO CSV /NH` → pid → image name without `.exe` (quoted CSV; names may hold spaces; ASCII only is relied on). */
export function parseTasklist(csv: string): Map<number, string> {
  const names = new Map<number, string>()
  for (const line of csv.split(/\r?\n/)) {
    const m = /^"((?:[^"]|"")*)","(\d+)"/.exec(line)
    if (m) names.set(Number(m[2]), (m[1] ?? '').replace(/""/g, '"').replace(/\.exe$/i, ''))
  }
  return names
}

/** The IPv4 and IPv6 netstat tables joined with image names (the tasklist text, or names already known). */
export function parseNetstat(v4: string, v6: string, tasklist: string | ReadonlyMap<number, string>): Port[] {
  const names = typeof tasklist === 'string' ? parseTasklist(tasklist) : tasklist
  const rows = new Map<number, Port>()
  for (const r of [...netstatRows(v4), ...netstatRows(v6)]) {
    const row: Port = { port: r.port, address: r.address }
    const name = r.pid > 0 ? names.get(r.pid) : undefined
    if (name) {
      row.process = name
      row.pid = r.pid
    }
    keep(rows, row)
  }
  return sorted(rows)
}

export type Outdated = DepRow
const ORDER = { major: 0, minor: 1, patch: 2, other: 3 }

function bump(current: string | undefined, latest: string): Outdated['bump'] {
  const a = /^(\d+)\.(\d+)\.(\d+)/.exec(current ?? '')
  const b = /^(\d+)\.(\d+)\.(\d+)/.exec(latest)
  if (!a || !b) return 'other'
  return a[1] !== b[1] ? 'major' : a[2] !== b[2] ? 'minor' : 'patch'
}

/**
 * npm answered with `{"error":{code,summary,…}}` (registry unreachable, offline): no package list at all. An outdated
 * dependency that is itself named `error` has `current`/`wanted`/`latest` and is a row, not a failure (SANTA1-07).
 */
export function npmFailed(json: string): boolean {
  try {
    const error = (JSON.parse(json) as { error?: unknown }).error
    if (typeof error !== 'object' || error === null) return false
    const has = (k: string): boolean => k in error
    return (has('code') || has('summary')) && !(has('current') || has('wanted') || has('latest'))
  } catch {
    return false
  }
}

/** `npm outdated --json` (exit 1 when anything is outdated): majors first, then by name. */
export function parseOutdated(json: string): Outdated[] {
  let data: Record<string, { current?: string; wanted?: string; latest?: string }>
  try {
    data = json.trim() ? JSON.parse(json) : {}
  } catch {
    return []
  }
  if (npmFailed(json)) return []
  return Object.entries(data)
    .map(([name, v]) => ({ name, current: v.current ?? '-', wanted: v.wanted ?? '-', latest: v.latest ?? '-', bump: bump(v.current, v.latest ?? '') }))
    .sort((a, b) => ORDER[a.bump] - ORDER[b.bump] || a.name.localeCompare(b.name))
}
