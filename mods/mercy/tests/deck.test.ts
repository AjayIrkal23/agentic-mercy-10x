import { describe, expect, test } from 'claude-code/testing'

import {
  applyTodo, crossed, flags, gitState, inQuietHours, overall, parsePr, parseRuns, playerArgvs, resetLabel, shouldSound, sparkCells,
} from '../hooks/lib/deck'
import { gitRows } from '../hooks/lib/deckviews'
import { parseOutdated, parsePorts } from '../hooks/lib/probes'

const OPTS = { sound: true, notify: true, paneAuto: true }

describe('modes', () => {
  test('full turns everything on; focus keeps sound and the band, toasts for failures only', () => {
    expect(flags('full', {}, OPTS)).toEqual({ status: true, band: true, paneAuto: true, toasts: 'all', sound: true, notify: true, restyle: true })
    const focus = flags('focus', {}, OPTS)
    expect([focus.band, focus.paneAuto, focus.toasts, focus.sound, focus.restyle]).toEqual([true, false, 'failures', true, false])
    expect(flags('quiet', {}, OPTS)).toMatchObject({ status: true, band: false, toasts: 'none', sound: false, notify: false })
    expect(flags('off', {}, OPTS).status).toBe(false)
  })
  test('a /ui toggle wins over the userConfig default', () => {
    expect(flags('full', { sound: false, pane: false }, OPTS)).toMatchObject({ sound: false, paneAuto: false, notify: true })
    expect(flags('full', { notify: true }, { ...OPTS, notify: false }).notify).toBe(true)
  })
})

describe('sound', () => {
  const f = flags('full', {}, OPTS)
  test('quiet hours wrap past midnight', () => {
    expect(inQuietHours('22-07', 23 * 60)).toBe(true)
    expect(inQuietHours('22-07', 6 * 60 + 59)).toBe(true)
    expect(inQuietHours('22-07', 12 * 60)).toBe(false)
    expect(inQuietHours('13:30-14:00', 13 * 60 + 45)).toBe(true)
    expect(inQuietHours('', 23 * 60)).toBe(false)
    expect(inQuietHours('nonsense', 23 * 60)).toBe(false)
  })
  test('done plays only after a long turn; every kind is throttled and muted in quiet hours', () => {
    const base = { now: 100_000, lastAt: 0, quiet: false, afterMs: 20_000 }
    expect(shouldSound('done', f, { ...base, turnMs: 5000 })).toBe(false)
    expect(shouldSound('done', f, { ...base, turnMs: 25_000 })).toBe(true)
    expect(shouldSound('input', f, base)).toBe(true)
    expect(shouldSound('input', f, { ...base, lastAt: 99_000 })).toBe(false)
    expect(shouldSound('error', f, { ...base, quiet: true })).toBe(false)
    expect(shouldSound('error', flags('quiet', {}, OPTS), base)).toBe(false)
  })
  test('players: the desktop sound theme first, then file players, then macOS', () => {
    const argvs = playerArgvs('done')
    expect(argvs[0]).toEqual(['canberra-gtk-play', '-i', 'complete', '-d', 'claude-code'])
    expect(argvs[1]).toEqual(['pw-play', '/usr/share/sounds/freedesktop/stereo/complete.oga'])
    expect(argvs.at(-1)?.[0]).toBe('afplay')
  })
})

describe('git', () => {
  const status = [
    '# branch.oid 49f60e238043727c9c1136ebb1058ea73aab8f26',
    '# branch.head main',
    '# branch.upstream origin/main',
    '# branch.ab +2 -1',
    '1 M. N... 100644 100644 100644 aaa bbb src/a.ts',
    '1 .M N... 100644 100644 100644 aaa bbb src/with space.ts',
    '2 R. N... 100644 100644 100644 aaa bbb R100 src/new.ts\tsrc/old.ts',
    'u UU N... 100644 100644 100644 100644 aaa bbb ccc src/conflict.ts',
    '? notes.md',
  ].join('\n')
  test('porcelain v2 counts, branch and per-file numstat', () => {
    const g = gitState(status, '3\t1\tsrc/a.ts\n-\t-\tsrc/with space.ts\n', 'abc1234\x1ffix: thing\x1f1700000000\n', 5)
    expect([g.branch, g.upstream, g.ahead, g.behind]).toEqual(['main', 'origin/main', 2, 1])
    expect([g.staged, g.modified, g.untracked, g.conflicts]).toEqual([2, 1, 1, 1])
    expect(g.files.find(x => x.path === 'src/a.ts')).toEqual({ path: 'src/a.ts', state: 'M', add: 3, del: 1 })
    expect(g.files.some(x => x.path === 'src/with space.ts')).toBe(true)
    expect(g.files.find(x => x.path === 'src/new.ts')?.state).toBe('R')
    expect(g.commits).toEqual([{ sha: 'abc1234', subject: 'fix: thing', at: 1_700_000_000_000 }])
    expect(g.at).toBe(5)
  })
  test('past 40 files the total still counts every change (SANTA-ui)', () => {
    const many = Array.from({ length: 100 }, (_, i) => `? f${i}.ts`).join('\n')
    const g = gitState(`# branch.head main\n${many}`, '', '', 0)
    expect([g.files.length, g.total]).toEqual([40, 100])
    expect(gitRows(g, 0, 80).some(r => r.text === '… 80 more')).toBe(true)
  })
  test('a detached head shows the short sha', () => {
    expect(gitState('# branch.oid 49f60e238043\n# branch.head (detached)\n', '', '', 0).branch).toBe('49f60e2')
  })
})

