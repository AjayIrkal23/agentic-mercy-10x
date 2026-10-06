import { describe, expect, test } from 'claude-code/testing'

import { dayKey, depsDue, depsRows, isDevPort, lastSessionLine, portChanges, portsRows, sessionSummary, shouldCompact, standupDays, withCard } from '../hooks/lib/auto'
import { emptyLedger, recordCommand, recordEdit } from '../hooks/lib/ledger'

describe('autonomous jobs: pure rules', () => {
  test('dev ports: known dev labels and dev runtimes on user ports; claude and system ports are not', () => {
    expect(isDevPort({ port: 5173, address: '0.0.0.0', process: 'node', label: 'vite' })).toBe(true)
    expect(isDevPort({ port: 4000, address: '127.0.0.1', process: 'bun' })).toBe(true)
    expect(isDevPort({ port: 43783, address: '127.0.0.1', process: 'claude' })).toBe(false)
    expect(isDevPort({ port: 27017, address: '127.0.0.1', label: 'mongodb' })).toBe(false)
    expect(isDevPort({ port: 631, address: '127.0.0.1', process: 'python3' })).toBe(false)
  })
  test('Windows image names are case-insensitive', () => {
    expect(isDevPort({ port: 4000, address: '::1', process: 'Node' })).toBe(true)
    expect(isDevPort({ port: 4000, address: '::1', process: 'Python' })).toBe(true)
    expect(isDevPort({ port: 3025, address: '127.0.0.1', process: 'node', pid: 1 })).toBe(true)
    expect(isDevPort({ port: 445, address: '0.0.0.0', process: 'System' })).toBe(false)
    expect(isDevPort({ port: 58572, address: '127.0.0.1', process: 'Claude' })).toBe(false)
    expect(portChanges([], [{ port: 3025, address: '127.0.0.1', process: 'Node' }])).toEqual(['▲ :3025 (Node) is up'])
  })
  test('port changes: up and down for dev servers only; the first scan is silent', () => {
    const vite = { port: 5173, address: '0.0.0.0', process: 'node', label: 'vite' }
    const mongo = { port: 27017, address: '127.0.0.1', label: 'mongodb' }
    expect(portChanges(undefined, [vite])).toEqual([])
    expect(portChanges([mongo], [mongo, vite])).toEqual(['▲ :5173 vite (node) is up'])
    expect(portChanges([vite, mongo], [mongo])).toEqual(['▼ :5173 vite (node) stopped'])
  })
  test('day key follows the local offset across midnight UTC; a Monday standup reaches back to Friday', () => {
    expect(dayKey(Date.UTC(2026, 9, 5, 20, 0), 330)).toBe('2026-10-06')
    expect(dayKey(Date.UTC(2026, 9, 5, 20, 0), 0)).toBe('2026-10-05')
    expect(standupDays(Date.UTC(2026, 9, 5, 9, 0), 0)).toBe(3) // Monday 2026-10-05
    expect(standupDays(Date.UTC(2026, 9, 6, 9, 0), 0)).toBe(1)
    expect(standupDays(Date.UTC(2026, 9, 4, 9, 0), 0)).toBe(2)
  })
  test('cards keep the newest 30 and replace by id', () => {
    const card = (id: number) => ({ id, command: 'ports', title: 't', markdown: 'm', at: id })
    let all = {}
    for (let i = 1; i <= 35; i++) all = withCard(all, card(i))
    expect(Object.keys(all).length).toBe(30)
    expect(Object.keys(withCard(all, { ...card(35), title: 'new' })).length).toBe(30)
    expect(withCard(all, { ...card(35), title: 'new' })['35']?.title).toBe('new')
  })
  test('session summary and its line', () => {
    const l = emptyLedger('s', 0)
    l.turn = 3
    recordEdit(l, '/r/src/a.ts', 10, '')
    recordCommand(l, { key: 'k', command: 'npm test', kinds: ['test'], verify: ['test'], ok: false, at: 20, ms: 5, turn: 3, agent: '' })
    const s = sessionSummary(l, 600_000, 1.5)
    expect(s).toMatchObject({ minutes: 10, turns: 3, files: 1, unverified: 1, commands: 1, failed: 1, costUsd: 1.5 })
    expect(lastSessionLine(s, 600_000 + 3_600_000)).toBe('Previous session (1h00m ago): 10 min · 3 turns · 1 files (1 left unverified) · 1 commands (1 failed) · $1.50')
    expect(lastSessionLine({ ...s, turns: 0 }, 0)).toBeUndefined()
  })
  test('auto-compact: interactive, past the threshold, at most every ten minutes, 0 = off', () => {
    const base = { threshold: 85, contextPct: 86, now: 2_000_000, lastAt: 0, interactive: true }
    expect(shouldCompact(base)).toBe(true)
    expect(shouldCompact({ ...base, contextPct: 84 })).toBe(false)
    expect(shouldCompact({ ...base, lastAt: 1_900_000 })).toBe(false)
    expect(shouldCompact({ ...base, interactive: false })).toBe(false)
    expect(shouldCompact({ ...base, threshold: 0 })).toBe(false)
  })
  test('pane rows: ports highlight dev servers; deps group by folder, majors first', () => {
    const rows = portsRows([{ port: 5173, address: '0.0.0.0', process: 'node', label: 'vite' }, { port: 27017, address: '127.0.0.1', label: 'mongodb' }], 80)
    expect(rows.map(r => r.color)).toEqual(['green', undefined])
    const deps = depsRows({ at: 1000, dirs: [{ dir: '/r', rows: [{ name: 'react', current: '18.2.0', wanted: '18.3.1', latest: '19.1.0', bump: 'major' }] }, { dir: '/r/server', rows: [] }] }, 3_601_000, 80)
    expect(deps.map(r => r.text)).toEqual(['/r: 1 outdated, 1 major', `  ${'react'.padEnd(28)} 18.2.0 → 19.1.0  major`, '/r/server: all current', 'checked 1h00m ago'])
  })
  test('npm outdated is due after a day, or after an hour when a folder could not be checked (A2v2-03)', () => {
    const full = { at: 1000, dirs: [{ dir: '/r', rows: [] }] }
    expect(depsDue(undefined, 5)).toBe(true)
    expect(depsDue(full, 1000 + 86_400_000)).toBe(false)
    expect(depsDue(full, 1001 + 86_400_000)).toBe(true)
    expect(depsDue({ ...full, partial: true }, 1000 + 3_600_000)).toBe(false)
    expect(depsDue({ ...full, partial: true }, 1001 + 3_600_000)).toBe(true)
    const rows = depsRows({ ...full, partial: true }, 3_601_000, 80).map(r => r.text)
    expect(rows.at(-1)).toBe('checked 1h00m ago · a folder could not be checked, asked again within the hour')
  })
  test('a failed port scan reads as a failure, never as "nothing is listening" or a Linux command', () => {
    const failed = portsRows(undefined, 80, 'netstat exited 1: Access is denied')
    expect(failed[0]).toMatchObject({ text: 'port scan failed: netstat exited 1: Access is denied', color: 'red' })
    expect(portsRows([], 80, 'x').some(r => r.text.includes('Nothing is listening'))).toBe(false)
    const kept = portsRows([{ port: 5173, address: '::1', process: 'node', label: 'vite' }], 80, 'tasklist timed out')
    expect(kept).toHaveLength(2)
    expect(kept[0]?.text).toBe('port scan failed: tasklist timed out')
    expect(kept[1]?.text).toContain('5173')
    expect(portsRows(undefined, 80)[0]?.text).not.toContain('ss -ltnpH')
    expect(portsRows([], 80)[0]?.text).toBe('Nothing is listening on TCP.')
  })
})
