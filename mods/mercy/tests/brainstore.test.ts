import type { On } from 'claude-code'
import { describe, expect, mock, test } from 'claude-code/testing'

import type { KnownCommand, RepoFacts } from '../types'
import { emptyFacts, mergeFacts } from '../hooks/lib/brain'
import { parseResetText, resumeAt } from '../hooks/lib/resume'
import { parseOptions, withErrors } from '../hooks/lib/runtime'
import { isScratchRoot, sweepStore } from '../hooks/lib/storekeys'

const DAY = 86_400_000
const cmd = (passes: number, lastAt: number): KnownCommand => ({ command: 'npm test', kind: 'test', passes, fails: 0, lastAt, lastOk: true, ms: 100 })
const facts = (patch: Partial<RepoFacts>): RepoFacts => ({ ...emptyFacts('/r', 0), ...patch })

describe('repo brain: concurrent sessions merge instead of overwriting (H-08)', () => {
  test('both sessions keep their passes, notes and session counts', () => {
    const base = facts({ commands: { 'npm test': cmd(2, 10) }, sessions: 3, notes: [{ text: 'a', at: 1 }] })
    const stored = facts({ commands: { 'npm test': cmd(4, 30) }, sessions: 4, notes: [{ text: 'a', at: 1 }, { text: 'b', at: 25 }] })
    const mine = facts({
      commands: { 'npm test': cmd(3, 20), 'npm run build': { ...cmd(1, 21), command: 'npm run build', kind: 'build' } },
      sessions: 4, notes: [{ text: 'a', at: 1 }, { text: 'c', at: 22 }],
    })
    const m = mergeFacts(stored, base, mine)
    expect(m.commands['npm test']?.passes).toBe(5)
    expect(m.commands['npm test']?.lastAt).toBe(30)
    expect(m.commands['npm run build']?.passes).toBe(1)
    expect(m.sessions).toBe(5)
    expect(m.notes.map(n => n.text)).toEqual(['a', 'c', 'b'])
  })
  test('nothing stored (forgotten, or first write): mine as is', () => {
    const mine = facts({ sessions: 1 })
    expect(mergeFacts(undefined, null, mine)).toEqual(mine)
  })
})

describe('store housekeeping (J-10)', () => {
  test('scratch roots are not repos worth a brain', () => {
    for (const r of ['/tmp/scratch/x', '/var/tmp/y', '/private/tmp/z', '/var/folders/ab/T/q', 'D:\\Profiles\\u\\AppData\\Local\\Temp\\w']) expect(isScratchRoot(r), r).toBe(true)
    for (const r of ['/repo/code/app', 'D:\\Projects\\app']) expect(isScratchRoot(r), r).toBe(false)
  })
  test('old and scratch repo keys go; fresh ones and the saved resume of this session stay', () => {
    const now = 400 * DAY
    const sweep = sweepStore([
      ['repo:/tmp/scratch/x', facts({ root: '/tmp/scratch/x', updatedAt: now })],
      ['repo:/repo/old', facts({ root: '/repo/old', updatedAt: now - 91 * DAY })],
      ['repo:/repo/fresh', facts({ root: '/repo/fresh', updatedAt: now - DAY })],
      ['resume:s1', { at: now + 60_000 }],
      ['resume:other', { at: now - 7 * 3_600_000 }],
    ], { now, resumeKey: 'resume:s1', rearm: true })
    expect(sweep.drop.sort()).toEqual(['repo:/repo/old', 'repo:/tmp/scratch/x', 'resume:other'])
    expect(sweep.rearmAt).toBe(now + 60_000)
  })
})

describe('feature health (H-06)', () => {
  test('a feature whose register threw stays marked error after session start', () => {
    expect(withErrors({ pulse: 'error', bridge: 'on' }, { pulse: 'on', bridge: 'off' })).toEqual({ pulse: 'error', bridge: 'off' })
  })
})

describe('auto-resume reset text (H-09)', () => {
  // Sunday 2026-10-04 19:35 UTC = Monday 01:05 in Asia/Kolkata (+330)
  const now = Date.UTC(2026, 9, 4, 19, 35)
  test('weekday, date, 24-hour and zone forms', () => {
    expect(parseResetText('resets Mon 5:10am (Asia/Kolkata)', now, 0)).toBe(Date.UTC(2026, 9, 4, 23, 40))
    expect(parseResetText('Weekly limit reached · resets Tue 5am', now, 330)).toBe(Date.UTC(2026, 9, 5, 23, 30))
    expect(parseResetText('resets Oct 6, 5am', now, 330)).toBe(Date.UTC(2026, 9, 5, 23, 30))
    expect(parseResetText('resets Oct 6 at 5:00am (Asia/Kolkata)', now, 0)).toBe(Date.UTC(2026, 9, 5, 23, 30))
    expect(parseResetText('resets 05:10', now, 330)).toBe(Date.UTC(2026, 9, 4, 23, 40))
    expect(parseResetText('resets 5:10am UTC', now, 330)).toBe(Date.UTC(2026, 9, 5, 5, 10))
    expect(parseResetText('resets 5:10am (UTC)', now, 330)).toBe(Date.UTC(2026, 9, 5, 5, 10))
    expect(parseResetText('resets 5:10am GMT+5:30', now, 0)).toBe(Date.UTC(2026, 9, 4, 23, 40))
  })
  test('a date already past or no time at all is not a reset time', () => {
    expect(parseResetText('resets Oct 1, 5am', now, 330)).toBeUndefined()
    expect(parseResetText('resets Mon', now, 330)).toBeUndefined()
  })
  test('an unreadable reset is retried at most twice in a row', () => {
    expect(resumeAt(now, 'rate_limit', [], 'gibberish', 0, 1)).toBe(now + 1_800_000)
    expect(resumeAt(now, 'rate_limit', [], 'gibberish', 0, 2)).toBeUndefined()
    expect(resumeAt(now, 'rate_limit', [], 'resets 5:10am (Asia/Kolkata)', 0, 5)).toBe(Date.UTC(2026, 9, 4, 23, 40) + 90_000)
  })
})

