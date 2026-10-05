import type { On } from 'claude-code'
import { describe, expect, mock, test } from 'claude-code/testing'

/** The engine beneath the plugin: a clock, quiet classic chains, a tool that answers. */
function engine(on: On, answer: (e: { tool: string; command?: unknown }) => unknown = () => ({ result: 'ok' })) {
  const clock = mock.clock(on, { now: 1_000_000 })
  mock.store(on)
  mock.env(on, {})
  on('classic.PreToolUse', () => ({}))
  on('classic.PostToolUse', () => ({}))
  on('session.model', () => ({ value: 'claude-sonnet-5-5' }))
  on('tool.call', (_$, e) => answer(e as { tool: string; command?: unknown }) as never)
  return clock
}

describe('guard through tool.call', () => {
  test('a dev server is denied before it runs', async ($, on) => {
    let ran = false
    engine(on, () => {
      ran = true
      return { result: 'started' }
    })
    const r = await $.tool.call({ tool: 'Bash', command: 'npm run dev' })
    expect(r.deny).toContain('dev server')
    expect(ran).toBe(false)
  })
  test('a live-looking secret is denied only where git would track it; a fixture value passes', async ($, on) => {
    engine(on)
    on('fs.exists', () => ({ value: true }))
    // git check-ignore: 1 = in a repo and not ignored, 128 = not in a repo
    const exitCode = (argv: readonly string[]): number => (argv.some(a => a.includes('/.aws/')) ? 128 : 1)
    const seen: string[][] = []
    on('process.run', (_$, e) => {
      seen.push([...e.argv])
      return { value: { exitCode: exitCode(e.argv), stdout: '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    })
    const key = 'AKIA' + 'ABCDEFGHIJKLMNOP'
    const bad = await $.tool.call({ tool: 'Write', file_path: '/r/src/config.ts', content: `export const key = "${key}"` })
    expect(bad.deny).toContain('AWS access key')
    // a repo owned by another OS user must not read as "no repo" (git exits 128 there too)
    expect(seen[0]).toContain('safe.directory=*')
    const ok = await $.tool.call({ tool: 'Write', file_path: '/r/src/config.ts', content: 'export const key = "AKIAIOSFODNN7EXAMPLE"' })
    expect(ok.deny).toBeUndefined()
    const outside = await $.tool.call({ tool: 'Write', file_path: '/u/.aws/credentials', content: `aws_access_key_id = ${key}` })
    expect(outside.deny).toBeUndefined()
  })
  test('the third identical failure carries a root-cause nudge', async ($, on) => {
    const clock = engine(on, () => ({ isError: true, result: 'Error: x', text: 'FAILED tests/a.py::test_x - AssertionError' }))
    let last: { context?: readonly string[] } = {}
    for (let i = 0; i < 3; i++) {
      last = await $.tool.call({ tool: 'Bash', command: 'pytest -q' })
      await clock.advance(1000)
    }
    expect((last.context ?? []).join('\n')).toContain('failed 3 times in a row')
  })
})

describe('verification gate at Stop', () => {
  test('blocks once when code changed after the last passing test', async ($, on) => {
    const clock = engine(on, e => (e.tool === 'Bash' ? { result: 'ok', text: '12 passed' } : { result: { filePath: '/r/src/a.ts' } }))
    on('classic.Stop', () => ({}))
    await $.tool.call({ tool: 'Bash', command: 'pnpm test' })
    await clock.advance(5000)
    await $.tool.call({ tool: 'Edit', file_path: '/r/src/a.ts', old_string: 'a', new_string: 'b' })
    const first = await $.classic.Stop({ stop_hook_active: false })
    expect(first.block).toContain('pnpm test')
    const again = await $.classic.Stop({ stop_hook_active: false })
    expect(again.block).toBeUndefined()
  })
  test('a test run started in the background is not evidence', async ($, on) => {
    const clock = engine(on, e => (e.tool === 'Bash' ? { result: 'ok' } : { result: { filePath: '/r/src/c.ts' } }))
    on('classic.Stop', () => ({}))
    await $.tool.call({ tool: 'Bash', command: 'npm test' })
    await clock.advance(5000)
    await $.tool.call({ tool: 'Edit', file_path: '/r/src/c.ts', old_string: 'a', new_string: 'b' })
    await clock.advance(5000)
    await $.tool.call({ tool: 'Bash', command: 'npm test', run_in_background: true })
    const r = await $.classic.Stop({ stop_hook_active: false })
    expect(r.block).toContain('npm test')
  })
  test('never blocks a continuation that a stop hook already caused', async ($, on) => {
    const clock = engine(on, e => (e.tool === 'Bash' ? { result: 'ok' } : { result: { filePath: '/r/src/b.ts' } }))
    on('classic.Stop', () => ({}))
    await $.tool.call({ tool: 'Bash', command: 'go test ./...' })
    await clock.advance(5000)
    await $.tool.call({ tool: 'Edit', file_path: '/r/src/b.ts', old_string: 'a', new_string: 'b' })
    const r = await $.classic.Stop({ stop_hook_active: true })
    expect(r.block).toBeUndefined()
  })
})

describe('router governor', () => {
  const router = '<!-- prompt-router v3 -->\n[Skills for this task]\n- **debug-investigation** (SHOULD-READ) — Evidence-first debugging: reproduce, classify the failing surface, form hypotheses before any fix.\n  ACTION: Skill("debug-investigation") before the related work.'
  test('a repeat inside the window is removed', async ($, on) => {
    engine(on)
    on('classic.UserPromptSubmit', () => ({ additionalContext: [router] }))
    const first = await $.classic.UserPromptSubmit({ prompt: 'fix the bug' })
    expect((first.additionalContext ?? []).join('')).toContain('debug-investigation')
    const second = await $.classic.UserPromptSubmit({ prompt: 'still broken' })
    expect((second.additionalContext ?? []).join('')).not.toContain('debug-investigation')
  })
})

describe('model tools', () => {
  test('session_state answers with the live ledger', async ($, on) => {
    engine(on)
    await $.tool.call({ tool: 'Bash', command: 'npm run build' })
    const r = await $.tool.call({ tool: 'mcp__mercy__session_state' })
    const state = JSON.parse(String(r.result)) as { recentCommands: Array<{ command: string; kinds: string[] }> }
    expect(state.recentCommands.at(-1)?.command).toBe('npm run build')
    expect(state.recentCommands.at(-1)?.kinds).toEqual(['build'])
  })
})
