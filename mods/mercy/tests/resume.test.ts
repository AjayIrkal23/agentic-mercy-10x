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

describe('/mercy command', () => {
  test('status answers with features, bridge and auto-resume state', async ($, on) => {
    engine(on)
    const r = await $.command.run({ command: 'mercy', args: 'status', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 120 } })
    expect(r.text).toContain('mercy mods')
    expect(r.text).toContain('bridge:')
    expect(r.text).toContain('auto-resume')
  })
})