/** A session in `root` over a store the test can read and write (values copied, as the engine does). */
function world(on: On, root: string, entries: Record<string, unknown>) {
  const clock = mock.clock(on, { now: 400 * DAY })
  const store = new Map<string, string>(Object.entries(entries).map(([k, v]) => [k, JSON.stringify(v)]))
  on('store.get', (_$, e) => ({ value: store.has(e.key) ? JSON.parse(store.get(e.key) as string) : undefined }))
  on('store.set', (_$, e) => {
    store.set(e.key, JSON.stringify(e.value))
    return { value: undefined }
  })
  on('store.delete', (_$, e) => {
    store.delete(e.key)
    return { value: undefined }
  })
  on('store.keys', () => ({ value: [...store.keys()] }))
  mock.env(on, {})
  on('session.start', (_$, e) => ({ cwd: e.cwd }))
  on('session.id', () => ({ value: 's1' }))
  on('session.repo', () => ({ value: { root, remote: null } as never }))
  on('session.model', () => ({ value: 'claude-sonnet-5-5' }))
  on('settings.read', () => ({ value: {} }))
  on('fs.read', () => ({ value: '{}' }))
  on('fs.exists', () => ({ value: false }))
  on('ui.status', () => ({ value: undefined }))
  on('tool.register', () => ({ value: undefined }) as never)
  on('command.register', () => ({ value: undefined }) as never)
  on('process.run', () => ({ value: { exitCode: 0, stdout: 'main\n', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }))
  on('classic.PreToolUse', () => ({}))
  on('turn.complete', () => ({ text: '' }))
  on('tool.call', () => ({ result: 'ok' }) as never)
  return Object.assign(store, { clock })
}

const read = (store: Map<string, string>, key: string): RepoFacts => JSON.parse(store.get(key) ?? 'null') as RepoFacts

describe('brain persistence through the engine', () => {
  test('session start prunes stale and scratch repo keys (J-10)', async ($, on) => {
    const store = world(on, '/repo/app', {
      'repo:/tmp/scratch/x': facts({ root: '/tmp/scratch/x', updatedAt: 400 * DAY }),
      'repo:/repo/old': facts({ root: '/repo/old', updatedAt: 300 * DAY }),
    })
    await $.session.start({ cwd: '/repo/app', surface: 'terminal', isInteractive: false })
    expect([...store.keys()]).toEqual(['repo:/repo/app'])
  })
  test('a session in a scratch repo writes no brain (J-10)', async ($, on) => {
    const store = world(on, '/tmp/scratch/e2e', {})
    await $.session.start({ cwd: '/tmp/scratch/e2e', surface: 'terminal', isInteractive: false })
    expect([...store.keys()]).toEqual([])
  })
  test("another session's write between turns is merged, not overwritten (H-08)", async ($, on) => {
    const store = world(on, '/repo/app', { 'repo:/repo/app': facts({ root: '/repo/app', commands: { 'npm test': cmd(2, 10) }, updatedAt: 399 * DAY }) })
    await $.session.start({ cwd: '/repo/app', surface: 'terminal', isInteractive: false })
    const other = read(store, 'repo:/repo/app')
    store.set('repo:/repo/app', JSON.stringify({ ...other, commands: { 'npm test': cmd(3, 400 * DAY) }, notes: [{ text: 'from s2', at: 1 }] }))
    await store.clock.advance(1000)
    await $.tool.call({ tool: 'Bash', command: 'npm test' })
    await $.turn.complete({ reason: 'answer', answer: 'done', durationMs: 10, isAborted: false, turnId: 't1' })
    const after = read(store, 'repo:/repo/app')
    expect(after.commands['npm test']?.passes).toBe(4)
    expect(after.notes.map(n => n.text)).toEqual(['from s2'])
  })
})

describe('option defaults have one source: plugin.json (H-13)', () => {
  test("the manifest's focusHide default reaches the skill listing; the TS side keeps no second list", async ($, on) => {
    world(on, '/repo/app', {})
    on('prompt.attachment', (_$, e) => ({ text: e.text }))
    await $.session.start({ cwd: '/repo/app', surface: 'terminal', isInteractive: false })
    const listing = 'The following skills are available:\n\n- caveman: terse.\n- postiz:post: schedule.\n- small-business:ads: ads.'
    const r = await $.prompt.attachment({ type: 'skill_listing', text: listing, origin: { kind: 'engine' } })
    expect(r.text).toContain('- caveman:')
    expect(r.text).not.toContain('postiz:post')
    expect(r.text).not.toContain('small-business:ads')
    expect(parseOptions(undefined).focusHide).toEqual([])
  })
})
