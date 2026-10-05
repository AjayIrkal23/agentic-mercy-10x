import type { On } from 'claude-code'
import { describe, expect, mock, test } from 'claude-code/testing'

// Engine-level bridge tests (audit H-04): a session starts in a repo without a root
// CLAUDE.md, so the mod owns the dox gate, tdd-guard, graphify and a post-write link.

const CONFIG = JSON.stringify({
  chains: {
    'pre-tool-use': [
      { id: 'tdd-guard-launcher-pre', type: 'advisory', tools: 'Write|Edit' },
      { id: 'graphify-enforce', type: 'advisory', tools: 'Task|Agent|Bash' },
      { id: 'dox-write-gate-write', type: 'gate', tools: 'Write|Edit' },
    ],
    'post-tool-use': [{ id: 'post-write-aggregator', type: 'advisory', tools: 'Write|Edit' }],
  },
})

type Answer = { exitCode?: number; out?: Record<string, unknown>; delayMs?: number }
type Py = { pre: () => Record<string, unknown>; stop: () => Record<string, unknown>; dispatch: (ids: string) => Answer }

function world(on: On, py: Partial<Py> = {}) {
  const clock = mock.clock(on, { now: 1_000_000 })
  mock.store(on)
  const env = new Map<string, string>()
  const log: string[] = []
  const toasts: string[] = []
  const ran: string[] = []
  const answer: Py = { pre: () => ({}), stop: () => ({}), dispatch: () => ({}), ...py }
  on('env.get', (_$, e) => ({ value: env.get(e.name) }))
  on('env.set', (_$, e) => {
    if (e.value === undefined) env.delete(e.name)
    else env.set(e.name, e.value)
    return { value: undefined }
  })
  on('ui.toast', (_$, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  on('session.repo', () => ({ value: { root: '/r', remote: null } as never }))
  on('session.cwd', () => ({ value: '/r' }))
  on('session.root', () => ({ value: '/r' }))
  on('session.model', () => ({ value: 'claude-sonnet-5-5' }))
  on('settings.read', () => ({ value: {} }))
  on('session.start', (_$, e) => ({ cwd: e.cwd }))
  on('session.id', () => ({ value: 's1' }))
  on('ui.status', () => ({ value: undefined }))
  on('classic.SessionStart', () => ({}))
  on('session.end', (_$, e) => {
    log.push('session end')
    return { sessionId: e.sessionId }
  })
  on('tool.register', () => ({ value: undefined }) as never)
  on('command.register', () => ({ value: undefined }) as never)
  on('fs.read', (_$, e) => ({ value: e.path.endsWith('dispatch.config.json') ? CONFIG : '{"skills":{}}' }))
  on('fs.exists', (_$, e) => ({ value: e.path === '/r/.git' }))
  on('process.run', async (_$, e) => {
    const at = e.argv.indexOf('--only')
    if (at < 0) return { value: { exitCode: 0, stdout: 'main\n', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
    const ids = e.argv[at + 1] ?? ''
    const a = answer.dispatch(ids)
    if (a.delayMs) await clock.sleep(a.delayMs)
    log.push(`dispatch ${ids}`)
    return { value: { exitCode: a.exitCode ?? 0, stdout: JSON.stringify(a.out ?? {}), stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  const failedSeen: string[] = []
  on('classic.PreToolUse', (_$, e) => {
    log.push(`python pre owned=${env.get('MERCY_MOD_OWNED') ?? ''}`)
    failedSeen.push(`${e.tool_use_id} sees ${env.get('MERCY_MOD_FAILED') ?? '-'}`)
    return answer.pre() as never
  })
  on('classic.PostToolUse', () => ({}))
  on('classic.Stop', () => {
    log.push('python stop')
    return answer.stop() as never
  })
  on('classic.PreCompact', () => {
    log.push('python precompact')
    return {} as never
  })
  on('tool.call', (_$, e) => {
    ran.push(e.tool)
    return { result: { filePath: '/r/src/a.ts' } } as never
  })
  return { clock, env, log, toasts, ran, failedSeen }
}

const start = { cwd: '/r', surface: 'terminal' as const, isInteractive: false }
const write = { tool: 'Write', file_path: '/r/src/a.ts', content: 'x' } as const
const post = { tool_name: 'Write', tool_input: { file_path: '/r/src/a.ts', content: 'x' }, tool_response: {}, tool_use_id: 't1' }
const deny = (reason: string) => ({ hookSpecificOutput: { permissionDecision: 'deny', permissionDecisionReason: reason } })

describe('bridge: owned links through dispatch.py --only', () => {
  test('session start claims the links in the env dispatch.py reads', async ($, on) => {
    const w = world(on)
    await $.session.start(start)
    expect((w.env.get('MERCY_MOD_OWNED') ?? '').split(',').sort()).toEqual(
      ['dox-write-gate-write', 'graphify-enforce', 'post-write-aggregator', 'tdd-guard-launcher-pre'])
    expect(w.env.get('MERCY_MOD_BEAT')).toBe('1000000')
  })
  test("an owned gate's deny is the call's deny; the tool never runs", async ($, on) => {
    const w = world(on, { dispatch: ids => (ids === 'dox-write-gate-write' ? { out: deny('dox: add a root CLAUDE.md') } : {}) })
    await $.session.start(start)
    const r = await $.tool.call(write)
    expect(r.isError).toBe(true)
    expect(r.text).toContain('dox: add a root CLAUDE.md')
    expect(w.ran).toEqual([])
  })
  test('a call the Python chain denies queues no background validation (H-07)', async ($, on) => {
    const w = world(on, { pre: () => ({ deny: 'first-write-skill-gate: read a skill first' }) })
    await $.session.start(start)
    const r = await $.tool.call(write)
    await w.clock.settle()
    expect(r.isError).toBe(true)
    expect(w.log.filter(l => l === 'dispatch tdd-guard-launcher-pre')).toEqual([])
  })
  test('a sync gate that fails to run is named in MERCY_MOD_FAILED for this very call; ownership stays (B1-06)', async ($, on) => {
    let fail = true
    const w = world(on, { dispatch: ids => (ids === 'dox-write-gate-write' && fail ? { exitCode: 1 } : {}) })
    await $.session.start(start)
    await $.tool.call(write)
    fail = false
    await $.tool.call(write)
    const [first, second] = w.failedSeen
    const tu = (first ?? '').split(' ')[0]
    expect(first).toBe(`${tu} sees ${tu}:dox-write-gate-write`)
    // the next call has its own tool_use_id: the old value is stale there, so dispatch.py skips the gate again
    expect(second?.startsWith(`${tu} `)).toBe(false)
    expect(w.env.get('MERCY_MOD_OWNED')).toContain('dox-write-gate-write')
  })
  // the test engine answers an ask with an approval, so the asked call runs
  test("an owned gate's ask lets the Python chain run; a Python deny there wins", async ($, on) => {
    let pyDeny = false
    const ask = { hookSpecificOutput: { permissionDecision: 'ask', permissionDecisionReason: 'dox: confirm' } }
    const w = world(on, { dispatch: ids => (ids === 'dox-write-gate-write' ? { out: ask } : {}), pre: () => (pyDeny ? { deny: 'py says no' } : {}) })
    await $.session.start(start)
    const asked = await $.tool.call(write)
    expect(asked.isError).toBeUndefined()
    expect(w.ran).toEqual(['Write'])
    expect(w.log).toContain(`python pre owned=${w.env.get('MERCY_MOD_OWNED')}`)
    pyDeny = true
    const denied = await $.tool.call(write)
    expect(denied.isError).toBe(true)
    expect(denied.text).toContain('py says no')
  })
  test('graphify runs before the Python chain for an Agent call (B1-22)', async ($, on) => {
    const w = world(on)
    await $.session.start(start)
    await $.tool.call({ tool: 'Agent', prompt: 'explore', description: 'x', subagent_type: 'Explore' })
    expect(w.log.slice(0, 2)).toEqual(['dispatch graphify-enforce', `python pre owned=${w.env.get('MERCY_MOD_OWNED')}`])
  })
})

describe('bridge: lanes are drained before readers', () => {
  test('Stop, PreCompact and session.end wait for queued post-write runs (H-11)', async ($, on) => {
    const w = world(on, { dispatch: ids => (ids === 'post-write-aggregator' ? { delayMs: 1000 } : {}) })
    await $.session.start(start)
    for (const run of [() => $.classic.Stop({ stop_hook_active: false }), () => $.classic.PreCompact({ trigger: 'auto', custom_instructions: null } as never),
      () => $.session.end({ reason: 'other', sessionId: 's', resume: { id: 's' } } as never)]) {
      w.log.length = 0
      await $.classic.PostToolUse(post as never)
      const p = run()
      await w.clock.advance(1000)
      await p
      expect(w.log[0]).toBe('dispatch post-write-aggregator')
    }
  })
  test('a write waits (bounded) for a running tdd-guard check and carries its advisory (B1-22)', async ($, on) => {
    const advice = { hookSpecificOutput: { additionalContext: 'tdd-guard: add a failing test for a.ts first' } }
    const w = world(on, { dispatch: ids => (ids === 'tdd-guard-launcher-pre' ? { delayMs: 1500, out: advice } : {}) })
    await $.session.start(start)
    await $.tool.call(write)
    const p = $.tool.call({ ...write, file_path: '/r/src/b.ts' })
    await w.clock.advance(1500)
    const r = await p
    expect((r.context ?? []).join('\n')).toContain('add a failing test')
  })
  test('release keeps queued runs: they still run for the calls Python skipped (H-11)', async ($, on) => {
    // a 5 s graphify run outlasts the 4 s drain, so the post-write run queues behind it
    const w = world(on, { dispatch: ids => (ids === 'graphify-enforce' ? { delayMs: 5000 } : {}) })
    await $.session.start(start)
    await $.tool.call({ tool: 'Bash', command: 'ls' })
    const queued = $.classic.PostToolUse(post as never)
    await w.clock.advance(4000)
    await queued
    const released = $.command.run({ command: 'mercy', args: 'release', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 120 } })
    await w.clock.advance(2000)
    expect((await released).text).toContain('Released')
    expect(w.log).toContain('dispatch post-write-aggregator')
  })
  test("a subagent's background advisory never reaches the main loop; the main loop's own does (NEW-08)", async ($, on) => {
    const advice = { hookSpecificOutput: { additionalContext: 'docs touched: read update-docs' } }
    const w = world(on, { dispatch: ids => (ids === 'post-write-aggregator' ? { out: advice } : {}) })
    await $.session.start(start)
    await $.classic.PostToolUse({ ...post, agent_id: 'sub1' } as never)
    await w.clock.settle()
    const fromSub = await $.tool.call({ tool: 'Read', file_path: '/r/README.md' })
    expect((fromSub.context ?? []).join('\n')).not.toContain('read update-docs')
    await $.classic.PostToolUse(post as never)
    await w.clock.settle()
    const fromMain = await $.tool.call({ tool: 'Read', file_path: '/r/README.md' })
    expect((fromMain.context ?? []).join('\n')).toContain('read update-docs')
  })
  test("a subagent's write: its tdd-guard advisory never rides the main loop's next write (NEW-09)", async ($, on) => {
    const advice = { hookSpecificOutput: { additionalContext: 'tdd-guard: add a failing test for a.ts first' } }
    const w = world(on, { dispatch: ids => (ids === 'tdd-guard-launcher-pre' ? { delayMs: 1500, out: advice } : {}) })
    await $.session.start(start)
    await $.tool.call({ ...write, agentId: 'sub1' } as never)
    const p = $.tool.call({ ...write, file_path: '/r/src/b.ts' })
    await w.clock.advance(1500)
    expect(((await p).context ?? []).join('\n')).not.toContain('add a failing test')
  })
  test("a subagent's tool result does not take the main loop's queued advisory (NEW-09)", async ($, on) => {
    const advice = { hookSpecificOutput: { additionalContext: 'docs touched: read update-docs' } }
    const w = world(on, { dispatch: ids => (ids === 'post-write-aggregator' ? { out: advice } : {}) })
    await $.session.start(start)
    await $.classic.PostToolUse(post as never)
    await w.clock.settle()
    const sub = await $.tool.call({ tool: 'Read', file_path: '/r/README.md', agentId: 'sub1' } as never)
    expect((sub.context ?? []).join('\n')).not.toContain('read update-docs')
    const main = await $.tool.call({ tool: 'Read', file_path: '/r/README.md' })
    expect((main.context ?? []).join('\n')).toContain('read update-docs')
  })
  test('the next tool call waits for the fast lane before its Python chain', async ($, on) => {
    const w = world(on, { dispatch: ids => (ids === 'post-write-aggregator' ? { delayMs: 1000 } : {}) })
    await $.session.start(start)
    await $.classic.PostToolUse(post as never)
    const p = $.tool.call({ tool: 'Read', file_path: '/r/README.md' })
    await w.clock.advance(1000)
    await p
    expect(w.log[0]).toBe('dispatch post-write-aggregator')
  })
})

describe('bridge: release and re-claim', () => {
  test('three failed background runs hand every link back, with a toast', async ($, on) => {
    const w = world(on, { dispatch: ids => (ids === 'post-write-aggregator' ? { exitCode: 1 } : {}) })
    await $.session.start(start)
    for (let i = 0; i < 3; i++) await $.classic.PostToolUse({ ...post, tool_use_id: `t${i}` } as never)
    await w.clock.settle()
    expect(w.env.get('MERCY_MOD_OWNED')).toBeUndefined()
    expect(w.toasts.join('\n')).toContain('back on the Python chain')
  })
  test('/mercy release uses the same release: env cleared, status shows nothing owned (H-12)', async ($, on) => {
    const w = world(on)
    await $.session.start(start)
    const presentation = { isFullscreen: false, columns: 120 }
    const r = await $.command.run({ command: 'mercy', args: 'release', origin: { kind: 'composer' }, presentation })
    expect(r.text).toContain('Released 4 hook links')
    expect(w.env.get('MERCY_MOD_OWNED')).toBeUndefined()
    const s = await $.command.run({ command: 'mercy', args: 'status', origin: { kind: 'composer' }, presentation })
    expect(s.text).toContain('bridge: 0 links owned')
  })
  test('/clear re-claims the links under the new session id', async ($, on) => {
    const w = world(on)
    await $.session.start(start)
    await $.classic.SessionStart({ source: 'clear', session_id: 's2', transcript_path: '' } as never)
    expect(w.env.get('MERCY_MOD_SESSION')).toBe('s2')
    expect(w.env.get('MERCY_MOD_OWNED')).toContain('dox-write-gate-write')
  })
})
