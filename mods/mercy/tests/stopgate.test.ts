import type { On } from 'claude-code'
import { describe, expect, mock, test } from 'claude-code/testing'

import { isConsent } from '../hooks/lib/consent'

/** A quiet engine whose Python Stop chain answers from `python` (B2-06). */
function engine(on: On, python: () => { block?: string } = () => ({})) {
  const clock = mock.clock(on, { now: 1_000_000 })
  mock.store(on)
  mock.env(on, {})
  on('classic.PreToolUse', () => ({}))
  on('classic.UserPromptSubmit', () => ({}))
  on('classic.Stop', () => python())
  on('session.model', () => ({ value: 'claude-sonnet-5-5' }))
  on('tool.call', (_$, e) => (e.tool === 'Bash' ? { result: 'ok' } : { result: { filePath: '/r/src/a.ts' } }) as never)
  return clock
}

describe('user consent (B2-06)', () => {
  test('the same clauses as hard-completion-gate, plus "just stop" and "skip verification"', () => {
    for (const t of ['stop', 'Stop.', 'ok, stop now', "Stop. Don't do anything else", "that's all", 'just stop', 'skip verification', 'no more changes!']) {
      expect(isConsent(t), t).toBe(true)
    }
    for (const t of ['stop the server and fix X', 'why did it stop?', 'skip verification of the logo and ship', '']) {
      expect(isConsent(t), t).toBe(false)
    }
  })
  test('a "stop" from the user is never blocked by the verify gate', async ($, on) => {
    const clock = engine(on)
    await $.tool.call({ tool: 'Bash', command: 'pnpm test' })
    await clock.advance(5000)
    await $.tool.call({ tool: 'Edit', file_path: '/r/src/a.ts', old_string: 'a', new_string: 'b' })
    await $.classic.UserPromptSubmit({ prompt: 'just stop' })
    const r = await $.classic.Stop({ stop_hook_active: false })
    expect(r.block).toBeUndefined()
  })
})

describe('one block per human turn, shared with the Python gates (B2-06)', () => {
  test('after a Python block this human turn the verify gate stays quiet; a new prompt re-arms it', async ($, on) => {
    let pythonBlocks = true
    const clock = engine(on, () => (pythonBlocks ? { block: 'hard-completion-gate: docs' } : {}))
    await $.classic.UserPromptSubmit({ prompt: 'fix the bug' })
    await $.tool.call({ tool: 'Bash', command: 'pnpm test' })
    await clock.advance(5000)
    await $.tool.call({ tool: 'Edit', file_path: '/r/src/a.ts', old_string: 'a', new_string: 'b' })
    const first = await $.classic.Stop({ stop_hook_active: false })
    expect(first.block).toContain('hard-completion-gate')
    pythonBlocks = false
    const second = await $.classic.Stop({ stop_hook_active: false })
    expect(second.block).toBeUndefined()
    await $.classic.UserPromptSubmit({ prompt: 'and the other one' })
    await $.tool.call({ tool: 'Edit', file_path: '/r/src/a.ts', old_string: 'b', new_string: 'c' })
    const third = await $.classic.Stop({ stop_hook_active: false })
    expect(third.block).toContain('pnpm test')
  })
  test('a task notification or a peer message is not a new human turn (NEW-10)', async ($, on) => {
    let pythonBlocks = true
    const clock = engine(on, () => (pythonBlocks ? { block: 'hard-completion-gate: docs' } : {}))
    await $.classic.UserPromptSubmit({ prompt: 'fix the bug' })
    await $.tool.call({ tool: 'Bash', command: 'pnpm test' })
    await clock.advance(5000)
    await $.tool.call({ tool: 'Edit', file_path: '/r/src/a.ts', old_string: 'a', new_string: 'b' })
    expect((await $.classic.Stop({ stop_hook_active: false })).block).toContain('hard-completion-gate')
    pythonBlocks = false
    // the verify gate (unverified edit) must not re-arm: no human typed these
    for (const prompt of ['<task-notification>\n<result>done</result>', '<cross-session-message from="x">ok</cross-session-message>']) {
      await $.classic.UserPromptSubmit({ prompt })
      expect((await $.classic.Stop({ stop_hook_active: false })).block, prompt).toBeUndefined()
    }
  })
})
