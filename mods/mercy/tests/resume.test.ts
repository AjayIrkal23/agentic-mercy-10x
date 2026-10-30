import type { On } from 'claude-code'
import { describe, expect, mock, test } from 'claude-code/testing'

import { RESUME_PROMPT } from '../hooks/lib/resume'

const HOUR = 3_600_000

/** A quiet engine: clock, store, a usage limit that resets in one hour, and a sink for prompts. */
function engine(on: On) {
  const clock = mock.clock(on, { now: 1_000_000 })
  mock.store(on)
  mock.env(on, {})
  const resetsAt = new Date(1_000_000 + HOUR).toISOString()
  on('session.usage', () => ({ value: { startedAt: 0, context: { window: 200_000 }, rateLimits: [{ kind: 'five_hour', percentUsed: 100, resetsAt }] } }))
  on('classic.StopFailure', () => ({}))
  on('session.start', (_$, e) => ({ cwd: e.cwd }))
  const sent: string[] = []
  on('prompt.submit', (_$, e) => {
    sent.push(e.text)
    return { text: e.text }
  })
  return { clock, sent }
}

describe('auto-resume', () => {
  test('a usage-limit stop sends the resume prompt after the reset, not before', async ($, on) => {
    const { clock, sent } = engine(on)
    await $.session.start({ cwd: '/r', surface: 'terminal', isInteractive: true }) // auto-resume never runs headless
    await $.classic.StopFailure({ error: 'rate_limit' })
    await clock.advance(HOUR) // the window has reset, the 90 s grace has not passed
    expect(sent).toEqual([])
    await clock.advance(2 * 60_000)
    expect(sent).toEqual([RESUME_PROMPT])
  })
  test('typing before the reset cancels it', async ($, on) => {
    const { clock, sent } = engine(on)
    await $.session.start({ cwd: '/r', surface: 'terminal', isInteractive: true })
    await $.classic.StopFailure({ error: 'rate_limit' })
    await $.prompt.submit({ text: 'back already', wait: false, origin: { kind: 'composer' } })
    await clock.advance(2 * HOUR)
    expect(sent).toEqual(['back already'])
  })
  test("a subagent's API error never schedules one", async ($, on) => {
    const { clock, sent } = engine(on)
    await $.session.start({ cwd: '/r', surface: 'terminal', isInteractive: true })
    await $.classic.StopFailure({ error: 'overloaded', agent_id: 'agent-1' })
    await clock.advance(2 * HOUR)
    expect(sent).toEqual([])
  })
})

/** The engine above plus a file system: `files` answers fs.read/exists, `writes` records fs.write. */
function fsEngine(on: On, files: Map<string, string>) {
  const e = engine(on)
  const writes: Array<{ path: string; text: string }> = []
  const norm = (p: string) => p.replace(/\\/g, '/')
  on('fs.exists', (_$, x) => ({ value: [...files.keys()].some(k => norm(x.path).endsWith(k)) }))
  on('fs.read', (_$, x) => {
    const hit = [...files.entries()].find(([k]) => norm(x.path).endsWith(k))
    if (!hit) throw new Error('ENOENT')
    return { value: hit[1] }
  })
  on('fs.write', (_$, x) => {
    writes.push({ path: norm(x.path), text: x.text })
    for (const k of [...files.keys()]) if (norm(x.path).endsWith(k)) files.set(k, x.text)
    return { value: undefined }
  })
  const toasts: string[] = []
  on('ui.toast', (_$, x) => {
    toasts.push(x.text)
    return { value: undefined }
  })
  on('session.id', () => ({ value: 's1' }))
  on('session.repo', () => ({ value: undefined }) as never)
  on('session.end', (_$, x) => ({ sessionId: x.sessionId ?? 's1' }) as never)
  on('settings.read', () => ({ value: {} }))
  on('tool.register', () => ({ value: undefined }) as never)
  on('command.register', () => ({ value: undefined }) as never)
  on('ui.status', () => ({ value: undefined }))
  on('ui.open', () => ({ value: { isPlaced: true } }) as never)
  on('env.set', () => ({ value: undefined }) as never)
  return { ...e, writes, toasts }
}