describe('ci', () => {
  test('a PR rollup: one failing check fails the whole', () => {
    const json = JSON.stringify({
      number: 12, title: 'Add export', state: 'OPEN', url: 'https://github.com/o/r/pull/12', isDraft: false, reviewDecision: 'REVIEW_REQUIRED',
      statusCheckRollup: [
        { __typename: 'CheckRun', name: 'test', status: 'COMPLETED', conclusion: 'SUCCESS', detailsUrl: 'https://x/1' },
        { __typename: 'CheckRun', name: 'lint', status: 'COMPLETED', conclusion: 'FAILURE', detailsUrl: 'https://x/2' },
        { __typename: 'CheckRun', name: 'e2e', status: 'IN_PROGRESS', conclusion: '' },
        { __typename: 'StatusContext', context: 'vercel', state: 'SUCCESS', targetUrl: 'https://x/3' },
      ],
    })
    const ci = parsePr(json, 9)
    expect(ci.source).toBe('pr')
    expect(ci.pr).toMatchObject({ number: 12, draft: false, review: 'REVIEW_REQUIRED' })
    expect(ci.checks.map(c => c.state)).toEqual(['pass', 'fail', 'pending', 'pass'])
    expect(ci.overall).toBe('fail')
  })
  test('workflow runs without a PR; empty is none', () => {
    const runs = parseRuns(JSON.stringify([{ workflowName: 'CI', status: 'completed', conclusion: 'success', url: 'https://x' }]), 1)
    expect([runs.source, runs.overall]).toEqual(['runs', 'pass'])
    expect(parseRuns('[]', 1).overall).toBe('none')
    expect(overall([{ name: 'a', state: 'pending' }, { name: 'b', state: 'pass' }])).toBe('pending')
    expect(parsePr('not json', 1).source).toBe('error')
  })
})

describe('ports and deps', () => {
  test('ss -ltnpH: port, address, process; one row per port', () => {
    const text = [
      'LISTEN 0      511          0.0.0.0:5173       0.0.0.0:*    users:(("node",pid=12345,fd=21))',
      'LISTEN 0      511             [::]:5173          [::]:*    users:(("node",pid=12345,fd=22))',
      'LISTEN 0      4096       127.0.0.1:27017      0.0.0.0:*',
    ].join('\n')
    expect(parsePorts(text)).toEqual([
      { port: 5173, address: '0.0.0.0', process: 'node', pid: 12345, label: 'vite' },
      { port: 27017, address: '127.0.0.1', label: 'mongodb' },
    ])
  })
  test('npm outdated: majors first', () => {
    const rows = parseOutdated(JSON.stringify({
      zod: { current: '3.22.0', wanted: '3.23.8', latest: '3.23.8' },
      react: { current: '18.2.0', wanted: '18.3.1', latest: '19.1.0' },
      vite: { wanted: '5.0.0', latest: '5.0.0' },
    }))
    expect(rows.map(r => [r.name, r.bump])).toEqual([['react', 'major'], ['zod', 'minor'], ['vite', 'other']])
    expect(parseOutdated('')).toEqual([])
  })
})

describe('usage', () => {
  test('crossed reports the highest mark passed this step only', () => {
    expect(crossed(60, 72, [70, 85])).toBe(70)
    expect(crossed(72, 90, [70, 85])).toBe(85)
    expect(crossed(90, 92, [70, 85])).toBeUndefined()
  })
  test('reset labels from ISO and epoch seconds', () => {
    const now = Date.UTC(2026, 9, 5, 12, 0)
    expect(resetLabel(new Date(now + 90 * 60_000).toISOString(), now, 0)).toBe('13:30 (in 1h30m)')
    expect(resetLabel(String((now + 30 * 60_000) / 1000), now, 330)).toBe('18:00 (in 30m00s)')
    expect(resetLabel(undefined, now, 0)).toBe('')
  })
  test('the sparkline is one Raster row: columns × 12 bytes, base64', () => {
    const cells = sparkCells([1, 5, 10], 3)
    expect(cells.length).toBe(Math.ceil((3 * 12) / 3) * 4)
    expect(sparkCells([], 4).length).toBe(Math.ceil((4 * 12) / 3) * 4)
  })
})

describe('todos', () => {
  test('TodoWrite replaces; TaskCreate adds by the id its result names; TaskUpdate moves or deletes', () => {
    let list = applyTodo([], 'TodoWrite', { todos: [{ content: 'a', status: 'completed', activeForm: 'A' }, { content: 'b', status: 'pending', activeForm: 'B' }] }, undefined)
    expect(list.map(t => t.status)).toEqual(['completed', 'pending'])
    list = applyTodo(list, 'TaskCreate', { subject: 'c', description: '' }, { task: { id: '7', subject: 'c' } })
    list = applyTodo(list, 'TaskUpdate', { taskId: '7', status: 'in_progress' }, undefined)
    expect(list.at(-1)).toEqual({ id: '7', text: 'c', status: 'in_progress' })
    list = applyTodo(list, 'TaskUpdate', { taskId: '7', status: 'deleted' }, undefined)
    expect(list.length).toBe(2)
  })
})