describe('shared resume lock and mod flag', () => {
  test('a fresh python lock skips the resume prompt and toasts why', async ($, on) => {
    const files = new Map([['state/resume-lock/s1', JSON.stringify({ owner: 'python', ts: Math.floor((1_000_000 + HOUR) / 1000) })]])
    const { clock, sent, toasts } = fsEngine(on, files)
    await $.session.start({ cwd: '/r', surface: 'terminal', isInteractive: true })
    await $.classic.StopFailure({ error: 'rate_limit' })
    await clock.advance(HOUR + 2 * 60_000)
    expect(sent).toEqual([])
    expect(toasts.some(t => t.includes('resume lock'))).toBe(true)
  })
  test('a free lock is written with owner mod before the prompt', async ($, on) => {
    const { clock, sent, writes } = fsEngine(on, new Map())
    await $.session.start({ cwd: '/r', surface: 'terminal', isInteractive: true })
    await $.classic.StopFailure({ error: 'rate_limit' })
    await clock.advance(HOUR + 2 * 60_000)
    expect(sent).toEqual([RESUME_PROMPT])
    const lock = writes.find(w => w.path.endsWith('state/resume-lock/s1'))
    expect(JSON.parse(lock?.text ?? '{}').owner).toBe('mod')
  })
  test('the mod flag is written at start, every 30 s, and zeroed at session.end', async ($, on) => {
    const { clock, writes } = fsEngine(on, new Map())
    await $.session.start({ cwd: '/r', surface: 'terminal', isInteractive: true })
    const flags = () => writes.filter(w => w.path.endsWith('state/mercy-mod.active.d/s1.json'))
    expect(flags()).toHaveLength(1)
    expect(JSON.parse(flags()[0]?.text ?? '{}').sid).toBe('s1')
    await clock.advance(30_000)
    expect(flags().length).toBeGreaterThanOrEqual(2)
    await $.session.end({ sessionId: 's1', reason: 'exit' } as never)
    expect(JSON.parse(flags().at(-1)?.text ?? '{}').ts).toBe(0)
  })
  test('/clear keeps the mod-flag poller alive under the new session id; a real exit stops it', async ($, on) => {
    const { clock, writes } = fsEngine(on, new Map())
    on('classic.SessionStart', () => ({}))
    const flags = () => writes.filter(w => w.path.includes('state/mercy-mod.active.d/')).map(w => JSON.parse(w.text))
    await $.session.start({ cwd: '/r', surface: 'terminal', isInteractive: true })
    await $.session.end({ sessionId: 's1', reason: 'clear' } as never)
    expect(flags().some(f => f.ts === 0)).toBe(false) // the process goes on: no ended flag
    await $.classic.SessionStart({ source: 'clear', session_id: 's2', transcript_path: '' } as never)
    const all = flags()
    const firstS2 = all.findIndex(f => f.sid === 's2')
    const s1Ended = all.findIndex(f => f.sid === 's1' && f.ts === 0)
    expect(s1Ended).toBeGreaterThanOrEqual(0) // the old id's file goes stale at once
    expect(s1Ended).toBeLessThan(firstS2)
    expect(writes.some(w => w.path.endsWith('state/mercy-mod.active.d/s2.json'))).toBe(true)
    const before = flags().length
    await clock.advance(120_000)
    expect(flags().slice(before).filter(f => f.sid === 's2').length).toBeGreaterThanOrEqual(3)
    await $.session.end({ sessionId: 's2', reason: 'prompt_input_exit' } as never)
    expect(flags().at(-1)?.ts).toBe(0)
    const ended = flags().length
    await clock.advance(120_000)
    expect(flags().length).toBe(ended)
  })
})

describe('/mercy command', () => {
  test('status answers with features, bridge and auto-resume state', async ($, on) => {
    engine(on)
    const r = await $.command.run({ command: 'mercy', args: 'status', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 120 } })
    expect(r.text).toContain('mercy mods')
    expect(r.text).toContain('bridge:')
    expect(r.text).toContain('auto-resume')
  })
})
